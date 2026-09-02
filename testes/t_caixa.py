# -*- coding: utf-8 -*-
"""Confere a leitura do caixa contra os totais impressos no proprio relatorio."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nfse.leitor_caixa import ler_caixa
from nfse.util import brl

BASE = BASE_DADOS

for arq in ["agostoo.PDF", "agostoooooo.PDF"]:
    c = ler_caixa(os.path.join(BASE, arq))
    print("=" * 78)
    print("%s | %s | unidade=%s caixa=%s | %s a %s"
          % (c.arquivo, c.empresa, c.unidade, c.caixa, c.periodo_inicio, c.periodo_fim))
    print("lancamentos lidos: %d" % len(c.lancamentos))
    for t in c.totais:
        print("  %-34s informado %3d / %12s   lido %3d / %12s   %s"
              % (t.secao, t.qtde_informada, brl(t.valor_informado),
                 t.qtde_lida, brl(t.valor_lido),
                 "OK" if t.confere else "*** DIVERGE ***"))
    for a in c.avisos:
        print("  AVISO:", a)
    tipos = {}
    for l in c.lancamentos:
        tipos[l.tipo] = tipos.get(l.tipo, 0) + 1
    print("  tipos:", tipos)
    print("  amostra:")
    for l in c.lancamentos[:3]:
        print("    ", l.data, l.secao, "|", l.tipo, "|", l.nome_bruto or l.cpf_historico,
              "|", brl(l.valor), "|", l.sinal, "| contrato", l.contrato)
