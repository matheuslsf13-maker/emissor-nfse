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
| `t_caixa.py` | leitura do caixa, seção por seção, contra os totais do relatório |
| `t_clientes.py` | cadastro: quantos, cidades, CPFs inválidos, amostras |
| `t_conciliar.py` | conciliação detalhada, com pendências e ajustes automáticos |
| `t_emissao.py` | XML campo por campo e a assinatura digital |
| `t_transmissao.py` | envelope SOAP, leitura do retorno e transmissão (servidor local, não toca na prefeitura) |
| `t_uma_nota.py <pasta>` | emite UMA nota valendo e mostra o XML inteiro (não transmite) |
| `t_bia.py <pasta>` | roda as duas unidades com os PDFs de agosto/2026 |
| `t_duplicatas.py` | mede as duplicatas do cadastro do TechCare |
| `t_busca.py "NOME"` | procurar alguém no cadastro (útil quando um paciente "some") |
| `t_amostra_clientes.py` | geometria crua do PDF — use se o layout do relatório mudar |

Os caminhos dos PDFs de referência estão em `apoio.py`.
