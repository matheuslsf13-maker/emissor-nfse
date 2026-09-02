# -*- coding: utf-8 -*-
"""Apoio dos testes: certificado autoassinado e carregamento dos dados reais.

O certificado criado aqui prova que o caminho de assinatura funciona. O
certificado de verdade (A1 da clinica) entra em config/certificados/ e nunca
e versionado.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

# Onde estao os relatorios reais usados nos testes de regressao. Eles NAO
# entram no repositorio -- sao dados de paciente. Quem clonar o projeto nao
# os tem, e os testes que dependem deles se anunciam como pulados em vez de
# quebrar com FileNotFoundError.
BASE_DADOS = os.environ.get(
    "NFSE_DADOS_TESTE",
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CAIXAS = ("agostoo.PDF", "agostoooooo.PDF")
CLIENTES = "CLIENTES.PDF"


def ha_dados_reais() -> bool:
    """Os PDFs de referencia estao nesta maquina?"""
    return all(os.path.exists(os.path.join(BASE_DADOS, f))
               for f in CAIXAS + (CLIENTES,))


def exigir_dados_reais(nome_do_teste: str) -> None:
    """Encerra o teste com aviso claro quando os PDFs nao estao aqui.

    Sai com codigo 0 de proposito: nao ter os relatorios nao e falha do
    codigo, e um teste "vermelho" por falta de dado treina todo mundo a
    ignorar vermelho.
    """
    if ha_dados_reais():
        return
    import sys as _sys

    print("%s: PULADO -- os relatorios reais nao estao nesta maquina." % nome_do_teste)
    print("   Eles nao entram no repositorio (dados de paciente).")
    print("   Para rodar, aponte NFSE_DADOS_TESTE para a pasta com:")
    for arquivo in CAIXAS + (CLIENTES,):
        print("      %s" % arquivo)
    _sys.exit(0)


def certificado_de_teste(caminho, senha=b"teste123"):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "TESTE"),
        x509.NameAttribute(NameOID.COMMON_NAME,
                           "CLINICA ODONTOLOGICA EXEMPLO LTDA:11222333000181"),
    ])
    agora = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - timedelta(days=1))
            .not_valid_after(agora + timedelta(days=365))
            .sign(chave, hashes.SHA256()))
    dados = pkcs12.serialize_key_and_certificates(
        b"teste", chave, cert, None,
        serialization.BestAvailableEncryption(senha))
    with open(caminho, "wb") as fh:
        fh.write(dados)
    return caminho


def carregar_tudo(unidade="gloria"):
    """Le os PDFs reais e devolve (config, caixas, cadastro, conciliacao)."""
    from nfse import config as cfgmod
    from nfse.conciliacao import conciliar
    from nfse.leitor_caixa import ler_caixa
    from nfse.leitor_clientes import ler_clientes_cache

    cfg = cfgmod.carregar()
    caixas = [ler_caixa(os.path.join(BASE_DADOS, f)) for f in CAIXAS]
    cadastro = ler_clientes_cache(os.path.join(BASE_DADOS, CLIENTES),
                                  cfgmod.PASTA_CACHE)
    resultado = conciliar(caixas, cadastro, cfg, unidade)
    return cfg, caixas, cadastro, resultado


def preparar_saida():
    """Pasta descartavel para os XMLs dos testes."""
    import tempfile

    return tempfile.mkdtemp(prefix="nfse-teste-")
