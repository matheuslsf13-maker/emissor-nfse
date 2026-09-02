# -*- coding: utf-8 -*-
"""Orquestra a geracao dos XMLs a partir de uma conciliacao ja conferida.

Dois modos:

* **teste** (`simular=True`) -- gera e assina os XMLs sem consumir numeracao
  e sem registrar antiduplicidade. Pode rodar quantas vezes quiser.
* **valendo** -- consome a numeracao de forma permanente e registra cada
  nota no controle. Nao ha desfazer.

Automacao amplifica erro de configuracao: na emissao manual um erro afeta
uma nota; automatizado, afeta todas. Por isso o modo teste e o padrao em
toda a interface.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from . import config as cfgmod
from .assinatura import ErroCertificado, assinar, carregar_pfx, conferir
from .controle import Controle
from .gerador_dps import ID_INFNFSE, gerar_nfse
from .util import brl


@dataclass
class NotaGerada:
    id: str
    numero: int
    arquivo: str
    tomador: str
    documento: str
    valor: str
    data: str
    secao: str
    assinada: bool = False
    detalhe_assinatura: dict = field(default_factory=dict)


@dataclass
class ResultadoEmissao:
    unidade: str
    competencia: str
    simulacao: bool
    pasta: str = ""
    geradas: list = field(default_factory=list)
    puladas: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    assinatura_ativa: bool = False
    aviso_certificado: str = ""

    @property
    def valor_total(self):
        from decimal import Decimal

        return sum((Decimal(n.valor) for n in self.geradas), Decimal("0"))


def _nome_arquivo(nota, numero: int) -> str:
    documento = nota.tomador.get("documento", "sem-documento")
    base = "%05d-%s-%s" % (numero, nota.data or "sem-data", documento)
    return re.sub(r"[^A-Za-z0-9\-_.]", "_", base) + ".xml"


def emitir(resultado_conciliacao, config, simular: bool = True,
           pasta_saida: str = None, apenas: set = None) -> ResultadoEmissao:
    """Gera (e assina, se houver certificado) os XMLs das notas conferidas."""
    unidade_chave = resultado_conciliacao.unidade
    unidade = config.unidade(unidade_chave)
    competencia = resultado_conciliacao.competencia

    saida = ResultadoEmissao(
        unidade=unidade_chave, competencia=competencia, simulacao=simular
    )

    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    pasta = pasta_saida or os.path.join(
        cfgmod.PASTA_SAIDA,
        "%s-%s-%s%s" % (unidade_chave, competencia, carimbo,
                        "-teste" if simular else ""),
    )
    os.makedirs(pasta, exist_ok=True)
    saida.pasta = pasta

    # --- certificado -------------------------------------------------------
    certificado = None
    try:
        certificado = carregar_pfx(
            config.caminho_certificado(unidade_chave),
            config.senha_certificado(unidade_chave),
        )
        if certificado.vencido:
            saida.aviso_certificado = (
                "O certificado desta unidade venceu em %s. Os XMLs foram gerados, "
                "mas não servem para transmitir."
                % certificado.validade.strftime("%d/%m/%Y")
            )
        saida.assinatura_ativa = True
    except ErroCertificado as erro:
        saida.aviso_certificado = (
            "%s Os XMLs foram gerados sem assinatura — servem para conferência, "
            "não para transmitir." % erro
        )

    controle = Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db"))
    # Em modo teste a numeracao nao e gravada, mas ainda precisa avancar: cada
    # nota tem que sair com o numero que teria de verdade, ou o Id do DPS
    # repetiria e a conferencia nao serviria para nada.
    proximo_simulado = controle.ultimo_numero(unidade_chave)

    for nota in resultado_conciliacao.notas:
        if apenas is not None and nota.id not in apenas:
            continue

        chave = Controle.chave(unidade_chave, nota.id)
        # A checagem vale tambem no modo teste: o teste tem que mostrar
        # exatamente o que sairia valendo, sem surpresa depois.
        anterior = controle.ja_emitida(chave)
        if anterior:
            saida.puladas.append({
                "id": nota.id,
                "tomador": nota.tomador.get("nome", ""),
                "valor": nota.valor,
                "motivo": "Já emitida em %s com o número %s."
                          % (anterior["em"][:10], anterior["numero"]),
            })
            continue

        if simular:
            proximo_simulado += 1
            numero = proximo_simulado
        else:
            numero = controle.proximo_numero(unidade_chave)
        try:
            xml = gerar_nfse(nota, unidade, config, numero)
            assinada = False
            detalhe = {}
            if certificado is not None:
                xml = assinar(xml, ID_INFNFSE, certificado, algoritmo="sha256")
                detalhe = conferir(xml)
                assinada = bool(detalhe.get("valida"))
            caminho = os.path.join(pasta, _nome_arquivo(nota, numero))
            with open(caminho, "wb") as fh:
                fh.write(xml)
        except Exception as erro:  # noqa: BLE001 - erro vira relatorio, nao stacktrace
            saida.erros.append({
                "id": nota.id,
                "tomador": nota.tomador.get("nome", ""),
                "erro": "%s: %s" % (type(erro).__name__, erro),
            })
            continue

        if not simular:
            controle.registrar(
                chave, numero, os.path.basename(caminho),
                "%s - R$ %s" % (nota.tomador.get("nome", ""), brl(nota.valor)),
                documento=nota.tomador.get("documento", ""),
                competencia=competencia,
                valor=nota.valor,
                secao=nota.secao,
            )

        saida.geradas.append(NotaGerada(
            id=nota.id,
            numero=numero,
            arquivo=os.path.basename(caminho),
            tomador=nota.tomador.get("nome", ""),
            documento=nota.tomador.get("documento", ""),
            valor=nota.valor,
            data=nota.data,
            secao=nota.secao,
            assinada=assinada,
            detalhe_assinatura=detalhe,
        ))

    controle.fechar()
    _gravar_relatorio(saida, resultado_conciliacao, pasta)
    return saida


def _gravar_relatorio(saida, conciliacao, pasta: str) -> None:
    """Deixa ao lado dos XMLs um resumo legivel do que foi gerado."""
    linhas = [
        "EMISSAO DE NFS-e - %s - competencia %s" % (saida.unidade, saida.competencia),
        "Modo: %s" % ("TESTE (nao consumiu numeracao)" if saida.simulacao
                      else "VALENDO (numeracao consumida)"),
        "Gerado em: %s" % datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "Arquivos de origem: %s" % ", ".join(conciliacao.arquivos),
        "",
        "Notas geradas: %d   Total: R$ %s" % (len(saida.geradas),
                                              brl(saida.valor_total)),
        "Assinatura digital: %s" % ("ativa" if saida.assinatura_ativa
                                    else "NAO aplicada"),
    ]
    if saida.aviso_certificado:
        linhas.append("Aviso: %s" % saida.aviso_certificado)
    if saida.puladas:
        linhas += ["", "Puladas por ja terem sido emitidas: %d" % len(saida.puladas)]
        linhas += ["  %s - %s" % (p["tomador"], p["motivo"]) for p in saida.puladas]
    if saida.erros:
        linhas += ["", "Erros: %d" % len(saida.erros)]
        linhas += ["  %s - %s" % (e["tomador"], e["erro"]) for e in saida.erros]
    if conciliacao.pendencias:
        linhas += ["", "Pendencias NAO emitidas: %d" % len(conciliacao.pendencias)]
        linhas += ["  %s - %s (R$ %s)" % (p.nome, p.titulo, brl(p.valor))
                   for p in conciliacao.pendencias]
    linhas += ["", "Detalhe das notas:"]
    linhas += [
        "  %5d  %s  %-42s %-18s R$ %10s  %s"
        % (n.numero, n.data, n.tomador[:42], n.documento, brl(n.valor), n.secao)
        for n in saida.geradas
    ]
    with open(os.path.join(pasta, "RELATORIO.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
