# -*- coding: utf-8 -*-
"""Leitura do RELATORIO - CLIENTES E FORNECEDORES do TechCare.

Cada cadastro ocupa sete linhas rotuladas. As colunas sao fixas, entao
lemos por faixa de coordenada em vez de por posicao de texto -- assim um
nome longo em ENDERECO nao invade o campo BAIRRO.

    NOME....: <nome>
    FICHA: <ficha>
    CNPJ / CPF: <doc>     I.E / RG: <rg>    FONE - 1: <fone>   FONE - 2: <fone>
    ENDERECO: <logradouro> <numero>         BAIRRO: <bairro>
    CIDADE.....: <cidade> CEP....: <cep>    ESTADO: <uf>  NASCIMENTO.: <data>  DT CAD.: <data>
    SITUACAO: <situacao>  VENDEDOR.: <v>    E-MAIL: <email>
    OBS..........: <obs>  INDICACAO..: <ind>

Como o relatorio tem ~1500 paginas, o resultado e guardado em cache pelo
hash do arquivo: a primeira leitura leva alguns minutos, as seguintes sao
instantaneas.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Callable

from .documentos import documento_valido, formatar_documento
from .pdf import ler_linhas
from .util import chave_nome, limpar, so_digitos

# Faixas de coordenada por campo.
#
# Cuidado: a linha NOME nao tem segunda coluna, entao o nome pode passar de
# x=213 -- foi assim que "KATIA CELENE MARIA DA SILVA SOUSA SPACE" chegou a
# ser lido sem o ultimo sobrenome. As demais linhas tem rotulo em 213 e
# precisam parar antes dele.
COL_NOME = (60, 560)
COL_VALOR1 = (60, 213)      # primeira coluna de valores
COL_VALOR2 = (240, 330)     # segunda coluna (RG, CEP)
COL_VALOR3 = (360, 386)     # terceira coluna estreita (UF)
COL_BAIRRO = (360, 600)
COL_FONE1 = (360, 455)
COL_NASC = (400, 494)
COL_EMAIL = (395, 600)
COL_ENDERECO = (60, 330)

RE_NUMERO_FINAL = re.compile(r"^(.*?)[\s,]+(\d{1,6}[A-Z]?)$")


@dataclass
class Cliente:
    nome: str = ""
    documento: str = ""         # so digitos
    rg: str = ""
    fone: str = ""
    logradouro: str = ""
    numero: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    email: str = ""
    nascimento: str = ""
    situacao: str = ""
    ficha: str = ""
    pagina: int = 0

    @property
    def chave(self) -> str:
        return chave_nome(self.nome)

    @property
    def documento_ok(self) -> bool:
        return documento_valido(self.documento)

    @property
    def documento_formatado(self) -> str:
        return formatar_documento(self.documento)

    @property
    def endereco_completo(self) -> bool:
        return bool(self.logradouro and self.bairro and self.cidade and self.cep)


@dataclass
class Cadastro:
    """Indice do cadastro, pronto para cruzamento."""

    arquivo: str = ""
    empresa: str = ""
    clientes: list = field(default_factory=list)
    por_documento: dict = field(default_factory=dict)
    por_nome: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    def indexar(self) -> None:
        self.por_documento = {}
        self.por_nome = {}
        for c in self.clientes:
            if c.documento:
                self.por_documento.setdefault(c.documento, []).append(c)
            if c.chave:
                self.por_nome.setdefault(c.chave, []).append(c)

    # -- consultas -------------------------------------------------------
    def por_cpf(self, documento: str):
        return self.por_documento.get(so_digitos(documento), [])

    def por_nome_exato(self, nome: str):
        return self.por_nome.get(chave_nome(nome), [])

    def por_prefixo(self, nome: str):
        """Nomes truncados pelo relatorio de caixa.

        O caixa corta nomes longos ("CRISTIANE DOS SANTOS DE"). Buscamos por
        prefixo, mas so aceitamos quando ha um unico candidato valido --
        CPF errado em nota fiscal e problema serio.
        """
        alvo = chave_nome(nome)
        if len(alvo) < 8:
            return []
        return [
            c
            for chave, lista in self.por_nome.items()
            if chave.startswith(alvo)
            for c in lista
        ]


def _rotulo(texto: str) -> str:
    """Normaliza NOME....: / CIDADE.....: para NOME / CIDADE."""
    base = texto.split(":", 1)[0]
    return chave_nome(base.replace(".", " ")).strip()


def _partir_endereco(valor: str):
    """RUA JAIME DE BARROS 800 -> (RUA JAIME DE BARROS, 800)."""
    valor = limpar(valor)
    if not valor:
        return "", ""
    m = RE_NUMERO_FINAL.match(valor)
    if m:
        return limpar(m.group(1)), m.group(2)
    return valor, "S/N"


def ler_clientes(caminho: str, progresso: Callable = None) -> Cadastro:
    cadastro = Cadastro(arquivo=os.path.basename(caminho))
    atual = None

    for linha in ler_linhas(caminho, progresso=progresso):
        texto = linha.texto
        if not texto:
            continue
        if texto.upper().startswith("EMPRESA:") and not cadastro.empresa:
            cadastro.empresa = limpar(texto.split(":", 1)[1])
            continue
        if linha.x0 > 30:
            continue  # numeracao de pagina e restos

        rotulo = _rotulo(texto)

        if rotulo == "NOME":
            if atual is not None and atual.nome:
                cadastro.clientes.append(atual)
            atual = Cliente(pagina=linha.pagina + 1)
            atual.nome = linha.fatia(*COL_NOME)
            continue
        if atual is None:
            continue

        if rotulo == "FICHA":
            atual.ficha = linha.fatia(*COL_VALOR1)
        elif rotulo.startswith("CNPJ"):
            atual.documento = so_digitos(linha.fatia(*COL_VALOR1))
            atual.rg = linha.fatia(*COL_VALOR2)
            atual.fone = linha.fatia(*COL_FONE1)
        elif rotulo.startswith("ENDERE"):
            atual.logradouro, atual.numero = _partir_endereco(
                linha.fatia(*COL_ENDERECO)
            )
            atual.bairro = linha.fatia(*COL_BAIRRO)
        elif rotulo == "CIDADE":
            atual.cidade = linha.fatia(*COL_VALOR1)
            atual.cep = so_digitos(linha.fatia(*COL_VALOR2))
            atual.uf = linha.fatia(*COL_VALOR3)
            atual.nascimento = linha.fatia(*COL_NASC)
        elif rotulo.startswith("SITUA"):
            atual.situacao = linha.fatia(*COL_VALOR1)
            atual.email = linha.fatia(*COL_EMAIL)

    if atual is not None and atual.nome:
        cadastro.clientes.append(atual)

    cadastro.indexar()
    invalidos = sum(1 for c in cadastro.clientes if c.documento and not c.documento_ok)
    sem_doc = sum(1 for c in cadastro.clientes if not c.documento)
    if invalidos:
        cadastro.avisos.append(
            "%d cadastros tem CPF/CNPJ que nao passa na validacao." % invalidos
        )
    if sem_doc:
        cadastro.avisos.append("%d cadastros estao sem CPF/CNPJ." % sem_doc)
    return cadastro


# --------------------------------------------------------------------------
# Cache: o relatorio tem ~1500 paginas; reler a cada execucao seria penoso.
# --------------------------------------------------------------------------

def _impressao_digital(caminho: str) -> str:
    """Hash barato: tamanho + inicio + fim do arquivo."""
    tamanho = os.path.getsize(caminho)
    h = hashlib.sha256()
    h.update(str(tamanho).encode())
    with open(caminho, "rb") as fh:
        h.update(fh.read(262144))
        if tamanho > 524288:
            fh.seek(-262144, os.SEEK_END)
            h.update(fh.read())
    return h.hexdigest()[:16]


def ler_clientes_cache(
    caminho: str, pasta_cache: str, progresso: Callable = None
) -> Cadastro:
    os.makedirs(pasta_cache, exist_ok=True)
    destino = os.path.join(
        pasta_cache, "clientes-%s.json" % _impressao_digital(caminho)
    )
    if os.path.exists(destino):
        with open(destino, encoding="utf-8") as fh:
            bruto = json.load(fh)
        cadastro = Cadastro(
            arquivo=bruto["arquivo"],
            empresa=bruto["empresa"],
            clientes=[Cliente(**c) for c in bruto["clientes"]],
            avisos=bruto.get("avisos", []),
        )
        cadastro.indexar()
        return cadastro

    cadastro = ler_clientes(caminho, progresso=progresso)
    with open(destino, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "arquivo": cadastro.arquivo,
                "empresa": cadastro.empresa,
                "avisos": cadastro.avisos,
                "clientes": [asdict(c) for c in cadastro.clientes],
            },
            fh,
            ensure_ascii=False,
        )
    return cadastro
