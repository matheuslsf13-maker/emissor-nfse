# -*- coding: utf-8 -*-
"""Geracao do XML no leiaute nacional da NFS-e (NFSe > infNFSe > DPS > infDPS).

Vila Velha aderiu ao padrao nacional em janeiro/2026 mas manteve o emissor
municipal: o XML segue o leiaute nacional e o envio vai para o WebService
da prefeitura, que repassa ao ADN. O DANFSe real de 04/08/2026 confirma:
campo ambGer = 1 (Prefeitura).

Armadilha que ja custou caro: `etree.SubElement(pai, "tag")` cria o
elemento SEM namespace mesmo quando o pai tem namespace default. O
serializador emite xmlns="" e a prefeitura rejeita com E1235 (falha no
esquema). Por isso toda tag passa por `_sub()`, que qualifica o nome.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from lxml import etree

from .util import so_digitos

NS = "http://www.sped.fazenda.gov.br/nfse"
NSMAP = {None: NS}
FUSO = timezone(timedelta(hours=-3))

# O Id do infNFSe e literal ate a prefeitura numerar a nota.
ID_INFNFSE = "NFS" + "0" * 50


# Tamanhos maximos do leiaute nacional. Campo estourado e rejeicao na
# prefeitura, e a mensagem que volta nao diz qual campo -- descobrir isso
# depois, com a nota ja recusada, custa muito mais do que cortar aqui.
# Nomes de paciente longos existem de verdade no cadastro da clinica.
LIMITES = {
    "xNome": 300, "xLgr": 255, "xCpl": 156, "xBairro": 150,
    "email": 80, "xDescServ": 2000, "xTribNac": 600, "xInfComp": 2000,
}


def _sub(pai, nome: str, texto=None):
    """SubElement sempre qualificado no namespace do padrao."""
    elemento = etree.SubElement(pai, "{%s}%s" % (NS, nome))
    if texto is not None:
        valor = str(texto)
        limite = LIMITES.get(nome)
        if limite and len(valor) > limite:
            valor = valor[:limite].rstrip()
        elemento.text = valor
    return elemento


def _dec(valor, casas: str = "0.01") -> str:
    return str(Decimal(str(valor)).quantize(Decimal(casas), rounding=ROUND_HALF_UP))


def id_dps(codigo_municipio: str, cnpj: str, serie: str, numero: int) -> str:
    """DPS + cLocEmi(7) + tpInsc(1) + CNPJ(14) + serie(5) + nDPS(15)."""
    return "DPS%s2%s%s%s" % (
        str(codigo_municipio).zfill(7),
        so_digitos(cnpj).zfill(14),
        str(serie).zfill(5),
        str(numero).zfill(15),
    )


def _preencher_emitente(pai, unidade: dict) -> None:
    emit = _sub(pai, "emit")
    _sub(emit, "CNPJ", so_digitos(unidade["cnpj"]))
    _sub(emit, "IM", so_digitos(unidade["inscricao_municipal"]))
    _sub(emit, "xNome", unidade["razao_social"])
    endereco = unidade["endereco"]
    ender = _sub(emit, "enderNac")
    _sub(ender, "xLgr", endereco["logradouro"])
    _sub(ender, "nro", endereco["numero"])
    if endereco.get("complemento"):
        _sub(ender, "xCpl", endereco["complemento"])
    _sub(ender, "xBairro", endereco["bairro"])
    _sub(ender, "cMun", endereco["codigo_municipio"])
    _sub(ender, "UF", endereco["uf"])
    _sub(ender, "CEP", so_digitos(endereco["cep"]))
    _sub(emit, "fone", so_digitos(unidade.get("telefone", "")))
    _sub(emit, "email", unidade.get("email", ""))


def _preencher_tomador(pai, tomador: dict) -> None:
    toma = _sub(pai, "toma")
    documento = so_digitos(tomador.get("documento", ""))
    if len(documento) == 14:
        _sub(toma, "CNPJ", documento)
    else:
        _sub(toma, "CPF", documento.zfill(11))
    _sub(toma, "xNome", tomador.get("nome", ""))
    end = _sub(toma, "end")
    ender_nac = _sub(end, "endNac")
    _sub(ender_nac, "cMun", tomador.get("codigo_municipio", ""))
    _sub(ender_nac, "CEP", so_digitos(tomador.get("cep", "")))
    _sub(end, "xLgr", tomador.get("logradouro", ""))
    _sub(end, "nro", tomador.get("numero") or "S/N")
    if tomador.get("complemento"):
        _sub(end, "xCpl", tomador["complemento"])
    _sub(end, "xBairro", tomador.get("bairro", ""))
    if tomador.get("email"):
        _sub(toma, "email", tomador["email"])


def _preencher_ibscbs(pai, ibscbs: dict, valor: Decimal) -> None:
    """Grupo IBS/CBS da Reforma Tributaria (NT SE/CGNFS-e n. 009)."""
    grupo = _sub(pai, "IBSCBS")
    _sub(grupo, "CST", ibscbs.get("cst", "000"))
    _sub(grupo, "cClassTrib", ibscbs.get("codigo_classificacao_tributaria", ""))
    valores = _sub(grupo, "gIBSCBS")
    _sub(valores, "vBC", _dec(valor))
    cbs = _sub(valores, "gCBS")
    aliquota = Decimal(str(ibscbs.get("aliquota_cbs", 0)))
    _sub(cbs, "pCBS", _dec(aliquota, "0.0001"))
    _sub(cbs, "vCBS", _dec(valor * aliquota / Decimal("100")))


def gerar_nfse(
    nota,
    unidade: dict,
    config,
    numero_dps: int,
    emitido_em: datetime = None,
    ambiente: str = "",
) -> bytes:
    """Monta o XML de uma NFS-e. Devolve bytes ainda sem assinatura."""
    servico = config.servico
    municipio = config.municipio
    faturamento = config.faturamento
    ibscbs = config.ibscbs or {}

    valor = Decimal(nota.valor if isinstance(nota.valor, str) else str(nota.valor))
    aliquota = Decimal(str(servico["aliquota_iss"]))
    iss = (valor * aliquota / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    retido = Decimal("0.00")
    agora = emitido_em or datetime.now(FUSO)
    serie = str(faturamento.get("serie", "00001"))
    # O ambiente vem de quem chama; a configuracao e so o padrao. Ler so da
    # configuracao fazia o XML sair marcado como PRODUCAO mesmo quando o
    # operador pedia teste -- nota valendo emitida achando que era ensaio.
    escolhido = ambiente or faturamento.get("ambiente", "homologacao")
    ambiente_xml = "1" if escolhido == "producao" else "2"

    raiz = etree.Element("{%s}NFSe" % NS, nsmap=NSMAP)
    raiz.set("versao", "1.01")

    info = _sub(raiz, "infNFSe")
    info.set("Id", ID_INFNFSE)
    _sub(info, "xLocEmi", municipio["nome"])
    _sub(info, "xLocPrestacao", municipio["nome"])
    _sub(info, "nNFSe", "0")                       # a prefeitura atribui
    _sub(info, "cLocIncid", servico["municipio_incidencia"])
    _sub(info, "xLocIncid", municipio["nome"])
    _sub(info, "xTribNac", servico["descricao_tributacao_nacional"])
    _sub(info, "verAplic", municipio["versao_aplicativo"])
    _sub(info, "ambGer", municipio["ambiente_gerador"])
    _sub(info, "tpEmis", "2")
    _sub(info, "cStat", "100")
    _sub(info, "dhProc", agora.replace(microsecond=0).isoformat())
    _sub(info, "nDFSe", str(numero_dps))
    _preencher_emitente(info, unidade)

    valores = _sub(info, "valores")
    _sub(valores, "vBC", _dec(valor))
    _sub(valores, "pAliqAplic", _dec(aliquota, "0.0001"))
    _sub(valores, "vISSQN", _dec(iss))
    _sub(valores, "vTotalRet", _dec(retido))
    _sub(valores, "vLiq", _dec(valor - retido))

    dps = _sub(info, "DPS")
    dps.set("versao", "1.00")
    info_dps = _sub(dps, "infDPS")
    info_dps.set(
        "Id", id_dps(municipio["codigo_ibge"], unidade["cnpj"], serie, numero_dps)
    )
    _sub(info_dps, "tpAmb", ambiente_xml)
    _sub(info_dps, "dhEmi", agora.replace(microsecond=0).isoformat())
    _sub(info_dps, "verAplic", municipio["versao_aplicativo"])
    _sub(info_dps, "serie", serie)
    _sub(info_dps, "nDPS", str(numero_dps))
    _sub(info_dps, "dCompet", _competencia_iso(nota.competencia))
    _sub(info_dps, "tpEmit", "1")
    _sub(info_dps, "cLocEmi", municipio["codigo_ibge"])

    prest = _sub(info_dps, "prest")
    _sub(prest, "CNPJ", so_digitos(unidade["cnpj"]))
    _sub(prest, "IM", so_digitos(unidade["inscricao_municipal"]))
    _sub(prest, "fone", so_digitos(unidade.get("telefone", "")))
    _sub(prest, "email", unidade.get("email", ""))
    reg = _sub(prest, "regTrib")
    _sub(reg, "opSimpNac", str(servico.get("opcao_simples_nacional", "1")))
    _sub(reg, "regEspTrib", str(servico.get("regime_especial", "0")))

    _preencher_tomador(info_dps, nota.tomador)

    serv = _sub(info_dps, "serv")
    local = _sub(serv, "locPrest")
    _sub(local, "cLocPrestacao", servico["municipio_prestacao"])
    codigo = _sub(serv, "cServ")
    _sub(codigo, "cTribNac", servico["codigo_tributacao_nacional"])
    _sub(codigo, "xDescServ", servico["descricao"])
    _sub(codigo, "cNBS", servico["codigo_nbs"])

    val_dps = _sub(info_dps, "valores")
    serv_prest = _sub(val_dps, "vServPrest")
    _sub(serv_prest, "vServ", _dec(valor))
    descontos = _sub(val_dps, "vDescCondIncond")
    _sub(descontos, "vDescIncond", "0.00")
    _sub(descontos, "vDescCond", "0.00")
    deducoes = _sub(val_dps, "vDedRed")
    _sub(deducoes, "vDR", "0.00")
    trib = _sub(val_dps, "trib")
    trib_mun = _sub(trib, "tribMun")
    # 1 = NAO retido. Inverter isso declara retencao que nao existe.
    _sub(trib_mun, "tribISSQN", str(servico["tributacao_issqn"]))
    _sub(trib_mun, "tpRetISSQN", str(servico["retencao_issqn"]))
    if ibscbs.get("emitir"):
        _preencher_ibscbs(trib, ibscbs, valor)

    return etree.tostring(
        raiz, xml_declaration=True, encoding="UTF-8", pretty_print=False
    )


def _competencia_iso(competencia: str) -> str:
    """'2026-08' -> '2026-08-01'."""
    partes = str(competencia).split("-")
    ano = int(partes[0])
    mes = int(partes[1]) if len(partes) > 1 else 1
    return date(ano, mes, 1).isoformat()
