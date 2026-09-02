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

/* --- resolucao de pendencia: escolher o cadastro certo --------------- */
function prepararBusca(loteId, lancamento) {
  const campo = document.getElementById("busca-" + lancamento);
  const caixa = document.getElementById("resultados-" + lancamento);
  if (!campo) return;
  let timer = null;
  campo.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const termo = campo.value.trim();
      if (termo.length < 3) { caixa.innerHTML = ""; return; }
      const r = await fetch("/lote/" + loteId + "/buscar?q=" + encodeURIComponent(termo));
      const d = await r.json();
      caixa.innerHTML = "";
      if (!d.resultados.length) {
        caixa.innerHTML = '<div style="color:var(--tinta-fraca)">Ninguém encontrado com esse nome ou CPF.</div>';
        return;
      }
      d.resultados.forEach((c) => {
        const item = document.createElement("div");
        item.innerHTML =
          "<b>" + c.nome + "</b> — " + c.documento_formatado +
          (c.valido ? "" : ' <span class="selo ruim">CPF inválido</span>') +
          '<br><span style="color:var(--tinta-fantasma)">' + c.endereco + "</span>";
        item.onclick = () => escolherCadastro(loteId, lancamento, c.documento, c.valido);
        caixa.appendChild(item);
      });
    }, 250);
  });
}

async function escolherCadastro(loteId, lancamento, documento, valido) {
  if (valido === false) {
    alert("Esse cadastro tem CPF inválido. Corrija no TechCare antes de usá-lo.");
    return;
  }
  const r = await fetch("/lote/" + loteId + "/escolher", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lancamento: lancamento, documento: documento }),
  });
  const d = await r.json();
  if (!r.ok) { alert(d.erro); return; }
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
