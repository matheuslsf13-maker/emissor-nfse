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
from .municipios import codigo_ibge
from .util import chave_nome, so_digitos

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMINHO_CONFIG = os.path.join(RAIZ, "config", "empresas.json")
PASTA_CERTIFICADOS = os.path.join(RAIZ, "config", "certificados")
CAMINHO_SENHAS = os.path.join(RAIZ, "config", "senhas.json")
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
                    "Envie o arquivo do certificado (.pfx) em Configuração, "
                    "no cartão da clínica."))
            elif not os.environ.get(dados.get("variavel_senha", "")):
                itens.append(_atencao(
                    "Senha do certificado de %s não definida" % nome,
                    "Informe a senha em Configuração, no cartão da clínica."))
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


def carregar_senhas(caminho: str = None) -> None:
    """Poe no ambiente as senhas de certificado informadas pela tela.

    Valem sobre as do senhas.bat: a da tela e sempre a mais recente, e foi
    conferida contra o certificado na hora em que foi salva.
    """
    try:
        with open(caminho or CAMINHO_SENHAS, encoding="utf-8") as fh:
            senhas = json.load(fh)
    except (OSError, ValueError):
        return
    for variavel, senha in senhas.items():
        if senha:
            os.environ[variavel] = senha


def guardar_senha(variavel: str, senha: str, caminho: str = None) -> None:
    alvo = caminho or CAMINHO_SENHAS
    try:
        with open(alvo, encoding="utf-8") as fh:
            senhas = json.load(fh)
    except (OSError, ValueError):
        senhas = {}
    senhas[variavel] = senha
    with open(alvo + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(senhas, fh, ensure_ascii=False, indent=2)
    os.replace(alvo + ".tmp", alvo)
    os.environ[variavel] = senha


carregar_senhas()


LISTAS_DE_REGRAS = ("secoes_que_emitem", "secoes_ignoradas",
                    "palavras_que_bloqueiam", "prefixos_convenio")


def salvar_faturamento(mudancas: dict, caminho: str = None) -> None:
    """Grava mudancas no bloco `faturamento`, sem tocar no resto do arquivo."""
    alvo = caminho or CAMINHO_CONFIG
    with open(alvo, encoding="utf-8") as fh:
        bruto = json.load(fh)
    bruto["faturamento"].update(mudancas)
    # Grava ao lado e troca: queda de energia no meio nao deixa a
    # configuracao pela metade.
    with open(alvo + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(bruto, fh, ensure_ascii=False, indent=2)
    os.replace(alvo + ".tmp", alvo)


CAMPOS_CONVENIO = ("nome", "cnpj", "cep", "logradouro", "numero", "bairro",
                   "cidade", "uf")


def validar_convenio(form) -> tuple:
    """Confere os dados de um convenio vindos da tela: (dados, erros).

    O convenio e o tomador da nota consolidada: CNPJ ou cidade errados so
    apareceriam como rejeicao da prefeitura, com a nota ja montada.
    """
    dados = {campo: " ".join((form.get(campo) or "").upper().split())
             for campo in CAMPOS_CONVENIO}
    dados["cnpj"] = so_digitos(dados["cnpj"])
    dados["cep"] = so_digitos(dados["cep"])
    dados["numero"] = dados["numero"] or "SN"
    erros = []
    if not dados["nome"]:
        erros.append("Informe a razão social.")
    if not cnpj_valido(dados["cnpj"]):
        erros.append("O CNPJ não passa na validação: confira os números.")
    if len(dados["cep"]) != 8:
        erros.append("O CEP precisa ter 8 números.")
    if not dados["logradouro"] or not dados["bairro"]:
        erros.append("Informe a rua e o bairro.")
    if not codigo_ibge(dados["cidade"], dados["uf"]):
        erros.append("Cidade e UF não foram reconhecidas: confira a grafia.")
    return dados, erros


def salvar_convenio(chave: str, dados: dict, caminho: str = None) -> None:
    """Grava os dados de um convenio, sem tocar nos outros."""
    convenios = dict(carregar(caminho).faturamento.get("convenios", {}))
    convenios[chave] = {**convenios.get(chave, {}), **dados}
    salvar_faturamento({"convenios": convenios}, caminho)


def garantir_pastas() -> None:
    for pasta in (PASTA_CERTIFICADOS, PASTA_CACHE, PASTA_LOTES, PASTA_SAIDA,
                  PASTA_ENTRADA):
        os.makedirs(pasta, exist_ok=True)
