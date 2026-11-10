# Testes

```
python testes/rodar_tudo.py      # leitura, conciliacao, XML, assinatura
python testes/t_transmissao.py   # envio, contra um servidor local
python testes/t_base_clientes.py # base de clientes e importacao incremental
```

Bateria completa contra os PDFs reais de agosto/2026 da Glória. Confere os
totais impressos no próprio relatório de caixa, o número de notas, o valor,
as pendências conhecidas, a estrutura do XML, a assinatura (inclusive
adulteração), a numeração e a antiduplicidade. Restaura `dados/controle.json`
e o certificado ao terminar — pode rodar à vontade.

Os outros scripts são de inspeção, para investigar um caso específico:

| Script | Para quê |
|---|---|
| `t_transmissao.py` | envelope SOAP, leitura do retorno e transmissão (servidor local, não toca na prefeitura) |
| `t_duplicatas.py` | mede as duplicatas do cadastro do TechCare |

Os caminhos dos PDFs de referência estão em `apoio.py`.
