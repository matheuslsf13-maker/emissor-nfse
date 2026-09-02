# -*- coding: utf-8 -*-
"""Gera o pacote de atualizacao para as maquinas que ja rodam o sistema.

Uso:

    python publicar.py 1.1.0
    python publicar.py 1.1.0 --notas "Corrige o bairro da Cobilandia"
    python publicar.py 1.1.0 --config config/remendo.json

Sai em `publicacao/`:

    emissor-nfse-1.1.0.zip   o codigo
    manifesto.json           o que a clinica le para saber que ha novidade

Suba os dois para qualquer lugar que sirva arquivos por HTTPS e aponte o
`manifesto` no `config/empresas.json` da clinica para a URL do
`manifesto.json`. O caminho do `.zip` vai dentro do manifesto, entao os dois
podem ficar em lugares diferentes.

**O pacote leva so codigo.** `dados/`, certificados, senhas e
`config/empresas.json` ficam de fora -- nao por esquecimento, mas porque um
pacote que carregasse esses arquivos apagaria a numeracao e o certificado da
clinica ao ser aplicado. O unico jeito de mexer na configuracao remota e o
`--config`, que MESCLA so as chaves citadas.

Antes de empacotar, a suite de testes roda. Publicar uma versao quebrada e
exatamente o erro que este sistema nao pode cometer: quem esta do outro lado
nao sabe reverter.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from datetime import datetime

RAIZ = os.path.dirname(os.path.abspath(__file__))
SAIDA = os.path.join(RAIZ, "publicacao")


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


INCLUIR_PASTAS = ("nfse", "web", "testes")
INCLUIR_ARQUIVOS = ("app.py", "LEIA-ME.md", "COMO-USAR.md",
                    "GUIA-DO-RESPONSAVEL.md", "requirements.txt", "VERSAO",
                    "Iniciar.bat", "instalar.bat", "publicar.bat")
IGNORAR = ("__pycache__", ".pyc", ".pyo", ".db", ".log")

TESTES = ("rodar_tudo.py", "t_base_clientes.py", "t_transmissao.py",
          "t_robustez.py", "t_atualizacao.py")


def rodar_testes() -> bool:
    print("Rodando os testes antes de publicar...\n")
    for teste in TESTES:
        caminho = os.path.join(RAIZ, "testes", teste)
        if not os.path.exists(caminho):
            continue
        processo = subprocess.run([sys.executable, caminho], cwd=RAIZ,
                                  capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        ultima = [l for l in (processo.stdout or "").splitlines() if l.strip()]
        print("  %-22s %s" % (teste, ultima[-1] if ultima else "sem saida"))
        if processo.returncode != 0:
            print("\n%s FALHOU. Nada foi publicado." % teste)
            print((processo.stdout or "")[-2000:])
            return False
    print()
    return True


def deve_ignorar(caminho: str) -> bool:
    return any(marca in caminho for marca in IGNORAR)


def montar_zip(destino: str) -> list:
    incluidos = []
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as pacote:
        for pasta in INCLUIR_PASTAS:
            raiz_pasta = os.path.join(RAIZ, pasta)
            if not os.path.isdir(raiz_pasta):
                continue
            for atual, _, arquivos in os.walk(raiz_pasta):
                for arquivo in arquivos:
                    completo = os.path.join(atual, arquivo)
                    if deve_ignorar(completo):
                        continue
                    relativo = os.path.relpath(completo, RAIZ).replace(os.sep, "/")
                    pacote.write(completo, relativo)
                    incluidos.append(relativo)
        for arquivo in INCLUIR_ARQUIVOS:
            completo = os.path.join(RAIZ, arquivo)
            if os.path.exists(completo):
                pacote.write(completo, arquivo)
                incluidos.append(arquivo)
    return incluidos


def main() -> int:
    analisador = argparse.ArgumentParser(description=__doc__)
    analisador.add_argument("versao", help="ex.: 1.1.0")
    analisador.add_argument("--notas", default="",
                            help="o que mudou, em uma frase, para aparecer na tela da clínica")
    analisador.add_argument("--config", default="",
                            help="JSON com as chaves de empresas.json a mesclar na clínica")
    analisador.add_argument("--url-base", default="",
                            help="prefixo das URLs no manifesto (ex.: https://.../releases/download/v1.1.0)")
    analisador.add_argument("--github", metavar="USUARIO/REPO",
                            help="publica via GitHub Releases: o manifesto já sai com a URL certa")
    analisador.add_argument("--drive", action="store_true",
                            help="nomes fixos, para hospedar no Google Drive sem refazer o link a cada versão")
    analisador.add_argument("--sem-testes", action="store_true",
                            help="pula os testes — use só se souber por quê")
    opcoes = analisador.parse_args()

    if not opcoes.sem_testes and not rodar_testes():
        return 1

    os.makedirs(SAIDA, exist_ok=True)
    with open(os.path.join(RAIZ, "VERSAO"), "w", encoding="utf-8") as fh:
        fh.write(opcoes.versao + "\n")

    # No Drive, cada arquivo novo ganha um ID novo -- e o link publico teria
    # que ser reconfigurado na clinica a cada versao. Com nome FIXO, o arquivo
    # e substituido por "Gerenciar versoes" no proprio Drive: o ID e o link
    # continuam os mesmos, e a clinica nunca precisa ser tocada de novo.
    nome_zip = ("emissor-nfse.zip" if (opcoes.drive or opcoes.github)
                else "emissor-nfse-%s.zip" % opcoes.versao)
    caminho_zip = os.path.join(SAIDA, nome_zip)
    incluidos = montar_zip(caminho_zip)

    with open(caminho_zip, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()

    alteracoes = {}
    if opcoes.config:
        with open(opcoes.config, encoding="utf-8") as fh:
            alteracoes = json.load(fh)

    # O GitHub serve `releases/latest/download/<arquivo>` como um endereco
    # permanente que sempre entrega a versao mais nova. Com isso a clinica e
    # configurada UMA vez e nunca mais -- publicar passa a ser um comando so,
    # sem nenhum passo manual.
    #
    # ARMADILHA, medida em 01/09/2026: o CDN do GitHub cacheia o asset pelo
    # NOME. Refazer uma release reusando `emissor-nfse.zip` faz o endereco
    # continuar entregando o arquivo antigo por alguns minutos -- com o
    # manifesto ja novo. A clinica baixa um par incompativel, e so nao instala
    # o pacote errado porque o sha256 e conferido antes de escrever qualquer
    # coisa. Ao corrigir uma release ja publicada, use uma versao nova em vez
    # de sobrescrever a mesma.
    url_base = opcoes.url_base
    if opcoes.github and not url_base:
        url_base = ("https://github.com/%s/releases/latest/download"
                    % opcoes.github.strip("/"))

    manifesto = {
        "versao": opcoes.versao,
        "publicado_em": datetime.now().isoformat(timespec="seconds"),
        "url": (url_base.rstrip("/") + "/" + nome_zip
                if url_base else nome_zip),
        "sha256": sha,
        "notas": opcoes.notas,
    }
    if alteracoes:
        manifesto["config"] = alteracoes

    caminho_manifesto = os.path.join(SAIDA, "manifesto.json")
    with open(caminho_manifesto, "w", encoding="utf-8") as fh:
        json.dump(manifesto, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    tamanho = os.path.getsize(caminho_zip) / 1024.0
    print("Versão %s publicada." % opcoes.versao)
    print("  %-22s %d arquivos, %.0f KB" % (nome_zip, len(incluidos), tamanho))
    print("  %-22s sha256 %s" % ("manifesto.json", sha[:16] + "…"))
    if alteracoes:
        print("  configuração          %d chave(s) a mesclar na clínica"
              % len(alteracoes))
    if opcoes.github:
        print("""
GitHub Releases — publique com:
  gh release create v%s publicacao/emissor-nfse.zip publicacao/manifesto.json

Na clínica, `atualizacao.manifesto` aponta uma vez para:
  %s/manifesto.json

Esse endereço é permanente: toda release nova passa a ser servida por ele
sem que a clínica precise ser tocada.""" % (opcoes.versao, url_base))
    elif opcoes.drive and not opcoes.url_base:
        print("""
Google Drive — só na PRIMEIRA vez:
  1. Suba os dois arquivos de publicacao/ para a pasta do Drive
  2. Em cada um: Compartilhar → "Qualquer pessoa com o link" → Leitor
  3. Copie o link do .zip e cole na chave "url" do manifesto.json
  4. Copie o link do manifesto.json e cole em config/empresas.json,
     na chave atualizacao.manifesto — nas DUAS máquinas

Nas próximas versões, só isto:
  Botão direito no arquivo, no Drive → Gerenciar versões → Enviar nova
  versão. O link não muda, e a clínica não precisa ser tocada.""")
    elif not opcoes.url_base:
        print("\nFalta o endereço: suba os dois arquivos e edite a chave \"url\"")
        print("do manifesto.json com o link direto do .zip.")
    print("\nNa clínica: Configuração → Procurar atualizações.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
