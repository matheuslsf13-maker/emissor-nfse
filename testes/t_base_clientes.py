# -*- coding: utf-8 -*-
"""Testa a base de clientes persistente e a importação incremental.

Usa o relatório real (12.017 cadastros) para a primeira carga e depois
monta relatórios sintéticos para os casos que interessam: pessoa nova,
CPF corrigido, endereço alterado, reimportação do mesmo arquivo.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from apoio import BASE_DADOS, CLIENTES, exigir_dados_reais

exigir_dados_reais("t_base_clientes")
from nfse import config as cfgmod
from nfse.base_clientes import BaseClientes
from nfse.leitor_clientes import Cadastro, Cliente, ler_clientes_cache

falhas = []
passou = 0


def checar(descricao, condicao, detalhe=""):
    global passou
    if condicao:
        passou += 1
        print("  [ok]    %s" % descricao)
    else:
        falhas.append(descricao)
        print("  [FALHA] %s   %s" % (descricao, detalhe))


def cadastro_de(*clientes):
    c = Cadastro(arquivo="sintetico", clientes=list(clientes))
    c.indexar()
    return c


pasta = tempfile.mkdtemp(prefix="nfse-base-")
try:
    caminho = os.path.join(pasta, "clientes", "gloria.json")

    print("1. Primeira carga (relatório real)")
    real = ler_clientes_cache(os.path.join(BASE_DADOS, CLIENTES),
                              cfgmod.PASTA_CACHE)
    base = BaseClientes(caminho, "gloria")
    checar("base começa vazia", not base.existe)
    r1 = base.mesclar(real, origem="CLIENTES.PDF")
    # 12.017 cadastros no PDF, mas 29 são a MESMA pessoa cadastrada duas vezes
    # (o padrão do TechCare: um registro com CPF terminado em 000-00 e outro
    # com o CPF bom). Fundir esses 29 é o comportamento certo.
    checar("leu os 12.017 cadastros do PDF", r1["lidos"] == 12017, str(r1["lidos"]))
    checar("base ficou com 11.988 pessoas (29 duplicatas fundidas)",
           base.total == 11988, str(base.total))
    checar("gravou em disco", os.path.exists(caminho))
    checar("o PDF de origem não foi alterado pelo merge",
           len(real.clientes) == 12017)

    print("\n2. Reimportar o MESMO relatório não duplica nada")
    base2 = BaseClientes(caminho, "gloria")
    checar("base recarregada do disco tem o mesmo total",
           base2.total == 11988, str(base2.total))
    r2 = base2.mesclar(real, origem="CLIENTES.PDF")
    checar("nenhum novo", r2["novos"] == 0, str(r2["novos"]))
    checar("nenhum atualizado", r2["atualizados"] == 0, str(r2["atualizados"]))
    checar("todos reconhecidos como iguais", r2["iguais"] == 11988, str(r2["iguais"]))
    checar("o relatório foi consolidado antes de mesclar",
           r2["consolidados"] == 11988, str(r2["consolidados"]))
    checar("total não mudou", base2.total == 11988, str(base2.total))

    print("\n3. Paciente novo entra")
    novo = Cliente(nome="ZORAIDE TESTE DA SILVA", documento="15119729711",
                   logradouro="RUA NOVA", numero="10", bairro="CENTRO",
                   cidade="VILA VELHA", uf="ES", cep="29100000",
                   nascimento="01/01/1990")
    novo.documento = "39053344705"      # CPF válido que não existe na base
    base3 = BaseClientes(caminho, "gloria")
    antes = base3.total
    r3 = base3.mesclar(cadastro_de(novo), origem="novo.pdf")
    checar("entrou 1 pessoa nova", r3["novos"] == 1, str(r3["novos"]))
    checar("total subiu 1", base3.total == antes + 1)
    checar("aparece na lista de novos",
           r3["lista_novos"][0]["nome"] == "ZORAIDE TESTE DA SILVA")

    print("\n4. CPF corrigido é reconhecido como a MESMA pessoa")
    base4 = BaseClientes(caminho, "gloria")
    pedro = next((c for c in base4.clientes
                  if c.chave.startswith("PEDRO ESTEFANI ROCHA")), None)
    checar("PEDRO está na base com CPF inválido",
           pedro is not None and not pedro.documento_ok,
           pedro.documento if pedro else "não achado")
    antes = base4.total
    corrigido = Cliente(**{**pedro.__dict__, "documento": "39053344705"})
    corrigido.documento = "11144477735"          # CPF válido
    r4 = base4.mesclar(cadastro_de(corrigido), origem="correcao.pdf")
    checar("não criou cadastro novo", r4["novos"] == 0, str(r4["novos"]))
    checar("marcou como atualizado", r4["atualizados"] == 1, str(r4["atualizados"]))
    checar("total não subiu", base4.total == antes, str(base4.total))
    pedro2 = next(c for c in base4.clientes
                  if c.chave.startswith("PEDRO ESTEFANI ROCHA"))
    checar("CPF agora é o corrigido e é válido",
           pedro2.documento == "11144477735" and pedro2.documento_ok,
           pedro2.documento)
    checar("a mudança de documento fica registrada",
           r4["lista_atualizados"][0]["documento_mudou"])

    print("\n5. Endereço alterado atualiza sem duplicar")
    base5 = BaseClientes(caminho, "gloria")
    alvo = base5.clientes[0]
    antes = base5.total
    mudado = Cliente(**{**alvo.__dict__})
    mudado.logradouro = "RUA QUE MUDOU"
    r5 = base5.mesclar(cadastro_de(mudado), origem="mudanca.pdf")
    checar("atualizou em vez de duplicar",
           r5["novos"] == 0 and r5["atualizados"] == 1 and base5.total == antes)
    checar("endereço novo aplicado",
           base5.clientes[0].logradouro == "RUA QUE MUDOU")

    print("\n6. Campo vazio no relatório não apaga o que já existe")
    base6 = BaseClientes(caminho, "gloria")
    alvo = base6.clientes[0]
    bairro_antes = alvo.bairro
    vazio = Cliente(**{**alvo.__dict__})
    vazio.bairro = ""
    r6 = base6.mesclar(cadastro_de(vazio), origem="incompleto.pdf")
    checar("nada foi alterado", r6["atualizados"] == 0, str(r6["atualizados"]))
    checar("bairro preservado", base6.clientes[0].bairro == bairro_antes)

    print("\n7. A base serve para conciliar")
    base7 = BaseClientes(caminho, "gloria")
    cadastro = base7.como_cadastro()
    checar("vira um Cadastro indexado", len(cadastro.clientes) == base7.total)
    achados = cadastro.por_nome_exato("VITORIA LAMAS DE SOUZA DOS SANTOS")
    checar("busca por nome funciona", len(achados) == 1, str(len(achados)))
    checar("busca por CPF funciona",
           len(cadastro.por_cpf("151.197.297-11")) == 1)

    print("\n8. Duplicata com CPF inválido não sobrescreve o válido")
    base8 = BaseClientes(caminho, "gloria")
    diego = next(c for c in base8.clientes
                 if c.chave.startswith("DIEGO GABRIEL CAMPOS"))
    checar("a duplicata ficou com o CPF válido", diego.documento_ok,
           diego.documento)
    ruim = Cliente(**{**diego.__dict__})
    ruim.documento = "87388000000"          # o CPF inválido do cadastro gêmeo
    base8.mesclar(cadastro_de(ruim), origem="regressao.pdf")
    depois = next(c for c in base8.clientes
                  if c.chave.startswith("DIEGO GABRIEL CAMPOS"))
    checar("CPF válido NÃO foi substituído pelo inválido",
           depois.documento_ok and depois.documento == diego.documento,
           depois.documento)

    print("\n9. Histórico das importações")
    resumo = BaseClientes(caminho, "gloria").resumo()
    checar("guardou as 7 importações", resumo["importacoes"] == 7,
           str(resumo["importacoes"]))
    checar("tem data de criação e de atualização",
           bool(resumo["criada_em"]) and bool(resumo["atualizada_em"]))
finally:
    shutil.rmtree(pasta, ignore_errors=True)


# --------------------------------------------------------------------------
print("\nBusca na base de clientes")
# Saber que ha "849 sem CPF valido" nao ajuda ninguem: o operador precisa
# CHEGAR neles para corrigir no TechCare. Antes, a unica forma era esbarrar
# no problema durante a conferencia, um lancamento por vez.
from nfse.util import chave_nome  # noqa: E402

pasta_busca = tempfile.mkdtemp(prefix="nfse-busca-")
try:
    base_b = BaseClientes(os.path.join(pasta_busca, "gloria.json"), "gloria")
    base_b.mesclar(real, origem="busca")
    base_b.salvar()

    achados, quantos = base_b.procurar("MARCELA")
    checar("acha por parte do nome", quantos > 0, quantos)
    checar("e todo achado contem o termo",
           all("MARCELA" in chave_nome(c.nome) for c in achados))

    alguem = next((c for c in base_b.clientes if c.documento_ok), None)
    if alguem:
        achados, quantos = base_b.procurar(alguem.documento)
        checar("acha pelo numero do documento", quantos >= 1, quantos)

    achados, quantos = base_b.procurar(filtro="sem_documento")
    checar("filtro sem_documento so traz documento invalido",
           all(not c.documento_ok for c in achados), len(achados))
    checar("e bate com a contagem de pendencias",
           quantos == base_b.pendencias()["sem_documento"],
           (quantos, base_b.pendencias()))

    achados, quantos = base_b.procurar("nao-existe-esse-nome")
    checar("busca sem resultado devolve vazio, nao quebra",
           achados == [] and quantos == 0)

    achados, _ = base_b.procurar(limite=5)
    checar("o limite e respeitado", len(achados) <= 5, len(achados))
finally:
    shutil.rmtree(pasta_busca, ignore_errors=True)

print("\n" + "=" * 62)
if falhas:
    print("%d verificacao(oes) FALHARAM:" % len(falhas))
    for f in falhas:
        print("   - %s" % f)
    sys.exit(1)
print("Tudo certo: %d verificacoes passaram." % passou)
