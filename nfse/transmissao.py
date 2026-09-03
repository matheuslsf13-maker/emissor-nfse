# -*- coding: utf-8 -*-
"""Transmissao dos XMLs ja gerados para o WebService da prefeitura.

Separado de `emissao.py` de proposito: gerar e transmitir sao dois passos
distintos, e transmitir e o unico que sai da maquina. Isso permite gerar
tudo, conferir, e so entao mandar -- e mandar de novo o que falhou, sem
regerar nada.

Os XMLs sao lidos do disco como estao. Nada e reserializado: um byte a mais
invalida a assinatura.

Regras de seguranca embutidas:

* nada e transmitido sem `permitir_envio` ligado na configuracao;
* a primeira transmissao deve ser de UMA nota (`limite=1`), para conferir o
  retorno antes de mandar o lote inteiro;
* o que ja foi aceito nao e reenviado -- a prefeitura recusaria por
  duplicidade e, em Vila Velha, cancelar exige processo administrativo.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import config as cfgmod
from .controle import Controle
from .envio import EnvioIndisponivel, enviar, interpretar_retorno, situacao


@dataclass
class ResultadoEnvio:
    arquivo: str
    numero_dps: str = ""
    aceita: bool = False
    numero_nota: str = ""
    codigo_verificacao: str = ""
    chave_acesso: str = ""
    mensagem: str = ""
    bruto: str = ""
    http: int = 0
    erro: str = ""
    tentativas: int = 0
    na_fila: bool = False


@dataclass
class ResultadoTransmissao:
    pasta: str
    ambiente: str
    url: str = ""
    enviadas: list = field(default_factory=list)
    puladas: list = field(default_factory=list)
    nao_enviadas: int = 0
    # Ligada quando o operador pediu para parar. O que ja saiu continua
    # valendo -- a diferenca esta em como a tela conta a historia.
    interrompida: bool = False

    @property
    def aceitas(self):
        return [e for e in self.enviadas if e.aceita]

    @property
    def recusadas(self):
        return [e for e in self.enviadas if not e.aceita]


# A prefeitura aceita UM envio por vez por CNPJ. Mandando em sequencia, a
# partir da segunda nota ela responde com esta mensagem -- e a nota, que esta
# perfeita, e recusada so por ritmo. Numa transmissao real de 276 notas isso
# derrubou 207 delas.
MARCAS_FILA = (
    "ja consta uma requisicao em andamento",
    "já consta uma requisição em andamento",
    "aguarde o processo anterior",
)


def erro_de_fila(mensagem: str) -> bool:
    """A recusa foi por ritmo, e nao por defeito da nota?

    Vale distinguir: erro de fila some sozinho ao tentar de novo, enquanto
    erro de conteudo volta igual para sempre. Tratar os dois do mesmo jeito
    faria o operador reenviar centenas de notas na mao, sem saber quais
    valiam a pena.
    """
    texto = (mensagem or "").lower()
    return any(marca in texto for marca in MARCAS_FILA)


# A prefeitura escreve a duplicidade de mais de um jeito, e o codigo E0014
# nem sempre vem junto. Sao marcas de "este numero ja foi usado" -- o unico
# erro que se resolve mexendo na numeracao, e nao no conteudo da nota.
MARCAS_DUPLICIDADE = (
    "e0014",
    "ja existe",
    "já existe",
    "duplicidade",
    "ja foi utilizado",
    "já foi utilizado",
)


def erro_de_duplicidade(mensagem: str) -> bool:
    """A recusa foi porque o numero ja existe do lado da prefeitura?

    Distinguir importa porque a saida e outra: nota recusada por conteudo se
    corrige no cadastro e se reenvia; numero repetido nao tem conserto no
    XML -- e preciso avancar a numeracao e gerar de novo. Sem separar os
    dois, o operador tenta reenviar para sempre.
    """
    texto = (mensagem or "").lower()
    return any(marca in texto for marca in MARCAS_DUPLICIDADE)


def _numero_do_arquivo(nome: str) -> str:
    """00042-2026-08-14-123... -> 42"""
    parte = nome.split("-", 1)[0]
    return str(int(parte)) if parte.isdigit() else ""


def ambiente_do_xml(xml: bytes) -> str:
    """Le o <tpAmb> gravado dentro do XML: 1 = producao, 2 = homologacao.

    O ambiente e escolhido na GERACAO, nao na transmissao, e fica coberto pela
    assinatura -- trocar depois e impossivel sem regerar a nota. Como a tela de
    transmissao deixa escolher o destino na hora do envio, os dois podem
    divergir: notas geradas em homologacao indo para a URL de producao. Um XML
    de teste mandado para valendo e rejeitado no melhor caso; conferir aqui e
    mais barato do que descobrir la.
    """
    achado = re.search(rb"<tpAmb>\s*(\d)\s*</tpAmb>", xml)
    if not achado:
        return ""
    return "producao" if achado.group(1) == b"1" else "homologacao"


def listar_xmls(pasta: str) -> list:
    return sorted(n for n in os.listdir(pasta) if n.lower().endswith(".xml"))


def transmitir(pasta: str, config, limite: int = None, apenas: set = None,
               progresso=None, tentativas: int = 4, espera: float = 1.5,
               pausa: float = 0.4, parar=None) -> ResultadoTransmissao:
    """Envia os XMLs da pasta. `limite=1` manda so o primeiro (recomendado).

    `progresso(feitos, total, ultimo)` e chamado a cada nota, para a tela
    poder mostrar andamento: um lote de 276 leva minutos, e sem retorno
    visual parece travado.

    `tentativas`/`espera` cuidam da trava de envio simultaneo da prefeitura;
    `pausa` e o respiro entre notas diferentes, que evita bater nela.

    `parar()` e consultado ANTES de cada nota. Devolvendo verdadeiro, o
    envio para ali -- nunca no meio de uma nota. Isso importa: interromper
    entre o envio e a gravacao do retorno deixaria uma nota emitida na
    prefeitura e desconhecida aqui, que e o pior estado possivel. O que ja
    saiu continua valendo; o que falta fica para um proximo envio.
    """
    estado = situacao(config)
    resultado = ResultadoTransmissao(
        pasta=pasta, ambiente=estado["ambiente"], url=estado["url"]
    )
    if not estado["pronto"]:
        raise EnvioIndisponivel(
            "O envio ainda não está liberado. Falta: %s."
            % "; ".join(estado["faltando"])
        )

    controle = Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db"))
    por_arquivo = controle.por_arquivo()

    arquivos = listar_xmls(pasta)
    if apenas is not None:
        arquivos = [a for a in arquivos if a in apenas]

    # Quantas serao de fato enviadas: as ja aceitas sao puladas, e `limite`
    # corta o resto. Sem isso a barra mostraria 5% quando ja acabou.
    ja_aceitas = sum(
        1 for a in arquivos
        if por_arquivo.get(a, (None, {}))[1].get("transmitida"))
    total_previsto = len(arquivos) - ja_aceitas
    if limite is not None:
        total_previsto = min(total_previsto, limite)

    for nome in arquivos:
        # Antes de comecar a nota, nunca no meio dela.
        if parar is not None and parar():
            resultado.interrompida = True
            resultado.nao_enviadas += 1
            continue
        if limite is not None and len(resultado.enviadas) >= limite:
            resultado.nao_enviadas += 1
            continue

        chave, registro = por_arquivo.get(nome, (None, {}))
        if registro.get("transmitida"):
            resultado.puladas.append({
                "arquivo": nome,
                "motivo": "Já transmitida em %s, nota %s."
                          % (registro.get("transmitida_em", "")[:10],
                             registro.get("numero_nota") or "sem número"),
            })
            continue

        with open(os.path.join(pasta, nome), "rb") as fh:
            xml = fh.read()

        item = ResultadoEnvio(arquivo=nome, numero_dps=_numero_do_arquivo(nome))
        if b"Signature" not in xml:
            # XML sem assinatura seria recusado de qualquer jeito. Barrar aqui
            # evita queimar numeracao e sujar o log da prefeitura.
            item.erro = (
                "XML sem assinatura digital — não transmitido. Coloque o "
                "certificado A1 da unidade e gere de novo."
            )
            resultado.enviadas.append(item)
            continue

        gerado_para = ambiente_do_xml(xml)
        if gerado_para and gerado_para != estado["ambiente"]:
            item.erro = (
                "Esta nota foi GERADA para %s e o envio seria para %s. O "
                "ambiente fica gravado dentro do XML e assinado — não dá para "
                "trocar na hora de transmitir. Mude o ambiente na Configuração "
                "e gere as notas de novo." % (gerado_para, estado["ambiente"])
            )
            resultado.enviadas.append(item)
            continue

        # A prefeitura processa um envio por vez por CNPJ. Insistir com
        # espera crescente e o que transforma "recusada" em "aceita" -- sem
        # isso, mandar um lote inteiro derruba a maior parte dele por ritmo.
        for tentativa in range(1, tentativas + 1):
            try:
                resposta = enviar(xml, config, acao="gerar")
                item.http = resposta["status"]
                lido = interpretar_retorno(resposta["retorno"] or resposta["corpo"])
                item.aceita = lido["aceita"]
                item.numero_nota = lido["numero"]
                item.codigo_verificacao = lido["codigo_verificacao"]
                item.chave_acesso = lido["chave"]
                item.mensagem = lido["mensagem"]
                item.bruto = lido["bruto"][:4000]
                item.erro = ""
            except Exception as erro:  # noqa: BLE001 - erro vira relatorio
                item.erro = "%s: %s" % (type(erro).__name__, erro)
                item.aceita = False

            if item.aceita or not erro_de_fila(item.mensagem or item.erro):
                break
            item.tentativas = tentativa
            if tentativa < tentativas:
                # Espera crescente: 1s, 2s, 3s... Fixa e curta demais bate na
                # mesma trava; longa demais faz um lote grande levar horas.
                time.sleep(espera * tentativa)

        if not item.aceita and erro_de_fila(item.mensagem or item.erro):
            item.na_fila = True

        if item.aceita and chave:
            controle.registrar_transmissao(
                chave,
                numero_nota=item.numero_nota,
                codigo_verificacao=item.codigo_verificacao,
                chave_acesso=item.chave_acesso,
                ambiente=estado["ambiente"],
            )
        resultado.enviadas.append(item)
        if progresso:
            progresso(len(resultado.enviadas), total_previsto, item)
        if pausa:
            time.sleep(pausa)

    controle.fechar()
    _gravar_log(resultado, pasta)
    return resultado


def _gravar_log(resultado, pasta: str) -> None:
    linhas = [
        "TRANSMISSAO - %s" % datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Ambiente: %s" % resultado.ambiente,
        "Destino : %s" % resultado.url,
        "",
        "Aceitas : %d" % len(resultado.aceitas),
        "Recusadas: %d" % len(resultado.recusadas),
        "Puladas : %d" % len(resultado.puladas),
        "",
    ]
    for e in resultado.enviadas:
        linhas.append(
            "%-44s HTTP %s  %s  nota %s  %s"
            % (e.arquivo, e.http or "-", "ACEITA" if e.aceita else "RECUSADA",
               e.numero_nota or "-",
               ("chave %s " % e.chave_acesso if e.chave_acesso else "")
               + (e.erro or e.mensagem or ""))
        )
        if e.bruto:
            linhas.append("    retorno: %s" % e.bruto[:800].replace("\n", " "))
    with open(os.path.join(pasta, "TRANSMISSAO.txt"), "a", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n\n")
