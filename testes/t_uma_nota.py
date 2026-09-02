# -*- coding: utf-8 -*-
"""Emite UMA nota valendo, para o primeiro teste real.

    python testes/t_uma_nota.py <pasta com os PDFs de agosto> [unidade]

Consome numeracao de verdade. Mostra o XML assinado inteiro, para conferir
campo por campo antes de transmitir. NAO transmite nada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import etree

from nfse import base_clientes
from nfse import config as cfgmod
from nfse.assinatura import conferir
from nfse.conciliacao import conciliar
from nfse.controle import Controle
from nfse.emissao import emitir
from nfse.leitor_caixa import ler_caixa
from nfse.util import brl

PASTA = sys.argv[1]
UNIDADE = sys.argv[2] if len(sys.argv) > 2 else "gloria"

CAIXAS = {
    "gloria": ["Relatório NF Glória clinico agosto 2026.PDF",
               "Relatório NF Glória contrato agosto 2026.PDF"],
    "cobilandia": ["Relatório NF Cobi clinico agosto 2026.PDF",
                   "Relatório NF Cobi contrato agosto 2026.PDF"],
}

cfg = cfgmod.carregar()
caixas = [ler_caixa(os.path.join(PASTA, f)) for f in CAIXAS[UNIDADE]]
base = base_clientes.abrir(cfgmod.PASTA_DADOS, UNIDADE)
r = conciliar(caixas, base.como_cadastro(), cfg, UNIDADE)

print("Conciliacao: %d notas previstas, R$ %s" % (len(r.notas), brl(r.valor_total)))

controle = Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db"))
print("Numeracao antes: ultimo numero usado = %d"
      % controle.ultimo_numero(UNIDADE))
controle.fechar()

# A escolhida: a primeira da lista, que e a mais simples de conferir.
escolhida = r.notas[0]
print()
print("Nota escolhida para o teste:")
print("   paciente : %s" % escolhida.tomador["nome"])
print("   CPF      : %s" % escolhida.tomador["documento"])
print("   data     : %s" % escolhida.data)
print("   valor    : R$ %s" % brl(escolhida.valor))
print("   secao    : %s" % escolhida.secao)
print("   lancto   : %s (caixa %s)" % (escolhida.lancto, escolhida.caixa))

saida = emitir(r, cfg, simular=False, apenas={escolhida.id})
print()
print("Resultado da emissao:")
print("   geradas  : %d" % len(saida.geradas))
print("   erros    : %d" % len(saida.erros))
for e in saida.erros:
    print("      %s" % e)
if not saida.geradas:
    print("   (nada gerado — pode ja ter sido emitida antes)")
    for p in saida.puladas:
        print("      pulada: %s" % p["motivo"])
    sys.exit(0)

nota = saida.geradas[0]
print("   numero DPS: %d" % nota.numero)
print("   arquivo   : %s" % nota.arquivo)
print("   assinada  : %s" % nota.assinada)
print("   pasta     : %s" % os.path.relpath(saida.pasta))

caminho = os.path.join(saida.pasta, nota.arquivo)
xml = open(caminho, "rb").read()
print()
print("Conferencia da assinatura: %s" % conferir(xml))

print()
print("=" * 70)
print("XML QUE SERA ENVIADO A PREFEITURA")
print("=" * 70)
arvore = etree.fromstring(xml)
bonito = etree.tostring(arvore, pretty_print=True, encoding="unicode")
import re
bonito = re.sub(r"(<ds:X509Certificate>)[^<]{60,}", r"\1…(certificado)…", bonito)
bonito = re.sub(r"(<ds:SignatureValue>)[^<]{60,}", r"\1…(assinatura)…", bonito)
print(bonito)

controle = Controle(os.path.join(cfgmod.PASTA_DADOS, "controle.db"))
print("Numeracao depois: ultimo numero usado = %d"
      % controle.ultimo_numero(UNIDADE))
print("Registradas no controle: %d" % controle.resumo()["emitidas"])
controle.fechar()
print()
print("NADA FOI TRANSMITIDO. O XML esta pronto na pasta acima.")
