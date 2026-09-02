# -*- coding: utf-8 -*-
"""Base de clientes que fica salva entre uma emissão e outra.

O relatório de clientes do TechCare tem mais de 1.500 páginas e traz o
cadastro inteiro desde 2019. Subir isso toda vez é desnecessário: a base é
guardada em disco e, quando chega um relatório novo, só a diferença entra.

Uma base por unidade (`dados/clientes/gloria.json`). Clientes de unidades
diferentes não se misturam -- um paciente da Cobilândia não pode ser usado
como tomador de um lançamento da Glória.

Como dois cadastros são reconhecidos como a mesma pessoa, nesta ordem:

1. **mesmo CPF/CNPJ válido** -- a identificação mais forte;
2. **mesmo nome + mesma data de nascimento** -- é o que permite reconhecer
   alguém cujo CPF foi corrigido no TechCare. Sem isso, corrigir um CPF
   inválido criaria um cadastro novo e o antigo, errado, ficaria para sempre.

Nada é apagado. Um cliente que sumiu do relatório continua na base, porque
ele ainda pode aparecer num caixa de mês anterior.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime

from .documentos import documento_valido
from .leitor_clientes import Cadastro, Cliente
from .util import chave_nome, so_digitos


def _chave_documento(cliente) -> str:
    documento = so_digitos(cliente.documento)
    if documento and documento_valido(documento):
        return "doc:" + documento
    return ""


def _chave_pessoa(cliente) -> str:
    nome = cliente.chave
    if not nome:
        return ""
    return "pessoa:%s|%s" % (nome, cliente.nascimento or "")


def _documentos_compativeis(a, b) -> bool:
    """Dois cadastros podem ser a mesma pessoa, olhando só o documento?

    Sim quando são iguais, ou quando pelo menos um é inválido/vazio -- é o
    caso do cadastro duplicado com CPF terminado em zeros, muito comum no
    TechCare.

    Não quando os dois são válidos e diferentes. Aí pode ser homônimo de
    verdade, e juntar significaria escolher um CPF no chute. Ficam separados,
    e a conciliação trata como pendência de homônimo -- que é honesto.
    """
    doc_a = so_digitos(a.documento)
    doc_b = so_digitos(b.documento)
    if doc_a == doc_b:
        return True
    return not (documento_valido(doc_a) and documento_valido(doc_b))


def _mudou(antigo, novo) -> list:
    """Campos que mudaram e valem registrar.

    Duas proteções:

    * campo vazio no relatório novo não apaga informação que já existe;
    * **documento válido nunca é substituído por inválido**. O mesmo paciente
      aparece cadastrado duas vezes, uma com CPF bom e outra com CPF
      terminado em zeros; sem essa regra, a ordem de leitura decidiria qual
      CPF vale, e o paciente poderia passar a travar do nada.
    """
    campos = ("documento", "logradouro", "numero", "bairro", "cidade", "uf",
              "cep", "email", "fone", "nascimento", "situacao")
    diferencas = []
    for campo in campos:
        valor_novo = getattr(novo, campo, "") or ""
        valor_antigo = getattr(antigo, campo, "") or ""
        if not valor_novo or valor_novo == valor_antigo:
            continue
        if campo == "documento":
            if documento_valido(valor_antigo) and not documento_valido(valor_novo):
                continue
        diferencas.append((campo, valor_antigo, valor_novo))
    return diferencas


def _melhor(a, b):
    """Entre dois cadastros da mesma pessoa, qual é o bom.

    O que tem CPF/CNPJ válido. É o padrão do TechCare: fica o registro antigo
    com CPF terminado em 000-00 e cria-se outro com o documento correto.
    Empate mantém o primeiro.
    """
    if documento_valido(so_digitos(a.documento)):
        return a, b
    if documento_valido(so_digitos(b.documento)):
        return b, a
    return a, b


def _consolidar(clientes) -> list:
    """Junta duplicatas dentro do PRÓPRIO relatório, antes de mesclar.

    Sem isto, as duas metades de um cadastro duplicado se sobrescreveriam a
    cada importação -- o endereço da pessoa ficaria alternando entre as duas
    versões e toda reimportação acusaria dezenas de "alterações" que não
    aconteceram.

    O registro com documento válido vence; os campos que faltam nele são
    preenchidos pelo gêmeo.
    """
    resultado: list = []
    por_documento: dict = {}
    por_pessoa: dict = {}

    for cliente in clientes:
        indice = por_documento.get(_chave_documento(cliente))
        if indice is None:
            candidato = por_pessoa.get(_chave_pessoa(cliente))
            if candidato is not None and _documentos_compativeis(
                resultado[candidato], cliente
            ):
                indice = candidato

        if indice is None:
            resultado.append(Cliente(**asdict(cliente)))
            posicao = len(resultado) - 1
            chave = _chave_documento(cliente)
            if chave:
                por_documento.setdefault(chave, posicao)
            chave = _chave_pessoa(cliente)
            if chave:
                por_pessoa.setdefault(chave, posicao)
            continue

        vencedor, perdedor = _melhor(resultado[indice], cliente)
        juntado = Cliente(**asdict(vencedor))
        for campo, valor in asdict(perdedor).items():
            if not getattr(juntado, campo, "") and valor:
                setattr(juntado, campo, valor)
        resultado[indice] = juntado
        chave = _chave_documento(juntado)
        if chave:
            por_documento.setdefault(chave, indice)

    return resultado


class BaseClientes:
    """Cadastro acumulado de uma unidade."""

    def __init__(self, caminho: str, unidade: str = ""):
        self.caminho = caminho
        self.unidade = unidade
        self.clientes: list = []
        self.criada_em = ""
        self.atualizada_em = ""
        self.historico: list = []
        self._carregar()

    # -- disco -------------------------------------------------------------
    def _carregar(self) -> None:
        if not os.path.exists(self.caminho):
            return
        with open(self.caminho, encoding="utf-8") as fh:
            bruto = json.load(fh)
        self.unidade = bruto.get("unidade", self.unidade)
        self.criada_em = bruto.get("criada_em", "")
        self.atualizada_em = bruto.get("atualizada_em", "")
        self.historico = bruto.get("historico", [])
        self.clientes = [Cliente(**c) for c in bruto.get("clientes", [])]

    def salvar(self) -> None:
        os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
        agora = datetime.now().isoformat(timespec="seconds")
        if not self.criada_em:
            self.criada_em = agora
        self.atualizada_em = agora
        temporario = self.caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as fh:
            json.dump({
                "unidade": self.unidade,
                "criada_em": self.criada_em,
                "atualizada_em": self.atualizada_em,
                "historico": self.historico[-30:],
                "clientes": [asdict(c) for c in self.clientes],
            }, fh, ensure_ascii=False)
        os.replace(temporario, self.caminho)

    # -- consulta ----------------------------------------------------------
    @property
    def existe(self) -> bool:
        return bool(self.clientes)

    @property
    def total(self) -> int:
        return len(self.clientes)

    def como_cadastro(self) -> Cadastro:
        """Devolve no formato que a conciliação já sabe consumir."""
        cadastro = Cadastro(
            arquivo="base de clientes (%s)" % self.unidade,
            empresa=self.unidade,
            clientes=list(self.clientes),
        )
        cadastro.indexar()
        return cadastro

    def resumo(self) -> dict:
        validos = sum(1 for c in self.clientes if c.documento_ok)
        return {
            "unidade": self.unidade,
            "total": self.total,
            "com_documento_valido": validos,
            "sem_documento_valido": self.total - validos,
            "criada_em": self.criada_em,
            "atualizada_em": self.atualizada_em,
            "importacoes": len(self.historico),
            "ultima": self.historico[-1] if self.historico else None,
        }

    # -- importação incremental --------------------------------------------
    def mesclar(self, cadastro_novo, origem: str = "") -> dict:
        """Junta um relatório recém-lido à base, guardando só a diferença."""
        entrando = _consolidar(cadastro_novo.clientes)
        por_documento = {}
        por_pessoa = {}
        for indice, cliente in enumerate(self.clientes):
            chave = _chave_documento(cliente)
            if chave:
                por_documento.setdefault(chave, indice)
            chave = _chave_pessoa(cliente)
            if chave:
                por_pessoa.setdefault(chave, indice)

        novos, atualizados, iguais = [], [], 0

        for cliente in entrando:
            indice = por_documento.get(_chave_documento(cliente))
            if indice is None:
                candidato = por_pessoa.get(_chave_pessoa(cliente))
                # Nome e nascimento iguais só valem como "mesma pessoa" se os
                # documentos não se contradisserem. Dois CPFs válidos e
                # diferentes ficam como cadastros separados.
                if candidato is not None and _documentos_compativeis(
                    self.clientes[candidato], cliente
                ):
                    indice = candidato

            if indice is None:
                # Cópia: sem isso a base guardaria a mesma instância que veio
                # do leitor, e uma atualização depois alteraria também o
                # cadastro de origem -- confusão garantida em qualquer
                # conferência feita na mesma execução.
                self.clientes.append(Cliente(**asdict(cliente)))
                posicao = len(self.clientes) - 1
                chave = _chave_documento(cliente)
                if chave:
                    por_documento.setdefault(chave, posicao)
                chave = _chave_pessoa(cliente)
                if chave:
                    por_pessoa.setdefault(chave, posicao)
                novos.append({
                    "nome": cliente.nome,
                    "documento": cliente.documento_formatado,
                    "valido": cliente.documento_ok,
                })
                continue

            antigo = self.clientes[indice]
            diferencas = _mudou(antigo, cliente)
            if not diferencas:
                iguais += 1
                continue

            for campo, _, valor_novo in diferencas:
                setattr(antigo, campo, valor_novo)
            atualizados.append({
                "nome": antigo.nome,
                "documento": antigo.documento_formatado,
                "mudancas": [
                    {"campo": c, "de": de or "(vazio)", "para": para}
                    for c, de, para in diferencas
                ],
                "documento_mudou": any(c == "documento" for c, _, _ in diferencas),
            })

        registro = {
            "em": datetime.now().isoformat(timespec="seconds"),
            "origem": origem,
            "lidos": len(cadastro_novo.clientes),
            "consolidados": len(entrando),
            "novos": len(novos),
            "atualizados": len(atualizados),
            "iguais": iguais,
            "total_depois": self.total,
        }
        self.historico.append(registro)
        self.salvar()

        return {
            **registro,
            "lista_novos": novos,
            "lista_atualizados": atualizados,
        }


def caminho_base(pasta: str, unidade: str) -> str:
    return os.path.join(pasta, "clientes", "%s.json" % unidade)


def abrir(pasta: str, unidade: str) -> BaseClientes:
    return BaseClientes(caminho_base(pasta, unidade), unidade)


def unidades_com_base(pasta: str) -> list:
    destino = os.path.join(pasta, "clientes")
    if not os.path.isdir(destino):
        return []
    return sorted(
        n[:-5] for n in os.listdir(destino) if n.endswith(".json")
    )
