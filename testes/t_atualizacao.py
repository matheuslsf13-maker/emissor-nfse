# -*- coding: utf-8 -*-
"""Atualizacao remota, do publicar ate o aplicar, com servidor de verdade.

Este e o teste que mais importa para o dia a dia da clinica: se a
atualizacao apagar a numeracao ou o certificado, o estrago e permanente e
ninguem por la vai saber consertar.

O que ele prova, em ordem de gravidade:

1. `dados/`, certificados e senhas NAO sao tocados, nem quando o pacote
   contem esses caminhos de proposito;
2. um pacote corrompido no meio do caminho e recusado ANTES de escrever
   qualquer coisa;
3. a versao anterior fica guardada e da para voltar;
4. `1.10.0` e reconhecida como mais nova que `1.9.0`.
"""

import hashlib
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nfse import config as cfgmod

# O console do Windows costuma vir em cp1252 e derruba o teste ao imprimir
# um caractere que ele nao tem -- e um teste que "falha" por acento esconde
# o resultado de verdade.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

passou = 0
falhas = []


def checar(nome, condicao, detalhe=""):
    global passou
    if condicao:
        passou += 1
        print("  [ok]    %s" % nome)
    else:
        falhas.append(nome)
        print("  [FALHA] %s %s" % (nome, ("-> " + str(detalhe)) if detalhe else ""))


# --------------------------------------------------------------------------
# Uma instalacao de mentira, com a mesma forma da de verdade.
# --------------------------------------------------------------------------
FALSA = tempfile.mkdtemp(prefix="nfse-atu-")
RAIZ_REAL = cfgmod.RAIZ
DADOS_REAL = cfgmod.PASTA_DADOS
CONFIG_REAL = cfgmod.CAMINHO_CONFIG

os.makedirs(os.path.join(FALSA, "nfse"))
os.makedirs(os.path.join(FALSA, "dados", "clientes"))
os.makedirs(os.path.join(FALSA, "config", "certificados"))

with open(os.path.join(FALSA, "VERSAO"), "w") as fh:
    fh.write("1.0.0\n")
with open(os.path.join(FALSA, "app.py"), "w") as fh:
    fh.write("# versao antiga\n")
with open(os.path.join(FALSA, "nfse", "regras.py"), "w") as fh:
    fh.write("# regras antigas\n")
with open(os.path.join(FALSA, "dados", "controle.db"), "wb") as fh:
    fh.write(b"NUMERACAO QUE NAO PODE SUMIR")
with open(os.path.join(FALSA, "dados", "clientes", "gloria.json"), "w") as fh:
    fh.write('{"clientes": "base real"}')
with open(os.path.join(FALSA, "config", "certificados", "gloria.pfx"), "wb") as fh:
    fh.write(b"CERTIFICADO A1")
with open(os.path.join(FALSA, "config", "senhas.bat"), "w") as fh:
    fh.write("set CERT_SENHA_UNIDADE=senha-ficticia\n")
with open(os.path.join(FALSA, "config", "empresas.json"), "w", encoding="utf-8") as fh:
    json.dump({"municipio_emitente": {"nome": "VILA VELHA", "permitir_envio": True},
               "unidades": {"cobilandia": {"endereco": {"bairro": "CONFIRMAR"}}},
               "atualizacao": {"manifesto": ""}}, fh, ensure_ascii=False)

cfgmod.RAIZ = FALSA
cfgmod.PASTA_DADOS = os.path.join(FALSA, "dados")
cfgmod.CAMINHO_CONFIG = os.path.join(FALSA, "config", "empresas.json")

from nfse import atualizacao as atu  # noqa: E402

atu.cfgmod.RAIZ = FALSA
atu.cfgmod.PASTA_DADOS = os.path.join(FALSA, "dados")


# --------------------------------------------------------------------------
print("\n1. Comparacao de versoes")
checar("1.1.0 e mais nova que 1.0.0", atu.ha_novidade("1.0.0", "1.1.0"))
checar("1.10.0 e mais nova que 1.9.0 (nao e texto)",
       atu.ha_novidade("1.9.0", "1.10.0"))
checar("a mesma versao nao e novidade", not atu.ha_novidade("1.2.3", "1.2.3"))
checar("versao mais velha nao e novidade", not atu.ha_novidade("2.0.0", "1.9.9"))
checar("versao com lixo nao quebra", atu.ha_novidade("1.0.0", "v1.2.0-beta"))


# --------------------------------------------------------------------------
print("\n2. Links do Google Drive")
# O link que o Drive oferece ao compartilhar aponta para a PAGINA do arquivo.
# Baixa-lo devolve HTML, e o sistema diria "nao ha atualizacao" sem erro
# nenhum -- falha silenciosa, que e pior do que falhar.
DIRETO = "https://drive.google.com/uc?export=download&id=1AbC-dEfGhIjKlMnOp"
checar("link de compartilhar vira link de download",
       atu.link_direto(
           "https://drive.google.com/file/d/1AbC-dEfGhIjKlMnOp/view?usp=sharing")
       == DIRETO)
checar("link antigo (open?id=) tambem",
       atu.link_direto("https://drive.google.com/open?id=1AbC-dEfGhIjKlMnOp")
       == DIRETO)
checar("link ja direto passa intacto", atu.link_direto(DIRETO) == DIRETO)
checar("URL de outro servidor nao e mexida",
       atu.link_direto("https://github.com/a/b/releases/download/v1/c.zip")
       == "https://github.com/a/b/releases/download/v1/c.zip")
checar("URL vazia nao quebra", atu.link_direto("") == "")
checar("pagina HTML e reconhecida",
       atu._parece_html(b"<!DOCTYPE html>\n<html>"))
checar("zip nao e confundido com HTML",
       not atu._parece_html(b"PK\x03\x04qualquer coisa"))


# --------------------------------------------------------------------------
print("\n3. O que o pacote pode e nao pode escrever")
checar("app.py e aceito", atu._seguro("app.py"))
checar("nfse/regras.py e aceito", atu._seguro("nfse/regras.py"))
checar("web/templates/x.html e aceito", atu._seguro("web/templates/x.html"))
checar("sair da pasta e recusado", not atu._seguro("../fora.py"))
checar("caminho absoluto e recusado", not atu._seguro("/etc/passwd"))
checar("unidade de disco e recusada", not atu._seguro("C:/Windows/x.dll"))
checar("arquivo solto na raiz e recusado", not atu._seguro("virus.exe"))
checar("dados/ e protegido", atu._preservado("dados/controle.db"))
checar("certificados sao protegidos",
       atu._preservado("config/certificados/gloria.pfx"))
checar("senhas.bat e protegido", atu._preservado("config/senhas.bat"))
checar("empresas.json e protegido", atu._preservado("config/empresas.json"))


# --------------------------------------------------------------------------
print("\n4. Servidor publicando uma versao nova")


def montar_pacote(conteudos):
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, texto in conteudos.items():
            z.writestr(nome, texto)
    return memoria.getvalue()


# Um pacote HOSTIL de proposito: alem do codigo novo, tenta sobrescrever a
# numeracao, o certificado, as senhas e escrever fora da pasta.
PACOTE = montar_pacote({
    "app.py": "# versao NOVA\n",
    "nfse/regras.py": "# regras NOVAS\n",
    "VERSAO": "1.1.0\n",
    "dados/controle.db": "NUMERACAO ZERADA PELO PACOTE",
    "dados/clientes/gloria.json": '{"clientes": "apagado"}',
    "config/certificados/gloria.pfx": "CERTIFICADO TROCADO",
    "config/senhas.bat": "set CERT_SENHA_GLORIA=invadido",
    "config/empresas.json": '{"tudo": "sobrescrito"}',
    "../fora.py": "# escapou da pasta\n",
})
SHA = hashlib.sha256(PACOTE).hexdigest()

MANIFESTO = {
    "versao": "1.1.0",
    "publicado_em": "2026-09-01T12:00:00",
    "url": "/emissor-nfse-1.1.0.zip",
    "sha256": SHA,
    "notas": "Corrige o bairro da Cobilândia",
    "novidades": ["Agora dá para buscar paciente por CPF"],
    "correcoes": ["O endereço da Cobilândia estava errado"],
    "config": {"unidades": {"cobilandia": {"endereco": {"bairro": "COBILANDIA"}}}},
}


class Servidor(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/manifesto"):
            corpo = json.dumps(MANIFESTO).encode("utf-8")
            tipo = "application/json"
        elif self.path.endswith(".zip"):
            corpo = PACOTE
            tipo = "application/zip"
        elif self.path.endswith("-quebrado.zip"):
            corpo = PACOTE[:-40]
            tipo = "application/zip"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *args):
        pass


servidor = http.server.HTTPServer(("127.0.0.1", 0), Servidor)
porta = servidor.server_address[1]
threading.Thread(target=servidor.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % porta

MANIFESTO["url"] = base + "/emissor-nfse-1.1.0.zip"

with open(cfgmod.CAMINHO_CONFIG, encoding="utf-8") as fh:
    bruto = json.load(fh)
bruto["atualizacao"]["manifesto"] = base + "/manifesto.json"
with open(cfgmod.CAMINHO_CONFIG, "w", encoding="utf-8") as fh:
    json.dump(bruto, fh, ensure_ascii=False)

try:
    class ConfigFalsa:
        bruto = {"atualizacao": {"manifesto": base + "/manifesto.json"}}

    info = atu.procurar(ConfigFalsa())
    checar("achou a versao publicada", info.get("disponivel") == "1.1.0", info)
    checar("reconheceu que ha novidade", info.get("novidade"), info)
    checar("trouxe as notas da versao",
           "Cobilândia" in info.get("notas", ""), info.get("notas"))
    # Novidade e correcao sao noticias diferentes para quem opera: "ganhei
    # alguma coisa" nao e o mesmo que "consertaram alguma coisa".
    checar("separa o que e novidade", info.get("novidades") == [
        "Agora dá para buscar paciente por CPF"], info.get("novidades"))
    checar("do que e correcao", info.get("correcoes") == [
        "O endereço da Cobilândia estava errado"], info.get("correcoes"))

    # ---------------------------------------------------------------
    print("\n5. Pacote corrompido nao encosta no disco")
    ruim = dict(info)
    ruim["sha256"] = "0" * 64
    antes = open(os.path.join(FALSA, "app.py")).read()
    try:
        atu.aplicar(ruim)
        checar("pacote adulterado e recusado", False, "aplicou mesmo assim")
    except atu.ErroAtualizacao as erro:
        checar("pacote adulterado e recusado com motivo claro",
               "corrompido" in str(erro) or "confere" in str(erro), str(erro))
    checar("e nada foi escrito", open(os.path.join(FALSA, "app.py")).read() == antes)

    # ---------------------------------------------------------------
    print("\n6. Aplicando a versao nova de verdade")
    resultado = atu.aplicar(info)

    checar("app.py foi atualizado",
           open(os.path.join(FALSA, "app.py")).read().strip() == "# versao NOVA")
    checar("nfse/regras.py foi atualizado",
           open(os.path.join(FALSA, "nfse", "regras.py")).read().strip()
           == "# regras NOVAS")
    checar("a versao subiu para 1.1.0", atu.versao_instalada() == "1.1.0")

    # As quatro que importam de verdade
    with open(os.path.join(FALSA, "dados", "controle.db"), "rb") as fh:
        checar("*** a NUMERACAO nao foi tocada ***",
               fh.read() == b"NUMERACAO QUE NAO PODE SUMIR")
    with open(os.path.join(FALSA, "dados", "clientes", "gloria.json")) as fh:
        checar("*** a base de clientes nao foi tocada ***",
               "base real" in fh.read())
    with open(os.path.join(FALSA, "config", "certificados", "gloria.pfx"), "rb") as fh:
        checar("*** o CERTIFICADO nao foi tocado ***", fh.read() == b"CERTIFICADO A1")
    with open(os.path.join(FALSA, "config", "senhas.bat")) as fh:
        checar("*** as SENHAS nao foram tocadas ***", "senha-ficticia" in fh.read())

    checar("o arquivo que tentava sair da pasta foi recusado",
           not os.path.exists(os.path.join(os.path.dirname(FALSA), "fora.py")))
    checar("e a recusa foi registrada no resultado",
           len(resultado["recusados"]) >= 5, resultado["recusados"])

    # ---------------------------------------------------------------
    print("\n7. Configuracao: mescla, nao sobrescreve")
    with open(cfgmod.CAMINHO_CONFIG, encoding="utf-8") as fh:
        depois = json.load(fh)
    checar("o bairro pendente foi corrigido pelo manifesto",
           depois["unidades"]["cobilandia"]["endereco"]["bairro"] == "COBILANDIA",
           depois["unidades"]["cobilandia"])
    checar("e o resto da configuracao continua la",
           depois["municipio_emitente"]["nome"] == "VILA VELHA", depois)
    checar("a mudanca foi relatada em portugues",
           any("bairro" in m for m in resultado["config"]), resultado["config"])

    # Depois de instalar, a pergunta muda de "existe versao nova?" para "o que
    # mudou aqui?" -- e a resposta sumia junto com a tela.
    checar("o resultado traz o resumo do que mudou",
           resultado.get("novidades") and resultado.get("correcoes"),
           (resultado.get("novidades"), resultado.get("correcoes")))
    historico = atu.historico()
    checar("e fica no historico, para consultar dias depois",
           historico and historico[0].get("novidades")
           and historico[0].get("correcoes"), historico[:1])
    checar("o historico diz de qual versao veio",
           historico[0]["de"] == "1.0.0" and historico[0]["para"] == "1.1.0",
           historico[0])

    # ---------------------------------------------------------------
    print("\n8. Da para voltar atras")
    guardadas = atu.versoes_guardadas()
    checar("a versao anterior ficou guardada", len(guardadas) >= 1, guardadas)

    atu.reverter(guardadas[0])
    checar("voltou o app.py antigo",
           open(os.path.join(FALSA, "app.py")).read().strip() == "# versao antiga")
    checar("voltou a versao antiga", atu.versao_instalada() == "1.0.0")
    with open(os.path.join(FALSA, "dados", "controle.db"), "rb") as fh:
        checar("e a numeracao continua intacta depois de voltar",
               fh.read() == b"NUMERACAO QUE NAO PODE SUMIR")

    try:
        atu.reverter("nao-existe")
        checar("versao inexistente da erro claro", False, "nao deu erro")
    except atu.ErroAtualizacao:
        checar("versao inexistente da erro claro", True)

finally:
    servidor.shutdown()
    shutil.rmtree(FALSA, ignore_errors=True)
    cfgmod.RAIZ = RAIZ_REAL
    cfgmod.PASTA_DADOS = DADOS_REAL
    cfgmod.CAMINHO_CONFIG = CONFIG_REAL


print("\n" + "=" * 62)
if falhas:
    print("%d verificacao(oes) FALHARAM:" % len(falhas))
    for f in falhas:
        print("   - %s" % f)
    sys.exit(1)
print("Tudo certo: %d verificacoes passaram." % passou)
