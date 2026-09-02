# -*- coding: utf-8 -*-
"""Carrega e valida config/empresas.json.

A configuracao e a unica fonte de CNPJ, endereco, aliquota e regras. O
comando `verificar` (e a tela Configuracao) usa `diagnostico()` para dizer
o que ainda falta antes de emitir de verdade.
"""

from __future__ import annotations

import json
import os

from .documentos import cnpj_valido
from .util import chave_nome

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_CONFIG = os.path.join(RAIZ, "config", "empresas.json")
PASTA_CERTIFICADOS = os.path.join(RAIZ, "config", "certificados")
PASTA_DADOS = os.path.join(RAIZ, "dados")
PASTA_CACHE = os.path.join(PASTA_DADOS, "cache")
PASTA_LOTES = os.path.join(PASTA_DADOS, "lotes")
PASTA_SAIDA = os.path.join(PASTA_DADOS, "saida")
PASTA_ENTRADA = os.path.join(RAIZ, "entrada")


class Config:
    def __init__(self, bruto: dict):
        self.bruto = bruto
        self.municipio = bruto["municipio_emitente"]
        self.servico = bruto["servico"]
        self.ibscbs = bruto.get("ibscbs", {})
        self.faturamento = bruto["faturamento"]
        self.unidades = bruto["unidades"]

    # -- acesso -----------------------------------------------------------
    def unidade(self, chave: str) -> dict:
        if chave not in self.unidades:
            raise KeyError("Unidade nao configurada: %s" % chave)
        dados = dict(self.unidades[chave])
        dados["chave"] = chave
        return dados

    def unidade_por_relatorio(self, nome_empresa: str):
        """Descobre a unidade a partir do cabecalho EMPRESA: do relatorio."""
        alvo = chave_nome(nome_empresa)
        for chave, dados in self.unidades.items():
            marcador = chave_nome(dados.get("empresa_no_relatorio", ""))
            if marcador and marcador in alvo:
                return chave
        return None

    def caminho_certificado(self, chave: str) -> str:
        return os.path.join(PASTA_CERTIFICADOS, self.unidade(chave)["certificado"])

    def senha_certificado(self, chave: str):
        return os.environ.get(self.unidade(chave)["variavel_senha"]) or None

    # -- diagnostico -------------------------------------------------------
    def diagnostico(self) -> list:
        """Lista o que impede a emissao, em ordem de gravidade.

        Cada item: {nivel, titulo, detalhe}. nivel em erro | atencao | info.
        """
        itens = []
        for chave, dados in self.unidades.items():
            nome = dados.get("apelido", chave)
            if not cnpj_valido(dados.get("cnpj", "")):
                itens.append(_erro(
                    "CNPJ inválido em %s" % nome,
                    "O CNPJ %s não passa na validação." % dados.get("cnpj")))
            faltando = [
                campo for campo, valor in dados.get("endereco", {}).items()
                if not valor and campo != "complemento"
            ]
            if faltando:
                itens.append(_erro(
                    "Endereço incompleto em %s" % nome,
                    "Faltam: %s." % ", ".join(faltando)))
            endereco_texto = json.dumps(
                dados.get("endereco", {}), ensure_ascii=False).upper()
            if "CONFIRMAR" in endereco_texto:
                # Nao e so um lembrete: esse texto entraria no XML como se
                # fosse o endereco do emitente.
                itens.append(_erro(
                    "Endereço de %s tem campo por confirmar" % nome,
                    "A palavra CONFIRMAR está no endereço e iria para dentro "
                    "da nota. Corrija em config/empresas.json antes de emitir."))
            resto = json.dumps(
                {k: v for k, v in dados.items() if k != "endereco"},
                ensure_ascii=False).upper()
            if "CONFIRMAR" in resto:
                itens.append(_atencao(
                    "Dados de %s ainda não confirmados" % nome,
                    "Há campos marcados como CONFIRMAR em config/empresas.json."))
            caminho = os.path.join(PASTA_CERTIFICADOS, dados.get("certificado", ""))
            if not os.path.exists(caminho):
                itens.append(_atencao(
                    "Certificado de %s não encontrado" % nome,
                    "Coloque o arquivo %s na pasta config/certificados/."
                    % dados.get("certificado")))
            elif not os.environ.get(dados.get("variavel_senha", "")):
                itens.append(_atencao(
                    "Senha do certificado de %s não definida" % nome,
                    "Defina a variável de ambiente %s (ou preencha config/senhas.bat) antes de assinar."
                    % dados.get("variavel_senha")))
            else:
                itens.extend(self._conferir_certificado(chave, nome, dados, caminho))

        if not self.municipio.get("endpoints", {}).get("producao"):
            itens.append(_info(
                "Endereço de produção do WebService desconhecido",
                "O envio automático só pode ser ligado depois que a prefeitura "
                "informar a URL de produção e habilitar os CNPJs."))

        if self.ibscbs.get("emitir") and not self.ibscbs.get("confirmado_pelo_contador"):
            itens.append(_erro(
                "IBS/CBS ligado sem confirmação do contador",
                "O código de classificação %s muda a redução de base (60%% ou "
                "30%%). Confirme com o contador antes de emitir."
                % self.ibscbs.get("codigo_classificacao_tributaria")))
        elif not self.ibscbs.get("emitir"):
            itens.append(_info(
                "Grupos de IBS/CBS desligados",
                "A Nota Técnica SE/CGNFS-e nº 009 prevê obrigatoriedade a partir "
                "de 03/08/2026. Confirme com o contador e ligue em "
                "config/empresas.json."))

        if self.faturamento.get("emitir_convenios"):
            itens.append(_atencao(
                "Emissão de convênios ligada",
                "Convênio recebe UMA nota consolidada por competência, não uma "
                "por paciente. Valide a consolidação antes de emitir."))
        return itens


    def _conferir_certificado(self, chave, nome, dados, caminho) -> list:
        """Abre o certificado e confere se ele e mesmo desta unidade.

        Certificado trocado de lugar assinaria as notas de uma clinica com o
        CNPJ da outra -- erro que so apareceria na rejeicao, ou pior, so na
        fiscalizacao.
        """
        from .assinatura import ErroCertificado, carregar_pfx

        try:
            cert = carregar_pfx(caminho, os.environ.get(dados["variavel_senha"]))
        except ErroCertificado as erro:
            return [_erro("Certificado de %s não abre" % nome, str(erro))]

        itens = []
        esperado = "".join(c for c in dados.get("cnpj", "") if c.isdigit())
        if cert.cnpj and esperado and cert.cnpj != esperado:
            itens.append(_erro(
                "O certificado de %s é de outra empresa" % nome,
                "O arquivo pertence ao CNPJ %s, mas esta unidade é %s. "
                "As notas sairiam assinadas pela empresa errada."
                % (cert.cnpj, esperado)))
        if cert.vencido:
            itens.append(_erro(
                "Certificado de %s vencido" % nome,
                "Venceu em %s. Não serve para transmitir."
                % cert.validade.strftime("%d/%m/%Y")))
        elif cert.dias_para_vencer <= 30:
            itens.append(_atencao(
                "Certificado de %s vence em %d dias" % (nome, cert.dias_para_vencer),
                "Vence em %s. Providencie a renovação antes que pare de emitir."
                % cert.validade.strftime("%d/%m/%Y")))
        return itens


def _erro(titulo, detalhe):
    return {"nivel": "erro", "titulo": titulo, "detalhe": detalhe}


def _atencao(titulo, detalhe):
    return {"nivel": "atencao", "titulo": titulo, "detalhe": detalhe}


def _info(titulo, detalhe):
    return {"nivel": "info", "titulo": titulo, "detalhe": detalhe}


def carregar(caminho: str = None) -> Config:
    alvo = caminho or CAMINHO_CONFIG
    if not os.path.exists(alvo):
        # O `empresas.json` guarda CNPJ, inscricao municipal e endereco das
        # clinicas -- dado real, que nao vai para o repositorio. Numa copia
        # recem-clonada ele nao existe, e o programa nao abriria. Partir do
        # exemplo deixa o sistema rodavel na hora, com dados ficticios que
        # ninguem confunde com os de verdade.
        exemplo = os.path.join(os.path.dirname(alvo), "empresas.exemplo.json")
        if os.path.exists(exemplo):
            import shutil

            shutil.copy2(exemplo, alvo)
        else:
            raise FileNotFoundError(
                "Configuração não encontrada: %s. Copie o "
                "config/empresas.exemplo.json para config/empresas.json e "
                "preencha os dados da clínica." % alvo
            )
    with open(alvo, encoding="utf-8") as fh:
        return Config(json.load(fh))


def garantir_pastas() -> None:
    for pasta in (PASTA_CERTIFICADOS, PASTA_CACHE, PASTA_LOTES, PASTA_SAIDA,
                  PASTA_ENTRADA):
        os.makedirs(pasta, exist_ok=True)
