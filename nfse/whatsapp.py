# -*- coding: utf-8 -*-
"""Abre a conversa do WhatsApp com o paciente, com a mensagem pronta.

**O que isto faz e o que NAO faz.** Monta um link `wa.me` que abre o
WhatsApp na conversa certa, com o texto ja escrito. Quem aperta enviar e a
pessoa -- nada sai sozinho, e nenhuma mensagem e disparada em lote. Isso e
deliberado: mensagem automatica para paciente e outra categoria de decisao,
que a clinica tem que tomar sabendo.

**O link nao anexa arquivo.** O `wa.me` so aceita texto; o PDF da nota, se a
clinica quiser mandar, e anexado a mao na propria conversa. Tentamos
resolver isso mandando o link direto da nota, mas o portal nacional
(`nfse.gov.br/consultapublica`) nao aceita a chave pela URL -- so tem o
formulario. Entao a mensagem leva a chave e diz onde consultar.
"""

from __future__ import annotations

from urllib.parse import quote

from .util import so_digitos

PORTAL = "https://www.nfse.gov.br/consultapublica"


def numero_para_whatsapp(telefone: str) -> str:
    """Converte o telefone do cadastro no formato que o WhatsApp espera.

    O TechCare grava como `(27)99814-8458`. O `wa.me` quer `5527998148458`:
    so digitos, com o codigo do pais na frente. Devolve vazio quando o
    numero nao serve -- e melhor nao oferecer o botao do que abrir uma
    conversa com quem nao existe.
    """
    digitos = so_digitos(telefone or "")
    if not digitos:
        return ""

    # Ja veio com o 55 na frente (13 digitos com celular, 12 com fixo).
    if len(digitos) in (12, 13) and digitos.startswith("55"):
        return digitos
    # Celular (11) ou fixo (10) com DDD.
    if len(digitos) in (10, 11):
        return "55" + digitos
    # Menos que isso e cadastro incompleto: "27", "9999", numero de ramal.
    return ""


def mensagem(nota: dict, unidade: dict) -> str:
    """Texto pronto para o paciente, na voz da clinica.

    Formal sem ser frio: quem recebe e paciente de consultorio, nao cliente
    de cobranca. A chave de acesso vai por extenso porque e ela que permite
    baixar o documento OFICIAL no portal -- e um PDF nosso, ainda que
    bonito, seria um documento nao-oficial circulando por WhatsApp.
    """
    nome = ""
    if nota.get("tomador"):
        primeiro = nota["tomador"].split()
        if primeiro:
            nome = primeiro[0].title()

    clinica = (unidade.get("nome_fantasia")
               or unidade.get("razao_social", "clínica"))

    linhas = []
    linhas.append("Olá%s! Somos da %s." % (", " + nome if nome else "", clinica))
    linhas.append("")
    linhas.append("Segue a nota fiscal do seu atendimento:")
    linhas.append("")

    if nota.get("numero_nota"):
        linhas.append("Nota fiscal nº %s" % nota["numero_nota"])
    if nota.get("valor"):
        linhas.append("Valor: R$ %s" % str(nota["valor"]).replace(".", ","))
    if nota.get("data"):
        linhas.append("Emitida em %s" % nota["data"])

    if nota.get("chave_acesso"):
        linhas += [
            "",
            "Para visualizar e baixar o documento oficial, acesse",
            PORTAL,
            "e informe a chave de acesso abaixo:",
            "",
            nota["chave_acesso"],
        ]

    linhas += ["", "Qualquer dúvida, estamos à disposição."]
    return chr(10).join(linhas)


def link(nota: dict, unidade: dict, telefone: str) -> str:
    """Link que abre a conversa com o texto pronto. Vazio se nao der."""
    numero = numero_para_whatsapp(telefone)
    if not numero:
        return ""
    return "https://wa.me/%s?text=%s" % (
        numero, quote(mensagem(nota, unidade), safe=""))
