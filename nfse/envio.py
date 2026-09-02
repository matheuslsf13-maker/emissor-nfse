# -*- coding: utf-8 -*-
"""Transmissao ao WebService municipal de Vila Velha (SIL Tecnologia).

O contrato foi lido direto do WSDL, nos dois ambientes (identicos):

    https://tributacao.vilavelha.es.gov.br/tbw/services/NotaFiscalNacional?wsdl
    http://tributacao.vilavelha.es.gov.br:8080/tbwhomologacao/services/NotaFiscalNacional?wsdl

**Escolher o servico certo importa.** O servidor publica varios no mesmo
caminho `/services/`:

    WSEntrada, WSSaida, WSUtil, WSInterface   interfaces genericas da SIL
    Abrasf10, Abrasf23, Abrasf24              protocolo ABRASF (legado)
    NotaFiscalNacional                        padrao nacional -- e o nosso

`NotaFiscalNacional` expoe quatro operacoes, SOAP 1.1 document/literal,
soapAction vazio, todas recebendo so `<xml>` e devolvendo `<return>`:

    NotaFiscalNacionalGerar        emitir
    NotaFiscalNacionalConsultar    consultar
    NotaFiscalNacionalCancelar     cancelar
    NotaFiscalNacionalSubstituir   substituir

Nao ha usuario nem senha no envelope: **a unica credencial e o certificado
que assina o XML**. A prefeitura reconhece o CNPJ pela assinatura. Por isso a
"habilitacao" que falta e o credenciamento do CNPJ para emitir por
WebService -- ter o certificado nao basta, ele precisa estar autorizado.

Enquanto `permitir_envio` estiver desligado, `enviar()` levanta
`EnvioIndisponivel` explicando o que falta. Melhor falhar dizendo o porque do
que transmitir as cegas contra um sistema da prefeitura.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_SIL = "http://webservices.sil.com/"


class EnvioIndisponivel(Exception):
    pass


def montar_envelope(xml_assinado: bytes,
                    operacao: str = "NotaFiscalNacionalGerar",
                    namespace: str = NS_SIL) -> bytes:
    """Envelope SOAP 1.1 para uma das operacoes de NotaFiscalNacional.

    O XML assinado entra escapado dentro de `<xml>`, que o WSDL declara como
    `xs:string`. Nada e reserializado: os bytes assinados vao como estao,
    senao a assinatura quebra.

    **`<xml>` NAO pode ficar no namespace da SIL.** O XSD do servico nao
    declara `elementFormDefault`, entao vale o padrao `unqualified`: o
    elemento da operacao e qualificado, os filhos dele nao. Usando
    `xmlns=` (namespace default) no elemento da operacao, `<xml>` herdaria o
    namespace, o servidor nao encontraria o parametro e receberia string
    vazia -- e responde `XML invalido: Fim prematuro do arquivo`. Por isso o
    namespace vai por PREFIXO, deixando `<xml>` sem namespace nenhum.
    """
    corpo = xml_assinado.decode("utf-8")
    corpo = re.sub(r"^<\?xml[^>]*\?>\s*", "", corpo)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<soap:Envelope xmlns:soap="%s"><soap:Body>'
        '<sil:%s xmlns:sil="%s"><xml>%s</xml></sil:%s>'
        "</soap:Body></soap:Envelope>"
        % (NS_SOAP, operacao, namespace, escape(corpo), operacao)
    ).encode("utf-8")


def situacao(config) -> dict:
    """Diz, em portugues, se da para transmitir e o que ainda falta."""
    municipio = config.municipio
    endpoints = municipio.get("endpoints", {})
    ambiente = config.faturamento.get("ambiente", "homologacao")
    url = endpoints.get(ambiente, "")

    faltando = []
    if not url:
        faltando.append("a URL do ambiente de %s" % ambiente)
    if not municipio.get("operacao_soap"):
        faltando.append("o nome da operação SOAP")
    if not municipio.get("permitir_envio"):
        faltando.append(
            "o credenciamento do CNPJ para emitir por WebService, que a "
            "prefeitura precisa liberar — depois disso, ligar permitir_envio "
            "em config/empresas.json"
        )
    return {
        "pronto": not faltando,
        "ambiente": ambiente,
        "url": url,
        "operacao": municipio.get("operacao_soap", ""),
        "faltando": faltando,
    }


def enviar(xml_assinado: bytes, config, acao: str = "gerar",
           timeout: int = 60) -> dict:
    """Transmite o XML assinado. `acao`: gerar | consultar | cancelar | substituir."""
    estado = situacao(config)
    if not estado["pronto"]:
        raise EnvioIndisponivel(
            "O envio automático ainda não está liberado. Falta: %s."
            % "; ".join(estado["faltando"])
        )

    import requests

    municipio = config.municipio
    operacoes = municipio.get("operacoes", {})
    operacao = operacoes.get(acao) or municipio["operacao_soap"]
    envelope = montar_envelope(
        xml_assinado, operacao, municipio.get("namespace_soap", NS_SIL)
    )
    resposta = requests.post(
        estado["url"],
        data=envelope,
        headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": ""},
        timeout=timeout,
    )
    return {
        "operacao": operacao,
        "status": resposta.status_code,
        "corpo": resposta.text,
        "retorno": _extrair_retorno(resposta.text),
    }


def _extrair_retorno(texto: str) -> str:
    """Tira o conteudo de <return> da resposta."""
    achado = re.search(r"<return>(.*?)</return>", texto or "", re.S)
    return achado.group(1).strip() if achado else ""


# --------------------------------------------------------------------------
# Leitura do retorno
#
# O WSDL so diz que <return> e uma string -- nao descreve o que vem dentro.
# Ate a primeira transmissao real, nao da para saber o formato exato. Por
# isso esta funcao tenta reconhecer os campos mais provaveis e SEMPRE guarda
# o texto cru: e olhando o cru da primeira nota que se aprende o resto.
# --------------------------------------------------------------------------

CAMPOS_NUMERO = ("nNFSe", "NumeroNfse", "Numero", "numeroNota")
CAMPOS_CODIGO = ("cVerif", "CodigoVerificacao", "codigoVerificacao")
CAMPOS_CHAVE = ("chaveAcesso", "ChaveAcesso", "Id")
# Vila Velha responde <Retorno><Status>ERRO</Status><MensagemErro>...
CAMPOS_ERRO = ("MensagemErro", "Mensagem", "mensagem", "erro", "Erro",
               "xMotivo", "descricao")
CAMPOS_STATUS = ("Status", "cStat", "codigo", "Codigo", "status")


def _primeiro(texto: str, tags) -> str:
    for tag in tags:
        achado = re.search(r"<%s>(.*?)</%s>" % (tag, tag), texto, re.S | re.I)
        if achado and achado.group(1).strip():
            return achado.group(1).strip()
    return ""


def interpretar_retorno(bruto: str) -> dict:
    """Tenta extrair numero, codigo de verificacao e mensagem do retorno."""
    texto = (bruto or "").strip()
    # A prefeitura devolve o XML escapado dentro do <return>, com &lt; &quot;
    # e &#xD;. Desescapar sempre que houver entidade -- sem isso a mensagem de
    # erro dela chega ilegivel, que e justamente quando mais se precisa dela.
    if "&" in texto:
        from html import unescape

        texto = unescape(texto)

    numero = _primeiro(texto, CAMPOS_NUMERO)
    codigo = _primeiro(texto, CAMPOS_CODIGO)
    chave = _primeiro(texto, CAMPOS_CHAVE)
    mensagem = _primeiro(texto, CAMPOS_ERRO)
    status = _primeiro(texto, CAMPOS_STATUS)

    # Vila Velha usa Status=PROCESSADO_COM_SUCESSO no aceite e Status=ERRO
    # na recusa, com a explicacao em MensagemErro.
    sucesso_declarado = "SUCESSO" in status.upper()
    erro_declarado = status.upper() in ("ERRO", "REJEITADO", "ERROR")
    parece_erro = erro_declarado or (bool(mensagem) and not numero)
    if not texto:
        parece_erro = True
        mensagem = "A prefeitura respondeu sem conteúdo."

    return {
        "aceita": ((bool(numero) or status == "100" or sucesso_declarado)
                   and not erro_declarado),
        "numero": numero,
        "codigo_verificacao": codigo,
        "chave": chave,
        "status": status,
        "mensagem": mensagem,
        "parece_erro": parece_erro,
        "bruto": bruto or "",
    }
