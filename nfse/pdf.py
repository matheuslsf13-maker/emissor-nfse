# -*- coding: utf-8 -*-
"""Extracao de texto do PDF preservando as colunas.

Por que nao `pdftotext -layout`: os relatorios do TechCare tem colunas cujo
alinhamento vertical varia alguns pontos por linha. O modo layout mistura
celulas de linhas vizinhas -- o valor de um lancamento aparece grudado no
nome de outro. Lendo as palavras com coordenadas e agrupando por `top`,
cada linha do relatorio volta intacta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterator

import pdfplumber

from .util import limpar


@dataclass
class Palavra:
    texto: str
    x0: float
    x1: float
    topo: float


@dataclass
class Linha:
    """Uma linha visual do relatorio, com as palavras ordenadas por x."""

    pagina: int
    topo: float
    palavras: list[Palavra] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return limpar(" ".join(p.texto for p in self.palavras))

    @property
    def x0(self) -> float:
        return self.palavras[0].x0 if self.palavras else 0.0

    def fatia(self, x_min: float, x_max: float) -> str:
        """Texto das palavras cujo inicio cai na faixa [x_min, x_max)."""
        return limpar(
            " ".join(p.texto for p in self.palavras if x_min <= p.x0 < x_max)
        )


def ler_linhas(
    caminho: str,
    tolerancia_y: float = 3.0,
    progresso: Callable[[int, int], None] | None = None,
) -> Iterator[Linha]:
    """Percorre o PDF devolvendo uma `Linha` por linha visual."""
    with pdfplumber.open(caminho) as pdf:
        total = len(pdf.pages)
        for indice, pagina in enumerate(pdf.pages):
            palavras = pagina.extract_words(
                x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False
            )
            grupos: dict[int, list[Palavra]] = {}
            for w in palavras:
                chave = int(round(w["top"] / tolerancia_y))
                grupos.setdefault(chave, []).append(
                    Palavra(w["text"], w["x0"], w["x1"], w["top"])
                )
            for chave in sorted(grupos):
                itens = sorted(grupos[chave], key=lambda p: p.x0)
                yield Linha(indice, chave * tolerancia_y, itens)
            pagina.flush_cache()
            pagina.get_textmap.cache_clear()
            if progresso:
                progresso(indice + 1, total)


def contar_paginas(caminho: str) -> int:
    with pdfplumber.open(caminho) as pdf:
        return len(pdf.pages)
