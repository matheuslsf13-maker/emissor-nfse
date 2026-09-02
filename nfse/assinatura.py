# -*- coding: utf-8 -*-
"""Assinatura XMLDSig com certificado A1 (.pfx).

Padrao nacional: RSA-SHA256, canonicalizacao C14N inclusiva, assinatura
enveloped. A Reference aponta para o Id do infNFSe e o <Signature> e irmao
dele (filho direto de NFSe).

Duas armadilhas:

* A assinatura cobre os bytes exatos do documento. Qualquer espaco ou quebra
  de linha adicionada depois a invalida -- por isso `pretty_print=False`
  sempre que o XML ja estiver assinado.
* ABRASF 2.03 (municipios que ainda nao migraram) usa SHA-1. O algoritmo
  vem da configuracao do municipio, nao esta fixo aqui.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree

NS_DS = "http://www.w3.org/2000/09/xmldsig#"

ALGORITMOS = {
    "sha256": {
        "assinatura": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        "digest": "http://www.w3.org/2001/04/xmlenc#sha256",
        "hash": hashes.SHA256,
        "hashlib": hashlib.sha256,
    },
    "sha1": {
        "assinatura": "http://www.w3.org/2000/09/xmldsig#rsa-sha1",
        "digest": "http://www.w3.org/2000/09/xmldsig#sha1",
        "hash": hashes.SHA1,
        "hashlib": hashlib.sha1,
    },
}


class ErroCertificado(Exception):
    pass


class Certificado:
    """Certificado A1 carregado de um .pfx."""

    def __init__(self, chave, certificado, cadeia=None):
        self.chave = chave
        self.certificado = certificado
        self.cadeia = cadeia or []

    @property
    def titular(self) -> str:
        try:
            return self.certificado.subject.rfc4514_string()
        except Exception:
            return "(não identificado)"

    @property
    def validade(self):
        return self.certificado.not_valid_after_utc

    @property
    def vencido(self) -> bool:
        from datetime import datetime, timezone

        return self.validade < datetime.now(timezone.utc)

    @property
    def cnpj(self) -> str:
        """CNPJ do titular, extraido do CN (ex.: '...LTDA:11222333000181')."""
        import re

        achado = re.search(r"(\d{14})\s*$", self.titular.split(",")[0])
        return achado.group(1) if achado else ""

    @property
    def dias_para_vencer(self) -> int:
        from datetime import datetime, timezone

        return (self.validade - datetime.now(timezone.utc)).days

    @property
    def base64_der(self) -> str:
        der = self.certificado.public_bytes(serialization.Encoding.DER)
        return base64.b64encode(der).decode()


def carregar_pfx(caminho: str, senha: str) -> Certificado:
    if not os.path.exists(caminho):
        raise ErroCertificado("Certificado não encontrado: %s" % caminho)
    if not senha:
        raise ErroCertificado(
            "A senha do certificado não foi informada. Preencha config/senhas.bat "
            "ou defina a variável de ambiente da unidade."
        )
    with open(caminho, "rb") as fh:
        dados = fh.read()
    try:
        chave, cert, cadeia = pkcs12.load_key_and_certificates(
            dados, senha.encode("utf-8")
        )
    except Exception as erro:
        raise ErroCertificado(
            "Não foi possível abrir o certificado (senha errada ou arquivo "
            "inválido): %s" % erro
        )
    if chave is None or cert is None:
        raise ErroCertificado("O arquivo .pfx não contém chave privada e certificado.")
    return Certificado(chave, cert, cadeia)


C14N_INCLUSIVA = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
C14N_EXCLUSIVA = "http://www.w3.org/2001/10/xml-exc-c14n#"

# Vila Velha exige canonicalizacao EXCLUSIVA. Descoberto na primeira
# transmissao real (01/09/2026): com a inclusiva, que a documentacao do
# projeto indicava, o retorno era sempre "Erro na assinatura: Falha na
# validacao da assinatura"; trocando para exclusiva, a nota foi aceita na
# hora. Nao ha como adivinhar isso -- so testando contra a prefeitura.
C14N_PADRAO = C14N_EXCLUSIVA


def _c14n(elemento, metodo: str = C14N_PADRAO) -> bytes:
    """Canonicalizacao, sem comentarios, inclusiva ou exclusiva."""
    return etree.tostring(elemento, method="c14n",
                          exclusive=(metodo == C14N_EXCLUSIVA),
                          with_comments=False)


def assinar(xml: bytes, id_referencia: str, certificado: Certificado,
            algoritmo: str = "sha256",
            canonicalizacao: str = C14N_PADRAO) -> bytes:
    """Assina o elemento de Id `id_referencia` e devolve o XML assinado.

    O <Signature> e inserido como ultimo filho da raiz, irmao do elemento
    referenciado -- e o que o leiaute nacional espera.
    """
    alg = ALGORITMOS[algoritmo]
    raiz = etree.fromstring(xml)

    if id_referencia:
        alvo = None
        for elemento in raiz.iter():
            if elemento.get("Id") == id_referencia:
                alvo = elemento
                break
        if alvo is None:
            raise ValueError("Nao ha elemento com Id=%s no XML." % id_referencia)
        uri = "#" + id_referencia
    else:
        # URI="" assina o documento inteiro. E o que o modelo de CONSULTA da
        # SIL usa: o <ConsultarNFE> nao tem Id em elemento nenhum.
        alvo = raiz
        uri = ""

    digest = base64.b64encode(
        alg["hashlib"](_c14n(alvo, canonicalizacao)).digest()).decode()

    # Namespace default, sem prefixo -- e como o modelo oficial da SIL
    # (xmlNacionalModeloEmissao.xml) mostra o elemento. Em XML puro tanto faz
    # `ds:Signature` quanto `Signature` com xmlns default, mas validador de
    # prefeitura costuma ser literal demais para arriscar.
    assinatura = etree.SubElement(raiz, "{%s}Signature" % NS_DS,
                                  nsmap={None: NS_DS})
    info = etree.SubElement(assinatura, "{%s}SignedInfo" % NS_DS)
    etree.SubElement(info, "{%s}CanonicalizationMethod" % NS_DS).set(
        "Algorithm", canonicalizacao
    )
    etree.SubElement(info, "{%s}SignatureMethod" % NS_DS).set(
        "Algorithm", alg["assinatura"]
    )
    referencia = etree.SubElement(info, "{%s}Reference" % NS_DS)
    referencia.set("URI", uri)
    transformacoes = etree.SubElement(referencia, "{%s}Transforms" % NS_DS)
    etree.SubElement(transformacoes, "{%s}Transform" % NS_DS).set(
        "Algorithm", "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    )
    etree.SubElement(transformacoes, "{%s}Transform" % NS_DS).set(
        "Algorithm", canonicalizacao
    )
    etree.SubElement(referencia, "{%s}DigestMethod" % NS_DS).set(
        "Algorithm", alg["digest"]
    )
    etree.SubElement(referencia, "{%s}DigestValue" % NS_DS).text = digest

    assinado = certificado.chave.sign(
        _c14n(info, canonicalizacao), padding.PKCS1v15(), alg["hash"]()
    )
    etree.SubElement(assinatura, "{%s}SignatureValue" % NS_DS).text = base64.b64encode(
        assinado
    ).decode()

    chave_info = etree.SubElement(assinatura, "{%s}KeyInfo" % NS_DS)
    dados_x509 = etree.SubElement(chave_info, "{%s}X509Data" % NS_DS)
    etree.SubElement(dados_x509, "{%s}X509Certificate" % NS_DS).text = (
        certificado.base64_der
    )

    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8",
                          pretty_print=False)


def conferir(xml: bytes) -> dict:
    """Revalida uma assinatura ja aplicada. Usado nos testes e na conferencia."""
    raiz = etree.fromstring(xml)
    assinatura = raiz.find("{%s}Signature" % NS_DS)
    if assinatura is None:
        return {"assinado": False, "erro": "XML sem assinatura."}

    info = assinatura.find("{%s}SignedInfo" % NS_DS)
    referencia = info.find("{%s}Reference" % NS_DS)
    uri = referencia.get("URI", "").lstrip("#")
    metodo = info.find("{%s}SignatureMethod" % NS_DS).get("Algorithm")
    algoritmo = "sha1" if metodo.endswith("rsa-sha1") else "sha256"
    alg = ALGORITMOS[algoritmo]
    canonicalizacao = info.find(
        "{%s}CanonicalizationMethod" % NS_DS).get("Algorithm", C14N_PADRAO)

    alvo = next((e for e in raiz.iter() if e.get("Id") == uri), None)
    if alvo is None:
        return {"assinado": True, "valida": False, "erro": "Referência perdida."}

    # remove o Signature antes de recalcular (transformacao enveloped)
    copia = etree.fromstring(etree.tostring(raiz))
    for s in copia.findall("{%s}Signature" % NS_DS):
        copia.remove(s)
    alvo_copia = next((e for e in copia.iter() if e.get("Id") == uri), None)
    digest = base64.b64encode(
        alg["hashlib"](_c14n(alvo_copia, canonicalizacao)).digest()).decode()
    esperado = referencia.find("{%s}DigestValue" % NS_DS).text

    certificado_b64 = assinatura.find(".//{%s}X509Certificate" % NS_DS).text
    from cryptography import x509

    cert = x509.load_der_x509_certificate(base64.b64decode(certificado_b64))
    valor = base64.b64decode(assinatura.find("{%s}SignatureValue" % NS_DS).text)
    try:
        cert.public_key().verify(
            valor, _c14n(info, canonicalizacao), padding.PKCS1v15(), alg["hash"]()
        )
        rsa_ok = True
    except Exception:
        rsa_ok = False

    return {
        "assinado": True,
        "algoritmo": algoritmo,
        "canonicalizacao": ("exclusiva" if canonicalizacao == C14N_EXCLUSIVA
                            else "inclusiva"),
        "digest_confere": digest == esperado,
        "rsa_confere": rsa_ok,
        "valida": digest == esperado and rsa_ok,
        "titular": cert.subject.rfc4514_string(),
    }
