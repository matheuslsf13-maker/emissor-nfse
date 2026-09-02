# -*- coding: utf-8 -*-
"""Gera o comprovante de emissao da NFS-e em PDF, para salvar ou imprimir.

**Isto NAO e o DANFSe oficial.** O documento da prefeitura segue um leiaute
padronizado por Nota Tecnica, com 21 secoes -- inclusive as que ficam vazias
no nosso caso (intermediario, retencoes federais, IBS/CBS, imunidade). Este
comprovante traz o que identifica a nota e permite conferi-la: prestador,
tomador, servico, valores e a chave de acesso.

Chamar de "DANFSe" seria enganoso, e alguem poderia apresenta-lo achando que
e o oficial. Quem precisar do documento exato usa a chave no portal -- e o
proprio comprovante diz isso.

**Por que gerar aqui, e nao baixar do portal.** A NFS-e que vale e o XML; o
papel e apenas a representacao dele. O portal nacional nao aceita a chave
pela URL e a prefeitura nao serve o DANFSe por endereco direto -- o caminho
de la seria digitar 50 digitos por nota, o que e inviavel quando o paciente
pede as notas do ano inteiro para a declaracao.

**Os dados saem do XML que nos mesmos assinamos**, guardado em
`dados/saida/`. Isso evita consultar a prefeitura nota a nota: ela processa
um pedido por vez por CNPJ, e cem consultas levariam muitos minutos. O
numero da nota e a chave, que so a prefeitura atribui, vem do controle.
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime

from . import config as cfgmod

NS = "{http://www.sped.fazenda.gov.br/nfse}"

# Preto no branco, sempre: o documento vai para o papel ou para a mao do
# paciente, e nao acompanha o tema da tela.
TINTA = (17, 17, 17)
TINTA_FRACA = (90, 90, 90)
LINHA = (200, 200, 200)


# As fontes embutidas do fpdf2 sao latin-1. Travessao, aspas curvas e
# reticencias -- comuns em texto copiado -- derrubariam a geracao inteira, e
# nome de paciente pode trazer qualquer coisa. Trocar e melhor do que
# carregar uma fonte Unicode de 1 MB para cada instalacao.
_TROCAS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
    " ": " ", "•": "-", "−": "-",
}


def _latin(texto: str) -> str:
    """Deixa o texto seguro para a fonte do PDF, sem perder o sentido."""
    if not texto:
        return ""
    for de, para in _TROCAS.items():
        texto = texto.replace(de, para)
    # O que sobrar de fora do latin-1 vira "?" em vez de derrubar o PDF: uma
    # letra trocada e melhor do que o paciente ficar sem o comprovante.
    return texto.encode("latin-1", "replace").decode("latin-1")


def _t(no, caminho: str) -> str:
    if no is None:
        return ""
    achado = no.find(NS + caminho.replace("/", "/" + NS))
    return (achado.text or "").strip() if achado is not None else ""


def _dinheiro(valor) -> str:
    """1234.5 -> '1.234,50'. Formato brasileiro, que e quem vai ler."""
    try:
        bruto = "{:,.2f}".format(float(valor))
    except (TypeError, ValueError):
        return str(valor or "0,00")
    # 1,234.50 -> 1.234,50: troca os separadores usando um marcador que nao
    # aparece em numero.
    return bruto.replace(",", "|").replace(".", ",").replace("|", ".")


def _porcento(valor) -> str:
    """'2.0000' -> '2,00%'. O XML traz quatro casas; ninguem le assim."""
    try:
        return ("%.2f" % float(valor)).replace(".", ",") + "%"
    except (TypeError, ValueError):
        return "%s%%" % (valor or "0")


def _data(iso: str) -> str:
    if not iso:
        return ""
    partes = str(iso)[:10].split("-")
    return "/".join(reversed(partes)) if len(partes) == 3 else str(iso)[:10]


def _documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 11:
        return "%s.%s.%s-%s" % (digitos[:3], digitos[3:6], digitos[6:9], digitos[9:])
    if len(digitos) == 14:
        return "%s.%s.%s/%s-%s" % (digitos[:2], digitos[2:5], digitos[5:8],
                                   digitos[8:12], digitos[12:])
    return valor or ""


def achar_xml(nome_arquivo: str) -> str:
    """Onde esta o XML desta nota, entre as pastas de saida.

    O controle guarda so o nome do arquivo, porque a pasta muda a cada lote.
    Procurar aqui evita ter que migrar o banco inteiro.
    """
    if not nome_arquivo or not os.path.isdir(cfgmod.PASTA_SAIDA):
        return ""
    for pasta in os.listdir(cfgmod.PASTA_SAIDA):
        caminho = os.path.join(cfgmod.PASTA_SAIDA, pasta, nome_arquivo)
        if os.path.exists(caminho):
            return caminho
    return ""


def dados_do_xml(caminho: str, registro: dict) -> dict:
    """Junta o XML assinado com o que so o controle sabe (numero e chave)."""
    from lxml import etree

    raiz = etree.parse(caminho).getroot()
    info = raiz.find(NS + "infNFSe") if etree.QName(raiz).localname != "infNFSe" else raiz
    emit = info.find(NS + "emit")
    ender = emit.find(NS + "enderNac") if emit is not None else None
    valores = info.find(NS + "valores")
    dps = info.find(NS + "DPS/" + NS + "infDPS")
    toma = dps.find(NS + "toma") if dps is not None else None
    fim = toma.find(NS + "end") if toma is not None else None
    nac = fim.find(NS + "endNac") if fim is not None else None
    serv = dps.find(NS + "serv/" + NS + "cServ") if dps is not None else None

    return {
        # Numero e chave vem da prefeitura, nao do nosso XML.
        "numero": registro.get("numero_nota") or "",
        "chave": registro.get("chave_acesso") or "",
        "emitida_em": registro.get("transmitida_em") or "",
        "ambiente": registro.get("ambiente") or "",
        "municipio": _t(info, "xLocEmi"),
        "serie": _t(dps, "serie"),
        "numero_dps": _t(dps, "nDPS"),
        "competencia": _t(dps, "dCompet"),
        "prestador": {
            "nome": _t(emit, "xNome"),
            "documento": _t(emit, "CNPJ") or _t(emit, "CPF"),
            "im": _t(emit, "IM"),
            "endereco": "%s, %s%s · %s · CEP %s" % (
                _t(ender, "xLgr"), _t(ender, "nro"),
                " — " + _t(ender, "xCpl") if _t(ender, "xCpl") else "",
                _t(ender, "xBairro"), _t(ender, "CEP")),
            "email": _t(emit, "email"),
        },
        "tomador": {
            "nome": _t(toma, "xNome"),
            "documento": _t(toma, "CPF") or _t(toma, "CNPJ"),
            "endereco": "%s, %s · %s%s" % (
                _t(fim, "xLgr"), _t(fim, "nro"), _t(fim, "xBairro"),
                " · CEP " + _t(nac, "CEP") if _t(nac, "CEP") else ""),
        },
        "servico": {
            "descricao": _t(serv, "xDescServ"),
            "codigo": _t(serv, "cTribNac"),
            "nbs": _t(serv, "cNBS"),
        },
        "valores": {
            "base": _t(valores, "vBC"),
            "aliquota": _t(valores, "pAliqAplic"),
            "iss": _t(valores, "vISSQN"),
            "liquido": _t(valores, "vLiq"),
        },
    }


def _uma_nota(pdf, d: dict) -> None:
    """Desenha uma nota em uma pagina."""
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    def rotulo(texto):
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(*TINTA_FRACA)
        pdf.cell(0, 4, _latin(texto).upper(), new_x="LMARGIN", new_y="NEXT")

    def corpo(texto, tamanho=9.5, estilo=""):
        pdf.set_font("Helvetica", estilo, tamanho)
        pdf.set_text_color(*TINTA)
        pdf.multi_cell(largura, 4.6, _latin(texto), new_x="LMARGIN", new_y="NEXT")

    def regua(espesso=False):
        pdf.ln(1.5)
        pdf.set_draw_color(*(TINTA if espesso else LINHA))
        pdf.set_line_width(0.5 if espesso else 0.2)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(2.5)

    # --- cabecalho ---
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*TINTA)
    pdf.cell(largura - 40, 7, _latin("Comprovante de emissão de NFS-e"))
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(40, 7, _latin(d["numero"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*TINTA_FRACA)
    pdf.cell(largura - 40, 4, _latin("Município de %s · Padrão Nacional"
                                     % (d["municipio"] or "").title()))
    pdf.cell(40, 4, _latin("NOTA FISCAL Nº"), align="R", new_x="LMARGIN", new_y="NEXT")
    regua(espesso=True)

    # --- chave ---
    rotulo("Chave de acesso")
    pdf.set_font("Courier", "", 10)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 5, _latin(d["chave"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*TINTA_FRACA)
    pdf.cell(0, 4, _latin("Consulte ou baixe a nota oficial em "
                          "nfse.gov.br/consultapublica"),
             new_x="LMARGIN", new_y="NEXT")
    regua()

    # --- datas ---
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*TINTA_FRACA)
    for titulo in ("EMITIDA EM", "COMPETÊNCIA", "DPS Nº / SÉRIE"):
        pdf.cell(largura / 3, 4, _latin(titulo))
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*TINTA)
    pdf.cell(largura / 3, 5, _latin(_data(d["emitida_em"])))
    pdf.cell(largura / 3, 5, _latin(_data(d["competencia"])))
    pdf.cell(largura / 3, 5, _latin("%s / %s" % (d["numero_dps"], d["serie"])))
    pdf.ln(6)
    regua()

    # --- partes ---
    for titulo, parte in (("Prestador do serviço", d["prestador"]),
                          ("Tomador do serviço", d["tomador"])):
        rotulo(titulo)
        corpo(parte["nome"], 11, "B")
        linha = _documento(parte["documento"])
        if parte.get("im"):
            linha += " · Inscrição municipal %s" % parte["im"]
        corpo(linha, 9)
        if parte.get("endereco", "").strip(" ,·"):
            corpo(parte["endereco"], 9)
        if parte.get("email"):
            corpo(parte["email"], 9)
        regua()

    # --- servico ---
    rotulo("Serviço prestado")
    corpo(d["servico"]["descricao"], 11, "B")
    corpo("Código de tributação nacional %s · NBS %s"
          % (d["servico"]["codigo"], d["servico"]["nbs"]), 9)
    regua()

    # --- valores ---
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*TINTA_FRACA)
    for titulo in ("BASE DE CÁLCULO", "ALÍQUOTA", "ISS APURADO", "VALOR TOTAL"):
        pdf.cell(largura / 4, 4, _latin(titulo))
    pdf.ln(4)
    pdf.set_text_color(*TINTA)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(largura / 4, 6, _latin("R$ " + _dinheiro(d["valores"]["base"])))
    pdf.cell(largura / 4, 6, _latin(_porcento(d["valores"]["aliquota"])))
    pdf.cell(largura / 4, 6, _latin("R$ " + _dinheiro(d["valores"]["iss"])))
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(largura / 4, 6, _latin("R$ " + _dinheiro(d["valores"]["liquido"])))
    pdf.ln(9)
    regua(espesso=True)

    # --- rodape ---
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(*TINTA_FRACA)
    pdf.multi_cell(largura, 3.6, _latin(
                   "Este comprovante reúne os dados da Nota Fiscal de Serviço "
                   "eletrônica emitida. Não substitui o DANFSe oficial: para "
                   "obtê-lo, informe a chave de acesso acima em "
                   "nfse.gov.br/consultapublica. A NFS-e que tem validade "
                   "fiscal é o documento eletrônico, e a chave permite "
                   "conferi-lo a qualquer momento."))
    if d.get("ambiente") and d["ambiente"] != "producao":
        pdf.ln(1)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(180, 40, 30)
        pdf.multi_cell(largura, 5, _latin("AMBIENTE DE TESTE - SEM VALOR FISCAL"))


def gerar(notas: list) -> bytes:
    """PDF com uma pagina por nota. Devolve os bytes."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(18, 16, 18)
    for dados in notas:
        pdf.add_page()
        _uma_nota(pdf, dados)
    saida = pdf.output()
    return bytes(saida)


def nome_do_arquivo(notas: list) -> str:
    """Nome que o paciente entende ao receber o arquivo."""
    if not notas:
        return "notas.pdf"
    nome = (notas[0]["tomador"]["nome"] or "paciente").title()
    nome = re.sub(r"[^\w\s-]", "", nome).strip().replace(" ", "-")
    if len(notas) == 1:
        return "NFSe-%s-%s.pdf" % (notas[0]["numero"] or "s-numero", nome)
    anos = sorted({(n.get("competencia") or "")[:4] for n in notas if n.get("competencia")})
    periodo = anos[0] if len(anos) == 1 else "%s-a-%s" % (anos[0], anos[-1]) if anos else ""
    return "NFSe-%s-%s-notas%s.pdf" % (
        nome, len(notas), "-" + periodo if periodo else "")
