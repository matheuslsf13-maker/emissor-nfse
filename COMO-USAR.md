# Emissor de NFS-e — como usar


Guia da pessoa que vai emitir as notas no dia a dia.
Não é preciso entender nada de programação.

---

## O que este programa faz

Todo mês, o TechCare gera o relatório de caixa com os pagamentos que os
pacientes fizeram. Este programa lê esse relatório, descobre o cadastro de
cada paciente e gera a nota fiscal de cada pagamento — as mesmas notas que
antes eram digitadas uma a uma no site da prefeitura.

**O programa não decide nada sozinho.** Ele mostra o que vai fazer, você
confere, e só então manda.

---

## Abrindo

Dois cliques em **Emissor NFS-e.bat**.

Abre uma janela preta e, logo depois, o navegador com o programa.

> **A janela preta tem que ficar aberta.** É ela que faz o programa
> funcionar. Fechar a janela é o mesmo que desligar o programa. No fim do
> dia pode fechar; no dia seguinte abre de novo.

Se o navegador não abrir sozinho, digite `localhost:5510` na barra de
endereço.

---

## O passo a passo do mês

### 1. Tirar os relatórios do TechCare

Você precisa de:

| Relatório | Quando |
|---|---|
| **CAIXA — LANÇAMENTOS** de cada clínica | todo mês |
| **CLIENTES E FORNECEDORES** | só na primeira vez, e quando houver pacientes novos |

Salve em PDF.

> Sobre o de clientes: na primeira vez ele é obrigatório, porque é dele que
> saem os endereços e CPFs. Depois disso o programa guarda tudo. Só mande de
> novo quando tiver paciente novo — o programa compara e guarda só o que
> mudou.

### 2. Arrastar para o programa

Na tela inicial, arraste os PDFs para a área indicada. Pode arrastar todos de
uma vez, em qualquer ordem, **das duas clínicas juntas** — o programa lê no
cabeçalho de cada relatório de qual clínica ele é e separa sozinho.

Clique em **Conferir**.

> Se você mandou relatórios das duas clínicas, aparece um botão de conferir
> para cada uma. Cada clínica é conferida e emitida separadamente.

### 3. Conferir

Esta é a tela mais importante. Ela mostra:

- **quantas notas vão sair** e o valor total;
- **o que ficou travado** e por quê.

Travado quer dizer que falta alguma coisa — normalmente um paciente sem
cadastro ou com CPF errado no TechCare. Cada item explica o que fazer.

**Você tem duas saídas para o que travou:**

1. **Buscar o paciente ali mesmo** — clique em "procurar" e digite o nome.
   Serve quando o nome no caixa está escrito diferente do cadastro.
2. **Deixar de fora** — as notas que não travaram saem normalmente. Corrija
   o cadastro no TechCare e passe o relatório de novo depois.

> Não precisa resolver tudo de uma vez. O que ficar de fora não se perde.

### 4. Emitir as notas

Um botão só: **Emitir as notas**.

São notas fiscais de verdade. Por isso a tela mostra **por qual clínica elas
saem** (nome e CNPJ) e pede para digitar `EMITIR`. Confira a clínica antes de
confirmar — cancelar nota em Vila Velha é processo na prefeitura.

> **Emitir aqui ainda não envia.** As notas ficam prontas no computador. O
> envio para a prefeitura é o passo 5.

> **Emitir de novo não repete nota.** O programa lembra o que já saiu: se
> você emitir o mesmo relatório outra vez, saem só as que faltam.

Dá para emitir só algumas: na lista **Vão virar nota**, marque as que quer.
Sem marcar nada, saem todas.

> **Para o contador:** o botão **Baixar planilha (.xlsx)** gera um arquivo
> com quatro abas — resumo, as notas que vão sair, as travadas e o que não
> gera nota. Os totais são fórmulas, então filtrar recalcula sozinho.

### 5. Transmitir

Aqui as notas vão para a prefeitura.

**Você não escolhe o ambiente de novo** — ele já está assinado dentro de cada
nota, e o programa manda para onde ela foi feita. A tela avisa se é teste ou
se vale de verdade. **Emitir já envia sozinho**; esta tela só mostra o
andamento e, se o envio parar no meio, o botão **Enviar as que faltam**.

Quando são muitas, o envio vai em fila, com **barra de progresso e tempo
restante**. A prefeitura aceita uma nota por vez por clínica, então o
programa espera a vez de cada uma — um lote grande leva de 2 a 20 minutos,
dependendo de quão rápido ela responde. **Não é travamento, e pode fechar a
tela que o envio continua.**

Quando a prefeitura aceita, ela devolve o **número da nota** e a **chave de
acesso**, que ficam guardados.

> **Cancelar em Vila Velha exige processo administrativo** na Secretaria de
> Finanças. Não é um clique — por isso as confirmações digitadas.

---

## Se você fechar a tela no meio

Nada se perde. Na tela inicial aparece **"Notas geradas, esperando a
prefeitura"**, com o botão para continuar de onde parou. Não precisa gerar
tudo de novo.

---

## Procurar um paciente

Menu **Clientes**. Dá para buscar por nome ou CPF, e filtrar por quem está
com cadastro incompleto:

- sem CPF válido
- sem endereço
- sem CEP

Serve para chegar em quem precisa de correção **antes** de gerar as notas.
Corrija no TechCare e mande o relatório de clientes de novo — o programa
compara e atualiza só quem mudou.

---

## Achar e conferir uma nota

Menu **Notas emitidas**. A lista mostra todas as notas que a prefeitura
aceitou, com a clínica de cada uma. Use a busca (nome, CPF ou número da
nota) e os filtros de **clínica** e **mês**.

Em cada nota: **Imprimir** (abre pronta para imprimir ou salvar em PDF) e
**WhatsApp** (abre a conversa com a mensagem pronta — você confere e envia).
Para várias de uma vez, marque as caixinhas e clique em **Imprimir ou salvar
as marcadas**.

No fim da tela, **Conferir uma nota direto na prefeitura**: cole a chave de
acesso (ou clique no número de uma nota da lista) e o programa pergunta ao
sistema da prefeitura o que está registrado lá. Serve quando o paciente liga
perguntando.

### Quando a prefeitura recusa por "número já existe"

Não é defeito da nota, e **reenviar não adianta**: os números já foram usados
na prefeitura. Acontece quando o controle se perde, ou quando **outro
computador** emitiu pela mesma clínica.

Na tela de transmissão aparece o botão **Consertar a numeração**. Ele leva a
uma tela só, que faz tudo de uma vez: descarta o lote, avança a numeração e
libera para gerar de novo — já com o número sugerido pelo que a prefeitura
acabou de recusar.

> Na dúvida, use um número um pouco maior. **Buraco na sequência não é
> problema; número repetido é.**

### Duas máquinas, uma numeração

Se o sistema roda no seu PC e no da clínica, **só uma pode emitir**. Cada uma
conta os números por conta própria, e a prefeitura recusa repetido.

Para comparar: **Configuração → Comparar com outro computador**. O botão copia
um texto com o último número de cada clínica e ambiente — é só mandar no
WhatsApp e conferir com a outra máquina.

### Parar um envio no meio

Enquanto o envio corre, aparece **Parar depois da nota atual**. Ele nunca
corta uma nota pela metade — termina a que está em curso e para ali.

As notas já aceitas **valem normalmente**. As que faltam continuam na pasta,
prontas e assinadas: é só transmitir de novo depois, daqui ou pela tela
inicial.

> Enquanto um envio está rodando, o botão de transmitir daquela pasta fica
> travado. Dois envios ao mesmo tempo disputariam a fila da prefeitura, que
> aceita uma nota por vez por CNPJ.

### Sair da tela sem parar o envio

Pode voltar ao início — o envio continua. Na tela inicial, a linha do lote
mostra uma **barrinha de progresso** que se atualiza sozinha, com quantas
faltam. Tem também **Atualizar agora**, se preferir.

### Só atualizar a base de clientes

Quando entrar paciente novo e você **não** quiser conferir caixa nenhum:
mande **apenas** o relatório *Clientes e Fornecedores*, sozinho, na tela
inicial. O sistema atualiza a base e diz o que entrou.

> **Ninguém é duplicado.** Quem já está na base é reconhecido — pelo CPF ou,
> quando falta CPF, pelo nome e data de nascimento — e só recebe o que
> mudou. Mandar o mesmo relatório duas vezes não cria uma pessoa a mais.

### Listas grandes

Quando a busca acha muita gente, aparece uma **barra de páginas** no fim da
lista: `‹ 1 2 3 … 17 ›`. Vale para a base de clientes, para as notas de um
paciente e para a lista de notas transmitidas.

### Corrigir o cadastro de um paciente

Na aba **Clientes**, comece a digitar o nome ou o CPF — as pessoas vão
aparecendo embaixo do campo; clique na certa. Depois use o botão
**corrigir** na linha dela.

Dá para arrumar nome, CPF, endereço, CEP, telefone e e-mail.

> **A correção não é desfeita** quando o relatório do TechCare vier de novo.
> Se um dia arrumarem lá com outro valor, o do TechCare volta a valer — que
> é o certo, porque significa que a origem foi corrigida.

O CPF é conferido na hora: se for inválido, a correção é recusada, porque a
prefeitura recusaria a nota.

### Escolher quais notas transmitir

Só é preciso quando um envio parou no meio. Na tela de transmitir, duas
opções:

- **Mandar as que faltam de uma vez** (já vem marcada)
- **Escolher quais** — abre a lista com o nome de cada paciente; marque as
  que quiser (o filtro ajuda a achar) e mande só aquelas

> As já aceitas aparecem marcadas e não podem ser reenviadas.

Depois de transmitir, aparece **o que fazer com as notas**: uma linha por
nota aceita, com o nome do paciente, o número, e os botões para abrir o PDF
(imprimir ou salvar) e chamar no WhatsApp.

### Quando um lançamento fica travado

A aba **Travados** mostra uma ficha **por pessoa** — se alguém travou em três
lançamentos do mês, é uma ficha só, e apontar o cadastro resolve os três.

Se o cadastro certo não estiver na lista de sugestões, use o campo de busca:
funciona por **nome** (em qualquer ordem: "santana priscila" acha "PRISCILA
SANTANA FERREIRA") ou por **CPF, com ou sem pontos**.

Quando o único cadastro encontrado tem **CPF inválido**, não há botão para
escolher — a prefeitura recusaria a nota. Corrija no TechCare e traga os
relatórios de novo.

### Mandar a nota para o contador

Na tela da nota há dois botões:

| Para quem | O que mandar |
|---|---|
| Paciente | **Baixar NFS-e (PDF oficial)** — o DANFSe, mesmo documento e mesmo leiaute da prefeitura |
| Contador | **Baixar XML** — a nota assinada, que é o que ele arquiva |

O PDF é montado com os dados que a **Receita Federal** guarda, buscados na
hora. Sai igual ao que sairia se você emitisse pelo portal.

### Notas de um paciente (imposto de renda)

Menu **Por paciente**. Busque por nome ou CPF e escolha o ano.

Aparecem todas as notas daquela pessoa, com o total. Marque as que quiser —
ou deixe todas — e clique em **Baixar PDF**. Sai um PDF com **uma página por nota, no leiaute da prefeitura**, já
nomeado: `DANFSe-Maria-Silva-12-notas-2026.pdf`. É só anexar no WhatsApp ou
no e-mail.

Com muitas notas leva alguns segundos — o sistema busca cada uma na Receita.
Se a internet estiver fora, sai um comprovante simplificado com a chave de
acesso, que permite baixar a nota no portal depois.

Se aparecer **“não tem nota emitida”**, a tela diz o motivo: pode ser o ano
errado, ou notas que só existem em teste.

> É o pedido que aparece no fim do ano. Antes, achar as notas de uma pessoa
> significava procurar uma a uma pela chave.

### Imprimir ou salvar uma nota

Na lista, cada nota tem o botão **imprimir**. Ele monta o documento aqui
mesmo — **não precisa ir ao portal nem digitar a chave**.

Na tela que abrir, use **Imprimir / salvar em PDF**:

- para **papel**, escolha a impressora;
- para **mandar ao paciente**, escolha **"Salvar como PDF"** e depois anexe
  o arquivo na conversa do WhatsApp.

### Avisar o paciente

Na lista, cada nota emitida **valendo** tem o botão **Avisar no WhatsApp**.
Ele abre a conversa com o paciente e a mensagem já escrita, com o número da
nota, o valor e a chave de acesso. **Você lê, confere e envia** — nada sai
sozinho.

A mensagem já basta: com a chave, o paciente baixa o documento oficial no
portal. Se ainda assim quiser mandar o PDF, use **copiar chave**, cole em
`nfse.gov.br/consultapublica`, baixe e anexe na conversa — o WhatsApp não
aceita anexo por link.

> Aparece "sem telefone" quando o cadastro do paciente não tem número
> válido. Corrija no TechCare e reimporte o relatório de clientes.

---

## Coisas que não podem acontecer

### Não apague a pasta `dados`

É ela que guarda a numeração das notas e a lista de quem já recebeu.
Perder essa pasta faz a numeração recomeçar do zero — e a prefeitura rejeita
número repetido.

**Faça backup uma vez por mês.** Botão **Backup** na tela de Configuração:
baixa um arquivo com o que não pode ser perdido. Guarde no Drive ou num pen
drive.

### Não mexa na pasta `config/certificados`

É a assinatura digital da clínica. Se sumir, o programa para de assinar
notas.

---

## Quando alguma coisa der errado

**Primeiro:** leia a mensagem na tela. Elas são escritas em português e
explicam o que fazer.

**Se não resolver**, avise o responsável e diga:

1. em que tela estava;
2. o que clicou;
3. a mensagem que apareceu (uma foto da tela resolve).

O responsável consegue corrigir o programa daqui e mandar a correção. Quando
ele avisar que corrigiu, faça o seguinte:

> **Configuração → Procurar atualizações → Instalar**
>
> Depois feche a janela preta e abra o programa de novo.

A atualização troca só o programa. A numeração, os pacientes, os
certificados e as notas já emitidas ficam onde estão.

---

## Resumo de bolso

```
1. TechCare  →  PDF de caixa (e de clientes, se houver paciente novo)
2. Arrastar para o programa  →  Conferir
3. Olhar o que travou  →  resolver ou deixar de fora
4. Conferir a clínica  →  digitar EMITIR  →  Emitir as notas
5. O envio sai sozinho  →  ver se a prefeitura aceitou
6. Notas emitidas  →  imprimir ou avisar o paciente, se precisar
```

**Uma vez por mês:** Configuração → Backup.

---

## Duas coisas pequenas

**Modo noturno.** O botão ◐ no canto superior direito alterna entre claro e
escuro. A escolha fica salva nesse computador.

**Voltar.** Toda tela tem, no alto, o link **← Voltar** — não precisa usar
o botão do navegador.
