https://claude.ai/code/artifact/14562e56-16ff-4dea-a306-d63c1225fb50
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

### 4. Gerar

Duas opções:

- **Simular** — faz tudo, mas nada vale. Use para ver o resultado sem
  compromisso. Pode simular quantas vezes quiser.
- **Gerar valendo** — cria as notas de verdade, cada uma com seu número.

> **Gerar não envia.** As notas ficam no seu computador. Nada foi para a
> prefeitura ainda.

### 5. Transmitir

Aqui as notas vão para a prefeitura e viram nota fiscal de verdade.

**Na primeira vez do mês, mande uma nota só.** Confira o retorno. Se estiver
certo, mande o resto. Leva dez segundos a mais e evita mandar duzentas notas
erradas.

Quando a prefeitura aceita, ela devolve o **número da nota** e a **chave de
acesso**. Os dois ficam guardados.

---

## Homologação e produção

| | O que é |
|---|---|
| **Homologação** | Ambiente de testes da prefeitura. Nada vale fiscalmente. |
| **Produção** | Vale de verdade. |

O ambiente é escolhido **na hora de gerar**, não na hora de transmitir — ele
fica gravado dentro da nota. Por isso a tela avisa para qual ambiente cada
pasta foi feita, e o botão do outro ambiente fica desligado.

Para transmitir em produção é preciso digitar a palavra `PRODUCAO`. Não é
implicância: **em Vila Velha, cancelar nota exige processo administrativo na
Secretaria de Finanças.** Não é um clique.

---

## Conferir uma nota

Menu **Consultar nota**. Cole a chave de acesso e clique em Consultar.

O programa pergunta direto ao sistema da prefeitura e mostra o que está
registrado lá. Serve quando o paciente liga perguntando, e serve para
conferir a primeira nota de produção.

A tela também lista as últimas notas transmitidas — é só clicar na chave.

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
4. Gerar valendo
5. Transmitir UMA  →  conferir  →  transmitir o resto
```

**Uma vez por mês:** Configuração → Backup.
