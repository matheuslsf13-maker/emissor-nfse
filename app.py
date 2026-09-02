# -*- coding: utf-8 -*-
"""Servidor local do Emissor de NFS-e.

Roda so na maquina da clinica (127.0.0.1). Nao expoe nada para a rede: os
relatorios trazem CPF e endereco de milhares de pacientes.

Fluxo da tela:
    1. arrastar os relatorios do TechCare
    2. conferir o que vai virar nota (e o que nao vai, com o motivo)
    3. gerar os XMLs -- em teste quantas vezes quiser, valendo so uma vez
"""

from __future__ import annotations

import io
import json
import os
import sys
import shutil
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from nfse import base_clientes
from nfse import planilha
from nfse import config as cfgmod
from nfse.conciliacao import conciliar
from nfse.controle import Controle, ControleIlegivel
from nfse.documentos import formatar_documento, so_digitos
from nfse.emissao import emitir
from nfse.envio import EnvioIndisponivel
from nfse.envio import situacao as situacao_envio
from nfse.leitor_caixa import ler_caixa
from nfse.leitor_clientes import ler_clientes_cache
from nfse.pdf import ler_linhas
from nfse.transmissao import (ambiente_do_xml, listar_xmls,
                              transmitir)
from nfse import atualizacao as atualizacao_mod
from nfse.consulta import consultar
from nfse.util import brl, chave_nome

app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
app.config["MAX_CONTENT_LENGTH"] = 512 * 1024 * 1024   # o cadastro passa de 30 MB
# App local: recarregar o template a cada requisicao custa nada e evita ter
# que reiniciar o servidor depois de ajustar uma tela.
app.config["TEMPLATES_AUTO_RELOAD"] = True


def _segredo_da_sessao() -> bytes:
    """Chave dos cookies de sessao, gerada uma vez e guardada em dados/.

    Fixa no codigo seria a mesma em toda instalacao; sorteada a cada boot
    derrubaria a sessao a cada reinicio. Guardada, resolve os dois.
    """
    caminho = os.path.join(cfgmod.PASTA_DADOS, "sessao.chave")
    os.makedirs(cfgmod.PASTA_DADOS, exist_ok=True)
    if os.path.exists(caminho):
        with open(caminho, "rb") as fh:
            chave = fh.read().strip()
            if len(chave) >= 32:
                return chave
    chave = os.urandom(32).hex().encode()
    with open(caminho, "wb") as fh:
        fh.write(chave)
    return chave


app.secret_key = _segredo_da_sessao()

# Versao que este processo carregou. Se o arquivo VERSAO mudar depois disso,
# uma atualizacao foi instalada e o programa ainda esta rodando o codigo
# antigo -- os templates recarregam sozinhos, o Python nao. Esse meio-termo e
# pior do que a versao antiga inteira: tela nova com logica velha da erro
# estranho, dificil de diagnosticar a distancia.
VERSAO_EM_EXECUCAO = atualizacao_mod.versao_instalada()

# Andamento das transmissoes em segundo plano, por pasta. Fica em memoria de
# proposito: se o programa fechar no meio, o que importa (quais notas a
# prefeitura aceitou) ja esta gravado no controle, nao aqui.
TRANSMISSOES = {}
RESULTADOS_TRANSMISSAO = {}


@app.context_processor
def _versao_pendente():
    """Deixa o aviso de reinicio visivel em TODAS as telas.

    O aviso que aparecia so na tela de Configuracao sumia assim que a
    operadora navegava para outro lugar, e ela seguia usando o programa pela
    metade sem saber.
    """
    try:
        no_disco = atualizacao_mod.versao_instalada()
    except Exception:  # noqa: BLE001
        return {"reinicio_pendente": None}
    if no_disco != VERSAO_EM_EXECUCAO:
        return {"reinicio_pendente": {"rodando": VERSAO_EM_EXECUCAO,
                                      "instalada": no_disco}}
    return {"reinicio_pendente": None}

# Estado dos lotes em memoria. O app e local e de um usuario so; os arquivos
# ficam em disco, entao reiniciar o servidor nao perde o trabalho -- basta
# reabrir o lote, que e reconciliado na hora.
LOTES: dict = {}
_TRAVA = threading.Lock()

CACHE_CADASTRO: dict = {}


# ---------------------------------------------------------------------------
# apoio
# ---------------------------------------------------------------------------

def caminho_lote(lote_id: str) -> str:
    return os.path.join(cfgmod.PASTA_LOTES, lote_id)


def salvar_lote(lote: dict) -> None:
    pasta = caminho_lote(lote["id"])
    os.makedirs(pasta, exist_ok=True)
    gravavel = {k: v for k, v in lote.items() if k not in ("progresso",)}
    with open(os.path.join(pasta, "lote.json"), "w", encoding="utf-8") as fh:
        json.dump(gravavel, fh, ensure_ascii=False, indent=2)


def carregar_lote(lote_id: str):
    if lote_id in LOTES:
        return LOTES[lote_id]
    caminho = os.path.join(caminho_lote(lote_id), "lote.json")
    if not os.path.exists(caminho):
        return None
    with open(caminho, encoding="utf-8") as fh:
        lote = json.load(fh)
    lote.setdefault("progresso", {"etapa": "pronto", "percentual": 100})
    LOTES[lote_id] = lote
    return lote


def limpar_antigos(pasta: str, manter: int, sufixo: str = "") -> None:
    """Guarda so as N pastas mais recentes.

    Cada conferencia guarda uma copia dos PDFs para poder ser reaberta, e o
    cadastro de clientes passa de 30 MB. Sem isso, o disco da clinica enche
    sozinho depois de alguns meses.

    Com `sufixo`, so apaga o que termina com ele -- e assim que as saidas de
    teste sao limpas sem encostar nas notas emitidas valendo, que ficam
    guardadas para sempre.
    """
    if not os.path.isdir(pasta):
        return
    itens = [n for n in sorted(os.listdir(pasta), reverse=True)
             if not sufixo or n.endswith(sufixo)]
    for nome in itens[manter:]:
        alvo = os.path.join(pasta, nome)
        if os.path.isdir(alvo):
            shutil.rmtree(alvo, ignore_errors=True)
        LOTES.pop(nome, None)


def _primeiras_linhas(caminho: str, quantas: int):
    """As primeiras linhas do PDF, ja materializadas.

    Separado de `identificar_pdf` de proposito: assim o `try` cobre a leitura
    inteira do PDF -- inclusive o que o pdfminer levanta preguicosamente, no
    meio da iteracao, e que um `try` em volta do `for` deixaria escapar.
    """
    linhas = []
    for linha in ler_linhas(caminho):
        linhas.append(linha)
        if len(linhas) >= quantas:
            break
    return linhas


def _motivo_pdf_ilegivel(erro: Exception) -> str:
    texto = str(erro).lower()
    if "password" in texto or "senha" in texto or "encrypt" in texto:
        return ("o arquivo está protegido por senha — gere o relatório de novo "
                "no TechCare, sem proteção")
    if "root" in texto or "syntax" in texto or "startxref" in texto:
        return ("o arquivo não é um PDF válido ou veio incompleto — baixe de "
                "novo do TechCare")
    return "não consegui abrir o arquivo (%s)" % type(erro).__name__


def destino_unico(pasta: str, nome: str) -> str:
    """Caminho livre dentro da pasta, sem sobrescrever nada.

    Os dois relatorios de caixa costumam sair do TechCare com o mesmo nome
    (`caixa.pdf` de cada clinica). Salvando os dois no mesmo destino, o
    segundo apagava o primeiro e a lista ficava com o MESMO arquivo duas
    vezes -- todo lancamento contado em dobro, sem aviso nenhum. Erro caro:
    o total batia com nada e ninguem entendia por que.
    """
    base, extensao = os.path.splitext(nome)
    candidato = os.path.join(pasta, nome)
    contador = 2
    while os.path.exists(candidato):
        candidato = os.path.join(pasta, "%s (%d)%s" % (base, contador, extensao))
        contador += 1
    return candidato


def identificar_pdf(caminho: str) -> dict:
    """Descobre, lendo o cabecalho, que relatorio e este.

    Evita que a operadora tenha que acertar qual arquivo vai em qual campo:
    ela arrasta os tres e o sistema se vira.
    """
    empresa = ""
    tipo = "desconhecido"
    periodo = ""
    linhas = 0
    try:
        leitura = list(_primeiras_linhas(caminho, 40))
    except Exception as erro:  # noqa: BLE001
        # PDF corrompido, cortado no meio do download, protegido por senha ou
        # simplesmente um arquivo com extensao .pdf que nao e PDF. Nada disso
        # pode virar tela de erro: quem opera na clinica precisa ler o motivo.
        return {"tipo": "ilegivel", "empresa": "", "caixa": "", "periodo": "",
                "motivo": _motivo_pdf_ilegivel(erro)}
    for linha in leitura:
        texto = linha.texto
        linhas += 1
        alvo = chave_nome(texto)
        if "CLIENTES E FORNECEDORES" in alvo:
            tipo = "clientes"
        elif alvo.startswith("CAIXA") and tipo == "desconhecido":
            tipo = "caixa"
        if texto.upper().startswith("EMPRESA:") and not empresa:
            empresa = texto.split(":", 1)[1].strip()
        if texto.upper().startswith("PER") and ":" in texto and not periodo:
            import re
            datas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
            if len(datas) >= 2:
                periodo = "%s a %s" % (datas[0], datas[1])
        if linhas > 40:
            break
    caixa = ""
    if tipo == "caixa" and empresa:
        partes = [p.strip().upper() for p in empresa.split("-")]
        caixa = partes[-1] if len(partes) > 2 else ""
    return {"tipo": tipo, "empresa": empresa, "caixa": caixa, "periodo": periodo}


def obter_cadastro(caminho: str, progresso=None):
    chave = os.path.abspath(caminho)
    if chave in CACHE_CADASTRO:
        return CACHE_CADASTRO[chave]
    cadastro = ler_clientes_cache(caminho, cfgmod.PASTA_CACHE, progresso=progresso)
    CACHE_CADASTRO[chave] = cadastro
    return cadastro


def conciliar_lote(lote: dict):
    """Reconcilia o lote na hora.

    O cadastro vem da base salva em disco, nunca do PDF: o PDF só serve para
    alimentar a base. Assim a operadora pode mandar só os dois caixas.
    """
    cfg = cfgmod.carregar()
    caixas = [ler_caixa(c) for c in lote["arquivos"]["caixas"]]
    unidade = lote.get("unidade") or cfg.unidade_por_relatorio(caixas[0].empresa)
    if not unidade:
        raise ValueError(
            "Não reconheci a unidade no cabeçalho do relatório (%s). "
            "Confira empresa_no_relatorio em config/empresas.json." % caixas[0].empresa
        )

    base = base_clientes.abrir(cfgmod.PASTA_DADOS, unidade)
    if not base.existe:
        raise ValueError(
            "Ainda não há base de clientes para %s. Mande o relatório "
            "CLIENTES E FORNECEDORES junto uma primeira vez — depois disso "
            "ele fica salvo." % unidade
        )
    cadastro = base.como_cadastro()

    escolhas = {k: so_digitos(v) for k, v in lote.get("escolhas", {}).items() if v}
    resultado = conciliar(caixas, cadastro, cfg, unidade,
                          competencia=lote.get("competencia") or "",
                          escolhas=escolhas)
    return cfg, cadastro, resultado


def _resumir_importacao(resultado: dict) -> dict:
    """Guarda no lote só o que a tela mostra — a lista inteira pode ser enorme."""
    return {
        "em": resultado["em"],
        "origem": resultado["origem"],
        "lidos": resultado["lidos"],
        "novos": resultado["novos"],
        "atualizados": resultado["atualizados"],
        "iguais": resultado["iguais"],
        "total_depois": resultado["total_depois"],
        "amostra_novos": resultado["lista_novos"][:40],
        "amostra_atualizados": [
            a for a in resultado["lista_atualizados"] if a["documento_mudou"]
        ][:40],
    }


def processar_em_segundo_plano(lote_id: str) -> None:
    """Le os PDFs fora da requisicao, para a tela poder mostrar progresso."""
    lote = LOTES[lote_id]
    try:
        cfg = cfgmod.carregar()
        lote["progresso"] = {"etapa": "Lendo os relatórios de caixa",
                             "percentual": 5}
        caixas = [ler_caixa(c) for c in lote["arquivos"]["caixas"]]
        lote["unidade"] = lote.get("unidade") or cfg.unidade_por_relatorio(
            caixas[0].empresa)

        def andamento(feito, total):
            lote["progresso"] = {
                "etapa": "Lendo o cadastro de clientes (página %d de %d)"
                         % (feito, total),
                "percentual": 10 + int(feito / max(total, 1) * 80),
            }

        # O PDF de clientes é opcional: só entra quando há gente nova para
        # acrescentar. A conciliação usa sempre a base salva.
        if lote["arquivos"].get("clientes"):
            lote["progresso"] = {"etapa": "Abrindo o cadastro de clientes",
                                 "percentual": 10}
            cadastro = obter_cadastro(lote["arquivos"]["clientes"],
                                      progresso=andamento)
            lote["progresso"] = {"etapa": "Atualizando a base de clientes",
                                 "percentual": 90}
            base = base_clientes.abrir(cfgmod.PASTA_DADOS, lote["unidade"])
            lote["importacao"] = _resumir_importacao(
                base.mesclar(cadastro, origem=os.path.basename(
                    lote["arquivos"]["clientes"]))
            )

        lote["progresso"] = {"etapa": "Cruzando o caixa com o cadastro", "percentual": 92}
        conciliar_lote(lote)

        lote["estado"] = "pronto"
        lote["progresso"] = {"etapa": "pronto", "percentual": 100}
    except Exception as erro:  # noqa: BLE001
        lote["estado"] = "erro"
        lote["erro"] = "%s: %s" % (type(erro).__name__, erro)
        lote["detalhe_erro"] = traceback.format_exc()
        lote["progresso"] = {"etapa": "erro", "percentual": 100}
    salvar_lote(lote)


# ---------------------------------------------------------------------------
# telas
# ---------------------------------------------------------------------------

@app.errorhandler(ControleIlegivel)
def controle_ilegivel(erro):
    """O controle da numeracao corrompeu.

    Vale uma tela propria, e nao um 500: e o arquivo mais critico do sistema,
    quem esta na recepcao nao sabe o que fazer com um traceback, e a acao
    certa (restaurar o backup) e diferente de tudo o mais que da errado aqui.
    """
    return render_template("controle_ilegivel.html", detalhe=str(erro)), 500


def lotes_por_transmitir() -> list:
    """Pastas de saída com XMLs que ainda não foram aceitos pela prefeitura.

    Sem isto o operador ficava preso: gerava as notas, saía da tela, e ao
    reabrir a conferência o sistema pulava tudo -- porque aqueles lançamentos
    já constavam como emitidos. As notas existiam no disco, prontas e
    assinadas, e não havia caminho de volta até elas.
    """
    if not os.path.isdir(cfgmod.PASTA_SAIDA):
        return []

    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        por_arquivo = controle.por_arquivo()

    pendentes = []
    for nome in sorted(os.listdir(cfgmod.PASTA_SAIDA), reverse=True):
        caminho = os.path.join(cfgmod.PASTA_SAIDA, nome)
        if not os.path.isdir(caminho):
            continue
        # Pasta de simulação e lote descartado não são transmissíveis.
        if nome.endswith("-teste") or "-DESCARTADO" in nome:
            continue
        arquivos = listar_xmls(caminho)
        if not arquivos:
            continue
        transmitidas = sum(
            1 for a in arquivos
            if por_arquivo.get(a, (None, {}))[1].get("transmitida"))
        faltam = len(arquivos) - transmitidas
        if not faltam:
            continue
        pendentes.append({
            "pasta": nome,
            "total": len(arquivos),
            "transmitidas": transmitidas,
            "faltam": faltam,
            "ambiente": ambiente_da_pasta(caminho),
            "quando": datetime.fromtimestamp(
                os.path.getmtime(caminho)).strftime("%d/%m/%Y %H:%M"),
        })
    return pendentes


@app.route("/")
def inicio():
    cfg = cfgmod.carregar()
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        resumo_controle = controle.resumo()
    lotes = []
    for nome in sorted(os.listdir(cfgmod.PASTA_LOTES), reverse=True)[:8]:
        lote = carregar_lote(nome)
        if lote:
            lotes.append(lote)
    bases = {}
    for chave in cfg.unidades:
        base = base_clientes.abrir(cfgmod.PASTA_DADOS, chave)
        if base.existe:
            bases[chave] = base.resumo()
    return render_template(
        "inicio.html",
        unidades=cfg.unidades,
        lotes=lotes,
        diagnostico=cfg.diagnostico(),
        controle=resumo_controle,
        bases=bases,
        pendentes=lotes_por_transmitir(),
    )


@app.post("/lote")
def criar_lote():
    arquivos = request.files.getlist("arquivos")
    if not arquivos:
        return jsonify({"erro": "Nenhum arquivo foi enviado."}), 400

    limpar_antigos(cfgmod.PASTA_LOTES, manter=9)
    limpar_antigos(cfgmod.PASTA_SAIDA, manter=20, sufixo="-teste")

    lote_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    pasta = caminho_lote(lote_id)
    os.makedirs(pasta, exist_ok=True)

    caixas, clientes, ignorados, detalhes = [], None, [], []
    for arquivo in arquivos:
        nome = os.path.basename(arquivo.filename or "arquivo.pdf")
        if not nome.lower().endswith(".pdf"):
            ignorados.append("%s (não é PDF)" % nome)
            continue
        destino = destino_unico(pasta, nome)
        try:
            arquivo.save(destino)
        except OSError as erro:
            ignorados.append("%s (não deu para salvar: %s)" % (nome, erro))
            continue
        info = identificar_pdf(destino)
        info["arquivo"] = nome
        detalhes.append(info)
        if info["tipo"] == "clientes":
            clientes = destino
        elif info["tipo"] == "caixa":
            caixas.append(destino)
        elif info["tipo"] == "ilegivel":
            ignorados.append("%s — %s" % (nome, info.get("motivo", "ilegível")))
        else:
            ignorados.append("%s (não reconheci que relatório é)" % nome)

    if not caixas:
        shutil.rmtree(pasta, ignore_errors=True)
        # Quando TODOS os arquivos falharam, o motivo de cada um explica mais
        # do que "falta o relatório de caixa".
        detalhe = "; ".join(ignorados)
        return jsonify({
            "erro": ("Falta pelo menos um relatório CAIXA - LANÇAMENTOS."
                     + ((" O que recebi: " + detalhe) if detalhe else "")),
            "detalhes": detalhes,
        }), 400

    # O cadastro de clientes só é obrigatório enquanto a unidade não tiver
    # base salva. Depois disso, ele vira opcional: mande de novo quando
    # houver paciente novo, e só a diferença entra.
    cfg = cfgmod.carregar()
    unidade_detectada = request.form.get("unidade") or ""
    if not unidade_detectada:
        primeiro = identificar_pdf(caixas[0])
        unidade_detectada = cfg.unidade_por_relatorio(primeiro.get("empresa", "")) or ""

    if not clientes and unidade_detectada:
        base = base_clientes.abrir(cfgmod.PASTA_DADOS, unidade_detectada)
        if not base.existe:
            shutil.rmtree(pasta, ignore_errors=True)
            return jsonify({
                "erro": "Ainda não há base de clientes para %s. Mande o "
                        "relatório CLIENTES E FORNECEDORES junto desta primeira "
                        "vez — depois ele fica salvo e não precisa mais."
                        % cfg.unidades.get(unidade_detectada, {}).get(
                            "apelido", unidade_detectada),
                "detalhes": detalhes,
            }), 400

    lote = {
        "id": lote_id,
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivos": {"caixas": caixas, "clientes": clientes},
        "detalhes": detalhes,
        "ignorados": ignorados,
        "unidade": unidade_detectada,
        "competencia": request.form.get("competencia") or "",
        "escolhas": {},
        "estado": "lendo",
        "progresso": {"etapa": "Preparando", "percentual": 1},
    }
    with _TRAVA:
        LOTES[lote_id] = lote
    salvar_lote(lote)

    threading.Thread(target=processar_em_segundo_plano, args=(lote_id,),
                     daemon=True).start()
    return jsonify({"id": lote_id})


@app.get("/lote/<lote_id>/progresso")
def progresso(lote_id: str):
    lote = carregar_lote(lote_id)
    if not lote:
        return jsonify({"erro": "Conferência não encontrada."}), 404
    return jsonify({
        "estado": lote.get("estado"),
        "progresso": lote.get("progresso", {}),
        "erro": lote.get("erro", ""),
    })


@app.get("/lote/<lote_id>")
def conferencia(lote_id: str):
    lote = carregar_lote(lote_id)
    if not lote:
        abort(404)
    if lote.get("estado") == "lendo":
        return render_template("carregando.html", lote=lote)
    if lote.get("estado") == "erro":
        return render_template("erro.html", lote=lote)

    cfg, cadastro, resultado = conciliar_lote(lote)
    return render_template(
        "conferencia.html",
        lote=lote,
        r=resultado,
        cfg=cfg,
        unidade=cfg.unidade(resultado.unidade),
        brl=brl,
        formatar_documento=formatar_documento,
        total_cadastro=len(cadastro.clientes),
        envio=situacao_envio(cfg),
        situacao_ambientes=situacao_por_ambiente(resultado),
    )


def situacao_por_ambiente(resultado) -> dict:
    """Quantas destas notas já saíram em cada ambiente.

    É o que responde "já testei, falta emitir valendo?" sem obrigar o
    operador a lembrar do que fez. Cada ambiente tem contagem própria, então
    um lote pode estar 100% testado e 0% emitido — que é justamente o estado
    normal entre conferir e valer.
    """
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        situacao = {}
        for ambiente in ("homologacao", "producao"):
            feitas = sum(
                1 for nota in resultado.notas
                if controle.ja_emitida(
                    Controle.chave(resultado.unidade, nota.id, ambiente))
            )
            situacao[ambiente] = {
                "feitas": feitas,
                "faltam": len(resultado.notas) - feitas,
                "total": len(resultado.notas),
            }
    return situacao


@app.post("/lote/<lote_id>/escolher")
def escolher(lote_id: str):
    """Resolve uma pendencia apontando o cadastro correto.

    So aceita documento que EXISTA no cadastro: o sistema nunca inventa
    endereco de tomador.
    """
    lote = carregar_lote(lote_id)
    if not lote:
        abort(404)
    dados = request.get_json(force=True)
    lancamento = dados.get("lancamento", "")
    documento = so_digitos(dados.get("documento", ""))

    _, cadastro, _ = conciliar_lote(lote)
    if documento and not cadastro.por_cpf(documento):
        return jsonify({
            "erro": "O CPF %s não existe no cadastro de clientes. Cadastre a "
                    "pessoa no TechCare e exporte o relatório de novo."
                    % formatar_documento(documento)
        }), 400

    lote.setdefault("escolhas", {})
    if documento:
        lote["escolhas"][lancamento] = documento
    else:
        lote["escolhas"].pop(lancamento, None)
    salvar_lote(lote)
    return jsonify({"ok": True})


@app.get("/lote/<lote_id>/buscar")
def buscar_cliente(lote_id: str):
    """Busca no cadastro para resolver uma pendencia."""
    lote = carregar_lote(lote_id)
    if not lote:
        abort(404)
    termo = chave_nome(request.args.get("q", ""))
    if len(termo) < 3:
        return jsonify({"resultados": []})
    _, cadastro, _ = conciliar_lote(lote)
    achados = []
    for cliente in cadastro.clientes:
        if termo in cliente.chave or termo in so_digitos(cliente.documento):
            achados.append({
                "nome": cliente.nome,
                "documento": cliente.documento,
                "documento_formatado": cliente.documento_formatado,
                "valido": cliente.documento_ok,
                "endereco": "%s, %s - %s - %s/%s" % (
                    cliente.logradouro, cliente.numero, cliente.bairro,
                    cliente.cidade, cliente.uf),
                "nascimento": cliente.nascimento,
            })
            if len(achados) >= 25:
                break
    return jsonify({"resultados": achados})


@app.get("/lote/<lote_id>/planilha")
def planilha_lote(lote_id: str):
    """Baixa a conferência em .xlsx, para o contador conferir fora do sistema.

    O RELATORIO.txt serve para olhar rápido, mas não dá para filtrar nem
    cruzar com o razão. Quem confere número trabalha em planilha.
    """
    lote = carregar_lote(lote_id)
    if not lote:
        abort(404)
    cfg, _, resultado = conciliar_lote(lote)
    unidade = cfg.unidade(resultado.unidade)
    # A competencia do lote so existe quando o operador digitou; a das notas
    # sempre existe, porque vem do proprio relatorio.
    competencia = (lote.get("competencia")
                   or (resultado.notas[0].competencia if resultado.notas else ""))
    try:
        dados = planilha.gerar(resultado, unidade, competencia,
                               aliquota_iss=cfg.servico.get("aliquota_iss", 0))
    except ImportError:
        abort(500, "A biblioteca openpyxl não está instalada. "
                   "Rode o instalar.bat novamente.")
    nome = "conferencia-%s-%s.xlsx" % (
        resultado.unidade, competencia.replace("/", "-"))
    return send_file(io.BytesIO(dados), as_attachment=True, download_name=nome,
                     mimetype="application/vnd.openxmlformats-officedocument."
                              "spreadsheetml.sheet")


@app.post("/lote/<lote_id>/gerar")
def gerar(lote_id: str):
    lote = carregar_lote(lote_id)
    if not lote:
        abort(404)
    # Tres caminhos, e o ambiente e escolhido AQUI, no lote:
    #   simular    -> nao consome numeracao, so para conferir
    #   homologacao-> vale como teste na prefeitura, numeracao propria
    #   producao   -> nota fiscal de verdade
    modo = request.form.get("modo", "simular")
    valendo = modo in ("homologacao", "producao")
    ambiente = modo if valendo else ""

    if modo == "producao" and chave_nome(
        request.form.get("confirmacao", "")
    ) != "EMITIR":
        return redirect(url_for("conferencia", lote_id=lote_id) + "?erro=confirmacao")

    # Lista vazia = todas. O operador pode marcar so algumas na conferencia
    # para emitir uma nota especifica -- a de um paciente que ele quer
    # conferir -- antes de soltar o mes inteiro.
    escolhidas = set(request.form.getlist("apenas")) or None

    cfg, _, resultado = conciliar_lote(lote)
    saida = emitir(resultado, cfg, simular=not valendo, ambiente=ambiente,
                   apenas=escolhidas)
    lote["ultima_saida"] = saida.pasta
    salvar_lote(lote)
    return render_template(
        "resultado.html",
        lote=lote,
        saida=saida,
        r=resultado,
        brl=brl,
        pasta_nome=os.path.basename(saida.pasta),
        pasta_relativa=os.path.relpath(saida.pasta, cfgmod.RAIZ),
    )


@app.get("/saida/<path:pasta>/zip")
def baixar_zip(pasta: str):
    caminho = os.path.join(cfgmod.PASTA_SAIDA, pasta)
    if not os.path.isdir(caminho) or ".." in pasta:
        abort(404)
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome in sorted(os.listdir(caminho)):
            zf.write(os.path.join(caminho, nome), nome)
    memoria.seek(0)
    return send_file(memoria, mimetype="application/zip", as_attachment=True,
                     download_name="%s.zip" % pasta)


def ambiente_da_pasta(caminho: str) -> str:
    """Para qual ambiente os XMLs desta pasta foram gerados.

    Lido do primeiro XML: o lote inteiro sai da mesma configuração, então um
    basta. Serve para avisar na tela antes do clique, e não depois da recusa.
    """
    for nome in listar_xmls(caminho):
        with open(os.path.join(caminho, nome), "rb") as fh:
            return ambiente_do_xml(fh.read(4000))
    return ""


@app.post("/saida/<path:pasta>/transmitir")
def transmitir_lote(pasta: str):
    """Transmite os XMLs de uma pasta de saída para a prefeitura.

    Duas travas: a primeira transmissão manda uma nota só, e produção exige
    confirmação digitada. Em Vila Velha, cancelar exige processo
    administrativo — errar aqui custa caro.
    """
    caminho = os.path.join(cfgmod.PASTA_SAIDA, pasta)
    if not os.path.isdir(caminho) or ".." in pasta:
        abort(404)
    if pasta.endswith("-teste"):
        abort(400, "XMLs de teste não são transmitidos: gere valendo antes.")

    cfg = cfgmod.carregar()

    # O ambiente vem das PRÓPRIAS notas, não de um botão: ele está assinado
    # dentro de cada XML e não pode ser trocado aqui. Perguntar de novo só
    # criava a chance de escolher errado -- e a recusa vinha depois, da
    # prefeitura, sem explicação óbvia.
    ambiente = ambiente_da_pasta(caminho) or "homologacao"
    cfg.faturamento["ambiente"] = ambiente
    quantidade = request.form.get("quantidade", "uma")
    limite = 1 if quantidade == "uma" else None

    erro = ""
    if ambiente == "producao" and chave_nome(
        request.form.get("confirmacao", "")
    ) != "PRODUCAO":
        erro = "Para transmitir em produção é preciso digitar PRODUCAO."

    # Uma nota so continua sincrona: e rapida e o operador quer ver o retorno
    # na hora. Lote grande vai para segundo plano -- 276 notas levam minutos,
    # e uma requisicao HTTP parada esse tempo todo parece travamento (e o
    # navegador pode desistir no meio, deixando o envio sem dono).
    if not erro and limite != 1:
        with _TRAVA:
            if TRANSMISSOES.get(pasta, {}).get("estado") == "enviando":
                erro = "Esta pasta já está sendo transmitida agora."
            else:
                TRANSMISSOES[pasta] = {
                    "estado": "enviando", "feitos": 0, "total": 0,
                    "aceitas": 0, "recusadas": 0, "na_fila": 0,
                    "ambiente": ambiente, "ultimo": "", "erro": "",
                }
        if not erro:
            threading.Thread(target=_transmitir_em_segundo_plano,
                             args=(pasta, caminho, ambiente),
                             daemon=True).start()
            return redirect(url_for("tela_transmitir", pasta=pasta))

    resultado = None
    if not erro:
        try:
            resultado = transmitir(caminho, cfg, limite=limite)
        except EnvioIndisponivel as falha:
            erro = str(falha)
        except Exception as falha:  # noqa: BLE001
            erro = "%s: %s" % (type(falha).__name__, falha)

    return render_template(
        "transmissao.html",
        pasta=pasta,
        resultado=resultado,
        erro=erro,
        ambiente=ambiente,
        envio=situacao_envio(cfg),
        arquivos=len(listar_xmls(caminho)),
        gerado_para=ambiente_da_pasta(caminho),
        andamento=TRANSMISSOES.get(pasta),
    )


def _transmitir_em_segundo_plano(pasta: str, caminho: str, ambiente: str) -> None:
    """Envia o lote fora da requisição, atualizando o andamento."""
    cfg = cfgmod.carregar()
    cfg.faturamento["ambiente"] = ambiente

    comeco = time.monotonic()

    def andou(feitos, total, item):
        with _TRAVA:
            estado = TRANSMISSOES.setdefault(pasta, {})
            estado["feitos"] = feitos
            estado["total"] = total
            # Estimativa pelo ritmo medido, nao por um numero fixo: a
            # prefeitura ora responde na hora, ora demora segundos, e a
            # diferenca entre 2 e 21 minutos para o mesmo lote e grande
            # demais para o operador ficar no escuro.
            decorrido = time.monotonic() - comeco
            if feitos >= 3 and total > feitos:
                por_nota = decorrido / feitos
                estado["faltam_seg"] = int(por_nota * (total - feitos))
            if item.aceita:
                estado["aceitas"] = estado.get("aceitas", 0) + 1
                estado["ultimo"] = "nota %s emitida" % (item.numero_nota or "?")
            else:
                estado["recusadas"] = estado.get("recusadas", 0) + 1
                if item.na_fila:
                    estado["na_fila"] = estado.get("na_fila", 0) + 1
                estado["ultimo"] = "DPS %s recusada" % (item.numero_dps or "?")

    try:
        resultado = transmitir(caminho, cfg, progresso=andou)
        with _TRAVA:
            TRANSMISSOES[pasta] = {
                "estado": "pronto",
                "feitos": len(resultado.enviadas),
                "total": len(resultado.enviadas),
                "aceitas": len(resultado.aceitas),
                "recusadas": len(resultado.recusadas),
                "na_fila": sum(1 for e in resultado.enviadas if e.na_fila),
                "ambiente": ambiente, "ultimo": "", "erro": "",
            }
        RESULTADOS_TRANSMISSAO[pasta] = resultado
    except Exception as falha:  # noqa: BLE001
        with _TRAVA:
            TRANSMISSOES.setdefault(pasta, {})["estado"] = "erro"
            TRANSMISSOES[pasta]["erro"] = "%s: %s" % (type(falha).__name__, falha)


@app.get("/saida/<path:pasta>/andamento")
def andamento_transmissao(pasta: str):
    estado = TRANSMISSOES.get(pasta)
    if not estado:
        return jsonify({"estado": "parado"})
    return jsonify(estado)


@app.get("/saida/<path:pasta>/transmitir")
def tela_transmitir(pasta: str):
    caminho = os.path.join(cfgmod.PASTA_SAIDA, pasta)
    if not os.path.isdir(caminho) or ".." in pasta:
        abort(404)
    cfg = cfgmod.carregar()
    return render_template(
        "transmissao.html",
        pasta=pasta,
        resultado=RESULTADOS_TRANSMISSAO.get(pasta),
        erro="",
        ambiente=cfg.faturamento.get("ambiente", "homologacao"),
        envio=situacao_envio(cfg),
        arquivos=len(listar_xmls(caminho)),
        gerado_para=ambiente_da_pasta(caminho),
        andamento=TRANSMISSOES.get(pasta),
    )


@app.get("/configuracao")
def configuracao():
    cfg = cfgmod.carregar()
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        resumo_controle = controle.resumo()
    certificados = {}
    for chave, dados in cfg.unidades.items():
        caminho = cfg.caminho_certificado(chave)
        info = {
            "arquivo": dados.get("certificado"),
            "existe": os.path.exists(caminho),
            "variavel": dados.get("variavel_senha"),
            "senha_definida": bool(os.environ.get(dados.get("variavel_senha", ""))),
            "titular": "", "validade": "", "vencido": None, "erro": "",
        }
        if info["existe"] and info["senha_definida"]:
            try:
                from nfse.assinatura import carregar_pfx
                cert = carregar_pfx(caminho, cfg.senha_certificado(chave))
                info["titular"] = cert.titular
                info["validade"] = cert.validade.strftime("%d/%m/%Y")
                info["vencido"] = cert.vencido
            except Exception as erro:  # noqa: BLE001
                info["erro"] = str(erro)
        certificados[chave] = info
    return render_template(
        "configuracao.html",
        cfg=cfg,
        diagnostico=cfg.diagnostico(),
        certificados=certificados,
        controle=resumo_controle,
        envio=situacao_envio(cfg),
        caminho_config=cfgmod.CAMINHO_CONFIG,
        versao=atualizacao_mod.versao_instalada(),
        versoes_guardadas=atualizacao_mod.versoes_guardadas()[:8],
        atualizacao=session.pop("atualizacao", None),
        descarte=session.pop("descarte", None),
    )


@app.post("/configuracao/numeracao")
def ajustar_numeracao():
    unidade = request.form.get("unidade", "")
    ultimo = request.form.get("ultimo", "0")
    ambiente = request.form.get("ambiente", "")
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        try:
            controle.ajustar_numeracao(unidade, int(ultimo), ambiente)
        except (TypeError, ValueError):
            pass
    return redirect(url_for("configuracao"))


@app.post("/atualizacao/procurar")
def procurar_atualizacao():
    """Só consulta: não baixa e não muda nada."""
    session["atualizacao"] = atualizacao_mod.procurar()
    return redirect(url_for("configuracao"))


@app.post("/atualizacao/aplicar")
def aplicar_atualizacao():
    informacao = atualizacao_mod.procurar()
    resultado = dict(informacao)
    if not informacao.get("novidade"):
        resultado["mensagem"] = "Já está na versão mais recente."
    else:
        try:
            aplicado = atualizacao_mod.aplicar(informacao)
            resultado["aplicado"] = aplicado
            resultado["mensagem"] = (
                "Atualizado para a versão %s (%d arquivo(s)). "
                "Feche e abra o programa para valer."
                % (aplicado["versao"], aplicado["arquivos"]))
        except atualizacao_mod.ErroAtualizacao as erro:
            resultado["erro_aplicar"] = str(erro)
    session["atualizacao"] = resultado
    return redirect(url_for("configuracao"))


@app.post("/atualizacao/reverter")
def reverter_atualizacao():
    nome = request.form.get("versao", "")
    resultado = {"instalada": atualizacao_mod.versao_instalada()}
    try:
        voltou = atualizacao_mod.reverter(nome)
        resultado["mensagem"] = (
            "Voltei para %s (%d arquivo(s)). Feche e abra o programa."
            % (voltou["versao"], voltou["arquivos"]))
    except atualizacao_mod.ErroAtualizacao as erro:
        resultado["erro_aplicar"] = str(erro)
    session["atualizacao"] = resultado
    return redirect(url_for("configuracao"))


@app.post("/saida/<path:pasta>/descartar")
def descartar_lote(pasta: str):
    """Joga fora um lote gerado com numeração errada, para poder refazer.

    O caso real: o controle da numeração é perdido, o sistema recomeça do 1 e
    o lote inteiro sai com números que a prefeitura já usou. Sem isto o
    operador fica preso -- a prefeitura recusa por duplicidade (E0014) e a
    antiduplicidade daqui impede gerar de novo.
    """
    caminho = os.path.join(cfgmod.PASTA_SAIDA, pasta)
    if not os.path.isdir(caminho) or ".." in pasta:
        abort(404)

    nomes = listar_xmls(caminho)
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        resultado = controle.descartar_lote(nomes)

    # Os XMLs vão para uma pasta com nome marcado, em vez de serem apagados:
    # são documentos assinados, e apagar sem poder olhar depois é pior do que
    # deixar uma pasta a mais no disco.
    if resultado["descartadas"] and not resultado["protegidas"]:
        novo_nome = caminho + "-DESCARTADO"
        contador = 2
        while os.path.exists(novo_nome):
            novo_nome = "%s-DESCARTADO-%d" % (caminho, contador)
            contador += 1
        try:
            os.rename(caminho, novo_nome)
        except OSError:
            pass

    session["descarte"] = resultado
    return redirect(url_for("configuracao"))


@app.route("/consultar", methods=["GET", "POST"])
def consultar_nota():
    """Confere uma nota direto na prefeitura, pela chave de acesso.

    Serve para provar que a nota existe do lado de la -- util quando o
    paciente liga perguntando, e util para conferir a primeira de producao.
    """
    cfg = cfgmod.carregar()
    resultado = erro = None
    chave = (request.form.get("chave") or request.args.get("chave") or "").strip()
    unidade = request.form.get("unidade") or next(iter(cfg.unidades))
    if request.method == "POST" and chave:
        chave_limpa = "".join(c for c in chave if c.isdigit())
        try:
            resultado = consultar(cfg, unidade, chave_acesso=chave_limpa)
        except Exception as falha:  # noqa: BLE001
            erro = "%s: %s" % (type(falha).__name__, falha)
    with Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db")) as controle:
        recentes = controle.transmitidas(limite=15)
    return render_template("consulta.html", cfg=cfg, resultado=resultado,
                           erro=erro, chave=chave, unidade=unidade,
                           recentes=recentes,
                           ambiente=cfg.faturamento.get("ambiente", ""))


@app.post("/backup")
def backup():
    """Zip com o que não pode ser perdido.

    Entram: o controle da numeração, a base de clientes e a configuração.

    **Não entram os certificados nem o senhas.bat.** Um .pfx com a senha do
    lado num arquivo que circula por e-mail é exatamente como uma assinatura
    digital vaza. Esses ficam por conta de quem é o dono, guardados fora daqui.
    """
    memoria = io.BytesIO()
    incluidos = []
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as zf:
        controle = os.path.join(cfgmod.PASTA_DADOS, "controle.db")
        if os.path.exists(controle):
            zf.write(controle, "dados/controle.db")
            incluidos.append("controle.db")
        pasta_clientes = os.path.join(cfgmod.PASTA_DADOS, "clientes")
        if os.path.isdir(pasta_clientes):
            for nome in sorted(os.listdir(pasta_clientes)):
                if nome.endswith(".json"):
                    zf.write(os.path.join(pasta_clientes, nome),
                             "dados/clientes/" + nome)
                    incluidos.append("clientes/" + nome)
        if os.path.exists(cfgmod.CAMINHO_CONFIG):
            zf.write(cfgmod.CAMINHO_CONFIG, "config/empresas.json")
            incluidos.append("empresas.json")
        zf.writestr("LEIA-ME.txt", os.linesep.join([
            "Backup do Emissor de NFS-e",
            "Gerado em %s" % datetime.now().strftime("%d/%m/%Y %H:%M"),
            "",
            "Conteudo: %s" % ", ".join(incluidos),
            "",
            "Para restaurar: copie as pastas 'dados' e 'config' por cima",
            "da instalacao, com o programa FECHADO.",
            "",
            "NAO estao aqui, de proposito:",
            "  - os certificados A1 (.pfx)",
            "  - o config/senhas.bat",
            "",
            "Guarde esses dois separadamente, em lugar seguro. Certificado",
            "com a senha junto, num arquivo que circula, e assinatura",
            "digital vazada.",
        ]))
    memoria.seek(0)
    return send_file(
        memoria, mimetype="application/zip", as_attachment=True,
        download_name="backup-nfse-%s.zip" % datetime.now().strftime("%Y%m%d-%H%M"),
    )


@app.get("/clientes")
def clientes():
    """Estado da base de clientes, com busca e lista de quem está incompleto.

    Antes esta tela só mostrava contagens. Saber que há "849 sem documento
    válido" não ajuda ninguém: o operador precisa CHEGAR neles para corrigir
    no TechCare, e não havia caminho — o problema só aparecia depois, na
    conferência, um lançamento por vez.
    """
    cfg = cfgmod.carregar()
    bases = {}
    for chave, dados in cfg.unidades.items():
        base = base_clientes.abrir(cfgmod.PASTA_DADOS, chave)
        bases[chave] = {
            "apelido": dados.get("apelido", chave),
            "existe": base.existe,
            "resumo": base.resumo(),
            "pendencias": base.pendencias() if base.existe else {},
            "historico": list(reversed(base.historico))[:12],
            "caminho": base.caminho,
        }

    unidade = request.args.get("unidade") or next(iter(cfg.unidades))
    termo = (request.args.get("q") or "").strip()
    filtro = request.args.get("filtro") or ""
    achados, quantos = [], 0
    if unidade in cfg.unidades:
        base = base_clientes.abrir(cfgmod.PASTA_DADOS, unidade)
        if base.existe and (termo or filtro):
            achados, quantos = base.procurar(termo, filtro)

    return render_template("clientes.html", bases=bases, unidade=unidade,
                           termo=termo, filtro=filtro, achados=achados,
                           quantos=quantos, cfg=cfg)


@app.get("/ajuda")
def ajuda():
    return render_template("ajuda.html")


@app.template_filter("dinheiro")
def filtro_dinheiro(valor):
    return brl(valor)


@app.template_filter("documento")
def filtro_documento(valor):
    return formatar_documento(valor)


@app.template_filter("data_br")
def filtro_data(valor):
    if not valor:
        return "-"
    partes = str(valor).split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else valor


def main():
    # O console do Windows costuma vir em cp1252 e derruba o programa ao
    # imprimir um caractere que ele nao tem. Numa janela na recepcao isso
    # aparece como "o sistema nao abre", sem explicacao nenhuma.
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    cfgmod.garantir_pastas()
    porta = int(os.environ.get("PORTA_EMISSOR", "5510"))

    # O servidor do Flask imprime um aviso de "development server" e uma linha
    # por requisicao. Numa janela preta na recepcao da clinica isso so assusta:
    # o app roda em 127.0.0.1, para uma pessoa. Deixamos so os erros.
    import logging

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if os.environ.get("ABRIR_NAVEGADOR", "1") == "1":
        import webbrowser
        threading.Timer(
            1.2, lambda: webbrowser.open("http://127.0.0.1:%d" % porta)
        ).start()
    print("")
    print("  Emissor de NFS-e aberto no navegador.")
    print("  Endereço: http://127.0.0.1:%d" % porta)
    print("")
    print("  Deixe esta janela aberta enquanto estiver usando.")
    print("  Para encerrar, feche esta janela.")
    print("")
    # run_simple no lugar de app.run(): evita o banner do Flask, que so
    # confunde quem estiver olhando para a janela.
    from werkzeug.serving import run_simple

    run_simple("127.0.0.1", porta, app, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
