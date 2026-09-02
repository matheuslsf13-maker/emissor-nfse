# -*- coding: utf-8 -*-
"""Regras de negocio: o que vira nota e o que nao vira.

Principio do projeto: nada sai silenciosamente. Todo lancamento recebe uma
decisao com motivo legivel, e o motivo aparece na tela. Se um lancamento
nao virou nota, o operador precisa saber qual regra o excluiu -- descobrir
isso tres meses depois seria muito pior.
"""

from __future__ import annotations

from .util import chave_nome

# Decisoes possiveis
EMITE = "emite"
NAO_EMITE = "nao_emite"

# Motivos (usados como chave de agrupamento na tela)
M_SAIDA = "Saída de caixa (lançamento negativo)"
M_DINHEIRO = "Recebimento em dinheiro (regra da clínica)"
M_ENVELOPE = "Envelope — movimento interno de caixa"
M_SECAO = "Seção do caixa que não gera nota"
M_CONVENIO = "Convênio — fatura consolidado, desligado nesta fase"
M_PARTICULAR = "Emissão de particulares desligada na configuração"
M_SEM_NOME = "Lançamento sem paciente identificável"


class Regras:
    def __init__(self, config):
        f = config.faturamento
        self.emitir_particulares = bool(f.get("emitir_particulares", True))
        self.emitir_convenios = bool(f.get("emitir_convenios", False))
        self.secoes = {chave_nome(s) for s in f.get("secoes_que_emitem", [])}
        self.bloqueios = [chave_nome(p) for p in f.get("palavras_que_bloqueiam", [])]
        # prefixos mais longos primeiro: "UNIMED ODONTO" antes de "UNIMED"
        self.prefixos_convenio = sorted(
            (chave_nome(p) for p in f.get("prefixos_convenio", [])),
            key=len,
            reverse=True,
        )

    # -- classificacao ----------------------------------------------------
    def convenio_de(self, nome: str):
        """Devolve o convenio quando o nome do paciente vem prefixado por ele."""
        alvo = chave_nome(nome)
        for prefixo in self.prefixos_convenio:
            if alvo == prefixo or alvo.startswith(prefixo + " "):
                return prefixo
        return None

    def nome_do_paciente(self, nome: str) -> str:
        """Remove o prefixo do convenio, deixando so o nome da pessoa."""
        convenio = self.convenio_de(nome)
        if not convenio:
            return chave_nome(nome)
        return chave_nome(nome)[len(convenio):].strip()

    def avaliar(self, lanc):
        """Devolve (decisao, motivo, tipo_faturamento).

        tipo_faturamento: 'particular' | 'convenio' | ''.
        """
        secao = chave_nome(lanc.secao)

        if lanc.sinal == "-":
            return NAO_EMITE, M_SAIDA, ""
        for palavra in self.bloqueios:
            if palavra and palavra in secao:
                motivo = M_DINHEIRO if palavra == "DINHEIRO" else M_ENVELOPE
                return NAO_EMITE, motivo, ""
        if lanc.tipo == "OUTRO":
            return NAO_EMITE, M_ENVELOPE if "ENVELOPE" in secao else M_SEM_NOME, ""
        if secao not in self.secoes:
            return NAO_EMITE, M_SECAO, ""

        # Boleto traz CPF no lugar do nome: nunca e convenio.
        if lanc.tipo == "BCO":
            if not self.emitir_particulares:
                return NAO_EMITE, M_PARTICULAR, "particular"
            return EMITE, "", "particular"

        convenio = self.convenio_de(lanc.nome_bruto)
        if convenio:
            if not self.emitir_convenios:
                return NAO_EMITE, M_CONVENIO, "convenio"
            return EMITE, "", "convenio"

        if not lanc.nome_bruto:
            return NAO_EMITE, M_SEM_NOME, ""
        if not self.emitir_particulares:
            return NAO_EMITE, M_PARTICULAR, "particular"
        return EMITE, "", "particular"
