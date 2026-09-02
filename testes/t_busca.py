# -*- coding: utf-8 -*-
"""Busca solta no cadastro, para investigar pendencias."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nfse import config as cfgmod
from nfse.leitor_clientes import ler_clientes_cache
from nfse.util import chave_nome

cad = ler_clientes_cache(os.path.join(BASE_DADOS, CLIENTES),
                         cfgmod.PASTA_CACHE)

for termo in sys.argv[1:]:
    alvo = chave_nome(termo)
    print("=== %s" % alvo)
    achados = [c for c in cad.clientes if alvo in c.chave or c.chave in alvo]
    if not achados:
        # tenta por sobreposicao de palavras
        palavras = set(alvo.split())
        pontuados = []
        for c in cad.clientes:
            comuns = palavras & set(c.chave.split())
            if len(comuns) >= max(2, len(palavras) - 2):
                pontuados.append((len(comuns), c))
        pontuados.sort(key=lambda x: -x[0])
        achados = [c for _, c in pontuados[:8]]
    for c in achados[:10]:
        print("   %-46s %s valido=%s  %s/%s" % (c.nome, c.documento_formatado,
                                                c.documento_ok, c.cidade, c.uf))
