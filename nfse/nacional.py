# -*- coding: utf-8 -*-
"""Ambiente de Dados Nacional (ADN): a nota como a Receita a guarda.

**Por que existe.** A prefeitura de Vila Velha recebe a nota, mas quem a
arquiva em definitivo e o ambiente nacional. O WebService municipal
(`NotaFiscalNacional`, da SIL) expoe quatro operacoes -- gerar, consultar,
cancelar, substituir -- e nenhuma devolve documento pronto. Conferido no
WSDL ao vivo nos dois ambientes: a palavra "danfse" nao aparece nele.

O ADN, sim, guarda a NFS-e assinada e completa, com campos que o nosso DPS
nao tinha porque quem os preenche e a propria Receita: o numero da nota, o
municipio por extenso, a descricao da tributacao, os totais de tributo
federal/estadual/municipal e a situacao atual do documento.

**A credencial e o mesmo certificado da clinica.** Aqui, porem, ele nao vai
dentro do XML: vai no aperto de mao TLS (mTLS). Testado em 02/09/2026 com o
certificado da Gloria contra a nota 8966 -- HTTP 200, XML oficial na mao.

**O PDF oficial ainda nao existe por API.** `GET /danfse/{chave}` responde
501 Not Implemented -- nao e falta de permissao nossa, e um endpoint que a
Receita publicou e ainda nao ligou. `baixar_danfse()` fica escrita assim
mesmo: no dia em que ligarem, o sistema passa a entregar o PDF oficial sem
precisar de mudanca. Ate la, o 501 vira uma frase em portugues em vez de um
erro cru.
"""

from __future__ import annotations

import base64
import gzip
import os
import secrets
import ssl
import tempfile

PRODUCAO = "https://sefin.nfse.gov.br/sefinnacional"
RESTRITA = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"


class ErroNacional(Exception):
    pass


class DanfseIndisponivel(ErroNacional):
    """O PDF oficial existe como endereco, mas ainda nao como servico."""


def _endereco(ambiente: str) -> str:
    return RESTRITA if ambiente == "homologacao" else PRODUCAO


class _Sessao:
    """Sessao HTTPS que se apresenta com o certificado da clinica.

    A chave privada precisa virar arquivo para o `ssl` do Python carregar --
    ele nao le de memoria. Entao ela e gravada CIFRADA, com uma senha
    aleatoria que so existe nesta execucao e nunca sai daqui, e o arquivo e
    apagado ao fechar a sessao. Chave privada em claro no disco, ainda que
    por segundos, e um risco que nao se justifica por conveniencia.
    """

    def __init__(self, certificado):
        from cryptography.hazmat.primitives.serialization import (
            BestAvailableEncryption, Encoding, PrivateFormat)

        self._caminho = None
        senha = secrets.token_urlsafe(32)
        fd, caminho = tempfile.mkstemp(suffix=".pem")
        try:
            with os.fdopen(fd, "wb") as saida:
                saida.write(certificado.chave.private_bytes(
                    Encoding.PEM, PrivateFormat.PKCS8,
                    BestAvailableEncryption(senha.encode())))
                saida.write(certificado.certificado.public_bytes(Encoding.PEM))
                for elo in (certificado.cadeia or []):
                    saida.write(elo.public_bytes(Encoding.PEM))
            self._caminho = caminho
            contexto = ssl.create_default_context()
            contexto.load_cert_chain(caminho, password=senha)
        except Exception:
            self._apagar()
            raise

        import requests
        from requests.adapters import HTTPAdapter

        class _ComCertificado(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                kwargs["ssl_context"] = contexto
                return super().init_poolmanager(*args, **kwargs)

        self.http = requests.Session()
        self.http.mount("https://", _ComCertificado())

    def _apagar(self):
        if self._caminho and os.path.exists(self._caminho):
            try:
                os.remove(self._caminho)
            except OSError:
                pass
        self._caminho = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._apagar()
        try:
            self.http.close()
        except Exception:
            pass


def _erro_legivel(resposta, chave: str) -> str:
    """Traduz o codigo HTTP para uma frase que diz o que fazer."""
    codigo = resposta.status_code
    if codigo == 404:
        return ("O ambiente nacional não tem essa nota (%s). Confira a "
                "chave, ou aguarde: uma nota recém-emitida leva alguns "
                "minutos para chegar lá." % chave[:10] + "...")
    if codigo in (401, 403):
        return ("O ambiente nacional recusou o certificado da clínica. "
                "Verifique se ele está válido e se o CNPJ é o mesmo da nota.")
    if codigo == 501:
        return ("A Receita ainda não liberou este serviço (respondeu 501). "
                "Não é problema da clínica.")
    return "O ambiente nacional respondeu %s." % codigo


def baixar_xml(chave: str, certificado, ambiente: str = "producao",
               timeout: int = 40) -> bytes:
    """O XML oficial da NFS-e, como a Receita o guarda.

    E o documento com validade fiscal -- o que o contador aceita e o que o
    paciente pode guardar. Vem compactado; devolvemos ja aberto.
    """
    with _Sessao(certificado) as sessao:
        resposta = sessao.http.get(
            "%s/nfse/%s" % (_endereco(ambiente), chave), timeout=timeout)
        if resposta.status_code != 200:
            raise ErroNacional(_erro_legivel(resposta, chave))
        try:
            corpo = resposta.json()
        except ValueError:
            raise ErroNacional("O ambiente nacional respondeu algo que não "
                               "consegui ler.")
    compactado = corpo.get("nfseXmlGZipB64")
    if not compactado:
        raise ErroNacional("A resposta veio sem o XML da nota.")
    try:
        return gzip.decompress(base64.b64decode(compactado))
    except Exception as erro:
        raise ErroNacional("Não consegui abrir o XML recebido: %s" % erro)


def baixar_varios(chaves, certificado, ambiente: str = "producao",
                  timeout: int = 40, aviso=None) -> dict:
    """Varios XMLs de uma vez, reusando a mesma sessao TLS.

    Abrir a sessao custa mais do que a consulta em si (0,3s contra 0,1s por
    nota). Com uma sessao so, cem notas levam cerca de dez segundos -- o que
    torna viavel montar o PDF do ano inteiro com os documentos oficiais em
    vez da nossa reconstrucao.

    Devolve {chave: xml}. Chave que falhar fica de fora, sem derrubar as
    outras: melhor entregar 29 notas de 30 do que erro nenhum.
    """
    achados = {}
    with _Sessao(certificado) as sessao:
        for posicao, chave in enumerate(chaves, 1):
            if aviso:
                aviso(posicao, len(chaves))
            try:
                resposta = sessao.http.get(
                    "%s/nfse/%s" % (_endereco(ambiente), chave),
                    timeout=timeout)
                if resposta.status_code != 200:
                    continue
                compactado = resposta.json().get("nfseXmlGZipB64")
                if compactado:
                    achados[chave] = gzip.decompress(
                        base64.b64decode(compactado))
            except Exception:  # noqa: BLE001
                continue
    return achados


def baixar_danfse(chave: str, certificado, ambiente: str = "producao",
                  timeout: int = 60) -> bytes:
    """O PDF oficial -- quando a Receita ligar o servico.

    Hoje responde 501. Deixamos escrito para que o dia em que ligarem nao
    precise de versao nova: quem chama trata `DanfseIndisponivel` caindo
    para o nosso comprovante.
    """
    with _Sessao(certificado) as sessao:
        resposta = sessao.http.get(
            "%s/danfse/%s" % (_endereco(ambiente), chave), timeout=timeout)
        if resposta.status_code == 501:
            raise DanfseIndisponivel(
                "A Receita ainda não liberou o download do DANFSe oficial "
                "por sistema (respondeu 501). Enquanto isso, use o "
                "comprovante daqui ou baixe o oficial informando a chave em "
                "nfse.gov.br/consultapublica.")
        if resposta.status_code != 200:
            raise ErroNacional(_erro_legivel(resposta, chave))
        corpo = resposta.content
        if corpo[:4] != b"%PDF":
            raise DanfseIndisponivel(
                "O ambiente nacional respondeu, mas não com um PDF.")
        return corpo


def nome_do_arquivo(xml: bytes, chave: str) -> str:
    """Nome legivel para o XML oficial, tirado do proprio XML.

    "NFSe-32052001233347759000102000000000896626090665196910.xml" nao diz
    nada a ninguem. O arquivo vai para o contador junto com dezenas de
    outros: numero e paciente resolvem.
    """
    import re

    def _campo(tag, dentro=None):
        alvo = dentro if dentro is not None else xml
        achado = re.search(rb"<%s>(.*?)</%s>" % (tag.encode(), tag.encode()),
                           alvo, re.S)
        return achado.group(1).decode("utf-8", "replace").strip() if achado else ""

    numero = _campo("nNFSe")
    # O <xNome> aparece para prestador e tomador; o do tomador esta dentro
    # do bloco <toma>. Pegar o primeiro traria o nome da clinica.
    bloco = re.search(rb"<toma>(.*?)</toma>", xml, re.S)
    nome = _campo("xNome", bloco.group(1)) if bloco else ""

    nome = re.sub(r"[^\w\s-]", "", nome.title()).strip().replace(" ", "-")
    if len(nome) > 60:
        nome = nome[:60].rstrip("-")

    partes = ["NFSe", numero or chave[:12], nome, "oficial"]
    return "-".join(p for p in partes if p) + ".xml"
