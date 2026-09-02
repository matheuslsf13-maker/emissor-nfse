# Guia do responsável

O que está publicado, como instalar na clínica e como consertar de longe.

> Este arquivo é para **quem cuida do sistema**. O manual de quem emite as
> notas no dia a dia é o `COMO-USAR.md` — esse pode ficar na clínica.

---

## 1. O que está no GitHub

O projeto fica em
[github.com/matheuslsf13-maker/emissor-nfse](https://github.com/matheuslsf13-maker/emissor-nfse),
público. Qualquer pessoa com o link consegue ver.

Lá tem duas coisas diferentes:

| | O quê |
|---|---|
| **O código** | As instruções que fazem o programa funcionar. É o que outro programador olha. |
| **O aplicativo pronto** | Em **Releases**, `EmissorNFSe-app.zip` (42 MB). Baixa, descompacta, dois cliques. |

Quem baixar o aplicativo abre o sistema completo, mas com **clínicas
fictícias**. Para emitir de verdade precisaria dos dados da própria empresa,
certificado A1 e credenciamento — e o WebService aqui é o de Vila Velha/ES.

### O que NÃO está publicado, de propósito

Certificados, senhas, o `config/empresas.json` com dados reais, a base de
15 mil pacientes e os relatórios do TechCare. Nada disso sobe — e não é
sorte, é `.gitignore`.

---

## 2. Instalar na clínica

O programa é feito em Python — pense nele como o motor que faz os arquivos
rodarem. A máquina da clínica precisa desse motor.

**1. Instalar o Python lá.** Baixe em <https://python.org/downloads>.

> Na primeira tela, **marque "Add python.exe to PATH"**, embaixo, antes de
> clicar em Install. É a caixinha mais fácil de passar batido e a causa nº 1
> de "instalei e não funciona".
>
> Se o aviso continuar aparecendo depois de instalar: feche a janela do
> terminal e abra de novo. O Windows só enxerga o Python em janelas abertas
> *depois* da instalação.

**2. Levar o programa.** Copie a pasta `emissor-nfse` (menos de 2 MB).

> **Não leve as pastas `dados`, `distribuicao` e `publicacao`.** A primeira é
> a numeração das *suas* notas — se for junto, a clínica começa com o número
> errado e a prefeitura rejeita.

**3. Rodar `instalar.bat`, uma vez.** Confere o Python, baixa os componentes
e prepara o arquivo de senhas sozinho.

**4. Pôr os certificados à mão** em `config\certificados\`.

> Eles nunca viajam junto com o programa: certificado e senha no mesmo
> pacote, passando por pen drive e e-mail, é assinatura digital vazada.

**5. Preencher `config\senhas.bat`** — o instalador já criou o arquivo.

**6. Abrir com `Iniciar.bat`** e conferir em **Configuração** se não sobrou
nenhum aviso vermelho.

> Faça um atalho: botão direito no `Iniciar.bat` → Enviar para → Área de
> trabalho.

### Plano B, se o Python der trabalho

```bash
python empacotar.py
```

Monta uma pasta de ~94 MB com o **Python já embutido**, que roda sem instalar
nada. Vale se a máquina for de rede corporativa ou tiver antivírus
bloqueando instalações.

---

## 3. Consertar de longe

O computador da clínica **não recebe nada** — ele vai buscar, num endereço
fixo na internet que funciona como um mural.

### Você, aqui

```bash
publicar.bat 2.1.0 "o que mudou"
```

Um comando só: entra na pasta certa, roda a bateria de testes, monta o
pacote e põe no ar. **Se algum teste falhar, não publica nada.**

O número da versão é você quem escolhe — só precisa ser **maior** que o
anterior, e nunca reaproveitado. Refazer uma versão com o mesmo número faz o
GitHub servir o pacote antigo por alguns minutos.

### Ela, na clínica

**Configuração → Procurar atualizações → Instalar**, e depois **fechar e
abrir o programa**.

> O reinício é obrigatório: as telas recarregam sozinhas, o código não. Entre
> instalar e reiniciar o sistema fica meio novo, meio velho. Enquanto isso,
> uma faixa fica avisando em todas as telas.

A atualização troca **só o programa**. Numeração, pacientes, certificados e
notas emitidas ficam onde estão — testado contra um pacote que tenta apagar
essas coisas de propósito. A versão anterior é guardada, e há botão para
voltar.

### Corrigir a configuração remotamente

Às vezes o erro está num dado, não no código. Crie um arquivo com só o que
muda:

```json
{"unidades": {"cobilandia": {"endereco": {"bairro": "COBILANDIA"}}}}
```

```bash
python publicar.py 2.1.0 --github matheuslsf13-maker/emissor-nfse --config remendo.json
```

Só as chaves citadas mudam lá; o resto da configuração da clínica fica
intacto.

---

## 4. Teste e produção

Não há configuração de ambiente para ligar. A escolha é feita **em cada
lote**, na hora de gerar:

| Botão | O que faz |
|---|---|
| **Só conferir** | Sem gastar numeração e sem falar com a prefeitura |
| **Gerar para teste** | Homologação — a prefeitura responde, nada vale fiscalmente |
| **Emitir valendo** | Nota fiscal real, pede `EMITIR` digitado |

**Testar não gasta nota real.** As numerações são independentes, como na
prefeitura. A tela mostra onde cada lote está:

```
Teste:   todas as 276 já foram geradas ✓
Valendo: nenhuma ainda — as 276 continuam disponíveis
```

Dá para **escolher quais notas** emitir: na lista, marque só as que quiser.
Serve para soltar uma nota específica valendo antes de comprometer o resto.

**A transmissão não pergunta o ambiente** — ele já está assinado dentro de
cada nota.

### Avisar o paciente no WhatsApp

Cada nota de **produção** ganha um botão que abre a conversa com o texto
pronto. Três decisões:

- **Nada é enviado sozinho.** O link só abre o WhatsApp; quem aperta enviar
  é a pessoa. Disparo automático para paciente é outra categoria de decisão.
- **Só notas de produção.** Nota de teste não existe para o paciente.
- **A mensagem leva a chave, não um PDF.** O `wa.me` não aceita anexo. Para
  mandar o arquivo, use **imprimir → salvar como PDF** e anexe na conversa.

### O ambiente nacional, e por que o PDF oficial ainda não sai

Testei os dois caminhos possíveis para obter o DANFSe oficial por sistema:

**O WebService municipal não tem.** Reli o WSDL ao vivo: `NotaFiscalNacional`
expõe Gerar, Consultar, Cancelar e Substituir. A palavra "danfse" não aparece
nele, nem "pdf".

**O ambiente nacional (ADN) tem o XML, não o PDF.** `GET /nfse/{chave}` em
`sefin.nfse.gov.br` devolve a NFS-e assinada e completa — testado com o
certificado da Glória contra a nota 8966, HTTP 200. Já `GET /danfse/{chave}`
responde **501, Not Implemented**: o endereço existe, o serviço não. Não é
falta de credenciamento nosso.

**Mas isso não impede nada — porque o DANFSe não é um arquivo que alguém
guarda.** É uma *representação gráfica padronizada* da NFS-e. Quem emite pelo
portal recebe um PDF gerado ali na hora, a partir do mesmo XML. É assim que
todo sistema emissor imprime nota: seguindo o leiaute publicado. Não havia
download a fazer; havia um leiaute a seguir.

Então `nfse/danfse_oficial.py` monta o DANFSe aqui. O leiaute foi **medido no
documento real** que a prefeitura emitiu para a nota 8966: página A4, moldura
em 5pt, colunas em x=10, 155, 310 e 445, rótulos em Helvetica-Bold 7 (6
quando longos), valores em Helvetica 7, onze linhas separando os blocos.

Comparando palavra por palavra, com posição: **96,5% batem** (518 palavras,
18 divergem). As 18 são todas explicáveis:

| Divergência | Por quê |
|---|---|
| "DANFESe" → "DANFSe" | Erro de digitação do emissor deles |
| "consulta pela chave" → "consultada" | Falta o "-da" no deles |
| CPF e CEP do tomador formatados | Eles formatam os do prestador e não os do tomador |
| "NNoommee EEmmpprreessaarriiaall" | Bug de renderização deles: o texto sai duplicado |
| "Exclusões da BC" vazio | Eles repetem ali o valor do ISS, que não é exclusão de base de nada |

`baixar_danfse()` continua tentando o PDF da Receita a cada download, e cai
para o nosso quando vem 501. No dia em que ligarem o serviço, a clínica passa
a receber o deles sem precisar de versão nova.

**Em lote isso é barato.** Abrir a sessão TLS custa mais que a consulta em si
(0,3s contra 0,1s por nota), então `baixar_varios()` reusa uma só: cem notas
levam cerca de dez segundos. Por isso o PDF do paciente sai no leiaute
oficial por padrão, e não como reconstrução local.

Uma regra no `/paciente/pdf`: o leiaute oficial só vale se **todas** as notas
vierem. Um PDF com metade das páginas em um formato e metade em outro
confundiria quem recebe — melhor cair inteiro para o comprovante local.

**A credencial ali é o mesmo certificado, em outro lugar.** Em Vila Velha ele
assina o XML e vai dentro dele; no ADN ele vai no aperto de mão TLS (mTLS).
Como o `ssl` do Python não carrega chave de memória, ela vira arquivo — mas
**cifrada**, com uma senha aleatória que só existe naquela execução, e o
arquivo é apagado ao fechar. Chave privada em claro no disco, ainda que por
segundos, não se justifica por conveniência.

O XML oficial traz o que o nosso não tinha, porque quem preenche é a Receita:
número da nota, município por extenso, descrição da tributação, totais de
tributo federal/estadual/municipal e a situação atual do documento.

### Notas de um paciente, em PDF

**Notas do paciente** busca por nome ou CPF, filtra por ano e gera um PDF
com uma página por nota — o pedido de imposto de renda.

Dois detalhes de desenho:

- **Os dados saem do XML que nós assinamos**, guardado em `dados/saida/`,
  não de consulta à prefeitura. Ela processa um pedido por vez por CNPJ:
  cem consultas levariam muitos minutos. Número e chave, que só ela atribui,
  vêm do controle.
- **É um comprovante, não o DANFSe oficial.** O documento da prefeitura tem
  21 seções padronizadas por Nota Técnica, incluindo as vazias no nosso caso
  (intermediário, retenções federais, IBS/CBS). Chamá-lo de DANFSe seria
  enganoso — alguém poderia apresentá-lo achando que é o oficial. Quem
  precisar dele usa a chave no portal, e o próprio comprovante diz isso.

### Imprimir a nota sem ir ao portal

A NFS-e que vale é o **XML**; o papel é apenas o *documento auxiliar* — uma
representação. Como a consulta já devolve o XML completo (prestador,
tomador, serviço, valores), o sistema monta o documento sozinho, e o
navegador imprime ou salva em PDF.

Isso evita o caminho antigo: ir ao portal, digitar 50 dígitos, baixar. O
portal nacional não aceita a chave pela URL (testado) e a prefeitura não
serve o DANFSe por endereço direto (404) — então gerar aqui era a única
saída que não passava por digitação manual.

O telefone vem da base de clientes, cruzado pelo CPF da nota. Sem número
válido, o botão não aparece.

### Planilha para o contador

Na conferência, **Baixar planilha (.xlsx)**: quatro abas (resumo, notas,
travados, não geram nota). Os totais são **fórmulas**, não números fixos —
se o contador filtrar uma linha, a soma acompanha. Um valor calculado e
gravado mentiria em silêncio justamente na conferência.

> **A prefeitura aceita uma nota por vez por CNPJ.** Medido contra um
> servidor que simula a fila: com resposta rápida, 276 notas levam ~2 min;
> com resposta lenta, ~21 min. Em todos os cenários **100% foram aceitas** —
> o sistema insiste sozinho no que é recusa por ritmo, e não insiste no que
> é erro de conteúdo. A tela mostra progresso e tempo restante; pode fechar
> que o envio continua.

---

## 5. Se algo der errado

| Sintoma | O que é |
|---|---|
| `E0014 — número já existe` | A numeração está atrás da prefeitura. Use "Descartar este lote" e ajuste a numeração em Configuração. |
| Tudo recusado por *"requisição em andamento"* | Fila da prefeitura. O sistema já insiste sozinho; se persistir, tente mais tarde. |
| "Arquivo de controle ilegível" | O `controle.db` corrompeu. Restaure o backup — a tela explica o passo a passo. |
| A operadora não sabe explicar | Peça **uma foto da tela**. As mensagens dizem o que fazer. |

---

## Resumo

```
MOSTRAR PARA ALGUÉM
  github.com/matheuslsf13-maker/emissor-nfse
  (para rodar: Releases → EmissorNFSe-app.zip)

INSTALAR NA CLÍNICA
  lá: instalar o Python ("Add python.exe to PATH")
  copiar a pasta + rodar instalar.bat
  pôr os .pfx e preencher config\senhas.bat

CORRIGIR DE LONGE
  publicar.bat 2.1.0 "o que mudou"
  lá: Configuração → Procurar atualizações → Instalar
      e fechar/abrir o programa

EMITIR O MÊS (na clínica)
  gerar para TESTE → transmitir → conferir
  gerar VALENDO    → transmitir uma → conferir → o resto
```

**Uma vez por mês, na clínica:** Configuração → Backup.
