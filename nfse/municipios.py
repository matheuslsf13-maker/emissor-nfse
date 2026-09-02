# -*- coding: utf-8 -*-
"""Codigo IBGE do municipio do tomador.

O cadastro do TechCare guarda cidade e UF em texto livre. A NFS-e exige o
codigo IBGE de 7 digitos. Tomadores de fora de Vila Velha (convenios ficam
em Sao Paulo, pacientes moram em Cariacica, Serra, Linhares) precisam do
codigo do municipio *deles* -- usar o do emitente distorce a apuracao.

A tabela vem da API de localidades do IBGE e esta congelada em
`dados/municipios_ibge.json` para o sistema funcionar sem internet.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache

from .util import chave_nome

_ARQUIVO = os.path.join(os.path.dirname(__file__), "dados", "municipios_ibge.json")

# Grafias que o cadastro usa e que nao batem com o nome oficial do IBGE.
APELIDOS = {
    "SAO PAULO SP": "3550308",
    "VILA VELHA ES": "3205200",
}


@lru_cache(maxsize=1)
def _tabela():
    """Devolve (por_uf_nome, por_nome, por_codigo)."""
    with open(_ARQUIVO, encoding="utf-8") as fh:
        bruto = json.load(fh)
    por_uf_nome: dict = {}
    por_nome: dict = {}
    por_codigo: dict = {}
    for codigo, uf, nome in bruto:
        chave = chave_nome(nome)
        por_uf_nome["%s|%s" % (uf.upper(), chave)] = codigo
        por_nome.setdefault(chave, []).append((codigo, uf, nome))
        por_codigo[codigo] = (nome, uf)
    return por_uf_nome, por_nome, por_codigo


def codigo_ibge(cidade: str, uf: str = ""):
    """Devolve o codigo IBGE, ou None quando nao da para decidir com certeza.

    Nunca chuta: se o nome existir em mais de uma UF e a UF nao foi
    informada, devolve None para o lancamento ser bloqueado e revisado.
    """
    if not cidade:
        return None
    chave = chave_nome(cidade)
    uf = (uf or "").strip().upper()

    apelido = APELIDOS.get("%s %s" % (chave, uf) if uf else chave)
    if apelido:
        return apelido

    por_uf_nome, por_nome, _ = _tabela()
    if uf:
        achado = por_uf_nome.get("%s|%s" % (uf, chave))
        if achado:
            return achado
    candidatos = por_nome.get(chave, [])
    if len(candidatos) == 1:
        return candidatos[0][0]
    return None


@lru_cache(maxsize=32)
def _por_uf(uf: str):
    with open(_ARQUIVO, encoding="utf-8") as fh:
        bruto = json.load(fh)
    return tuple((c, n) for c, u, n in bruto if u.upper() == uf)


@lru_cache(maxsize=4096)
def codigo_ibge_aproximado(cidade: str, uf: str = "", corte: float = 0.86):
    """Tenta resolver erros de digitacao do cadastro ("VILA VLEHA").

    Devolve (codigo, nome_oficial) apenas quando ha um unico candidato
    claramente melhor que os demais dentro da UF. A correcao nunca e
    silenciosa: quem chama registra o ajuste para aparecer na conferencia.
    """
    import difflib

    if not cidade or not uf:
        return None
    alvo = chave_nome(cidade)
    if not alvo:
        return None
    candidatos = _por_uf(uf.upper())
    if not candidatos:
        return None
    notas = [
        (difflib.SequenceMatcher(None, alvo, chave_nome(n)).ratio(), c, n)
        for c, n in candidatos
    ]
    notas.sort(reverse=True)
    melhor = notas[0]
    segundo = notas[1] if len(notas) > 1 else (0.0, "", "")
    if melhor[0] >= corte and melhor[0] - segundo[0] >= 0.05:
        return melhor[1], melhor[2]
    return None


def nome_por_codigo(codigo: str):
    _, _, por_codigo = _tabela()
    achado = por_codigo.get(str(codigo))
    return achado[0] if achado else None


def descrever(codigo: str) -> str:
    _, _, por_codigo = _tabela()
    achado = por_codigo.get(str(codigo))
    return "%s/%s" % (achado[0], achado[1]) if achado else str(codigo)
