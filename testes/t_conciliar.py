# -*- coding: utf-8 -*-
"""Conciliacao completa com os dados reais de agosto/2026 (Gloria)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nfse import config as cfgmod
from nfse.conciliacao import conciliar
from nfse.leitor_caixa import ler_caixa
from nfse.leitor_clientes import ler_clientes_cache
from nfse.util import brl

BASE = BASE_DADOS

cfg = cfgmod.carregar()
caixas = [ler_caixa(os.path.join(BASE, f)) for f in ("agostoo.PDF", "agostoooooo.PDF")]
cad = ler_clientes_cache(os.path.join(BASE, "CLIENTES.PDF"), cfgmod.PASTA_CACHE)

unidade = cfg.unidade_por_relatorio(caixas[0].empresa)
print("unidade detectada:", unidade)

r = conciliar(caixas, cad, cfg, unidade)
print("periodo %s a %s | competencia %s" % (r.periodo_inicio, r.periodo_fim, r.competencia))
print("lancamentos lidos : %d" % r.total_lancamentos)
print("notas previstas   : %d   R$ %s" % (len(r.notas), brl(r.valor_total)))
print("pendencias        : %d   R$ %s" % (len(r.pendencias), brl(r.valor_pendente)))
print("cobertura         : %.1f%%" % r.cobertura)

print("\nnao geram nota:")
for motivo, d in sorted(r.descartes.items(), key=lambda x: -x[1]["qtde"]):
    print("   %-48s %3d   R$ %s" % (motivo, d["qtde"], brl(d["valor"])))

print("\nnotas por secao:")
for s in r.por_secao():
    print("   %-34s %3d   R$ %s" % (s["secao"], s["qtde"], brl(s["valor"])))

print("\npendencias:")
for p in r.pendencias:
    print("   [%s] %s | %s | %s | R$ %s"
          % (p.motivo, p.titulo, p.nome, p.secao, brl(p.valor)))
    for c in p.candidatos[:4]:
        print("        candidato: %s %s valido=%s" % (c["nome"], c["documento_formatado"], c["valido"]))

ajustadas = [n for n in r.notas if n.ajustes]
print("\najustes automaticos: %d" % len(ajustadas))
for n in ajustadas[:12]:
    print("   %s | %s" % (n.tomador["nome"], "; ".join(n.ajustes)))

print("\navisos:", r.avisos)

print("\nexemplo de nota:")
n = r.notas[0]
print("  ", n.data, n.secao, brl(n.valor_decimal), n.origem_cruzamento)
for k, v in n.tomador.items():
    print("     %-18s %s" % (k, v))
