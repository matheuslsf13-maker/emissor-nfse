# -*- coding: utf-8 -*-
"""Leitura do relatorio CAIXA - LANCAMENTOS do TechCare.

O relatorio e dividido em secoes ("31 - VENDA - PIX"), cada uma terminada
por uma linha "QTDE n VALOR x". Guardamos esses totais e conferimos contra
o que foi lido: se divergir, o operador e avisado em vez de receber uma
conciliacao silenciosamente incompleta.

O codigo numerico da secao NAO e confiavel -- 54 e "MANUT ORTO - CARTAO
DEBITO" no caixa da clinica e "REC ODC - BOLETO" no caixa de contratos.
Classificamos sempre pelo nome.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Callable

from .pdf import ler_linhas
from .util import chave_nome, data_br, limpar, moeda, so_digitos

# Fronteiras das colunas em pontos (origem: cabecalho do relatorio).
COL_LANCTO = (0, 64)
COL_DATA = (64, 105)
COL_HISTORICO = (105, 310)
COL_VALOR = (310, 356)
COL_SINAL = (356, 372)
COL_NUMDOC = (372, 416)
COL_RESP = (416, 440)
COL_USUARIO = (440, 520)

RE_SECAO = re.compile(r"^(\d{1,3})\s*-\s*(.+)$")
RE_QTDE = re.compile(r"^QTDE\s+(\d+)\s+VALOR\s+([\d.,]+)$", re.I)
RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
RE_CPF_HIST = re.compile(r"(\d{3}\.\d{3}\.\d{3}-\d{2})")
RE_CONTRATO = re.compile(r"^(\d+/[\d\-]+)\s*-\s*(.+)$")


@dataclass
class Lancamento:
    """Uma linha do caixa, ainda sem cruzamento com o cadastro."""

    origem: str                 # nome do arquivo de onde veio
    caixa: str                  # "CLINICA" ou "CONTRATOS"
    secao_codigo: str
    secao: str                  # nome da secao, normalizado
    lancto: str
    data: date | None
    historico: str
    valor: Decimal
    sinal: str                  # "+" entrada, "-" saida
    num_doc: str
    responsavel: str
    usuario: str
    pagina: int

    # derivados do historico
    tipo: str = ""              # VENDA | MAN | REC | BCO | OUTRO
    contrato: str = ""
    nome_bruto: str = ""        # nome como aparece no caixa
    cpf_historico: str = ""     # preenchido nos lancamentos BCO

    @property
    def id(self) -> str:
        return "%s:%s:%s" % (self.caixa, self.lancto, self.num_doc)

    @property
    def nome_chave(self) -> str:
        return chave_nome(self.nome_bruto)


@dataclass
class TotalSecao:
    secao: str
    qtde_informada: int
    valor_informado: Decimal
    qtde_lida: int = 0
    valor_lido: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def confere(self) -> bool:
        return (
            self.qtde_lida == self.qtde_informada
            and abs(self.valor_lido - self.valor_informado) < Decimal("0.01")
        )


@dataclass
class Caixa:
    """Resultado da leitura de um relatorio de caixa."""

    arquivo: str
    empresa: str = ""           # "VILA VELHA - GLORIA - CLINICA"
    unidade: str = ""           # "GLORIA"
    caixa: str = ""             # "CLINICA" | "CONTRATOS"
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    lancamentos: list = field(default_factory=list)
    totais: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def divergencias(self):
        return [t for t in self.totais if not t.confere]


def _e_cabecalho_lancamentos(texto: str) -> bool:
    t = texto.upper()
    return t.startswith("CAIXA -") and "AMENTOS" in t


def _e_registro_exclusoes(texto: str) -> bool:
    return "REGISTRO DE EXCLUS" in texto.upper()


def _partir_empresa(valor: str):
    """VILA VELHA - GLORIA - CLINICA  ->  (GLORIA, CLINICA)."""
    partes = [limpar(p) for p in valor.split("-")]
    unidade = partes[1].upper() if len(partes) > 1 else ""
    caixa = partes[-1].upper() if len(partes) > 2 else ""
    return unidade, caixa


def _interpretar_historico(lanc) -> None:
    """Extrai tipo, contrato, nome e CPF do campo HISTORICO.

    Formatos observados:
        VENDA - FULANO DE TAL
        MAN   - FULANO DE TAL
        REC   - 32260/04 - FULANO DE TAL
        BCO   - 22230368 - 772.889.127-87
        ENVELOPE
    """
    texto = limpar(lanc.historico)
    if " - " in texto:
        prefixo, _, resto = texto.partition(" - ")
    else:
        prefixo, resto = texto, ""
    prefixo = prefixo.strip().upper()

    if prefixo in ("VENDA", "MAN", "REC", "BCO"):
        lanc.tipo = prefixo
    else:
        lanc.tipo = "OUTRO"
        lanc.nome_bruto = texto
        return

    if lanc.tipo == "BCO":
        # BCO - <nosso numero> - <CPF>
        achado = RE_CPF_HIST.search(resto)
        if achado:
            lanc.cpf_historico = so_digitos(achado.group(1))
        else:
            for parte in resto.split(" - "):
                d = so_digitos(parte)
                if len(d) == 11:
                    lanc.cpf_historico = d
                    break
        lanc.contrato = limpar(resto.split(" - ")[0]) if " - " in resto else ""
        return

    m = RE_CONTRATO.match(resto)
    if m:
        lanc.contrato = m.group(1)
        lanc.nome_bruto = limpar(m.group(2))
    else:
        lanc.nome_bruto = limpar(resto)


def ler_caixa(caminho: str, progresso: Callable = None):
    """Le um PDF de caixa e devolve os lancamentos com os totais por secao."""
    resultado = Caixa(arquivo=os.path.basename(caminho))
    em_lancamentos = False
    secao_codigo = ""
    secao_nome = ""
    total_atual = None

    for linha in ler_linhas(caminho, progresso=progresso):
        texto = linha.texto
        if not texto:
            continue

        # --- cabecalho do relatorio ---------------------------------------
        if texto.upper().startswith("EMPRESA:") and not resultado.empresa:
            resultado.empresa = limpar(texto.split(":", 1)[1])
            resultado.unidade, resultado.caixa = _partir_empresa(resultado.empresa)
        if (
            texto.upper().startswith("PER")
            and ":" in texto
            and resultado.periodo_inicio is None
        ):
            datas = re.findall(r"\d{2}/\d{2}/\d{4}", texto)
            if len(datas) >= 2:
                resultado.periodo_inicio = data_br(datas[0])
                resultado.periodo_fim = data_br(datas[1])

        if _e_cabecalho_lancamentos(texto):
            em_lancamentos = True
            continue
        if _e_registro_exclusoes(texto):
            em_lancamentos = False
            continue
        if not em_lancamentos:
            continue

        # --- fim de secao --------------------------------------------------
        m_qtde = RE_QTDE.match(texto)
        if m_qtde:
            if total_atual is None:
                total_atual = TotalSecao(secao_nome, 0, Decimal("0"))
            total_atual.qtde_informada = int(m_qtde.group(1))
            total_atual.valor_informado = moeda(m_qtde.group(2)) or Decimal("0")
            resultado.totais.append(total_atual)
            total_atual = None
            secao_codigo = secao_nome = ""
            continue

        # --- inicio de secao -----------------------------------------------
        if linha.x0 < 30 and not RE_DATA.match(linha.fatia(*COL_DATA)):
            m_secao = RE_SECAO.match(texto)
            if m_secao and not m_secao.group(2)[0].isdigit():
                if total_atual is not None:
                    resultado.totais.append(total_atual)
                secao_codigo = m_secao.group(1)
                secao_nome = limpar(m_secao.group(2)).upper()
                total_atual = TotalSecao(secao_nome, 0, Decimal("0"))
                continue

        # --- linha de lancamento -------------------------------------------
        lancto = linha.fatia(*COL_LANCTO)
        data_txt = linha.fatia(*COL_DATA)
        if not lancto.isdigit() or not RE_DATA.match(data_txt):
            continue

        valor = moeda(linha.fatia(*COL_VALOR))
        if valor is None:
            resultado.avisos.append(
                "Linha sem valor legivel (pag. %d): %s" % (linha.pagina + 1, texto[:80])
            )
            continue

        lanc = Lancamento(
            origem=resultado.arquivo,
            caixa=resultado.caixa,
            secao_codigo=secao_codigo,
            secao=secao_nome,
            lancto=lancto,
            data=data_br(data_txt),
            historico=linha.fatia(*COL_HISTORICO),
            valor=valor,
            sinal=linha.fatia(*COL_SINAL) or "+",
            num_doc=linha.fatia(*COL_NUMDOC),
            responsavel=linha.fatia(*COL_RESP),
            usuario=linha.fatia(*COL_USUARIO),
            pagina=linha.pagina + 1,
        )
        _interpretar_historico(lanc)
        resultado.lancamentos.append(lanc)
        if total_atual is not None:
            total_atual.qtde_lida += 1
            total_atual.valor_lido += valor

    if total_atual is not None:
        resultado.totais.append(total_atual)

    for t in resultado.divergencias:
        resultado.avisos.append(
            "Secao %s: o relatorio informa %d lancamentos (%s), foram lidos %d (%s)."
            % (t.secao, t.qtde_informada, t.valor_informado, t.qtde_lida, t.valor_lido)
        )
    return resultado
