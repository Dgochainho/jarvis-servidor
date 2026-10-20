"""
Página `/matriz` — a matriz de 128×32 simulada no browser (Fase 8.d, L8).

É um cliente do `visual_service` igual ao que o Matrix Portal vai ser: liga ao
mesmo `ws://…:8766/visual`, recebe as mesmas mensagens, desenha com a mesma
fonte (`fontes/fonte_5x8.json`) e decide a linha activa com o relógio local,
a 30 fps. Quando o hardware chegar, troca-se esta página pelo nó e o servidor
não muda.

As regras de desenho são as que o nó vai ter, e por isso estão escritas aqui
uma vez e devem ser copiadas para lá tal e qual:

  - três filas de 8 píxeis, em y = 1, 12 e 23; cada fila centrada;
  - a entrada activa é a última com t ≤ posição;
  - se a activa ocupa ≤ 2 filas, a primeira fila da seguinte aparece na
    fila 3, apagada (30%) — o "verso seguinte em tom apagado" do PDF;
  - a cor é a `a1` da paleta (o realce), levada a um brilho mínimo, porque
    num LED uma cor escura é um LED apagado;
  - sem servidor: mantém a última cor, pára a letra, baixa para 20% e tenta
    religar com espera crescente (PDF: "uma luz fraca parece repouso").

O que esta página tem e o nó não: o ajuste de offset, para afinar de ouvido
(L4), e os números do relógio por baixo da matriz.
"""

PAGINA_MATRIZ = r"""<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Matriz virtual</title>
<style>
:root { --pagina: #f4f4f2; --cartao: #ffffff; --tinta: #1d1d1b; --suave: #6b6b66; --linha: #dcdcd6; }
@media (prefers-color-scheme: dark) {
  :root { --pagina: #161615; --cartao: #20201e; --tinta: #ececea; --suave: #a3a39c; --linha: #3a3a36; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 20px 16px 40px; background: var(--pagina); color: var(--tinta);
       font: 14px/1.45 system-ui, sans-serif; }
h1 { font-size: 20px; margin: 0 0 4px; }
p.sub { margin: 0 0 16px; color: var(--suave); max-width: 70ch; }
.painel { background: #050505; border-radius: 10px; padding: 14px; overflow-x: auto; }
canvas { display: block; margin: 0 auto; image-rendering: pixelated; }
.dados { display: flex; flex-wrap: wrap; gap: 6px 20px; margin: 12px 0; font: 13px ui-monospace, monospace; }
.dados b { font-weight: 600; }
.controlo { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
            background: var(--cartao); border: 1px solid var(--linha); border-radius: 10px; padding: 10px 14px; }
.controlo input[type=range] { width: min(320px, 70vw); }
.controlo button { font: inherit; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--linha);
                   background: var(--pagina); color: var(--tinta); cursor: pointer; }
#ligacao.ok { color: #1a7f37; } #ligacao.falha { color: #b42318; }
@media (prefers-color-scheme: dark) { #ligacao.ok { color: #4ac26b; } #ligacao.falha { color: #f97066; } }
</style>
</head>
<body>
<h1>Matriz virtual</h1>
<p class="sub">Fase 8.d. Dois painéis HUB75 de 64×32 em cadeia, simulados LED a LED,
com a fonte 5×8 que o nó vai levar. Liga ao <code>visual_service</code> como o
Matrix Portal vai ligar.</p>

<div class="painel"><canvas id="matriz"></canvas></div>

<div class="dados">
  <span>ligação: <b id="ligacao">—</b></span>
  <span>posição: <b id="posicao">—</b></span>
  <span>entrada: <b id="entrada">—</b></span>
  <span>letra: <b id="letra">—</b></span>
  <span>faixa: <b id="faixa">—</b></span>
</div>

<div class="controlo">
  <label for="offset">Offset</label>
  <input id="offset" type="range" min="-2000" max="2000" step="50" value="0">
  <b id="offset-valor">0 ms</b>
  <button id="offset-zero" type="button">zero</button>
  <span style="color: var(--suave)">positivo = a letra aparece mais cedo</span>
</div>

<script>
"use strict";

const COLS = 128, LINHAS = 32;
const LED = 6, FOLGA = 1;            // um LED de 5 px com 1 px de intervalo
const FILAS_Y = [1, 12, 23];
const APAGADA = 0.3, SEM_SERVIDOR = 0.2;
const BRILHO_MINIMO = 200;           // canal mais forte, de 0 a 255

const canvas = document.getElementById("matriz");
canvas.width = COLS * LED;
canvas.height = LINHAS * LED;
const ctx = canvas.getContext("2d");

let fonte = null;
let track = { id: null };
let letras = null;
let ancora = { progresso: 0, local: performance.now(), a_tocar: false };
let ligado = false;
let cor = [235, 235, 235];

// -- offset, guardado neste browser -------------------------------------
const campoOffset = document.getElementById("offset");
function lerOffset() { try { return Number(localStorage.getItem("matriz.offset")) || 0; } catch (e) { return 0; } }
function guardarOffset(v) { try { localStorage.setItem("matriz.offset", String(v)); } catch (e) {} }
campoOffset.value = lerOffset();
function mostrarOffset() { document.getElementById("offset-valor").textContent = campoOffset.value + " ms"; }
campoOffset.addEventListener("input", () => { guardarOffset(campoOffset.value); mostrarOffset(); });
document.getElementById("offset-zero").addEventListener("click", () => { campoOffset.value = 0; guardarOffset(0); mostrarOffset(); });
mostrarOffset();

// -- cor -------------------------------------------------------------------
function corDe(hex) {
  if (!hex || !/^#[0-9a-f]{6}$/i.test(hex)) return [235, 235, 235];
  const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  const maior = Math.max(...c);
  if (maior === 0) return [235, 235, 235];
  const f = Math.max(1, BRILHO_MINIMO / maior);
  return c.map(v => Math.min(255, Math.round(v * f)));
}

// -- desenho ---------------------------------------------------------------
const leds = new Float32Array(COLS * LINHAS);   // brilho de 0 a 1

function escrever(texto, y, brilho) {
  const avanco = fonte.avanco, largura = fonte.largura;
  const total = texto.length * avanco - 1;
  let x = Math.floor((COLS - total) / 2);
  for (const ch of texto) {
    const glifo = fonte.glifos[String(ch.codePointAt(0))];
    if (glifo) {
      for (let linha = 0; linha < fonte.altura; linha++) {
        for (let col = 0; col < largura; col++) {
          if (glifo[linha] & (1 << (largura - 1 - col))) {
            const px = x + col, py = y + linha;
            if (px >= 0 && px < COLS && py >= 0 && py < LINHAS) leds[py * COLS + px] = brilho;
          }
        }
      }
    }
    x += avanco;
  }
}

function posicaoAgora() {
  const passou = ancora.a_tocar ? performance.now() - ancora.local : 0;
  return ancora.progresso + passou + Number(campoOffset.value);
}

function entradaActiva(linhas, pos) {
  let i = -1;
  for (let k = 0; k < linhas.length; k++) { if (linhas[k][0] <= pos) i = k; else break; }
  return i;
}

function quadro() {
  leds.fill(0);
  let info = "—";

  if (fonte && letras && letras.id === track.id && letras.linhas.length) {
    const pos = posicaoAgora();
    const i = entradaActiva(letras.linhas, pos);
    const brilhoBase = ligado ? 1 : SEM_SERVIDOR;
    info = i < 0 ? "antes da 1.ª" : (i + 1) + " de " + letras.linhas.length;

    if (i >= 0) {
      const filas = letras.linhas[i][1];
      filas.forEach((f, n) => escrever(f, FILAS_Y[n], brilhoBase));
      const seguinte = letras.linhas[i + 1];
      if (filas.length <= 2 && seguinte && seguinte[1].length) {
        escrever(seguinte[1][0], FILAS_Y[2], APAGADA * brilhoBase);
      }
    } else if (i < 0 && letras.linhas[0] && letras.linhas[0][1].length) {
      // Antes da primeira linha: a primeira, apagada, a anunciar.
      escrever(letras.linhas[0][1][0], FILAS_Y[1], APAGADA * brilhoBase);
    }
  }

  const fundo = 14;
  ctx.fillStyle = "#050505";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  for (let y = 0; y < LINHAS; y++) {
    for (let x = 0; x < COLS; x++) {
      const b = leds[y * COLS + x];
      ctx.fillStyle = b > 0
        ? `rgb(${Math.round(cor[0] * b)},${Math.round(cor[1] * b)},${Math.round(cor[2] * b)})`
        : `rgb(${fundo},${fundo},${fundo})`;
      ctx.fillRect(x * LED, y * LED, LED - FOLGA, LED - FOLGA);
    }
  }

  const p = Math.max(0, posicaoAgora()) / 1000;
  document.getElementById("posicao").textContent =
    Math.floor(p / 60) + ":" + String(Math.floor(p % 60)).padStart(2, "0") + "." + Math.floor((p % 1) * 10)
    + (ancora.a_tocar ? "" : " (parada)");
  document.getElementById("entrada").textContent = info;
}

setInterval(quadro, 1000 / 30);

// -- ligação ---------------------------------------------------------------
let espera = 1000;

function ligar() {
  const ws = new WebSocket(`ws://${location.hostname}:8766/visual`);
  const estadoLigacao = document.getElementById("ligacao");

  ws.onopen = () => { ligado = true; espera = 1000; estadoLigacao.textContent = "ligada"; estadoLigacao.className = "ok"; };

  ws.onmessage = (evento) => {
    const m = JSON.parse(evento.data);
    const agora = performance.now();

    if (m.t === "track") {
      track = m;
      if (m.paleta) cor = corDe(m.paleta.a1 || m.paleta.dom);
      if (m.id) ancora = { progresso: m.progress_ms, local: agora, a_tocar: ancora.a_tocar };
      document.getElementById("faixa").textContent = m.id ? `${m.titulo} — ${m.artista}` : "nada a tocar";
    } else if (m.t === "letras") {
      letras = m;
      document.getElementById("letra").textContent = `${m.estado} (${m.motivo || "—"}), ${m.linhas.length} entradas`;
    } else if (m.t === "estado") {
      ancora = { progresso: m.progress_ms, local: agora, a_tocar: m.a_tocar };
    }
  };

  ws.onclose = () => {
    // Pára a letra onde está (a posição deixa de andar) e o quadro passa a
    // desenhar a 20%: uma luz fraca parece repouso, um ecrã preto parece avaria.
    if (ligado) {
      ancora = { progresso: posicaoAgora() - Number(campoOffset.value), local: performance.now(), a_tocar: false };
    }
    ligado = false;
    estadoLigacao.textContent = `sem servidor — nova tentativa em ${Math.round(espera / 1000)} s`;
    estadoLigacao.className = "falha";
    setTimeout(ligar, espera);
    espera = Math.min(espera * 2, 30000);
  };
}

fetch("/matriz/fonte.json").then(r => r.json()).then(f => { fonte = f; ligar(); });
</script>
</body>
</html>
"""
