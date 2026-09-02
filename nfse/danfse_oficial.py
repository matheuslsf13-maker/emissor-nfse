# -*- coding: utf-8 -*-
"""DANFSe: o documento no leiaute oficial, montado do XML da Receita.

**Por que da para fazer isto.** O DANFSe nao e um arquivo que a prefeitura
guarda e entrega -- e uma *representacao grafica* padronizada da NFS-e. Quem
emite pelo portal recebe um PDF gerado ali na hora, a partir do mesmo XML.
E assim que todo sistema emissor imprime nota: seguindo o leiaute publicado.
Nao ha download de PDF a fazer, nem no WebService municipal (quatro
operacoes, nenhuma devolve documento) nem no ambiente nacional
(`/danfse/{chave}` responde 501, servico nao implementado).

**Fidelidade.** O leiaute aqui foi medido no DANFSe que a propria prefeitura
emitiu para a nota 8966: pagina A4, moldura em 5pt, colunas em x=10, 155,
310 e 445, rotulos em Helvetica-Bold 7 (6 quando longos), valores em
Helvetica 7, e onze linhas separando os blocos.

**A fonte dos dados e o XML oficial**, baixado do ambiente nacional com o
certificado da clinica -- nao a nossa reconstrucao do que enviamos. Isso
importa: numero da nota, situacao, data de processamento e o nome com
acentuacao sao preenchidos pela Receita, e so aparecem la.

Duas diferencas deliberadas em relacao ao emissor de Vila Velha: escrevemos
"DANFSe" (o deles diz "DANFESe") e o campo "Exclusoes e Reducoes da Base de
Calculo" sai vazio, como manda o padrao -- o deles repete ali o valor do
ISS, que nao e uma exclusao de base de nada.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree as ET

from .municipios import nome_por_codigo

NS = "{http://www.sped.fazenda.gov.br/nfse}"

# Colunas e medidas tiradas do DANFSe real.
COLUNAS = (10.0, 155.0, 310.0, 445.0)
SEPARADORES = (50.5, 148.5, 235.5, 301.5, 369.5, 382.5, 441.5, 539.5,
               587.5, 671.5, 726.5)
MOLDURA = (5.0, 5.0, 584.0, 831.0)   # x, y, largura, altura

# Helvetica sobe 0,718 do corpo acima da linha de base. O leiaute foi medido
# pelo topo dos caracteres, entao e por aqui que se converte para a linha de
# base que o fpdf espera.
ASCENDER = 0.718

SITUACAO = {"100": "NFS-e Gerada", "101": "NFS-e Cancelada",
            "102": "NFS-e Substituída"}
EMITENTE = {"1": "Prestador de Serviços", "2": "Tomador de Serviços",
            "3": "Intermediário de Serviços"}
SIMPLES = {"0": "Não optante", "1": "Não optante",
           "2": "Optante - MEI", "3": "Optante - ME/EPP"}
REGIME_ESPECIAL = {"0": "Nenhum", "1": "Ato Cooperado",
                   "2": "Estimativa", "3": "Microempresa Municipal",
                   "4": "Notário ou Registrador", "5": "Profissional Autônomo",
                   "6": "Sociedade de Profissionais"}
TRIBUTACAO_ISSQN = {"1": "Operação Tributável",
                    "2": "Exportação de Serviço",
                    "3": "Não Incidência",
                    "4": "Imunidade"}
RETENCAO_ISSQN = {"1": "Não retido", "2": "Retido pelo Tomador",
                  "3": "Retido pelo Intermediário"}
VAZIO = "-"


def _txt(no, caminho: str, padrao: str = "") -> str:
    """Texto de um caminho relativo, com o namespace aplicado a cada passo."""
    if no is None:
        return padrao
    achado = no.find("/".join(NS + parte for parte in caminho.split("/")))
    return (achado.text or "").strip() if achado is not None else padrao


def _data(iso: str) -> str:
    """2026-09-02T00:00:00-03:00 -> 02/09/2026."""
    if not iso or len(iso) < 10:
        return ""
    ano, mes, dia = iso[:10].split("-")
    return "%s/%s/%s" % (dia, mes, ano)


def _dinheiro(valor: str) -> str:
    try:
        bruto = "{:,.2f}".format(float(valor))
    except (TypeError, ValueError):
        return VAZIO
    return "R$ " + bruto.replace(",", "|").replace(".", ",").replace("|", ".")


def _porcento(valor: str) -> str:
    try:
        return "{:.2f}".format(float(valor)).replace(".", ",") + "%"
    except (TypeError, ValueError):
        return VAZIO


def _documento(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 14:
        return "%s.%s.%s/%s-%s" % (digitos[:2], digitos[2:5], digitos[5:8],
                                   digitos[8:12], digitos[12:])
    if len(digitos) == 11:
        return "%s.%s.%s-%s" % (digitos[:3], digitos[3:6], digitos[6:9],
                                digitos[9:])
    return valor or VAZIO


def _cep(valor: str) -> str:
    digitos = re.sub(r"\D", "", valor or "")
    if len(digitos) == 8:
        return "%s-%s" % (digitos[:5], digitos[5:])
    return valor or ""


def _codigo_servico(codigo: str) -> str:
    """041201 -> 04.12.01, como o DANFSe mostra."""
    digitos = re.sub(r"\D", "", codigo or "")
    if len(digitos) == 6:
        return "%s.%s.%s" % (digitos[:2], digitos[2:4], digitos[4:6])
    return codigo or ""


def _codigo_nbs(codigo: str) -> str:
    """123012300 -> 1.2301.23.00."""
    digitos = re.sub(r"\D", "", codigo or "")
    if len(digitos) == 9:
        return "%s.%s.%s.%s" % (digitos[0], digitos[1:5], digitos[5:7],
                                digitos[7:])
    return codigo or ""


def _municipio(codigo: str, uf: str = "") -> str:
    nome = nome_por_codigo(codigo) or ""
    if not nome:
        return VAZIO
    return "%s / %s" % (nome, uf) if uf else nome


def ler(xml: bytes) -> dict:
    """Le o XML oficial e devolve os campos que o DANFSe mostra."""
    raiz = ET.fromstring(xml)
    inf = raiz.find(NS + "infNFSe")
    if inf is None:
        raise ValueError("Este XML não parece uma NFS-e.")

    dps = inf.find(NS + "DPS/" + NS + "infDPS")
    emit = inf.find(NS + "emit")
    ender = emit.find(NS + "enderNac") if emit is not None else None
    prest = dps.find(NS + "prest") if dps is not None else None
    toma = dps.find(NS + "toma") if dps is not None else None
    serv = dps.find(NS + "serv") if dps is not None else None
    vals = inf.find(NS + "valores")
    regime = prest.find(NS + "regTrib") if prest is not None else None
    trib_mun = None
    if dps is not None:
        trib_mun = dps.find(NS + "valores/" + NS + "trib/" + NS + "tribMun")

    end_toma = toma.find(NS + "end") if toma is not None else None
    end_nac = end_toma.find(NS + "endNac") if end_toma is not None else None
    doc_toma = (_txt(toma, "CNPJ") or _txt(toma, "CPF") or _txt(toma, "NIF"))

    uf_emit = _txt(ender, "UF")
    papel = EMITENTE.get(_txt(dps, "tpEmit"), VAZIO)

    return {
        "chave": (inf.get("Id") or "").replace("NFS", ""),
        "municipio_emissao": "%s / %s" % (_txt(inf, "xLocEmi"), uf_emit),
        "ambiente_gerador": _txt(inf, "ambGer"),
        "tipo_ambiente": _txt(dps, "tpAmb"),
        "numero": _txt(inf, "nNFSe"),
        "competencia": _data(_txt(dps, "dCompet")),
        "emissao_nfse": _data(_txt(inf, "dhProc")),
        "numero_dps": _txt(dps, "nDPS"),
        "serie_dps": _txt(dps, "serie"),
        "emissao_dps": _data(_txt(dps, "dhEmi")),
        "emitente": papel,
        "situacao": SITUACAO.get(_txt(inf, "cStat"), _txt(inf, "cStat")),
        "finalidade": "NFS-e regular",
        "prestador": {
            "papel": papel,
            "documento": _documento(_txt(emit, "CNPJ") or _txt(emit, "CPF")),
            "im": _txt(emit, "IM") or VAZIO,
            "fone": _txt(emit, "fone") or VAZIO,
            "nome": _txt(emit, "xNome"),
            # xLocEmi, e nao a tabela do IBGE: e o nome como a prefeitura
            # o grava, e e ele que sai no documento dela.
            "municipio": "%s / %s" % (_txt(inf, "xLocEmi"), uf_emit),
            "ibge_cep": "%s / %s" % (_txt(ender, "cMun"),
                                     _cep(_txt(ender, "CEP"))),
            "endereco": " ".join(p for p in (_txt(ender, "xLgr"),
                                             _txt(ender, "nro"),
                                             _txt(ender, "xCpl")) if p),
            "email": _txt(emit, "email") or VAZIO,
            "simples": SIMPLES.get(_txt(regime, "opSimpNac"), VAZIO),
        },
        "tomador": {
            "documento": _documento(doc_toma),
            "im": _txt(toma, "IM") or VAZIO,
            "fone": _txt(toma, "fone") or VAZIO,
            "nome": _txt(toma, "xNome"),
            "municipio": _municipio(_txt(end_nac, "cMun"), uf_emit),
            "ibge_cep": "%s / %s" % (_txt(end_nac, "cMun"),
                                     _cep(_txt(end_nac, "CEP"))),
            "endereco": ", ".join(p for p in (_txt(end_toma, "xLgr"),
                                              _txt(end_toma, "nro"),
                                              _txt(end_toma, "xBairro"))
                                  if p) or VAZIO,
            "email": _txt(toma, "email") or VAZIO,
        },
        "servico": {
            "codigo": _codigo_servico(_txt(serv, "cServ/cTribNac")),
            "nbs": _codigo_nbs(_txt(serv, "cServ/cNBS")),
            "local": "%s/ Brasil" % _municipio(
                _txt(serv, "locPrest/cLocPrestacao"), uf_emit),
            "descricao": _txt(serv, "cServ/xDescServ"),
        },
        "issqn": {
            "tipo": TRIBUTACAO_ISSQN.get(_txt(trib_mun, "tribISSQN"), VAZIO),
            "municipio_incidencia": "%s / %s/ -" % (
                _txt(inf, "xLocIncid") or VAZIO, uf_emit),
            "regime_especial": REGIME_ESPECIAL.get(
                _txt(regime, "regEspTrib"), VAZIO),
            "imunidade": VAZIO,
            "suspensao": "Não",
            "processo": VAZIO,
            "base": _dinheiro(_txt(vals, "vBC")),
            "aliquota": _porcento(_txt(vals, "pAliqAplic")),
            "retencao": RETENCAO_ISSQN.get(_txt(trib_mun, "tpRetISSQN"),
                                           VAZIO),
            "apurado": _dinheiro(_txt(vals, "vISSQN")),
        },
        "totais": {
            "servico": _dinheiro(_txt(dps, "valores/vServPrest/vServ")),
            "liquido": _dinheiro(_txt(vals, "vLiq")),
        },
    }


def gerar(xmls) -> bytes:
    """Monta o PDF do DANFSe. Aceita um XML ou varios, um por pagina.

    Varios importa no pedido de fim de ano: o paciente quer as notas do ano
    inteiro em um arquivo so, e cada uma tem que sair no leiaute completo.
    """
    from fpdf import FPDF

    if isinstance(xmls, (bytes, bytearray, str)):
        xmls = [xmls]
    if not xmls:
        raise ValueError("Nenhuma nota para montar o PDF.")

    pdf = FPDF(unit="pt", format="A4")
    pdf.set_auto_page_break(False)
    for xml in xmls:
        _pagina(pdf, ler(xml))
    return bytes(pdf.output())


def _pagina(pdf, d: dict) -> None:
    """Desenha uma nota inteira numa pagina nova."""
    pdf.add_page()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.5)
    pdf.rect(*MOLDURA)

    def escrever(x, topo, texto, negrito=False, tamanho=7.0):
        """Posiciona pelo TOPO do texto, que e como o leiaute foi medido.

        O `text()` do fpdf recebe a linha de base; o topo fica um ascender
        acima dela. Sem essa conversao tudo desce ~2pt e nada alinha com o
        documento da prefeitura.
        """
        if texto in (None, ""):
            return
        pdf.set_font("Helvetica", "B" if negrito else "", tamanho)
        pdf.text(x, topo + tamanho * ASCENDER, str(texto))

    def faixa(y, rotulos, valores, tamanho=7.0):
        """Uma linha de rotulos com a linha de valores logo abaixo."""
        for coluna, rotulo in zip(COLUNAS, rotulos):
            escrever(coluna, y, rotulo, True, tamanho)
        for coluna, valor in zip(COLUNAS, valores):
            escrever(coluna, y + 10, valor)

    # -- cabecalho ---------------------------------------------------------
    escrever(231, 10.2, "DANFSe v2.0", True, 10)
    escrever(196, 24.2, "Documento Auxiliar da NFS-e", True, 10)
    for linha, (rotulo, valor) in enumerate((
            ("Município:", d["municipio_emissao"]),
            ("Ambiente Gerador:", d["ambiente_gerador"]),
            ("Tipo de Ambiente:", d["tipo_ambiente"]))):
        escrever(437, 12 + linha * 12, rotulo, False, 8)
        # O municipio sai em corpo 6; os outros dois valores, em 7.
        escrever(515, 11.5 + linha * 12, valor, False, 6 if linha == 0 else 7)

    for y in SEPARADORES:
        pdf.line(12, y, 581, y)

    # -- identificacao -----------------------------------------------------
    escrever(10, 68, "CHAVE DE ACESSO DA NFS-E", True)
    escrever(10, 78, d["chave"])

    faixa(88, ("NÚMERO DA NFS-E", "COMPETÊNCIA DA NFS-E", None, None),
          (d["numero"], d["competencia"], d["emissao_nfse"], None))
    escrever(310, 89, "DATA E HORA DA EMISSÃO DA NFS-E", True, 6)

    escrever(457, 90, "A autenticidade desta NFS-e pode ser", True, 6)
    escrever(453, 98, "consultada pela chave de acesso no portal", True, 6)
    escrever(485, 106, "nacional da NFS-e", True, 6)

    faixa(108, ("NÚMERO DA DPS", "SÉRIE DA DPS", None, None),
          (d["numero_dps"], d["serie_dps"], d["emissao_dps"], None))
    escrever(310, 109, "DATA E HORA DA EMISSÃO DA DPS", True, 6)

    faixa(128, ("EMITENTE DA NFS-E", "SITUAÇÃO DA NFS-E", "FINALIDADE", None),
          (d["emitente"], d["situacao"], d["finalidade"], None))

    # -- prestador ---------------------------------------------------------
    p = d["prestador"]
    faixa(155, ("PRESTADOR / FORNECEDOR", "CNPJ / CPF / NIF",
                "Indicador Municipal (Inscrição)", "Telefone"),
          (p["papel"], p["documento"], p["im"], p["fone"]))
    faixa(175, ("Nome / Nome Empresarial", None,
                "Município / Sigla / UF", "Código IBGE / CEP"),
          (p["nome"], None, p["municipio"], p["ibge_cep"]))
    faixa(195, ("Endereço", None, "E-mail", None),
          (p["endereco"], None, p["email"], None))
    # Esta linha nao usa as quatro colunas do resto: os tres rotulos ficam
    # espremidos a esquerda, como no documento da prefeitura.
    escrever(10, 215, "Simples Nacional", True)
    # 71, e nao 70: em 70 "Nacional" e "Data" se encostam e quem copiar o
    # texto do PDF le "NacionalData".
    escrever(71, 215, "Data de Competência", True)
    escrever(153, 215, "Regime de Apuração Tributária pelo SN", True)
    escrever(10, 225, p["simples"])
    escrever(153, 225, VAZIO)

    # -- tomador -----------------------------------------------------------
    t = d["tomador"]
    faixa(240, ("TOMADOR / ADQUIRENTE", "CNPJ / CPF / NIF",
                "Indicador Municipal (Inscrição)", "Telefone"),
          (None, t["documento"], t["im"], t["fone"]))
    faixa(260, ("Nome / Nome Empresarial", None,
                "Município / Sigla / UF", "Código IBGE / CEP"),
          (t["nome"], None, t["municipio"], t["ibge_cep"]))
    faixa(280, ("Endereço", None, "E-mail", None),
          (t["endereco"], None, t["email"], None))

    # -- destinatario e intermediario --------------------------------------
    # Ficam vazios nesta operacao: o servico e prestado direto ao paciente.
    # O leiaute exige os blocos mesmo assim.
    faixa(308, ("DESTINATÁRIO DA OPERAÇÃO", "CNPJ / CPF / NIF", None,
                "Telefone"), (None, None, None, None))
    faixa(328, ("Nome / Nome Empresarial", None, "Município / Sigla / UF",
                "Código IBGE / CEP"), (None, None, "/", "/"))
    faixa(348, ("Endereço", None, "E-mail", None), (", ,", None, None, None))
    escrever(177, 373, "INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e",
             False, 8)

    # -- servico -----------------------------------------------------------
    s = d["servico"]
    escrever(10, 387, "SERVIÇO PRESTADO", True)
    escrever(155, 389, "Código de Tributação Nacional / Municipal", True, 6)
    escrever(310, 387, "Código da NBS", True)
    escrever(445, 388, "Local da Prestação / Sigla UF / País", True, 6)
    escrever(155, 398, s["codigo"])
    escrever(310, 398, s["nbs"])
    escrever(445, 397, s["local"])
    escrever(10, 411, "Descrição do Serviço", True)
    escrever(10, 421, s["descricao"])

    # -- ISSQN -------------------------------------------------------------
    i = d["issqn"]
    escrever(10, 451, "TRIBUTAÇÃO MUNICIPAL (ISSQN)", True, 6)
    escrever(155, 450, "Tipo de Tributação do ISSQN", True)
    escrever(310, 448, "Município / Sigla UF / País de Incidência do ISSQN",
             True)
    escrever(155, 460, i["tipo"])
    escrever(310, 458, i["municipio_incidencia"])

    escrever(9, 471, "Regime Especial de Tributação ISSQN", True, 6)
    escrever(155, 470, "Tipo de Imunidade do ISSQN", True)
    escrever(310, 469, "Suspensão da Exigibilidade do ISSQN", True, 6)
    escrever(445, 468, "Número Processo Suspensão", True)
    escrever(9, 480, i["regime_especial"])
    escrever(155, 480, i["imunidade"])
    escrever(310, 478, i["suspensao"])
    escrever(445, 478, i["processo"])

    faixa(490, ("Benefício Municipal", "Cálculo do BM",
                "Total Deduções/Reduções", "Desconto Incondicionado"),
          (VAZIO, VAZIO, VAZIO, VAZIO))
    faixa(518, ("BC ISSQN", "Alíquota Aplicada", "Retenção do ISSQN",
                "ISSQN Apurado"),
          (i["base"], i["aliquota"], i["retencao"], i["apurado"]))

    # -- tributacao federal ------------------------------------------------
    escrever(10, 546, "TRIBUTAÇÃO FEDERAL (EXCETO CBS)", True, 6)
    escrever(155, 546, "IRRF", True, 6)
    escrever(310, 546, "Contribuição Previdenciária - Retida", True, 6)
    escrever(445, 546, "Contribuições Sociais - Retidas", True, 6)
    for x in (155, 310, 445):
        escrever(x, 555, VAZIO)
    escrever(10, 566, "PIS - Débito Apuração Própria", True, 6)
    escrever(155, 566, "COFINS - Débito Apuração Própria", True, 6)
    escrever(310, 566, "Descrição Contrib. Sociais - Retidas", True, 6)
    for x in (10, 155, 310):
        escrever(x, 575, VAZIO)

    # -- IBS / CBS ---------------------------------------------------------
    # A reforma tributaria ainda nao incide sobre estas notas. Os campos
    # existem no leiaute e saem vazios, como no documento da prefeitura.
    escrever(10, 591, "TRIBUTAÇÃO IBS / CBS", True)
    escrever(155, 591, "CST / cClassTrib", True)
    escrever(310, 592, "Indicador de Operação / Código IBGE Incidência / "
                       "Município Incidência / Sigla UF", True, 6)
    escrever(155, 601, "/")
    escrever(310, 601, "///")
    escrever(10, 612, "Exclusões e Reduções da Base de Cálculo", True, 6)
    escrever(155, 612, "Base de Cálculo Após Exclusões e Reduções", True, 6)
    escrever(310, 611, "Red. Alíquota IBS / Red. Alíquota CBS", True)
    escrever(445, 611, "Alíquota - IBS UF / IBS Mun", True)
    faixa(612, (None, None, None, None), (VAZIO, VAZIO, "R$ 0,00", "0,00%"))
    faixa(631, ("Alíq. Efetiva Municipal - IBS",
                "Valor Apurado Municipal - IBS",
                "Alíq. Efetiva Estadual - IBS",
                "Valor Apurado Estadual - IBS"),
          ("0,00%", VAZIO, "0,00%", VAZIO))
    faixa(651, ("Valor Total Apurado - IBS", "Alíquota - CBS",
                "Alíquota Efetiva - CBS", "Valor Total Apurado - CBS"),
          (VAZIO, "0,00%", "0,00%", VAZIO))

    # -- totais ------------------------------------------------------------
    tot = d["totais"]
    faixa(676, ("VALOR TOTAL DA NFS-E", "VALOR DA OPERAÇÃO / SERVIÇO",
                "Desconto Incondicionado", "Desconto Condicionado"),
          (None, tot["servico"], VAZIO, VAZIO))
    escrever(10, 707, "Total das Retenções (ISSQN / Federais)", True, 6)
    escrever(155, 706, "VALOR LÍQUIDO DA NFS-e", True)
    escrever(310, 706, "Total do IBS/CBS", True)
    escrever(445, 706, "VALOR LÍQUIDO DA NFS-e + IBS/CBS", True)
    faixa(706, (None, None, None, None),
          (VAZIO, tot["liquido"], VAZIO, tot["liquido"]))

    escrever(10, 732, "INFORMAÇÕES COMPLEMENTARES", True, 8)


def nome_do_arquivo(xmls) -> str:
    """DANFSe-8966-Priscila-Santana-Ferreira.pdf

    Com varias notas DA MESMA pessoa, o nome diz de quem sao, quantas e de
    que ano -- e o arquivo que o paciente recebe para a declaracao. Com
    pacientes diferentes o nome fica generico: por um nome so ali, o arquivo
    mentiria sobre o que tem dentro.
    """
    if isinstance(xmls, (bytes, bytearray, str)):
        xmls = [xmls]
    dados = [ler(x) for x in xmls]
    if not dados:
        return "DANFSe.pdf"

    if len(dados) == 1:
        nome = _apelido(dados[0]["tomador"]["nome"])
        partes = ["DANFSe", dados[0]["numero"] or dados[0]["chave"][:12], nome]
        return "-".join(p for p in partes if p) + ".pdf"

    pessoas = {d["tomador"]["nome"] for d in dados}
    nome = _apelido(dados[0]["tomador"]["nome"]) if len(pessoas) == 1 else ""

    anos = sorted({d["competencia"][-4:] for d in dados if d["competencia"]})
    periodo = anos[0] if len(anos) == 1 else (
        "%s-a-%s" % (anos[0], anos[-1]) if anos else "")
    partes = ["DANFSe", nome, "%d-notas" % len(dados), periodo]
    return "-".join(p for p in partes if p) + ".pdf"


def _apelido(nome: str) -> str:
    """Nome de pessoa em forma de nome de arquivo."""
    limpo = re.sub(r"[^\w\s-]", "", (nome or "").title())
    return limpo.strip().replace(" ", "-")[:60].rstrip("-")
