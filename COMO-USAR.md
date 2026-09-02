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
uma vez, em qualquer ordem — o programa reconhece qual é qual sozinho.

Clique em **Conferir**.

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

### 4. Gerar as notas

Três opções, e o ambiente é escolhido **aqui** — não há configuração para
mexer:

| Botão | O que faz |
|---|---|
| **Só conferir** | Monta as notas sem gastar numeração e sem falar com a prefeitura. Pode repetir à vontade. |
| **Gerar para teste** | Cria as notas em **homologação**. Dá para transmitir e a prefeitura responde de verdade, mas nada vale fiscalmente. |
| **Emitir valendo** | Cria **nota fiscal de verdade**. Pede para digitar `EMITIR`. |

> **Gerar não envia.** As notas ficam no seu computador. Nada foi para a
> prefeitura ainda — isso é o passo 5.

Acima dos botões, o programa mostra **onde aquele lote está**:

```
Teste:   todas as 276 já foram geradas ✓
Valendo: nenhuma ainda — as 276 continuam disponíveis para emitir
```

Assim dá para saber o que já foi testado e o que ainda falta emitir de
verdade, sem precisar lembrar.

> **Testar não gasta nota real.** As numerações de teste e de produção são
> separadas, como na prefeitura. Testar o mês inteiro e depois emitir valendo
> é o caminho normal, não retrabalho.

> **Para o contador:** o botão **Baixar planilha (.xlsx)** gera um arquivo
> com quatro abas — resumo, as notas que vão sair, as travadas e o que não
> gera nota. Os totais são fórmulas, então filtrar recalcula sozinho.

### 5. Transmitir

Aqui as notas vão para a prefeitura.

**Você não escolhe o ambiente de novo** — ele já está assinado dentro de cada
nota, e o programa manda para onde ela foi feita. A tela avisa se é teste ou
se vale de verdade. Para transmitir valendo, é preciso digitar `PRODUCAO`.

**Na primeira vez, mande uma nota só.** Confira o retorno. Se estiver certo,
mande o resto.

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

## Conferir uma nota

Menu **Consultar nota**. Cole a chave de acesso e clique em Consultar.

O programa pergunta direto ao sistema da prefeitura e mostra o que está
registrado lá. Serve quando o paciente liga perguntando, e serve para
conferir a primeira nota de produção.

A tela também lista as últimas notas transmitidas — é só clicar na chave.

### Mandar a nota para o contador

Na tela da nota há dois botões:

| Para quem | O que mandar |
|---|---|
| Paciente | **Baixar NFS-e (PDF oficial)** — o DANFSe, mesmo documento e mesmo leiaute da prefeitura |
| Contador | **Baixar XML** — a nota assinada, que é o que ele arquiva |

O PDF é montado com os dados que a **Receita Federal** guarda, buscados na
hora. Sai igual ao que sairia se você emitisse pelo portal.

### Notas de um paciente (imposto de renda)

Menu **Notas do paciente**. Busque por nome ou CPF e escolha o ano.

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
4. Gerar para TESTE  →  transmitir  →  ver se a prefeitura aceitou
5. Gerar VALENDO    →  transmitir UMA  →  conferir  →  o resto
```

O passo 4 é opcional depois que você pegar confiança — mas testar não gasta
nota real, então nunca custa.

**Uma vez por mês:** Configuração → Backup.

---

## Duas coisas pequenas

**Modo noturno.** O botão ◐ no canto superior direito alterna entre claro e
escuro. A escolha fica salva nesse computador.

**Voltar.** Toda tela tem, no rodapé, um link para o início — não precisa
usar o botão do navegador.
