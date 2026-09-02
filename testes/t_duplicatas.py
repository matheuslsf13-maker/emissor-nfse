# -*- coding: utf-8 -*-
"""Mede as duplicatas do cadastro do TechCare, sem achismo.

Serve para decidir com dados o que a base pode fundir com segurança.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from apoio import BASE_DADOS, CLIENTES, exigir_dados_reais

exigir_dados_reais("t_duplicatas")
from nfse import config as cfgmod
from nfse.documentos import documento_valido
from nfse.leitor_clientes import ler_clientes_cache
from nfse.util import so_digitos

cad = ler_clientes_cache(os.path.join(BASE_DADOS, CLIENTES), cfgmod.PASTA_CACHE)
total = len(cad.clientes)
print("cadastros lidos: %d" % total)

# --- 1. grupos por documento valido ------------------------------------
por_doc = defaultdict(list)
for c in cad.clientes:
    d = so_digitos(c.documento)
    if documento_valido(d):
        por_doc[d].append(c)

grupos_doc = {d: l for d, l in por_doc.items() if len(l) > 1}
extras_doc = sum(len(l) - 1 for l in grupos_doc.values())
print("\n1. Mesmo CPF/CNPJ valido em mais de um cadastro")
print("   grupos: %d   cadastros a mais: %d" % (len(grupos_doc), extras_doc))
nomes_iguais = sum(1 for l in grupos_doc.values() if len({c.chave for c in l}) == 1)
print("   com nome identico (duplicata pura): %d" % nomes_iguais)
print("   com nomes diferentes:               %d" % (len(grupos_doc) - nomes_iguais))
for d, l in list(grupos_doc.items())[:5]:
    nomes = sorted({c.nome for c in l})
    print("      %s -> %s" % (l[0].documento_formatado, " | ".join(n[:34] for n in nomes)))

# --- 2. grupos por nome + nascimento, ignorando os ja unidos por doc ----
ja_unido = set()
for l in grupos_doc.values():
    for c in l[1:]:
        ja_unido.add(id(c))

por_pessoa = defaultdict(list)
for c in cad.clientes:
    if id(c) in ja_unido:
        continue
    if c.chave:
        por_pessoa["%s|%s" % (c.chave, c.nascimento or "")].append(c)

grupos_pes = {k: l for k, l in por_pessoa.items() if len(l) > 1}
extras_pes = sum(len(l) - 1 for l in grupos_pes.values())
print("\n2. Mesmo nome + nascimento (fora os ja unidos pelo documento)")
print("   grupos: %d   cadastros a mais: %d" % (len(grupos_pes), extras_pes))

ambos_validos = 0
um_invalido = 0
for l in grupos_pes.values():
    docs = [so_digitos(c.documento) for c in l]
    validos = [d for d in docs if documento_valido(d)]
    if len(set(validos)) > 1:
        ambos_validos += 1
    else:
        um_invalido += 1
print("   com DOIS CPFs validos e diferentes: %d  <- NAO devem ser fundidos" % ambos_validos)
print("   com no maximo um CPF valido:        %d  <- podem ser fundidos" % um_invalido)

for k, l in list(grupos_pes.items())[:6]:
    print("      %s" % l[0].nome[:44])
    for c in l:
        print("         %-16s valido=%-5s %s, %s" % (
            c.documento_formatado, c.documento_ok, c.logradouro[:24], c.numero))

print("\n3. Conclusao")
esperado = total - extras_doc - (extras_pes if not ambos_validos else 0)
print("   cadastros lidos               : %d" % total)
print("   fundir duplicatas por documento: -%d" % extras_doc)
print("   fundir por nome+nascimento     : -%d" % extras_pes)
print("   base final esperada            : %d" % (total - extras_doc - extras_pes))
