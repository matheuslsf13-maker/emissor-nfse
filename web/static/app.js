/* --------------------------------------------------------------------------
   Tema claro/escuro.

   Sem escolha salva, segue o sistema. O botao alterna e grava em
   localStorage -- por maquina, que e o certo aqui: o programa e local e quem
   usa a clinica de manha nao e quem mexe nele de noite.
   -------------------------------------------------------------------------- */

function temaAtual() {
  var salvo = null;
  try { salvo = localStorage.getItem("tema"); } catch (e) { /* sem storage */ }
  if (salvo) { return salvo; }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "escuro" : "claro";
}

function alternarTema() {
  var novo = temaAtual() === "escuro" ? "claro" : "escuro";
  document.documentElement.setAttribute("data-tema", novo);
  try { localStorage.setItem("tema", novo); } catch (e) { /* sem storage */ }
  desenharBotaoTema();
}

function desenharBotaoTema() {
  var botao = document.getElementById("botao-tema");
  if (!botao) { return; }
  var escuro = temaAtual() === "escuro";
  botao.textContent = escuro ? "☀" : "☾";
  botao.title = escuro ? "Mudar para claro" : "Mudar para escuro";
}

document.addEventListener("DOMContentLoaded", desenharBotaoTema);


/* Interacoes da tela. Sem framework: o app roda offline na maquina da clinica. */

function tamanhoLegivel(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " KB";
  return (bytes / 1048576).toFixed(1) + " MB";
}

function iniciarEnvio() {
  const solta = document.getElementById("solta");
  const campo = document.getElementById("arquivos");
  const lista = document.getElementById("lista");
  const botao = document.getElementById("enviar");
  const dica = document.getElementById("dica");
  const mensagem = document.getElementById("mensagem");
  const explicacao = document.getElementById("explicacao");
  if (!solta) return;

  let arquivos = [];

  function desenhar() {
    lista.innerHTML = "";
    arquivos.forEach((a, i) => {
      const div = document.createElement("div");
      div.className = "arquivo";
      div.innerHTML =
        '<span>📄</span><span class="nome"></span>' +
        '<span class="peso"></span>' +
        '<button type="button" class="botao pequeno secundario">remover</button>';
      div.querySelector(".nome").textContent = a.name;
      div.querySelector(".peso").textContent = tamanhoLegivel(a.size);
      div.querySelector("button").onclick = () => {
        arquivos.splice(i, 1);
        desenhar();
      };
      lista.appendChild(div);
    });
    const pronto = arquivos.length >= 1;
    botao.disabled = !pronto;
    explicacao.style.display = arquivos.length ? "flex" : "none";
    if (arquivos.length) {
      dica.textContent = arquivos.length + " arquivo(s) selecionado(s).";
    }
  }

  function receber(novos) {
    for (const a of novos) {
      if (!a.name.toLowerCase().endsWith(".pdf")) continue;
      if (!arquivos.some((x) => x.name === a.name && x.size === a.size)) {
        arquivos.push(a);
      }
    }
    desenhar();
  }

  campo.addEventListener("change", (e) => receber(e.target.files));
  ["dragenter", "dragover"].forEach((ev) =>
    solta.addEventListener(ev, (e) => {
      e.preventDefault();
      solta.classList.add("sobre");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    solta.addEventListener(ev, (e) => {
      e.preventDefault();
      solta.classList.remove("sobre");
    })
  );
  solta.addEventListener("drop", (e) => receber(e.dataTransfer.files));

  document.getElementById("formulario").addEventListener("submit", async (e) => {
    e.preventDefault();
    botao.disabled = true;
    botao.textContent = "Enviando os arquivos...";
    mensagem.innerHTML = "";

    const dados = new FormData();
    arquivos.forEach((a) => dados.append("arquivos", a));

    try {
      const resposta = await fetch("/lote", { method: "POST", body: dados });
      const corpo = await resposta.json();
      if (!resposta.ok) {
        mensagem.innerHTML =
          '<div class="faixa erro"><span class="icone">■</span><div>' +
          "<b>Não deu para começar</b><p>" + corpo.erro + "</p></div></div>";
        botao.disabled = false;
        botao.textContent = "Conferir os lançamentos";
        return;
      }
      window.location = "/lote/" + corpo.id;
    } catch (erro) {
      mensagem.innerHTML =
        '<div class="faixa erro"><span class="icone">■</span><div><b>Falha ao enviar</b><p>' +
        erro + "</p></div></div>";
      botao.disabled = false;
      botao.textContent = "Conferir os lançamentos";
    }
  });

  desenhar();
}

function acompanhar(loteId) {
  const barra = document.getElementById("barra");
  const etapa = document.getElementById("etapa");
  async function bater() {
    try {
      const r = await fetch("/lote/" + loteId + "/progresso");
      const d = await r.json();
      if (d.progresso) {
        barra.style.width = (d.progresso.percentual || 0) + "%";
        if (d.progresso.etapa && d.progresso.etapa !== "pronto") {
          etapa.textContent = d.progresso.etapa;
        }
      }
      if (d.estado === "pronto" || d.estado === "erro") {
        window.location.reload();
        return;
      }
    } catch (e) { /* servidor ocupado lendo; tenta de novo */ }
    setTimeout(bater, 900);
  }
  bater();
}

function trocarAba(nome) {
  document.querySelectorAll(".abas button").forEach((b) =>
    b.classList.toggle("ativa", b.dataset.aba === nome)
  );
  document.querySelectorAll(".painel").forEach((p) =>
    p.classList.toggle("ativo", p.dataset.aba === nome)
  );
}

function filtrarTabela(idCampo, idTabela) {
  const campo = document.getElementById(idCampo);
  const tabela = document.getElementById(idTabela);
  if (!campo || !tabela) return;
  campo.addEventListener("input", () => {
    const termo = campo.value.trim().toLowerCase();
    let visiveis = 0;
    tabela.querySelectorAll("tbody tr").forEach((tr) => {
      const bate = !termo || tr.textContent.toLowerCase().includes(termo);
      tr.style.display = bate ? "" : "none";
      if (bate) visiveis++;
    });
    const contador = document.getElementById(idCampo + "-conta");
    if (contador) contador.textContent = visiveis + " linha(s)";
  });
}

/* --------------------------------------------------------------------------
   Sugestao de paciente enquanto se digita.

   Digitar o nome inteiro e apertar Procurar so para descobrir que a grafia
   do cadastro era outra e trabalho repetido -- e com quase doze mil pessoas
   na base, a grafia raramente e a que se imagina. Aqui as opcoes vao
   aparecendo, e escolher uma preenche o campo e envia o formulario.

   `opcoes.aoEscolher(cliente, campo)` permite decidir o que preencher: a
   tela de clientes quer o nome, a de notas quer o CPF (que e unico).
   -------------------------------------------------------------------------- */

function sugerirPaciente(idCampo, opcoes) {
  const campo = document.getElementById(idCampo);
  if (!campo) return;
  opcoes = opcoes || {};

  const caixa = document.createElement("div");
  caixa.className = "resultados-busca";
  caixa.style.marginTop = "6px";
  campo.insertAdjacentElement("afterend", caixa);

  function unidade() {
    if (opcoes.unidade) return opcoes.unidade;
    // A unidade sai do proprio formulario: trocar de clinica no seletor tem
    // que trocar as sugestoes junto.
    const sel = campo.form && campo.form.querySelector("[name='unidade']");
    return sel ? sel.value : "";
  }

  function fechar() { caixa.innerHTML = ""; }

  function escolher(cliente) {
    if (opcoes.aoEscolher) {
      opcoes.aoEscolher(cliente, campo);
    } else {
      campo.value = cliente.nome;
    }
    fechar();
    if (opcoes.enviar !== false && campo.form) campo.form.submit();
  }

  let timer = null;
  let pedido = 0;

  campo.addEventListener("input", () => {
    clearTimeout(timer);
    const termo = campo.value.trim();
    if (termo.length < 3) { fechar(); return; }
    timer = setTimeout(async () => {
      const meu = ++pedido;
      let d;
      try {
        const r = await fetch("/clientes/buscar?unidade=" +
                              encodeURIComponent(unidade()) +
                              "&q=" + encodeURIComponent(termo));
        if (!r.ok) throw new Error("HTTP " + r.status);
        d = await r.json();
      } catch (e) {
        // Sugestao e conveniencia: se falhar, o formulario normal continua
        // funcionando e nao vale assustar ninguem com um alerta.
        fechar();
        return;
      }
      if (meu !== pedido) return;

      const achados = (d && d.resultados) || [];
      if (!achados.length) { fechar(); return; }

      caixa.innerHTML = "";
      achados.forEach((c) => {
        const item = document.createElement("div");
        item.className = "achado sugestao";
        item.tabIndex = 0;

        const info = document.createElement("div");
        info.className = "info";
        const nome = document.createElement("b");
        nome.textContent = c.nome;
        info.appendChild(nome);
        const linha = document.createElement("div");
        linha.className = "endereco";
        linha.textContent = c.documento_formatado +
          (c.valido ? "" : " · CPF inválido") +
          (c.endereco ? " · " + c.endereco : "");
        info.appendChild(linha);
        item.appendChild(info);

        item.onclick = () => escolher(c);
        item.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); escolher(c); }
        };
        caixa.appendChild(item);
      });

      if (d.total > achados.length) {
        const mais = document.createElement("div");
        mais.className = "achado-aviso";
        mais.textContent = "e mais " + (d.total - achados.length) +
                           ". Escreva mais para reduzir a lista.";
        caixa.appendChild(mais);
      }
    }, 220);
  });

  campo.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { fechar(); return; }
    // Seta para baixo entra na lista: quem digita rapido nao quer soltar o
    // teclado para pegar o mouse.
    if (e.key === "ArrowDown") {
      const primeiro = caixa.querySelector(".sugestao");
      if (primeiro) { e.preventDefault(); primeiro.focus(); }
    }
  });
  caixa.addEventListener("keydown", (e) => {
    const itens = Array.from(caixa.querySelectorAll(".sugestao"));
    const atual = itens.indexOf(document.activeElement);
    if (e.key === "ArrowDown" && atual < itens.length - 1) {
      e.preventDefault(); itens[atual + 1].focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (atual > 0) itens[atual - 1].focus(); else campo.focus();
    } else if (e.key === "Escape") {
      fechar(); campo.focus();
    }
  });
}

/* --------------------------------------------------------------------------
   Resolucao de pendencia: apontar qual cadastro e o certo.

   Esta busca nao dava sinal de vida: digitava-se e, se nada aparecesse, nao
   havia como saber se era termo curto demais, se ninguem batia, ou se a
   busca tinha falhado. Agora cada estado diz o que e -- e o resultado tem
   botao "E este", igual aos candidatos sugeridos logo acima, em vez de uma
   linha que so quem descobre e que da para clicar.
   -------------------------------------------------------------------------- */

function prepararBusca(loteId, ficha, lancamentos) {
  const campo = document.getElementById("busca-" + ficha);
  const caixa = document.getElementById("resultados-" + ficha);
  const alvos = lancamentos || [ficha];
  if (!campo || !caixa) return;

  function aviso(texto) {
    caixa.innerHTML = "";
    const linha = document.createElement("div");
    linha.className = "achado-aviso";
    linha.textContent = texto;
    caixa.appendChild(linha);
  }

  let timer = null;
  let pedido = 0;

  campo.addEventListener("input", () => {
    clearTimeout(timer);
    const termo = campo.value.trim();
    if (!termo) { caixa.innerHTML = ""; return; }
    if (termo.replace(/[^0-9A-Za-zÀ-ÿ]/g, "").length < 3) {
      aviso("Digite pelo menos 3 letras do nome, ou o começo do CPF.");
      return;
    }
    aviso("Procurando…");

    timer = setTimeout(async () => {
      const meu = ++pedido;
      let d;
      try {
        const r = await fetch("/lote/" + loteId + "/buscar?q=" +
                              encodeURIComponent(termo));
        if (!r.ok) throw new Error("HTTP " + r.status);
        d = await r.json();
      } catch (e) {
        // Sem isto, falha de rede virava tela parada: o operador ficava
        // digitando achando que a busca nao existe.
        aviso("Não consegui buscar agora (" + e.message + "). " +
              "Tente de novo.");
        return;
      }
      // Uma resposta antiga nao pode sobrescrever a busca atual.
      if (meu !== pedido) return;

      const achados = (d && d.resultados) || [];
      if (!achados.length) {
        aviso("Ninguém com esse nome ou CPF no cadastro. " +
              "Tente só o primeiro nome, ou o CPF sem pontos.");
        return;
      }

      caixa.innerHTML = "";
      achados.forEach((c) => {
        const item = document.createElement("div");
        item.className = "achado";

        const info = document.createElement("div");
        info.className = "info";
        const nome = document.createElement("b");
        nome.textContent = c.nome;
        info.appendChild(nome);
        info.appendChild(document.createTextNode(" — " + c.documento_formatado));
        if (!c.valido) {
          const selo = document.createElement("span");
          selo.className = "selo ruim";
          selo.textContent = "CPF inválido";
          selo.style.marginLeft = "6px";
          info.appendChild(selo);
        }
        const end = document.createElement("div");
        end.className = "endereco";
        end.textContent = c.endereco + (c.nascimento ? " · nasc. " + c.nascimento : "");
        info.appendChild(end);
        item.appendChild(info);

        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "botao pequeno" + (c.valido ? "" : " secundario");
        botao.textContent = alvos.length > 1
          ? "É este (" + alvos.length + ")" : "É este";
        botao.onclick = () =>
          escolherCadastro(loteId, alvos, c.documento, c.valido);
        item.appendChild(botao);

        caixa.appendChild(item);
      });

      if (d.total > achados.length) {
        const mais = document.createElement("div");
        mais.className = "achado-aviso";
        mais.textContent = "Mostrando " + achados.length + " de " + d.total +
                           ". Escreva mais para reduzir a lista.";
        caixa.appendChild(mais);
      }
    }, 250);
  });

  // A lista NAO fecha ao clicar fora. Ela fica no fluxo da ficha, sem tapar
  // nada, e fechar sozinha so faria o operador perder o resultado que
  // acabou de achar por ter clicado no lugar errado. Esc limpa, e apagar o
  // campo tambem.
  campo.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { caixa.innerHTML = ""; campo.blur(); }
  });
}

async function escolherCadastro(loteId, lancamentos, documento, valido) {
  if (valido === false) {
    alert("Esse cadastro tem CPF inválido — a prefeitura recusaria a nota. " +
          "Corrija no TechCare e exporte os relatórios de novo.");
    return;
  }
  // Aceita um lancamento solto ou a lista inteira da pessoa.
  const alvos = Array.isArray(lancamentos) ? lancamentos : [lancamentos];
  let d;
  try {
    const r = await fetch("/lote/" + loteId + "/escolher", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lancamentos: alvos, documento: documento }),
    });
    d = await r.json();
    if (!r.ok) { alert(d.erro || "Não consegui aplicar a escolha."); return; }
  } catch (e) {
    alert("Não consegui aplicar a escolha agora: " + e.message);
    return;
  }
  window.location.reload();
}

/* --------------------------------------------------------------------------
   Escolher quais notas sair.

   O operador precisa poder emitir UMA nota especifica -- a de um paciente
   que ele quer conferir -- antes de soltar o mes inteiro. Sem isso, testar
   valendo significava emitir tudo.
   -------------------------------------------------------------------------- */

function escolhidas() {
  return Array.from(document.querySelectorAll(".escolha:checked"))
              .map(function (c) { return c.value; });
}

function contarEscolhas() {
  var n = escolhidas().length;
  var total = document.querySelectorAll(".escolha").length;
  var conta = document.getElementById("escolhas-conta");
  if (conta) {
    conta.textContent = n + " selecionada(s)";
    conta.style.display = n === total ? "none" : "";
  }
  // O botao diz quantas vao sair so quando NAO sao todas: "Emitir valendo"
  // e mais limpo do que "Emitir 276 valendo" no caso normal.
  var sufixo = (n === total || n === 0) ? "" : "(" + n + ")";
  document.querySelectorAll(".quantas").forEach(function (e) {
    e.textContent = sufixo;
  });
  var marcarTudo = document.getElementById("marcar-todas");
  if (marcarTudo) {
    marcarTudo.checked = n === total;
    marcarTudo.indeterminate = n > 0 && n < total;
  }
}

function marcarTodas(ligado) {
  document.querySelectorAll(".escolha").forEach(function (c) {
    // So mexe no que esta visivel: com um filtro aplicado, "marcar todas"
    // deve valer para o que esta na tela, nao para a lista inteira.
    var linha = c.closest("tr");
    if (!linha || linha.style.display !== "none") { c.checked = ligado; }
  });
  contarEscolhas();
}

function levarEscolhas(formulario) {
  var ids = escolhidas();
  var total = document.querySelectorAll(".escolha").length;
  if (ids.length === 0) {
    alert("Selecione pelo menos uma nota na lista \"Vão virar nota\".");
    return false;
  }
  formulario.querySelectorAll("input[name='apenas']").forEach(function (e) {
    e.remove();
  });
  // Mandar a lista so quando ela e parcial mantem o caso normal simples.
  if (ids.length < total) {
    ids.forEach(function (id) {
      var campo = document.createElement("input");
      campo.type = "hidden";
      campo.name = "apenas";
      campo.value = id;
      formulario.appendChild(campo);
    });
  }
  return true;
}

document.addEventListener("DOMContentLoaded", contarEscolhas);


/* Copiar a chave de acesso.

   Sao 50 digitos: digitar a mao erra, e conferir o que foi digitado erra
   mais ainda. A copia tem tres caminhos, do melhor para o que sempre
   funciona -- porque um botao que "nao deu" e pior do que nao existir:

     1. Clipboard API, o caminho normal;
     2. execCommand, para navegador antigo ou pagina sem foco;
     3. selecionar a chave na tela, para a pessoa dar Ctrl+C.

   O passo 3 nao depende de permissao nenhuma. */

function copiarChave(botao, chave) {
  var texto = botao.textContent;

  function avisar(mensagem) {
    botao.textContent = mensagem;
    setTimeout(function () { botao.textContent = texto; }, 1800);
  }

  function selecionarNaTela() {
    var celula = botao.closest("tr")
      ? botao.closest("tr").querySelector(".mono")
      : null;
    if (!celula) { avisar("copie da tela"); return; }
    var faixa = document.createRange();
    faixa.selectNodeContents(celula);
    var selecao = window.getSelection();
    selecao.removeAllRanges();
    selecao.addRange(faixa);
    avisar("selecionada — Ctrl+C");
  }

  function porExecCommand() {
    var campo = document.createElement("textarea");
    campo.value = chave;
    campo.style.position = "fixed";
    campo.style.top = "-1000px";
    document.body.appendChild(campo);
    campo.select();
    var deu = false;
    try { deu = document.execCommand("copy"); } catch (e) { deu = false; }
    document.body.removeChild(campo);
    if (deu) { avisar("copiada!"); } else { selecionarNaTela(); }
  }

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(chave)
      .then(function () { avisar("copiada!"); })
      .catch(porExecCommand);
    return;
  }
  porExecCommand();
}


function confirmarEmissao(evento) {
  const campo = document.getElementById("confirmacao");
  if (campo.value.trim().toUpperCase() !== "EMITIR") {
    evento.preventDefault();
    alert('Para emitir valendo, digite EMITIR no campo de confirmação.');
    return false;
  }
  return confirm(
    "Isto consome a numeração das notas de forma permanente e não tem desfazer.\n\n" +
    "Confirma?"
  );
}
