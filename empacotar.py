# -*- coding: utf-8 -*-
"""Monta a pasta do aplicativo para instalar na clinica.

    python empacotar.py

Sai em `distribuicao/EmissorNFSe/`, uma pasta que roda em qualquer Windows
64 bits **sem instalar Python nem nada**. Copie para o computador da clinica
(pen drive, Drive, rede) e mande a operadora dar dois cliques em
`Emissor NFS-e.bat`.

**Por que Python embutido e nao um .exe.** Um `.exe` de PyInstaller sela o
codigo dentro do executavel: cada correcao vira um binario de ~80 MB para
republicar, e antivirus corporativo costuma pegar no pe. Com o Python
embutido, o codigo continua sendo arquivo `.py` do lado -- e a atualizacao
remota troca so os arquivos que mudaram, uns poucos KB. Como o combinado e
justamente poder consertar a clinica daqui, essa e a escolha que sustenta a
promessa.

O que vai junto:

    runtime/         Python 3.12 embutido + as bibliotecas (~90 MB)
    nfse/ web/ app.py   o programa
    config/          configuracao SEM certificado e SEM senha
    Emissor NFS-e.bat   o atalho que a operadora usa

O que NAO vai, e tem que ser posto a mao na clinica:

    config/certificados/*.pfx    o certificado A1
    config/senhas.bat            a senha dele

Isso e deliberado. Certificado viajando junto com a senha, num pacote que
passa por pen drive e e-mail, e assinatura digital vazada.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

RAIZ = os.path.dirname(os.path.abspath(__file__))
DESTINO = os.path.join(RAIZ, "distribuicao", "EmissorNFSe")


def _console_utf8() -> None:
    """Faz o console aguentar acento e seta, em qualquer Windows.

    O terminal do Windows costuma vir em cp1252, que nao tem "→". Sem isto,
    um print no fim do trabalho derruba o script DEPOIS de ele ja ter feito
    tudo -- e parece que falhou quando nao falhou.
    """
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_console_utf8()


VERSAO_PYTHON = "3.12.10"
URL_PYTHON = ("https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip"
              % (VERSAO_PYTHON, VERSAO_PYTHON))
CACHE = os.path.join(RAIZ, "distribuicao", "_cache")

BIBLIOTECAS = ["flask", "lxml", "cryptography", "requests", "pdfplumber"]

COPIAR_PASTAS = ("nfse", "web", "testes")
COPIAR_ARQUIVOS = ("app.py", "LEIA-ME.md", "COMO-USAR.md",
                   "requirements.txt", "VERSAO", "publicar.py")

INICIAR_BAT = r"""@echo off
title Emissor de NFS-e - NAO FECHE esta janela
cd /d "%~dp0"

rem A senha do certificado nunca fica no codigo nem na configuracao: vem
rem deste arquivo, que fica so nesta maquina e nao entra em backup nenhum.
if exist "config\senhas.bat" call "config\senhas.bat"

if not exist "config\certificados\*.pfx" (
  echo.
  echo   ATENCAO: nao encontrei nenhum certificado em config\certificados\
  echo   O sistema abre, mas nao vai conseguir assinar nota.
  echo.
)

echo.
echo   Emissor de NFS-e esta abrindo...
echo   O navegador abre sozinho. Se nao abrir, entre em:
echo.
echo       http://localhost:5510
echo.
echo   Para encerrar, feche esta janela.
echo.

"runtime\python.exe" app.py
if errorlevel 1 (
  echo.
  echo   O programa parou com erro. A mensagem acima explica o motivo.
  echo   Se nao resolver, mande a tela para o responsavel.
  echo.
  pause
)
"""

SENHAS_EXEMPLO = r"""@echo off
rem  ------------------------------------------------------------------
rem  SENHAS DOS CERTIFICADOS - so nesta maquina, nunca em backup ou e-mail
rem  ------------------------------------------------------------------
rem  Renomeie este arquivo para  senhas.bat  e ponha as senhas de verdade.

set CERT_SENHA_GLORIA=troque-aqui
set CERT_SENHA_COBILANDIA=troque-aqui
"""


def baixar_python() -> str:
    os.makedirs(CACHE, exist_ok=True)
    destino = os.path.join(CACHE, "python-embed-%s.zip" % VERSAO_PYTHON)
    if os.path.exists(destino) and os.path.getsize(destino) > 5_000_000:
        print("  Python embutido: já estava no cache")
        return destino
    print("  Baixando Python %s embutido..." % VERSAO_PYTHON)
    urllib.request.urlretrieve(URL_PYTHON, destino)
    return destino


def montar_runtime(zip_python: str) -> None:
    runtime = os.path.join(DESTINO, "runtime")
    shutil.rmtree(runtime, ignore_errors=True)
    os.makedirs(runtime, exist_ok=True)
    with zipfile.ZipFile(zip_python) as z:
        z.extractall(runtime)

    # O Python embutido vem com `import site` desligado e sem site-packages
    # no caminho. Sem estas duas linhas ele nao enxerga biblioteca nenhuma.
    caminho_pth = os.path.join(runtime, "python312._pth")
    with open(caminho_pth, "w", encoding="ascii") as fh:
        fh.write("python312.zip\n.\nLib\\site-packages\n..\n\nimport site\n")

    print("  Instalando as bibliotecas (demora um pouco)...")
    alvo = os.path.join(runtime, "Lib", "site-packages")
    processo = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet",
         "--disable-pip-version-check", "--target", alvo,
         "--python-version", "3.12", "--only-binary=:all:"] + BIBLIOTECAS,
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if processo.returncode != 0:
        raise SystemExit("Falhou ao instalar as bibliotecas:\n%s"
                         % (processo.stderr or processo.stdout)[-3000:])


def copiar_programa() -> None:
    ignorar = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo")
    for pasta in COPIAR_PASTAS:
        origem = os.path.join(RAIZ, pasta)
        if os.path.isdir(origem):
            shutil.copytree(origem, os.path.join(DESTINO, pasta),
                            dirs_exist_ok=True, ignore=ignorar)
    for arquivo in COPIAR_ARQUIVOS:
        origem = os.path.join(RAIZ, arquivo)
        if os.path.exists(origem):
            shutil.copy2(origem, os.path.join(DESTINO, arquivo))

    # Configuracao vai; certificado e senha NAO.
    os.makedirs(os.path.join(DESTINO, "config", "certificados"), exist_ok=True)
    shutil.copy2(os.path.join(RAIZ, "config", "empresas.json"),
                 os.path.join(DESTINO, "config", "empresas.json"))
    with open(os.path.join(DESTINO, "config", "senhas-EXEMPLO.bat"),
              "w", encoding="utf-8") as fh:
        fh.write(SENHAS_EXEMPLO)
    with open(os.path.join(DESTINO, "config", "certificados", "COLOQUE-AQUI.txt"),
              "w", encoding="utf-8") as fh:
        fh.write(
            "Coloque nesta pasta os arquivos .pfx dos certificados A1.\n\n"
            "Os nomes têm que bater com o que está em config/empresas.json,\n"
            "na chave \"certificado\" de cada unidade.\n\n"
            "A senha de cada um vai em config/senhas.bat (veja o EXEMPLO).\n")

    for pasta in ("dados", "entrada"):
        os.makedirs(os.path.join(DESTINO, pasta), exist_ok=True)

    with open(os.path.join(DESTINO, "Emissor NFS-e.bat"), "w",
              encoding="cp1252", errors="replace") as fh:
        fh.write(INICIAR_BAT)


def limpar_dados() -> None:
    """Deixa `dados/` vazia no pacote que vai para a clinica.

    Precisa rodar DEPOIS da conferencia: so de importar o `app` ja nasce um
    `dados/sessao.chave`, e emitir qualquer coisa criaria `controle.db`. Um
    controle.db de teste chegando na clinica levaria numeracao errada junto
    -- o erro mais caro que este sistema pode cometer. A pasta de
    distribuicao e descartavel; a instalada na clinica nunca passa por aqui.
    """
    dados = os.path.join(DESTINO, "dados")
    shutil.rmtree(dados, ignore_errors=True)
    os.makedirs(dados, exist_ok=True)


def tamanho(pasta: str) -> float:
    total = 0
    for atual, _, arquivos in os.walk(pasta):
        for arquivo in arquivos:
            total += os.path.getsize(os.path.join(atual, arquivo))
    return total / (1024.0 * 1024.0)


def main() -> int:
    print("Montando o aplicativo em distribuicao/EmissorNFSe/\n")
    os.makedirs(DESTINO, exist_ok=True)
    montar_runtime(baixar_python())
    copiar_programa()

    runtime_python = os.path.join(DESTINO, "runtime", "python.exe")
    print("\n  Conferindo se o pacote roda por conta própria...")
    processo = subprocess.run(
        [runtime_python, "-c",
         "import flask, lxml.etree, cryptography, requests, pdfplumber, sqlite3;"
         "print('bibliotecas ok')"],
        cwd=DESTINO, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if processo.returncode != 0:
        print("  FALHOU: %s" % (processo.stderr or "")[-1500:])
        return 1
    print("  %s" % (processo.stdout or "").strip())

    processo = subprocess.run(
        [runtime_python, "-c", "import app; print('o programa carrega')"],
        cwd=DESTINO, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    if processo.returncode != 0:
        print("  FALHOU ao carregar o app: %s" % (processo.stderr or "")[-1500:])
        return 1
    print("  %s" % (processo.stdout or "").strip())

    limpar_dados()
    sobrou = [n for n in os.listdir(os.path.join(DESTINO, "dados"))]
    if sobrou:
        print("  ATENÇÃO: sobrou coisa em dados/ -> %s" % sobrou)
        return 1
    print("  dados/ está limpa — sem numeração nem histórico de teste")

    print("\nPronto — %.0f MB em distribuicao/EmissorNFSe/" % tamanho(DESTINO))
    print("""
Para instalar na clínica:
  1. Copie a pasta EmissorNFSe inteira para o computador de lá
  2. Ponha os .pfx em config\\certificados\\
  3. Copie config\\senhas-EXEMPLO.bat para config\\senhas.bat e ponha as senhas
  4. Dois cliques em "Emissor NFS-e.bat"
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
