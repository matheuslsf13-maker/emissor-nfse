# -*- coding: utf-8 -*-
"""Roda o lote real de agosto/2026 das DUAS unidades (arquivos da Bia).

Uso:  python testes/t_bia.py <pasta com os 6 PDFs>
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nfse import base_clientes
from nfse import config as cfgmod
from nfse.conciliacao import conciliar
from nfse.leitor_caixa import ler_caixa
from nfse.leitor_clientes import ler_clientes_cache
from nfse.util import brl

PASTA = sys.argv[1]

UNIDADES = {
    "gloria": {
        "caixas": ["Relatório NF Glória clinico agosto 2026.PDF",
                   "Relatório NF Glória contrato agosto 2026.PDF"],
        "clientes": "Relação pacientes Glória agosto 2026.PDF",
    },
    "cobilandia": {
        "caixas": ["Relatório NF Cobi clinico agosto 2026.PDF",
                   "Relatório NF Cobi contrato agosto 2026.PDF"],
        "clientes": "Relação pacientes Cobilandia agosto 2026.PDF",
    },
}

cfg = cfgmod.carregar()

for unidade, arquivos in UNIDADES.items():
    print("=" * 74)
    print("  %s" % cfg.unidades[unidade]["apelido"].upper())
    print("=" * 74)

    t = time.time()
    cadastro = ler_clientes_cache(os.path.join(PASTA, arquivos["clientes"]),
                                  cfgmod.PASTA_CACHE)
    print("cadastro lido: %d fichas em %.0fs" % (len(cadastro.clientes),
                                                 time.time() - t))

    base = base_clientes.abrir(cfgmod.PASTA_DADOS, unidade)
    antes = base.total
    imp = base.mesclar(cadastro, origem=arquivos["clientes"])
    print("base de clientes: %d -> %d  (novos %d, atualizados %d, iguais %d)"
          % (antes, base.total, imp["novos"], imp["atualizados"], imp["iguais"]))

    caixas = [ler_caixa(os.path.join(PASTA, f)) for f in arquivos["caixas"]]
    divergentes = [t for c in caixas for t in c.divergencias]
    print("caixas: %d lancamentos | %s" % (
        sum(len(c.lancamentos) for c in caixas),
        "todas as secoes fecham" if not divergentes else "%d DIVERGEM" % len(divergentes)))

    r = conciliar(caixas, base.como_cadastro(), cfg, unidade)
    print()
    print("  periodo        : %s a %s   competencia %s"
          % (r.periodo_inicio, r.periodo_fim, r.competencia))
    print("  VAO VIRAR NOTA : %3d   R$ %12s" % (len(r.notas), brl(r.valor_total)))
    print("  travados       : %3d   R$ %12s" % (len(r.pendencias), brl(r.valor_pendente)))
    print("  cobertura      : %.1f%%" % r.cobertura)
    print()
    print("  nao geram nota:")
    for motivo, d in sorted(r.descartes.items(), key=lambda x: -x[1]["qtde"]):
        print("     %-52s %3d  R$ %10s" % (motivo[:52], d["qtde"], brl(d["valor"])))
    print()
    print("  por secao:")
    for s in r.por_secao():
        print("     %-34s %3d  R$ %10s" % (s["secao"], s["qtde"], brl(s["valor"])))
    if r.pendencias:
        print()
        print("  travados (nao viram nota):")
        for p in r.pendencias:
            print("     [%s] %s | %s | R$ %s"
                  % (p.motivo, p.nome[:40], p.secao, brl(p.valor)))
    ajustes = [n for n in r.notas if n.ajustes]
    if ajustes:
        print()
        print("  ajustes automaticos: %d" % len(ajustes))
        vistos = set()
        for n in ajustes:
            for a in n.ajustes:
                if a not in vistos:
                    vistos.add(a)
                    print("     %s" % a[:110])
    if r.avisos:
        print()
        print("  avisos:")
        for a in r.avisos:
            print("     %s" % a)
    print()
