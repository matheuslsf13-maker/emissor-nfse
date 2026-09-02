# Emissor de NFS-e — padrão nacional, emissor municipal de Vila Velha/ES

Lê os relatórios de caixa de um sistema de gestão odontológica, cruza com o
cadastro de pacientes e emite as NFS-e assinadas direto no WebService da
prefeitura — no lugar de digitar uma a uma no portal.

Roda como aplicativo local: um `.bat`, o navegador abre sozinho, e quem opera
não precisa saber nada de programação nem de fiscal.

> **Estado:** transmitindo em homologação de Vila Velha desde 01/09/2026.
> Emissão validada com 650 lançamentos reais de duas unidades.

---

## O que ele resolve

Uma clínica com 400 recebimentos por mês precisa de 400 notas. Digitadas a
mão, são dias de trabalho e erros de digitação em CPF e valor. O caixa do
sistema de gestão já tem tudo — falta cruzar com o cadastro e montar o XML.

```
PDF do caixa  ─┐
                ├─→  conciliação  →  XML assinado  →  prefeitura  →  nº da nota
PDF de clientes ┘
```

O trabalho difícil não é gerar XML. É **decidir o que vira nota**, encontrar
o paciente certo quando o nome vem escrito diferente, e **não emitir duas
vezes** — porque em Vila Velha cancelar nota exige processo administrativo.

---

## Como funciona

**Leitura dos PDFs por coordenadas.** `pdftotext -layout` mistura colunas de
linhas vizinhas e corrompe os valores em silêncio. O leitor agrupa palavras
por posição vertical e corta por faixas de `x` conhecidas — e confere o total
lido contra o total impresso no próprio relatório. Divergência vira aviso, não
nota errada.

**Base de clientes incremental.** O cadastro é reimportado quando há paciente
novo; o sistema funde por documento válido ou por nome + nascimento, e um CPF
válido nunca é substituído por um inválido.

**Numeração em SQLite, gravada antes do envio.** Número repetido é rejeitado
pela prefeitura. A chave de antiduplicidade é `unidade + lançamento` — não
CPF + valor, porque quatro parcelas iguais no mesmo dia são quatro
atendimentos de verdade.

**Assinatura XMLDSig** RSA-SHA256 com certificado A1, canonicalização
exclusiva.

**Atualização remota.** O responsável publica uma versão; a clínica clica em
atualizar. O pacote carrega só código — `dados/`, certificados e senhas nunca
são tocados, o que é testado contra um pacote hostil de propósito. O `sha256`
é conferido **antes** de escrever qualquer arquivo, e isso não é zelo teórico:
o CDN do GitHub cacheia assets por nome, então refazer uma release reusando o
mesmo nome faz o endereço servir o pacote antigo junto com o manifesto novo.
A conferência transforma isso em "não atualiza agora" em vez de uma
instalação meio velha, meio nova.

---

## Três coisas que só a transmissão real revelou

Nenhuma está na documentação do provedor. Ficam aqui porque quem for integrar
com um município SIL Tecnologia vai passar pelas mesmas.

**1. O parâmetro `<xml>` tem que ser *unqualified*.** O XSD não declara
`elementFormDefault`, então vale o padrão. Com `xmlns=` no elemento da
operação, o filho herda o namespace, o servidor não acha o parâmetro e
responde `XML inválido: Fim prematuro do arquivo`. A solução é pôr o
namespace por prefixo:

```xml
<sil:NotaFiscalNacionalGerar xmlns:sil="http://webservices.sil.com/">
  <xml>...</xml>
</sil:NotaFiscalNacionalGerar>
```

**2. Canonicalização exclusiva, não inclusiva.** Com a inclusiva o retorno é
`Erro na assinatura: Falha na validação da assinatura` — para qualquer
Reference e qualquer algoritmo. Foi o único parâmetro que mudou entre a recusa
e o aceite.

**3. A consulta exige o CNPJ do consulente e assinatura com `URI=""`.** Sem o
CNPJ: `Não foi localizado o CNPJ ou CPF do Consulente`. E o retorno traz a
nota escapada **duas vezes** — sem desescapar o segundo nível, o status diz
sucesso e nenhum campo aparece.

---

## Rodando

```bash
pip install -r requirements.txt
python app.py
```

A configuração parte de `config/empresas.exemplo.json`, com dados fictícios.
Para valer, preencha `config/empresas.json` com os dados da sua clínica e
ponha o certificado A1 em `config/certificados/`.

Sem certificado o sistema funciona: gera os XMLs **sem assinatura**, que
servem para conferência mas não para transmitir.

### Empacotar para uma máquina sem Python

```bash
python empacotar.py
```

Monta uma pasta com Python 3.12 embutido que roda em qualquer Windows 64
bits. Escolhido em vez de PyInstaller porque o código continua sendo `.py` —
a atualização remota troca alguns KB em vez de republicar um binário.

---

## Testes

```bash
python testes/rodar_tudo.py       # conciliação e emissão, ponta a ponta
python testes/t_robustez.py       # PDF corrompido, nomes repetidos, concorrência
python testes/t_atualizacao.py    # atualização remota contra um pacote hostil
python testes/t_transmissao.py    # envelope SOAP, assinatura, trava de ambiente
python testes/t_base_clientes.py  # importação incremental
```

Cerca de 200 verificações. Os testes que dependem de relatórios reais são
pulados quando os PDFs não estão presentes — o repositório não os inclui, por
serem dados de paciente.

---

## O que **não** está aqui

Nem certificados, nem senhas, nem `config/empresas.json` com dados reais, nem
a base de pacientes, nem os PDFs. Tudo isso fica fora do versionamento por
`.gitignore` — o repositório tem o programa, não a clínica.

---

## Estrutura

```
app.py                 servidor Flask e as telas
nfse/
  pdf.py               leitura por coordenadas
  leitor_caixa.py      recebimentos, com conferência dos totais
  leitor_clientes.py   cadastro de pacientes
  base_clientes.py     base incremental, com fusão de duplicatas
  conciliacao.py       o que vira nota, o que trava e por quê
  gerador_dps.py       XML do padrão nacional
  assinatura.py        XMLDSig com certificado A1
  envio.py             SOAP do WebService municipal
  consulta.py          conferir a nota do lado da prefeitura
  controle.py          numeração e antiduplicidade (SQLite)
  atualizacao.py       atualização remota
empacotar.py           monta o aplicativo com Python embutido
publicar.py            gera o pacote de atualização
```

Comentários em português, explicando **por que** cada decisão foi tomada —
principalmente onde a escolha óbvia estava errada.
