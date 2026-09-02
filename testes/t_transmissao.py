# -*- coding: utf-8 -*-
"""Testa a transmissao inteira contra um servidor local que imita a prefeitura.

Nada sai para a prefeitura de verdade: o teste sobe um servidor em 127.0.0.1
que devolve respostas parecidas com as do WebService (uma aceita, uma
recusada) e aponta a configuracao para ele.

Cobre: montagem do envelope, leitura do <return>, gravacao do numero
devolvido no controle, e a trava que impede reenviar o que ja foi aceito.
"""
import http.server
import json
import os
import shutil
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from apoio import carregar_tudo, certificado_de_teste, exigir_dados_reais

exigir_dados_reais("t_transmissao")
from nfse import config as cfgmod
from nfse.controle import Controle
from nfse.emissao import emitir
from nfse.envio import interpretar_retorno, montar_envelope
from nfse.transmissao import ambiente_do_xml, listar_xmls, transmitir

ACEITA = """<?xml version="1.0"?><S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
<S:Body><ns2:NotaFiscalNacionalGerarResponse xmlns:ns2="http://webservices.sil.com/">
<return>&lt;retorno&gt;&lt;cStat&gt;100&lt;/cStat&gt;&lt;nNFSe&gt;9001&lt;/nNFSe&gt;&lt;cVerif&gt;A1B2C3&lt;/cVerif&gt;&lt;/retorno&gt;</return>
</ns2:NotaFiscalNacionalGerarResponse></S:Body></S:Envelope>"""

RECUSADA = """<?xml version="1.0"?><S:Envelope xmlns:S="http://schemas.xmlsoap.org/soap/envelope/">
<S:Body><ns2:NotaFiscalNacionalGerarResponse xmlns:ns2="http://webservices.sil.com/">
<return>&lt;retorno&gt;&lt;cStat&gt;E1235&lt;/cStat&gt;&lt;Mensagem&gt;Falha no esquema XML&lt;/Mensagem&gt;&lt;/retorno&gt;</return>
</ns2:NotaFiscalNacionalGerarResponse></S:Body></S:Envelope>"""

recebidos = []


class Prefeitura(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        recebidos.append(self.rfile.read(tamanho).decode("utf-8"))
        corpo = (ACEITA if len(recebidos) % 2 == 1 else RECUSADA).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


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


print("1. Envelope SOAP")
env = montar_envelope(b'<?xml version="1.0"?><NFSe><a/></NFSe>').decode()
checar("operacao correta", "<sil:NotaFiscalNacionalGerar" in env, env[:200])
checar("namespace da SIL por prefixo",
       'xmlns:sil="http://webservices.sil.com/"' in env, env[:200])
# O XSD do servico nao declara elementFormDefault, entao os filhos sao
# unqualified: <xml> NAO pode herdar o namespace da SIL. Com namespace
# default a prefeitura recebe o parametro vazio e responde
# "XML invalido: Fim prematuro do arquivo".
checar("<xml> fica sem namespace (unqualified)",
       "<xml>&lt;NFSe&gt;" in env
       and 'xmlns="http://webservices.sil.com/"' not in env, env[:200])
checar("sem usuario/senha (o servico nao pede)",
       "<usuario>" not in env and "<hashSenha>" not in env)

print("\n2. Leitura do retorno")
aceito = interpretar_retorno(
    "&lt;retorno&gt;&lt;cStat&gt;100&lt;/cStat&gt;&lt;nNFSe&gt;9001&lt;/nNFSe&gt;"
    "&lt;cVerif&gt;A1B2C3&lt;/cVerif&gt;&lt;/retorno&gt;")
checar("reconhece nota aceita", aceito["aceita"], str(aceito))
checar("extrai o numero da nota", aceito["numero"] == "9001", aceito["numero"])
checar("extrai o codigo de verificacao", aceito["codigo_verificacao"] == "A1B2C3")
recusado = interpretar_retorno(
    "&lt;retorno&gt;&lt;Mensagem&gt;Falha no esquema XML&lt;/Mensagem&gt;&lt;/retorno&gt;")
checar("reconhece recusa", not recusado["aceita"] and recusado["parece_erro"])
checar("mostra a mensagem da prefeitura",
       recusado["mensagem"] == "Falha no esquema XML", recusado["mensagem"])
checar("guarda sempre o texto cru", bool(recusado["bruto"]))

print("\n3. Transmissao ponta a ponta (servidor local)")
servidor = http.server.HTTPServer(("127.0.0.1", 0), Prefeitura)
porta = servidor.server_address[1]
threading.Thread(target=servidor.serve_forever, daemon=True).start()

# dados/ propria: o teste nunca encosta no controle.db real. Antes ele fazia
# backup e restaurava, mas se o teardown falhasse (e falhou uma vez, por causa
# do arquivo SQLite aberto), as notas do teste ficavam registradas como se
# fossem reais -- e a proxima emissao de verdade comecaria no numero errado.
import tempfile
PASTA_DADOS_REAL = cfgmod.PASTA_DADOS
cfgmod.PASTA_DADOS = tempfile.mkdtemp(prefix="nfse-dados-")
CONTROLE = os.path.join(cfgmod.PASTA_DADOS, "controle.db")

cfg, caixas, cad, r = carregar_tudo()
pasta = os.path.join(cfgmod.PASTA_SAIDA, "_teste-transmissao")
shutil.rmtree(pasta, ignore_errors=True)

# Pasta de certificados propria: o teste nao encosta nos certificados reais.
import tempfile
pasta_certs_real = cfgmod.PASTA_CERTIFICADOS
senha_real = os.environ.get("CERT_SENHA_GLORIA")
cfgmod.PASTA_CERTIFICADOS = tempfile.mkdtemp(prefix="nfse-certs-")

try:
    certificado_de_teste(os.path.join(cfgmod.PASTA_CERTIFICADOS, "gloria.pfx"))
    os.environ["CERT_SENHA_GLORIA"] = "teste123"

    cfg.municipio["endpoints"]["homologacao"] = "http://127.0.0.1:%d/services" % porta
    cfg.faturamento["ambiente"] = "homologacao"

    # gera 4 notas valendo, so para ter arquivos assinados
    r.notas = r.notas[:4]
    saida = emitir(r, cfg, simular=False, pasta_saida=pasta)
    checar("4 notas geradas e assinadas",
           len(saida.geradas) == 4 and all(n.assinada for n in saida.geradas))

    t1 = transmitir(pasta, cfg, limite=1)
    checar("com limite=1, manda uma nota so", len(t1.enviadas) == 1)
    checar("as outras ficam esperando", t1.nao_enviadas == 3, str(t1.nao_enviadas))
    checar("a primeira foi aceita", len(t1.aceitas) == 1)
    checar("numero devolvido pela prefeitura foi lido",
           t1.enviadas[0].numero_nota == "9001", t1.enviadas[0].numero_nota)
    checar("o servidor recebeu o envelope certo",
           recebidos and "NotaFiscalNacionalGerar" in recebidos[0])
    checar("a assinatura foi junto, intacta",
           "&lt;ds:Signature" in recebidos[0] or "Signature" in recebidos[0])

    with Controle(CONTROLE) as controle:
        transmitidas = controle.resumo()["transmitidas"]
    checar("controle gravou a transmissao", transmitidas == 1, str(transmitidas))

    t2 = transmitir(pasta, cfg)
    checar("a ja aceita nao e reenviada", len(t2.puladas) == 1, str(len(t2.puladas)))
    checar("as 3 restantes foram enviadas", len(t2.enviadas) == 3)
    checar("recusa e reportada, nao engolida", len(t2.recusadas) >= 1)
    recusada = t2.recusadas[0]
    checar("mensagem da recusa aparece",
           "esquema" in (recusada.mensagem or "").lower(), recusada.mensagem)

    t3 = transmitir(pasta, cfg)
    checar("recusada pode ser reenviada", len(t3.enviadas) >= 1)

    # O ambiente e escolhido na GERACAO e fica assinado dentro do XML. Mandar
    # nota de homologacao para a URL de producao tem que ser barrado aqui,
    # antes de sair da maquina -- foi o buraco que a tela de transmissao abria
    # ao deixar escolher o destino na hora do envio.
    with open(os.path.join(pasta, listar_xmls(pasta)[0]), "rb") as fh:
        checar("XML carrega o ambiente em que foi gerado",
               ambiente_do_xml(fh.read()) == "homologacao")

    cfg.faturamento["ambiente"] = "producao"
    cfg.municipio["endpoints"]["producao"] = "http://127.0.0.1:%d/services" % porta
    antes = len(recebidos)
    t4 = transmitir(pasta, cfg, limite=1)
    checar("nota de homologacao nao e transmitida para producao",
           len(t4.aceitas) == 0 and len(t4.recusadas) == 1, str(t4.recusadas))
    checar("e o bloqueio acontece antes de sair da maquina",
           len(recebidos) == antes, "o servidor recebeu mesmo assim")
    checar("o motivo explica o que fazer",
           "gere as notas de novo" in (t4.recusadas[0].erro or "").lower(),
           t4.recusadas[0].erro)
    cfg.faturamento["ambiente"] = "homologacao"

    checar("log de transmissao gravado",
           os.path.exists(os.path.join(pasta, "TRANSMISSAO.txt")))
finally:
    servidor.shutdown()
    shutil.rmtree(cfgmod.PASTA_CERTIFICADOS, ignore_errors=True)
    cfgmod.PASTA_CERTIFICADOS = pasta_certs_real
    if senha_real is None:
        os.environ.pop("CERT_SENHA_GLORIA", None)
    else:
        os.environ["CERT_SENHA_GLORIA"] = senha_real
    shutil.rmtree(pasta, ignore_errors=True)
    shutil.rmtree(cfgmod.PASTA_DADOS, ignore_errors=True)
    cfgmod.PASTA_DADOS = PASTA_DADOS_REAL

print("\n" + "=" * 62)
if falhas:
    print("%d verificacao(oes) FALHARAM:" % len(falhas))
    for f in falhas:
        print("   - %s" % f)
    sys.exit(1)
print("Tudo certo: %d verificacoes passaram." % passou)
