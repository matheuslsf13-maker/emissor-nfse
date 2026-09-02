# -*- coding: utf-8 -*-
"""Normalizacao de texto, numeros e datas.

O relatorio do TechCare vem de um PDF com fonte de codificacao imperfeita:
acentos aparecem como caracteres de substituicao. Todo cruzamento por nome
usa `chave_nome`, que remove acentos e ruido, de forma que "ANGELICA" e
"ANGELICA" (com acento perdido) caiam na mesma chave.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# Caracteres que o extrator de PDF produz quando nao consegue mapear o glifo.
_RUIDO = "\ufffd\u00a0"


def limpar(texto: str) -> str:
    """Colapsa espacos e remove caracteres de controle."""
    if not texto:
        return ""
    texto = texto.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", texto).strip()


def sem_acento(texto: str) -> str:
    """Remove acentos preservando as letras base."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def chave_nome(nome: str) -> str:
    """Chave canonica para cruzar nomes entre relatorios diferentes.

    Maiusculas, sem acento, sem pontuacao, espacos colapsados. Caracteres
    de substituicao viram espaco (o PDF perde acentos de forma inconsistente,
    entao 'NERCI BULI?O' e 'NERCI BULIAO' precisam bater no prefixo).
    """
    texto = limpar(nome).upper()
    for c in _RUIDO:
        texto = texto.replace(c, " ")
    texto = sem_acento(texto)
    texto = re.sub(r"[^A-Z0-9 ]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def moeda(texto: str) -> Decimal | None:
    """Converte '1,234.56' ou '1.234,56' em Decimal.

    O TechCare emite no formato americano (virgula de milhar, ponto decimal).
    Aceitamos os dois para nao quebrar se a configuracao do sistema mudar.
    """
    if texto is None:
        return None
    t = limpar(str(texto)).replace(" ", "")
    if not t:
        return None
    t = re.sub(r"[^0-9,.\-]", "", t)
    if not t:
        return None
    if "," in t and "." in t:
        # o separador decimal e o que aparece por ultimo
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # so virgula: decimal brasileiro, salvo quando ha 3 digitos depois
        inteiro, _, frac = t.rpartition(",")
        t = t.replace(",", "") if len(frac) == 3 and inteiro else t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


def brl(valor) -> str:
    """Formata para exibicao: 1234.5 -> '1.234,50'."""
    if valor is None:
        return "-"
    inteiro = f"{Decimal(valor):,.2f}"
    return inteiro.replace(",", "@").replace(".", ",").replace("@", ".")


def data_br(texto: str) -> date | None:
    """Converte 'dd/mm/aaaa' ou 'dd/mm/aa' em date."""
    t = limpar(texto)
    m = re.match(r"^(\d{2})/(\d{2})/(\d{2,4})$", t)
    if not m:
        return None
    d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")
