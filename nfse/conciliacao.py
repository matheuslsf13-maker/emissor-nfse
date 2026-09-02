# -*- coding: utf-8 -*-
"""Cruzamento do caixa com o cadastro de clientes.

Regra que atravessa o arquivo inteiro: **nunca chutar dados do tomador**.
Nome nao e chave unica. Quando o cruzamento e ambiguo, o lancamento vira
pendencia e aparece listado -- nao se escolhe CPF por sorteio.

Saida:
    notas       -- prontas para virar XML
    pendencias  -- bloqueadas, cada uma com motivo e como resolver
    descartes   -- excluidas por regra de negocio, agrupadas por motivo
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal

from .documentos import documento_valido, formatar_documento
from .municipios import codigo_ibge, codigo_ibge_aproximado, descrever
from .regras import EMITE, M_SECAO, Regras
from .util import chave_nome, so_digitos

# Motivos de pendencia (chave estavel: a tela usa para agrupar e orientar)
P_SEM_CADASTRO = "cliente_sem_cadastro"
P_CPF_INVALIDO = "cpf_invalido"
P_HOMONIMO = "homonimo"
P_BOLETO_SEM_CADASTRO = "boleto_sem_cadastro"
P_ENDERECO = "endereco_incompleto"
P_MUNICIPIO = "municipio_desconhecido"

ORIENTACAO = {
    P_SEM_CADASTRO: "Cadastre o paciente no TechCare ou aponte aqui embaixo qual cadastro é o dele.",
    P_CPF_INVALIDO: "O CPF gravado no cadastro não passa na validação. Corrija no TechCare.",
    P_HOMONIMO: "Existe mais de um cadastro com esse nome. Escolha qual é o certo.",
    P_BOLETO_SEM_CADASTRO: "Esse CPF pagou boleto mas não está no cadastro de clientes desta unidade.",
    P_ENDERECO: "O cadastro está sem rua, bairro ou CEP. Complete no TechCare.",
    P_MUNICIPIO: "A cidade do cadastro não foi reconhecida. Corrija a grafia no TechCare.",
}


@dataclass
class Tomador:
    documento: str = ""
    nome: str = ""
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    codigo_municipio: str = ""
    email: str = ""
    fone: str = ""

    @property
    def documento_formatado(self) -> str:
        return formatar_documento(self.documento)


@dataclass
class Nota:
    """Uma nota prevista, ainda sem numero."""

    id: str
    unidade: str
    data: str                    # AAAA-MM-DD
    competencia: str             # AAAA-MM
    valor: str                   # texto com 2 casas, para nao perder precisao
    secao: str
    caixa: str
    lancto: str
    contrato: str
    historico: str
    tipo_faturamento: str        # particular | convenio
    tomador: dict = field(default_factory=dict)
    origem_cruzamento: str = ""  # cpf | nome | prefixo | manual | convenio
    ajustes: list = field(default_factory=list)

    @property
    def valor_decimal(self) -> Decimal:
        return Decimal(self.valor)


@dataclass
class Pendencia:
    id: str
    motivo: str
    titulo: str
    orientacao: str
    data: str
    valor: str
    secao: str
    caixa: str
    lancto: str
    nome: str
    documento: str = ""
    candidatos: list = field(default_factory=list)


@dataclass
class Resultado:
    unidade: str = ""
    unidade_nome: str = ""
    competencia: str = ""
    periodo_inicio: str = ""
    periodo_fim: str = ""
    arquivos: list = field(default_factory=list)
    notas: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    descartes: dict = field(default_factory=dict)   # motivo -> {qtde, valor}
    avisos: list = field(default_factory=list)
    total_lancamentos: int = 0
    # Secao que aparece no caixa e nao esta em secoes_que_emitem nem na lista
    # de bloqueio. Nao e a mesma coisa que uma secao excluida de proposito:
    # e algo que ninguem configurou, e alguem precisa decidir.
    secoes_desconhecidas: dict = field(default_factory=dict)

    # -- resumos usados pela tela ------------------------------------------
    @property
    def valor_total(self) -> Decimal:
        return sum((n.valor_decimal for n in self.notas), Decimal("0"))

    @property
    def valor_pendente(self) -> Decimal:
        return sum((Decimal(p.valor) for p in self.pendencias), Decimal("0"))

    @property
    def cobertura(self) -> float:
        base = len(self.notas) + len(self.pendencias)
        return (len(self.notas) / base * 100.0) if base else 100.0

    def por_secao(self) -> list:
        agrupado = {}
        for n in self.notas:
            item = agrupado.setdefault(n.secao, {"qtde": 0, "valor": Decimal("0")})
            item["qtde"] += 1
            item["valor"] += n.valor_decimal
        return sorted(
            ({"secao": k, **v} for k, v in agrupado.items()),
            key=lambda x: -x["valor"],
        )


def _competencia(d: date) -> str:
    return "%04d-%02d" % (d.year, d.month)


def _tomador_de_cliente(cliente, ajustes: list):
    """Monta o tomador a partir de um cadastro, resolvendo o codigo IBGE."""
    codigo = codigo_ibge(cliente.cidade, cliente.uf)
    if not codigo:
        aproximado = codigo_ibge_aproximado(cliente.cidade, cliente.uf)
        if aproximado:
            codigo = aproximado[0]
            ajustes.append(
                "Cidade do cadastro '%s' entendida como %s."
                % (cliente.cidade, descrever(codigo))
            )
    return Tomador(
        documento=cliente.documento,
        nome=cliente.nome,
        logradouro=cliente.logradouro,
        numero=cliente.numero or "S/N",
        bairro=cliente.bairro,
        cidade=cliente.cidade,
        uf=cliente.uf,
        cep=cliente.cep,
        codigo_municipio=codigo or "",
        email=cliente.email,
        fone=cliente.fone,
    )


def _candidatos_para_tela(clientes) -> list:
    return [
        {
            "nome": c.nome,
            "documento": c.documento,
            "documento_formatado": c.documento_formatado,
            "valido": c.documento_ok,
            "endereco": "%s, %s - %s - %s/%s"
            % (c.logradouro, c.numero, c.bairro, c.cidade, c.uf),
            "nascimento": c.nascimento,
        }
        for c in clientes[:12]
    ]


def _resolver_particular(lanc, cadastro, regras):
    """Devolve (cliente, origem) ou (None, motivo_de_pendencia)."""
    if lanc.tipo == "BCO":
        documento = lanc.cpf_historico
        if not documento_valido(documento):
            return None, (P_CPF_INVALIDO, documento, [])
        achados = cadastro.por_cpf(documento)
        if not achados:
            return None, (P_BOLETO_SEM_CADASTRO, documento, [])
        validos = [c for c in achados if c.documento_ok]
        return (validos or achados)[0], "cpf"

    nome = regras.nome_do_paciente(lanc.nome_bruto) or lanc.nome_bruto
    achados = cadastro.por_nome_exato(nome)
    origem = "nome"
    if not achados:
        achados = cadastro.por_prefixo(nome)
        origem = "prefixo"
    if not achados:
        return None, (P_SEM_CADASTRO, "", [])

    validos = [c for c in achados if c.documento_ok]
    if not validos:
        return None, (P_CPF_INVALIDO, achados[0].documento,
                      _candidatos_para_tela(achados))

    documentos = {c.documento for c in validos}
    if len(documentos) > 1:
        return None, (P_HOMONIMO, "", _candidatos_para_tela(validos))
    return validos[0], origem


def conciliar(
    caixas,
    cadastro,
    config,
    unidade: str,
    competencia: str = "",
    escolhas: dict = None,
) -> Resultado:
    """Cruza os caixas com o cadastro e devolve notas, pendencias e descartes.

    `escolhas` mapeia id-do-lancamento -> CPF/CNPJ escolhido pelo operador
    para resolver uma pendencia. O documento precisa existir no cadastro:
    o sistema nunca inventa endereco de tomador.
    """
    regras = Regras(config)
    escolhas = escolhas or {}
    dados_unidade = config.unidade(unidade)
    resultado = Resultado(
        unidade=unidade,
        unidade_nome=dados_unidade.get("apelido", unidade),
        arquivos=[c.arquivo for c in caixas],
    )

    inicios = [c.periodo_inicio for c in caixas if c.periodo_inicio]
    fins = [c.periodo_fim for c in caixas if c.periodo_fim]
    if inicios:
        resultado.periodo_inicio = min(inicios).isoformat()
    if fins:
        resultado.periodo_fim = max(fins).isoformat()
    resultado.competencia = competencia or (
        _competencia(max(fins)) if fins else ""
    )

    for caixa in caixas:
        resultado.avisos.extend(caixa.avisos)

    consolidado_convenio = {}

    for caixa in caixas:
        for lanc in caixa.lancamentos:
            resultado.total_lancamentos += 1
            decisao, motivo, tipo = regras.avaliar(lanc)
            if decisao != EMITE:
                item = resultado.descartes.setdefault(
                    motivo, {"qtde": 0, "valor": Decimal("0")}
                )
                item["qtde"] += 1
                item["valor"] += lanc.valor
                if motivo == M_SECAO:
                    achado = resultado.secoes_desconhecidas.setdefault(
                        lanc.secao, {"qtde": 0, "valor": Decimal("0"),
                                     "caixa": lanc.caixa}
                    )
                    achado["qtde"] += 1
                    achado["valor"] += lanc.valor
                continue

            base = {
                "id": lanc.id,
                "unidade": unidade,
                "data": lanc.data.isoformat() if lanc.data else "",
                "competencia": resultado.competencia,
                "valor": "%.2f" % lanc.valor,
                "secao": lanc.secao,
                "caixa": lanc.caixa,
                "lancto": lanc.lancto,
                "contrato": lanc.contrato,
                "historico": lanc.historico,
                "tipo_faturamento": tipo,
            }

            if tipo == "convenio":
                convenio = regras.convenio_de(lanc.nome_bruto)
                grupo = consolidado_convenio.setdefault(
                    convenio, {"valor": Decimal("0"), "qtde": 0}
                )
                grupo["valor"] += lanc.valor
                grupo["qtde"] += 1
                continue

            # --- particular ------------------------------------------------
            ajustes = []
            escolha = escolhas.get(lanc.id)
            if escolha:
                achados = cadastro.por_cpf(escolha)
                cliente = next(
                    (c for c in achados if c.documento_ok),
                    achados[0] if achados else None,
                )
                origem = "manual"
                if cliente is None:
                    resultado.pendencias.append(
                        _pendencia(lanc, P_SEM_CADASTRO, "", [])
                    )
                    continue
                ajustes.append(
                    "Cadastro apontado manualmente na conferência: %s."
                    % formatar_documento(escolha)
                )
            else:
                cliente, origem = _resolver_particular(lanc, cadastro, regras)
                if cliente is None:
                    motivo_pend, documento, candidatos = origem
                    resultado.pendencias.append(
                        _pendencia(lanc, motivo_pend, documento, candidatos)
                    )
                    continue

            tomador = _tomador_de_cliente(cliente, ajustes)
            if not tomador.codigo_municipio:
                resultado.pendencias.append(
                    _pendencia(lanc, P_MUNICIPIO, tomador.documento, [],
                               nome=cliente.nome)
                )
                continue
            if not (tomador.logradouro and tomador.bairro and tomador.cep):
                resultado.pendencias.append(
                    _pendencia(lanc, P_ENDERECO, tomador.documento, [],
                               nome=cliente.nome)
                )
                continue
            if origem == "prefixo":
                ajustes.append(
                    "O caixa cortou o nome em '%s'; o cadastro completo é '%s'."
                    % (lanc.nome_bruto, cliente.nome)
                )

            resultado.notas.append(
                Nota(
                    **base,
                    tomador=asdict(tomador),
                    origem_cruzamento=origem,
                    ajustes=ajustes,
                )
            )

    # --- convenios consolidados --------------------------------------------
    for convenio, grupo in consolidado_convenio.items():
        dados = config.faturamento.get("convenios", {}).get(convenio)
        if not dados:
            resultado.avisos.append(
                "Convenio %s tem %d lancamentos (%s) mas nao esta configurado "
                "em faturamento.convenios." % (convenio, grupo["qtde"], grupo["valor"])
            )
            continue
        tomador = Tomador(
            documento=so_digitos(dados["cnpj"]),
            nome=dados["nome"],
            logradouro=dados.get("logradouro", ""),
            numero=dados.get("numero", "SN"),
            bairro=dados.get("bairro", ""),
            cidade=dados.get("cidade", ""),
            uf=dados.get("uf", ""),
            cep=so_digitos(dados.get("cep", "")),
            codigo_municipio=codigo_ibge(dados.get("cidade", ""), dados.get("uf", ""))
            or "",
        )
        resultado.notas.append(
            Nota(
                id="CONVENIO:%s:%s" % (convenio, resultado.competencia),
                unidade=unidade,
                data=resultado.periodo_fim,
                competencia=resultado.competencia,
                valor="%.2f" % grupo["valor"],
                secao="CONVENIO %s" % convenio,
                caixa="CONSOLIDADO",
                lancto="",
                contrato="",
                historico="Consolidado de %d atendimentos" % grupo["qtde"],
                tipo_faturamento="convenio",
                tomador=asdict(tomador),
                origem_cruzamento="convenio",
                ajustes=["Nota consolidada do convênio na competência."],
            )
        )

    resultado.notas.sort(key=lambda n: (n.data, n.lancto))
    resultado.pendencias.sort(key=lambda p: (p.motivo, p.data))
    return resultado


def _pendencia(lanc, motivo, documento, candidatos, nome=""):
    titulos = {
        P_SEM_CADASTRO: "Paciente não encontrado no cadastro",
        P_CPF_INVALIDO: "CPF do cadastro inválido",
        P_HOMONIMO: "Mais de um cadastro com o mesmo nome",
        P_BOLETO_SEM_CADASTRO: "CPF do boleto não está no cadastro",
        P_ENDERECO: "Endereço do cadastro incompleto",
        P_MUNICIPIO: "Cidade do cadastro não reconhecida",
    }
    return Pendencia(
        id=lanc.id,
        motivo=motivo,
        titulo=titulos.get(motivo, motivo),
        orientacao=ORIENTACAO.get(motivo, ""),
        data=lanc.data.isoformat() if lanc.data else "",
        valor="%.2f" % lanc.valor,
        secao=lanc.secao,
        caixa=lanc.caixa,
        lancto=lanc.lancto,
        nome=nome or lanc.nome_bruto or formatar_documento(lanc.cpf_historico),
        documento=documento,
        candidatos=candidatos,
    )
