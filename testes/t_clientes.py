# -*- coding: utf-8 -*-
"""Le o cadastro completo e resume o que foi extraido."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from nfse.leitor_clientes import ler_clientes_cache
from nfse.municipios import codigo_ibge

CAM = os.path.join(BASE_DADOS, CLIENTES)
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "dados", "cache")

marca = [time.time()]


def progresso(feito, total):
    if feito % 200 == 0 or feito == total:
        print("   pagina %d/%d (%.0fs)" % (feito, total, time.time() - marca[0]),
              flush=True)


t = time.time()
cad = ler_clientes_cache(CAM, CACHE, progresso=progresso)
print("lidos %d cadastros em %.1fs" % (len(cad.clientes), time.time() - t))
print("empresa:", cad.empresa)
for a in cad.avisos:
    print("  AVISO:", a)

ok = sum(1 for c in cad.clientes if c.documento_ok)
end = sum(1 for c in cad.clientes if c.endereco_completo)
print("documento valido: %d   endereco completo: %d" % (ok, end))

cidades = {}
for c in cad.clientes:
    cidades[(c.cidade, c.uf)] = cidades.get((c.cidade, c.uf), 0) + 1
print("cidades distintas:", len(cidades))
desconhecidas = [(k, v) for k, v in cidades.items() if not codigo_ibge(k[0], k[1])]
print("sem codigo IBGE:", sorted(desconhecidas, key=lambda x: -x[1])[:15])
print("top cidades:", sorted(cidades.items(), key=lambda x: -x[1])[:8])

print("\namostra:")
for c in cad.clientes[:4]:
    print("  %-42s %-18s %s, %s - %s - %s/%s CEP %s | %s"
          % (c.nome, c.documento_formatado, c.logradouro, c.numero, c.bairro,
             c.cidade, c.uf, c.cep, c.email or "-"))

print("\ncasos citados no handoff:")
for alvo in ["PEDRO ESTEFANI ROCHA BERNARDES", "MARIA LAMAS DE SOUZA DOS SANTOS",
             "VITORIA LAMAS DE SOUZA DOS SANTOS"]:
    achados = cad.por_nome_exato(alvo)
    print("  %-36s -> %s" % (alvo, [(a.documento_formatado, a.documento_ok) for a in achados]))
for cpf in ["089.487.787-90", "071.746.437-79", "772.889.127-87"]:
    print("  %s -> %s" % (cpf, [a.nome for a in cad.por_cpf(cpf)]))
