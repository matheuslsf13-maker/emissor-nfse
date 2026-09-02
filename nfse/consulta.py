# -*- coding: utf-8 -*-
"""Consulta de nota ja emitida no WebService da prefeitura.

Serve para conferir, do lado da prefeitura, uma nota que o sistema diz ter
emitido -- sem depender do portal web e sem precisar do login da clinica.

O formato do pedido veio do modelo oficial da SIL
(`xmlNacionalModeloConsulta.xml`), nao de tentativa e erro:

    <ConsultarNFE>
      <consul><CNPJ>...</CNPJ></consul>     CNPJ do prestador, tomador ou
      <chaveAcesso>...</chaveAcesso>        intermediario da nota
      <DPS></DPS>                           alternativa: a chave do DPS
      <Signature .../>                      assinado, como a emissao
    </ConsultarNFE>

Duas coisas que o servidor exige e que a documentacao nao diz:

* **o CNPJ do consulente e obrigatorio** -- sem ele o retorno e
  `Nao foi localizado o CNPJ ou CPF do Consulente`;
* **o pedido tem que ser assinado**, com a mesma canonicalizacao exclusiva da
  emissao, mas com `URI=""` (documento inteiro), porque `<ConsultarNFE>` nao
  tem `Id` em elemento nenhum.

Ha limite de concorrencia por contribuinte: o servidor recusa uma segunda
consulta enquanto a anterior nao terminou (`Ja consta uma requisicao em
andamento`). Por isso a consulta e sequencial e nunca em paralelo.
"""

from __future__ import annotations

from html import unescape

from lxml import etree

from .assinatura import carregar_pfx
from .envio import NS_SIL, _extrair_retorno, montar_envelope, situacao


def montar_consulta(cnpj: str, chave_acesso: str = "", dps: str = "") -> bytes:
    """XML de pedido de consulta, ainda sem assinatura."""
    if not chave_acesso and not dps:
        raise ValueError("Informe a chave de acesso ou a chave do DPS.")
    raiz = etree.Element("ConsultarNFE")
    consul = etree.SubElement(raiz, "consul")
    etree.SubElement(consul, "CNPJ").text = cnpj
    etree.SubElement(raiz, "chaveAcesso").text = chave_acesso
    etree.SubElement(raiz, "DPS").text = dps
    return etree.tostring(raiz, xml_declaration=True, encoding="UTF-8",
                          pretty_print=False)


def _texto_solto(texto: str, tag: str) -> str:
    """Le uma tag do envelope externo por regex.

    Precisa ser por texto porque o <Status> fica no <Retorno> de fora, e a
    raiz ja foi trocada pela nota que vinha dentro de <XML>.
    """
    import re

    achado = re.search(r"<%s>(.*?)</%s>" % (tag, tag), texto, re.S)
    return achado.group(1).strip() if achado else ""


def _texto(raiz, caminho: str) -> str:
    achado = raiz.find(caminho)
    return (achado.text or "").strip() if achado is not None else ""


def interpretar_consulta(bruto: str) -> dict:
    """Le o retorno da consulta em algo que a tela consegue mostrar."""
    texto = (bruto or "").strip()
    if "&lt;" in texto or "&amp;" in texto:
        texto = unescape(texto)
    resposta = {"bruto": texto, "encontrada": False, "situacao": "",
                "numero": "", "chave": "", "emitida_em": "", "valor": "",
                "tomador": "", "documento_tomador": "", "mensagem": ""}
    if not texto:
        resposta["mensagem"] = "A prefeitura respondeu sem conteúdo."
        return resposta
    try:
        raiz = etree.fromstring(texto.encode("utf-8"))
    except Exception:
        resposta["mensagem"] = "Não consegui ler a resposta da prefeitura."
        return resposta

    # A nota inteira vem ESCAPADA de novo, dentro de <XML>. Sem desescapar
    # esse segundo nivel, o retorno parece vazio: o Status diz sucesso e
    # nenhum campo aparece.
    interno = raiz.find(".//XML")
    if interno is not None and (interno.text or "").strip():
        try:
            nota = etree.fromstring(
                unescape(interno.text).strip().encode("utf-8"))
            resposta["xml_nota"] = etree.tostring(
                nota, encoding="unicode", pretty_print=True)
            raiz = nota
        except Exception:
            pass

    def buscar(*nomes):
        for nome in nomes:
            for elemento in raiz.iter():
                if etree.QName(elemento).localname == nome and (elemento.text or "").strip():
                    return elemento.text.strip()
        return ""

    status = _texto_solto(texto, "Status")
    erro = _texto_solto(texto, "MensagemErro")
    resposta["numero"] = buscar("nNFSe", "NumeroNfse", "Numero")
    resposta["chave"] = buscar("chaveAcesso", "ChaveAcesso")
    resposta["emitida_em"] = buscar("dhProc", "dhEmi", "DataEmissao")
    resposta["valor"] = buscar("vLiq", "ValorLiquido", "vServ")
    # O tomador tem que sair de dentro de <toma>: o primeiro <xNome> do
    # documento e o do EMITENTE, e sem essa qualificacao a tela mostraria a
    # clinica no lugar do paciente.
    NS_NFSE = "{http://www.sped.fazenda.gov.br/nfse}"
    toma = raiz.find(".//%stoma" % NS_NFSE)
    if toma is not None:
        nome = toma.find("%sxNome" % NS_NFSE)
        resposta["tomador"] = (nome.text or "").strip() if nome is not None else ""
        for tag in ("CPF", "CNPJ"):
            doc = toma.find("%s%s" % (NS_NFSE, tag))
            if doc is not None and (doc.text or "").strip():
                resposta["documento_tomador"] = doc.text.strip()
                break
    resposta["situacao"] = status
    resposta["mensagem"] = erro
    if not resposta["chave"]:
        # A chave de acesso vive no atributo Id do infNFSe: NFS + 50 digitos.
        info = raiz.find(".//{http://www.sped.fazenda.gov.br/nfse}infNFSe")
        if info is not None:
            resposta["chave"] = (info.get("Id") or "").replace("NFS", "", 1)
    resposta["encontrada"] = bool(resposta["numero"]) and not erro
    return resposta


def consultar(config, unidade: str, chave_acesso: str = "", dps: str = "",
              timeout: int = 60) -> dict:
    """Consulta uma nota. Assina o pedido com o certificado da unidade."""
    import requests

    estado = situacao(config)
    dados = config.unidades[unidade]
    caminho = config.caminho_certificado(unidade)
    certificado = carregar_pfx(caminho, config.senha_certificado(unidade))

    from .assinatura import assinar

    pedido = montar_consulta(dados["cnpj"], chave_acesso, dps)
    assinado = assinar(pedido, "", certificado)
    envelope = montar_envelope(
        assinado,
        config.municipio.get("operacoes", {}).get(
            "consultar", "NotaFiscalNacionalConsultar"),
        config.municipio.get("namespace_soap", NS_SIL),
    )
    resposta = requests.post(
        estado["url"], data=envelope,
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
        timeout=timeout,
    )
    lido = interpretar_consulta(
        _extrair_retorno(resposta.text) or resposta.text)
    lido["http"] = resposta.status_code
    lido["ambiente"] = estado["ambiente"]
    return lido
