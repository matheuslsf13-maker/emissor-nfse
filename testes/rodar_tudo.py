# -*- coding: utf-8 -*-
"""Roda a bateria completa contra os dados reais de agosto/2026 (Gloria).

Serve de rede de seguranca: se alguem mexer no leitor, na conciliacao ou no
gerador e os numeros mudarem, isto acusa na hora.

    python testes/rodar_tudo.py

Os valores esperados vieram da conferencia manual de agosto/2026: 346
lancamentos, 246 notas, R$ 58.864,54, 5 pendencias conhecidas.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from decimal import Decimal

from apoio import BASE_DADOS, CAIXAS, carregar_tudo, certificado_de_teste, exigir_dados_reais

exigir_dados_reais("rodar_tudo")
from nfse import config as cfgmod
from nfse.assinatura import assinar, carregar_pfx, conferir
from nfse.controle import Controle
from nfse.documentos import cpf_valido, cnpj_valido
from nfse.emissao import emitir
from nfse.gerador_dps import ID_INFNFSE, gerar_nfse, id_dps
from nfse.leitor_caixa import ler_caixa
from nfse.municipios import codigo_ibge
from nfse.util import brl, moeda

ESPERADO = {
    "lancamentos": 346,
    "notas": 246,
    "valor": Decimal("58864.54"),
    "pendencias": 5,
}

falhas = []
passou = 0


def checar(descricao, condicao, detalhe=""):
    global passou
    if condicao:
        passou += 1
        print("  [ok]    %s" % descricao)
    else:
        falhas.append(descricao)
        print("  [FALHA] %s   %s" % (descricao, detalhe))


print("1. Utilidades")
checar("CPF valido reconhecido", cpf_valido("162.900.487-16"))
checar("CPF terminado em zeros recusado", not cpf_valido("875.560.000-00"))
checar("CNPJ das duas unidades valido",
       cnpj_valido("11222333000181") and cnpj_valido("12345678000195"))
checar("Vila Velha resolve para 3205200", codigo_ibge("VILA VELHA", "ES") == "3205200")
checar("Valor no formato do TechCare", moeda("58,864.54") == Decimal("58864.54"))

print("\n2. Leitura do caixa (confere com os totais impressos no relatorio)")
total_lidos = 0
for arquivo in CAIXAS:
    caixa = ler_caixa(os.path.join(BASE_DADOS, arquivo))
    total_lidos += len(caixa.lancamentos)
    checar("%s: todas as secoes fecham" % arquivo, not caixa.divergencias,
           "; ".join(t.secao for t in caixa.divergencias))
checar("total de lancamentos = %d" % ESPERADO["lancamentos"],
       total_lidos == ESPERADO["lancamentos"], "lidos %d" % total_lidos)

print("\n3. Conciliacao")
cfg, caixas, cadastro, r = carregar_tudo()
checar("unidade reconhecida pelo cabecalho", r.unidade == "gloria", r.unidade)
checar("competencia 2026-08", r.competencia == "2026-08", r.competencia)
checar("notas previstas = %d" % ESPERADO["notas"],
       len(r.notas) == ESPERADO["notas"], "obtidas %d" % len(r.notas))
checar("valor total = R$ %s" % brl(ESPERADO["valor"]),
       r.valor_total == ESPERADO["valor"], "obtido R$ %s" % brl(r.valor_total))
checar("pendencias = %d" % ESPERADO["pendencias"],
       len(r.pendencias) == ESPERADO["pendencias"],
       "obtidas %d" % len(r.pendencias))
checar("nenhuma nota com CPF/CNPJ invalido",
       all(cpf_valido(n.tomador["documento"]) or cnpj_valido(n.tomador["documento"])
           for n in r.notas))
checar("nenhuma nota sem codigo de municipio",
       all(n.tomador["codigo_municipio"] for n in r.notas))
checar("nenhuma nota sem endereco",
       all(n.tomador["logradouro"] and n.tomador["bairro"] and n.tomador["cep"]
           for n in r.notas))
checar("nenhuma secao com DINHEIRO virou nota",
       not any("DINHEIRO" in n.secao for n in r.notas))
checar("nenhum ENVELOPE virou nota",
       not any("ENVELOPE" in n.secao for n in r.notas))
checar("nenhum convenio virou nota nesta fase",
       not any(n.tipo_faturamento == "convenio" for n in r.notas))
checar("todo lancamento foi classificado",
       len(r.notas) + len(r.pendencias)
       + sum(d["qtde"] for d in r.descartes.values()) == ESPERADO["lancamentos"])

print("\n3b. Base de clientes salva substitui o PDF sem mudar nada")
import tempfile as _tmp

from nfse.base_clientes import BaseClientes

_pasta_base = _tmp.mkdtemp(prefix="nfse-base-")
try:
    _base = BaseClientes(os.path.join(_pasta_base, "g.json"), r.unidade)
    _imp = _base.mesclar(cadastro, origem="CLIENTES.PDF")
    checar("base absorveu o cadastro", _base.total > 0, str(_base.total))
    checar("duplicatas do TechCare foram fundidas",
           _base.total < _imp["lidos"],
           "%d de %d" % (_base.total, _imp["lidos"]))
    _pela_base = conciliar_base = None
    from nfse.conciliacao import conciliar as _conciliar
    _pela_base = _conciliar(caixas, _base.como_cadastro(), cfg, r.unidade)
    checar("mesmo numero de notas pela base",
           len(_pela_base.notas) == len(r.notas),
           "%d vs %d" % (len(_pela_base.notas), len(r.notas)))
    checar("mesmo valor total pela base",
           _pela_base.valor_total == r.valor_total)
    checar("mesmas pendencias pela base",
           len(_pela_base.pendencias) == len(r.pendencias))
    checar("mesmo CPF em todas as notas",
           {n.id: n.tomador["documento"] for n in _pela_base.notas}
           == {n.id: n.tomador["documento"] for n in r.notas})
    _r2 = _base.mesclar(cadastro, origem="CLIENTES.PDF")
    checar("reimportar o mesmo relatorio nao muda nada",
           _r2["novos"] == 0 and _r2["atualizados"] == 0,
           "novos=%d atualizados=%d" % (_r2["novos"], _r2["atualizados"]))
finally:
    shutil.rmtree(_pasta_base, ignore_errors=True)

print("\n4. Geracao do XML")
xml = gerar_nfse(r.notas[0], cfg.unidade("gloria"), cfg, 1)
texto = xml.decode("utf-8")
checar("nenhum elemento fora do namespace (xmlns vazio)", 'xmlns=""' not in texto)
# A unica quebra de linha permitida e a que separa a declaracao do documento;
# ela fica fora do elemento assinado. Qualquer outra invalidaria a assinatura.
corpo = xml.split(b"?>", 1)[1].lstrip(b"\n")
checar("documento sem identacao (identar quebraria a assinatura)",
       b"\n" not in corpo, "%d quebras" % corpo.count(b"\n"))
checar("Id do infDPS com 45 caracteres",
       len(id_dps("3205200", "11222333000181", "00001", 1)) == 45)
checar("Id do infNFSe = NFS + 50 zeros", ID_INFNFSE == "NFS" + "0" * 50)
checar("ISS nao retido (tpRetISSQN = 1)", "<tpRetISSQN>1</tpRetISSQN>" in texto)
checar("nao optante do Simples (opSimpNac = 1)", "<opSimpNac>1</opSimpNac>" in texto)
checar("codigo de tributacao nacional 041201", "<cTribNac>041201</cTribNac>" in texto)
checar("aliquota de 2%", "<pAliqAplic>2.0000</pAliqAplic>" in texto)

print("\n5. Assinatura digital")
pasta_tmp = tempfile.mkdtemp(prefix="nfse-teste-")
try:
    pfx = certificado_de_teste(os.path.join(pasta_tmp, "teste.pfx"))
    cert = carregar_pfx(pfx, "teste123")
    assinado = assinar(xml, ID_INFNFSE, cert)
    resultado = conferir(assinado)
    checar("assinatura confere", resultado.get("valida"), str(resultado))
    checar("algoritmo SHA-256", resultado.get("algoritmo") == "sha256")
    # Vila Velha so aceita canonicalizacao EXCLUSIVA -- comprovado na
    # primeira transmissao real. Com a inclusiva, "Falha na validacao da
    # assinatura" em todas as tentativas.
    checar("canonicalizacao exclusiva",
           resultado.get("canonicalizacao") == "exclusiva",
           str(resultado.get("canonicalizacao")))
    checar("CanonicalizationMethod exc-c14n no XML",
           b"xml-exc-c14n#" in assinado)
    trocado = assinado.replace(b"<vServ>%s</vServ>" % r.notas[0].valor.encode(),
                               b"<vServ>9999.00</vServ>", 1)
    checar("adulterar valor invalida a assinatura",
           trocado != assinado and not conferir(trocado).get("valida"))
    espacado = assinado.replace(b"</toma>", b"</toma>\n ", 1)
    checar("espaco a mais invalida a assinatura",
           not conferir(espacado).get("valida"))

    print("\n6. Emissao completa (numeracao e antiduplicidade)")
    # dados/ propria: nunca mexe no controle.db real.
    pasta_dados_real = cfgmod.PASTA_DADOS
    cfgmod.PASTA_DADOS = os.path.join(pasta_tmp, "dados")
    os.makedirs(cfgmod.PASTA_DADOS, exist_ok=True)
    controle_real = os.path.join(cfgmod.PASTA_DADOS, "controle.db")
    # Aponta a pasta de certificados para um diretorio temporario: o teste
    # nunca toca nos certificados reais da clinica, e funciona igual havendo
    # ou nao certificado instalado.
    pasta_certs_real = cfgmod.PASTA_CERTIFICADOS
    senha_real = os.environ.get("CERT_SENHA_GLORIA")
    cfgmod.PASTA_CERTIFICADOS = os.path.join(pasta_tmp, "certificados")
    os.makedirs(cfgmod.PASTA_CERTIFICADOS, exist_ok=True)
    try:
        shutil.copy2(pfx, os.path.join(cfgmod.PASTA_CERTIFICADOS, "gloria.pfx"))
        os.environ["CERT_SENHA_GLORIA"] = "teste123"

        s1 = emitir(r, cfg, simular=False,
                    pasta_saida=os.path.join(pasta_tmp, "valendo"))
        checar("emitiu as %d notas" % ESPERADO["notas"],
               len(s1.geradas) == ESPERADO["notas"], "%d" % len(s1.geradas))
        checar("todas assinadas e validas",
               all(n.assinada for n in s1.geradas))
        numeros = [n.numero for n in s1.geradas]
        checar("numeracao sequencial de 1 a %d" % ESPERADO["notas"],
               numeros == list(range(1, ESPERADO["notas"] + 1)))
        checar("nenhum numero repetido", len(set(numeros)) == len(numeros))
        checar("nenhum erro na geracao", not s1.erros, str(s1.erros[:2]))

        s2 = emitir(r, cfg, simular=False,
                    pasta_saida=os.path.join(pasta_tmp, "valendo2"))
        checar("rodar de novo nao duplica nenhuma nota", not s2.geradas)
        checar("todas as %d aparecem como ja emitidas" % ESPERADO["notas"],
               len(s2.puladas) == ESPERADO["notas"])
        with Controle(controle_real) as _c:
            checar("numeracao nao avancou",
                   _c.ultimo_numero("gloria") == ESPERADO["notas"])
    finally:
        cfgmod.PASTA_CERTIFICADOS = pasta_certs_real
        if senha_real is None:
            os.environ.pop("CERT_SENHA_GLORIA", None)
        else:
            os.environ["CERT_SENHA_GLORIA"] = senha_real
        cfgmod.PASTA_DADOS = pasta_dados_real
finally:
    shutil.rmtree(pasta_tmp, ignore_errors=True)

print("\n" + "=" * 62)
if falhas:
    print("%d verificacao(oes) FALHARAM:" % len(falhas))
    for f in falhas:
        print("   - %s" % f)
    sys.exit(1)
print("Tudo certo: %d verificacoes passaram." % passou)
