# -*- coding: utf-8 -*-
"""Gera os XMLs de agosto/2026 e valida a assinatura com um certificado de teste.

O certificado autoassinado criado aqui serve so para provar que o caminho
de assinatura funciona. O certificado real (A1 da clinica) entra em
config/certificados/.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from lxml import etree

from apoio import carregar_tudo, certificado_de_teste, exigir_dados_reais

exigir_dados_reais("t_emissao")
from nfse import config as cfgmod
from nfse.assinatura import assinar, carregar_pfx, conferir
from nfse.emissao import emitir
from nfse.gerador_dps import ID_INFNFSE, gerar_nfse, id_dps
from nfse.util import brl

cfg, caixas, cad, r = carregar_tudo()
unidade = r.unidade

print("== 1. emissao em modo teste (sem certificado configurado)")
saida = emitir(r, cfg, simular=True)
print("   geradas: %d   total R$ %s" % (len(saida.geradas), brl(saida.valor_total)))
print("   erros  : %d" % len(saida.erros))
for e in saida.erros[:5]:
    print("      ", e)
print("   aviso  :", saida.aviso_certificado[:110])
print("   pasta  :", os.path.relpath(saida.pasta))

print("\n== 2. XML de uma nota")
nota = r.notas[0]
xml = gerar_nfse(nota, cfg.unidade(unidade), cfg, 1)
texto = xml.decode("utf-8")
print("   tamanho:", len(xml), "bytes")
print("   xmlns vazio presente?", 'xmlns=""' in texto)
print("   Id infDPS:", id_dps(cfg.municipio["codigo_ibge"],
                              cfg.unidade(unidade)["cnpj"], "00001", 1),
      "(%d chars)" % len(id_dps(cfg.municipio["codigo_ibge"],
                                cfg.unidade(unidade)["cnpj"], "00001", 1)))
print("   Id infNFSe: %d chars" % len(ID_INFNFSE))
raiz = etree.fromstring(xml)


def mostrar(elemento, nivel=0, limite=60):
    if mostrar.contador > limite:
        return
    tag = etree.QName(elemento).localname
    valor = (elemento.text or "").strip()
    print("      " + "  " * nivel + tag + (": " + valor if valor else ""))
    mostrar.contador += 1
    for filho in elemento:
        mostrar(filho, nivel + 1, limite)


mostrar.contador = 0
mostrar(raiz)

print("\n== 3. assinatura com certificado de teste")
with tempfile.TemporaryDirectory() as tmp:
    pfx = certificado_de_teste(os.path.join(tmp, "teste.pfx"))
    cert = carregar_pfx(pfx, "teste123")
    print("   titular:", cert.titular)
    print("   vencido:", cert.vencido)
    assinado = assinar(xml, ID_INFNFSE, cert)
    print("   bytes assinados:", len(assinado))
    print("   conferencia:", conferir(assinado))

    print("\n== 4. adulterar o XML deve invalidar a assinatura")
    valor_original = b"<vServ>%s</vServ>" % nota.valor.encode()
    adulterado = assinado.replace(valor_original, b"<vServ>9999.00</vServ>", 1)
    assert adulterado != assinado, "o teste nao conseguiu adulterar o XML"
    print("   valor trocado, assinatura ainda valida?",
          conferir(adulterado).get("valida"))

    print("\n== 5. espaco a mais fora de tag tambem invalida")
    quebrado = assinado.replace(b"</toma>", b"</toma>\n  ", 1)
    print("   assinatura ainda valida?", conferir(quebrado).get("valida"))
