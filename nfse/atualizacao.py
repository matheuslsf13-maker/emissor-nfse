# -*- coding: utf-8 -*-
"""Atualizacao remota: consertar a clinica sem ir ate la.

O sistema roda em dois lugares (a maquina do responsavel e a da clinica) e
quem opera na clinica nao mexe em codigo. Quando aparece um erro la, o
conserto tem que chegar sozinho.

**Como funciona.** O responsavel publica uma versao nova (`publicar.py` gera
um `.zip` e um `manifesto.json`) em qualquer lugar que sirva arquivos por
HTTPS -- GitHub Releases, Google Drive, um servidor proprio. A clinica
consulta o manifesto, ve que ha versao mais nova, baixa, confere e aplica.

**O que a atualizacao NUNCA toca**, por mais que o pacote contenha:

    dados/                  numeracao, base de clientes, historico
    config/certificados/    certificado A1
    config/senhas.bat       senhas
    entrada/  saida/        relatorios e notas

Isso nao e detalhe de implementacao, e a regra que torna a atualizacao
segura: o pacote so carrega CODIGO. Se um dia um pacote errado for
publicado, o pior que acontece e o programa parar -- nunca perder a
numeracao ou o certificado.

**Antes de trocar qualquer coisa, o codigo atual e copiado** para
`dados/versoes/<versao>-<data>/`. Se a versao nova nao subir, `reverter()`
volta a anterior. Uma atualizacao que quebra o sistema numa sexta-feira, sem
volta, e pior do que o erro que ela consertava.

A configuracao (`config/empresas.json`) e caso a parte: e dado local, mas as
vezes o conserto E nela (um endereco errado, um endpoint que mudou). Por
isso o manifesto pode trazer um bloco `config` que e MESCLADO -- so as
chaves que ele cita mudam, o resto do arquivo fica como esta.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import zipfile
from datetime import datetime

from . import config as cfgmod

# Pastas e arquivos que uma atualizacao jamais sobrescreve.
PRESERVAR = (
    "dados", "entrada", "saida", "config/certificados", "config/senhas.bat",
    "config/empresas.json", ".git", "__pycache__",
)

# So estes caminhos sao aceitos de dentro do pacote. Um zip nao pode escrever
# onde quiser: e arquivo baixado da internet.
PERMITIDOS = ("app.py", "nfse/", "web/", "testes/", "LEIA-ME.md",
              "COMO-USAR.md", "GUIA-DO-RESPONSAVEL.md", "requirements.txt",
              "VERSAO", "Iniciar.bat", "instalar.bat", "publicar.bat")


class ErroAtualizacao(Exception):
    pass


def versao_instalada() -> str:
    caminho = os.path.join(cfgmod.RAIZ, "VERSAO")
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    return "0.0.0"


def _como_numero(versao: str) -> tuple:
    """'1.10.2' -> (1, 10, 2), para comparar direito.

    Comparacao de texto diria que '1.10' < '1.9', o que faria a clinica
    recusar justamente a atualizacao mais nova.
    """
    partes = []
    for pedaco in str(versao).split("."):
        digitos = "".join(c for c in pedaco if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    while len(partes) < 3:
        partes.append(0)
    return tuple(partes[:3])


def ha_novidade(instalada: str, disponivel: str) -> bool:
    return _como_numero(disponivel) > _como_numero(instalada)


def url_do_manifesto(config=None) -> str:
    cfg = config or cfgmod.carregar()
    return (cfg.bruto.get("atualizacao", {}) or {}).get("manifesto", "")


# O link que o Google Drive oferece ao compartilhar aponta para a PAGINA do
# arquivo, nao para o arquivo: baixa-lo devolve HTML. Estes dois formatos sao
# os que o Drive gera hoje.
_PADROES_DRIVE = (
    r"drive\.google\.com/file/d/([\w-]{10,})",
    r"drive\.google\.com/(?:uc|open)\?(?:[^&]*&)*id=([\w-]{10,})",
)


def link_direto(url: str) -> str:
    """Converte link de compartilhamento do Drive em link de download.

    Sem isto, o manifesto "baixado" seria a pagina HTML do Drive e o sistema
    diria que nao ha atualizacao -- sem erro nenhum, o que e pior do que
    falhar. Qualquer outra URL passa intacta.
    """
    import re

    for padrao in _PADROES_DRIVE:
        achado = re.search(padrao, url or "")
        if achado:
            return ("https://drive.google.com/uc?export=download&id=%s"
                    % achado.group(1))
    return url


def _parece_html(conteudo: bytes) -> bool:
    inicio = conteudo[:400].lstrip().lower()
    return inicio.startswith(b"<!doctype html") or inicio.startswith(b"<html")


def procurar(config=None, timeout: int = 20) -> dict:
    """Consulta o manifesto. Nao baixa nada e nao muda nada."""
    url = url_do_manifesto(config)
    instalada = versao_instalada()
    if not url:
        return {"ativo": False, "instalada": instalada,
                "mensagem": "A atualização automática não está configurada."}

    import requests

    try:
        resposta = requests.get(link_direto(url), timeout=timeout,
                                headers={"Cache-Control": "no-cache"})
        resposta.raise_for_status()
        if _parece_html(resposta.content):
            # Causa quase certa no Drive: o arquivo nao esta compartilhado.
            # Sem dizer isso, a mensagem seria "JSONDecodeError" -- tecnicamente
            # correta e inutil para quem tem que resolver.
            return {"ativo": True, "instalada": instalada, "erro": True,
                    "mensagem": "O endereço devolveu uma página da web em vez "
                                "do arquivo. No Google Drive, o manifesto "
                                "precisa estar compartilhado como \"qualquer "
                                "pessoa com o link\"."}
        manifesto = resposta.json()
    except Exception as erro:  # noqa: BLE001
        # Sem internet, servidor fora, JSON quebrado: nada disso pode
        # atrapalhar quem esta emitindo nota. Vira aviso, nunca erro.
        return {"ativo": True, "instalada": instalada, "erro": True,
                "mensagem": "Não consegui verificar agora (%s)."
                            % type(erro).__name__}

    disponivel = str(manifesto.get("versao", "")).strip()
    return {
        "ativo": True,
        "instalada": instalada,
        "disponivel": disponivel,
        "novidade": ha_novidade(instalada, disponivel),
        "notas": manifesto.get("notas", ""),
        "publicado_em": manifesto.get("publicado_em", ""),
        "url_pacote": manifesto.get("url", ""),
        "sha256": manifesto.get("sha256", ""),
        "config": manifesto.get("config") or {},
        "manifesto": manifesto,
    }


def _seguro(nome: str) -> bool:
    """O caminho pode sair do pacote para o disco?"""
    limpo = nome.replace("\\", "/")
    if limpo.startswith("/") or ".." in limpo.split("/"):
        return False
    if ":" in limpo:
        return False
    return any(limpo == p or limpo.startswith(p) for p in PERMITIDOS)


def _preservado(nome: str) -> bool:
    limpo = nome.replace("\\", "/")
    return any(limpo == p or limpo.startswith(p.rstrip("/") + "/")
               for p in PRESERVAR)


def guardar_versao_atual(versao: str) -> str:
    """Copia o codigo atual para dados/versoes/. Devolve a pasta."""
    destino = os.path.join(
        cfgmod.PASTA_DADOS, "versoes",
        "%s-%s" % (versao or "sem-versao", datetime.now().strftime("%Y%m%d-%H%M%S")))
    os.makedirs(destino, exist_ok=True)
    for item in PERMITIDOS:
        origem = os.path.join(cfgmod.RAIZ, item.rstrip("/"))
        if not os.path.exists(origem):
            continue
        alvo = os.path.join(destino, item.rstrip("/"))
        if os.path.isdir(origem):
            shutil.copytree(origem, alvo, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            shutil.copy2(origem, alvo)
    return destino


def mesclar_config(alteracoes: dict) -> list:
    """Aplica as chaves que o manifesto cita, deixando o resto intacto.

    Devolve a lista do que mudou, em portugues, para o log e para a tela.
    O arquivo local pode ter ajustes que so a clinica conhece; sobrescrever
    tudo apagaria esses ajustes sem ninguem perceber.
    """
    if not alteracoes:
        return []
    caminho = os.path.join(cfgmod.RAIZ, "config", "empresas.json")
    with open(caminho, encoding="utf-8") as fh:
        atual = json.load(fh)

    mudancas = []

    def fundir(destino, novo, prefixo=""):
        for chave, valor in novo.items():
            caminho_chave = "%s.%s" % (prefixo, chave) if prefixo else chave
            if isinstance(valor, dict) and isinstance(destino.get(chave), dict):
                fundir(destino[chave], valor, caminho_chave)
            elif destino.get(chave) != valor:
                mudancas.append("%s: %r → %r"
                                % (caminho_chave, destino.get(chave), valor))
                destino[chave] = valor

    fundir(atual, alteracoes)
    if mudancas:
        with open(caminho, "w", encoding="utf-8") as fh:
            json.dump(atual, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    return mudancas


def aplicar(informacao: dict, timeout: int = 120) -> dict:
    """Baixa, confere e aplica o pacote. Guarda a versao atual antes."""
    url = informacao.get("url_pacote")
    if not url:
        raise ErroAtualizacao("O manifesto não diz onde está o pacote.")

    import requests

    try:
        resposta = requests.get(link_direto(url), timeout=timeout)
        resposta.raise_for_status()
        pacote = resposta.content
    except Exception as erro:  # noqa: BLE001
        raise ErroAtualizacao("Não consegui baixar a atualização: %s" % erro)

    if _parece_html(pacote):
        # Drive devolvendo a pagina de aviso, ou um link que nao e o arquivo.
        # Sem esta checagem o erro apareceria mais adiante como "zip inválido",
        # que nao ajuda ninguem a descobrir que o problema e a permissão.
        raise ErroAtualizacao(
            "O endereço devolveu uma página da web em vez do arquivo. No "
            "Google Drive, o arquivo precisa estar compartilhado como "
            "\"qualquer pessoa com o link\". Nada foi alterado.")

    esperado = (informacao.get("sha256") or "").strip().lower()
    calculado = hashlib.sha256(pacote).hexdigest()
    if esperado and calculado != esperado:
        # Download truncado ou arquivo trocado. Aplicar assim mesmo poderia
        # deixar o sistema com metade do codigo novo e metade do velho.
        raise ErroAtualizacao(
            "O arquivo baixado não confere com o esperado — download "
            "incompleto ou corrompido. Nada foi alterado.")

    try:
        zip_pacote = zipfile.ZipFile(io.BytesIO(pacote))
    except Exception as erro:  # noqa: BLE001
        raise ErroAtualizacao("O pacote não é um arquivo .zip válido: %s" % erro)

    nomes = [n for n in zip_pacote.namelist() if not n.endswith("/")]
    recusados = [n for n in nomes if not _seguro(n) or _preservado(n)]
    aceitos = [n for n in nomes if n not in recusados]
    if not aceitos:
        raise ErroAtualizacao("O pacote não tem nenhum arquivo aplicável.")

    backup = guardar_versao_atual(versao_instalada())

    escritos = []
    try:
        for nome in aceitos:
            destino = os.path.join(cfgmod.RAIZ, nome.replace("/", os.sep))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            with open(destino, "wb") as fh:
                fh.write(zip_pacote.read(nome))
            escritos.append(nome)
    except Exception as erro:  # noqa: BLE001
        raise ErroAtualizacao(
            "Falhou no meio da atualização (%s). O código anterior está em %s "
            "— use 'Voltar para a versão anterior'." % (erro, backup))

    mudancas_config = mesclar_config(informacao.get("config") or {})
    _registrar(informacao, escritos, recusados, mudancas_config, backup)

    return {
        "versao": informacao.get("disponivel", ""),
        "arquivos": len(escritos),
        "recusados": recusados,
        "config": mudancas_config,
        "backup": backup,
    }


def versoes_guardadas() -> list:
    pasta = os.path.join(cfgmod.PASTA_DADOS, "versoes")
    if not os.path.isdir(pasta):
        return []
    return sorted(os.listdir(pasta), reverse=True)


def reverter(nome_versao: str) -> dict:
    """Volta o codigo para uma copia guardada."""
    origem = os.path.join(cfgmod.PASTA_DADOS, "versoes", nome_versao)
    if ".." in nome_versao or not os.path.isdir(origem):
        raise ErroAtualizacao("Versão guardada não encontrada: %s" % nome_versao)

    # A propria volta e guardada: dois cliques errados nao podem deixar o
    # sistema sem nenhuma copia.
    guardar_versao_atual(versao_instalada())

    restaurados = 0
    for raiz_atual, _, arquivos in os.walk(origem):
        for arquivo in arquivos:
            completo = os.path.join(raiz_atual, arquivo)
            relativo = os.path.relpath(completo, origem).replace(os.sep, "/")
            if not _seguro(relativo) or _preservado(relativo):
                continue
            destino = os.path.join(cfgmod.RAIZ, relativo.replace("/", os.sep))
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            shutil.copy2(completo, destino)
            restaurados += 1
    return {"versao": nome_versao, "arquivos": restaurados}


def _registrar(informacao, escritos, recusados, config, backup) -> None:
    linha = {
        "em": datetime.now().isoformat(timespec="seconds"),
        "de": versao_instalada(),
        "para": informacao.get("disponivel", ""),
        "arquivos": len(escritos),
        "recusados": recusados,
        "config": config,
        "backup": backup,
    }
    caminho = os.path.join(cfgmod.PASTA_DADOS, "atualizacoes.log")
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
