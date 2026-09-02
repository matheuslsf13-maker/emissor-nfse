# -*- coding: utf-8 -*-
"""Inspeciona a geometria do relatorio de clientes numa amostra de paginas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pdfplumber

CAM = os.path.join(BASE_DADOS, CLIENTES)

with pdfplumber.open(CAM) as pdf:
    total = len(pdf.pages)
    print("paginas:", total)
    for i in (0, 400, 900, 1400, total - 1):
        page = pdf.pages[i]
        rows = {}
        for w in page.extract_words(x_tolerance=1.5, y_tolerance=2):
            rows.setdefault(int(round(w["top"] / 3)), []).append(w)
        print("--- pagina", i, "---")
        for k in sorted(rows)[:14]:
            ws = sorted(rows[k], key=lambda w: w["x0"])
            print("   " + "  ".join("%s@%d" % (w["text"], w["x0"]) for w in ws))
        page.flush_cache()
