"""
Página `/tema` — o LCD da BOX simulado, uma vez por cada capa do corpus
(Fase 8.b, passo 2).

Existe para escolher os números do `tema_service` a olhar para as capas
reais, e não para duas. Os parâmetros vêm no URL, por isso uma combinação que
pareça boa pode guardar-se como um link.

Não chama o Spotify: lê o `capas.jsonl` e as imagens vêm do CDN, pelo browser.
Pode ficar aberta sem custar nada ao polling da BOX.

O desenho copia o `display_LCD.c` à letra: ecrã de 320×240, barra de voz de
10 px no topo, capa de 120×120 a 8 px da esquerda, texto de 170 px a 8 px da
direita, botões de 70, 100 e 70 × 38 a 6 px do fundo. O raio dos botões e a
fonte são aproximações — a fonte do LVGL é a Montserrat 14 em bitmap.
"""

from html import escape

import tema_service


# As cores da barra de voz, copiadas do `voice_ui_cor` do firmware.
CORES_BARRA = {
    "dormido": "#5a5a5a",
    "ouve": "#22c55e",
    "pensa": "#f59e0b",
    "fala": "#3b82f6",
    "aberto": "#14b8a6",
}


ESTILO = """
:root {
  --pagina: #f4f4f2; --cartao: #ffffff; --tinta: #1d1d1b; --suave: #6b6b66;
  --linha: #dcdcd6; --ok: #1a7f37; --falha: #b42318; --aviso: #9a6700;
}
@media (prefers-color-scheme: dark) {
  :root {
    --pagina: #161615; --cartao: #20201e; --tinta: #ececea; --suave: #a3a39c;
    --linha: #3a3a36; --ok: #4ac26b; --falha: #f97066; --aviso: #e3b341;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 20px 16px 48px; background: var(--pagina);
  color: var(--tinta); font: 14px/1.45 system-ui, sans-serif;
}
h1 { font-size: 20px; margin: 0 0 4px; }
p.sub { margin: 0 0 16px; color: var(--suave); max-width: 70ch; }
form {
  display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: end;
  background: var(--cartao); border: 1px solid var(--linha);
  border-radius: 10px; padding: 12px 14px; margin-bottom: 14px;
}
label.campo { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--suave); }
label.campo input, label.campo select {
  font: inherit; color: var(--tinta); background: var(--pagina);
  border: 1px solid var(--linha); border-radius: 6px; padding: 5px 7px; width: 110px;
}
label.marca { display: flex; gap: 6px; align-items: center; font-size: 13px; }
button.aplicar {
  font: inherit; padding: 6px 14px; border-radius: 6px; border: 0;
  background: var(--tinta); color: var(--pagina); cursor: pointer;
}
a.repor { color: var(--suave); font-size: 13px; }
.resumo { display: flex; flex-wrap: wrap; gap: 8px 20px; margin: 0 0 18px; font-size: 13px; }
.resumo b { font-variant-numeric: tabular-nums; }
.grelha {
  display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 342px), 1fr));
}
.cartao {
  background: var(--cartao); border: 1px solid var(--linha);
  border-radius: 10px; padding: 10px; min-width: 0;
}
.cartao.referencia { border: 2px dashed var(--suave); }
.lcd-caixa { overflow-x: auto; }
.lcd {
  position: relative; width: 320px; height: 240px; overflow: hidden;
  font: 14px/16px "Montserrat", system-ui, sans-serif; margin: 0 auto;
}
.lcd .barra { position: absolute; left: 0; right: 0; top: 0; height: 10px; }
.lcd img, .lcd .sem-capa {
  position: absolute; left: 8px; top: 60px; width: 120px; height: 120px; object-fit: cover;
}
.lcd .sem-capa { background: repeating-linear-gradient(45deg, #0002 0 6px, #0000 6px 12px); }
.lcd .texto {
  position: absolute; right: 8px; top: 50%; transform: translateY(-50%);
  width: 170px; text-align: center; white-space: pre-wrap; overflow-wrap: anywhere;
}
.lcd .btn {
  position: absolute; bottom: 6px; height: 38px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center; font-size: 14px;
}
.lcd .b1 { left: 10px; width: 70px; }
.lcd .b2 { left: 110px; width: 100px; }
.lcd .b3 { right: 10px; width: 70px; }
.legenda { margin: 8px 2px 0; font-size: 12px; color: var(--suave); }
.legenda .nome { color: var(--tinta); font-weight: 600; overflow-wrap: anywhere; }
.amostras { display: flex; flex-wrap: wrap; gap: 4px 10px; margin-top: 6px; }
.amostra { display: inline-flex; align-items: center; gap: 4px; font: 11px ui-monospace, monospace; }
.amostra i { width: 12px; height: 12px; border-radius: 3px; border: 1px solid var(--linha); display: inline-block; }
.contrastes { display: flex; flex-wrap: wrap; gap: 2px 10px; margin-top: 6px; font: 12px ui-monospace, monospace; }
.passa { color: var(--ok); } .falha { color: var(--falha); font-weight: 700; }
.etiqueta {
  display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 4px;
  background: var(--aviso); color: var(--cartao); font-size: 11px; font-weight: 600;
}
"""


PARAMETROS_FORMULARIO = [
    ("contraste_texto", "Contraste texto", "0.1"),
    ("contraste_botao", "Contraste botão/fundo", "0.1"),
    ("fundo_l_max", "Fundo L máx", "0.01"),
    ("fundo_c_max", "Fundo croma máx", "0.01"),
    ("claro_a_partir", "Capa clara a partir de L", "0.01"),
    ("claro_l_min", "Fundo claro L mín", "0.01"),
]


def _lcd(tema, capa_url, linhas, barra, premido):
    botao = tema["botao_premido"] if premido else tema["botao"]

    imagem = (
        f'<img src="{escape(capa_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
        if capa_url
        else '<div class="sem-capa"></div>'
    )

    botoes = "".join(
        f'<div class="btn {classe}" style="background:{botao};color:{tema["texto_botao"]}">'
        f"{escape(rotulo)}</div>"
        for classe, rotulo in (("b1", "<<"), ("b2", "PLAY / PAUSE"), ("b3", ">>"))
    )

    return (
        f'<div class="lcd-caixa"><div class="lcd" style="background:{tema["fundo"]}">'
        f'<div class="barra" style="background:{CORES_BARRA[barra]}"></div>'
        f"{imagem}"
        f'<div class="texto" style="color:{tema["texto"]}">{escape(linhas)}</div>'
        f"{botoes}</div></div>"
    )


def _numeros(contrastes, p):
    minimos = {
        "texto": p["contraste_texto"],
        "botao": p["contraste_botao"],
        "texto_botao": p["contraste_texto"],
        "texto_premido": p["contraste_texto"],
    }
    nomes = {
        "texto": "texto",
        "botao": "botão/fundo",
        "texto_botao": "txt botão",
        "texto_premido": "txt premido",
    }

    return "".join(
        f'<span class="{"passa" if contrastes[k] >= minimos[k] else "falha"}">'
        f"{nomes[k]} {contrastes[k]:.2f}</span>"
        for k in nomes
    )


def _amostras(tema):
    return "".join(
        f'<span class="amostra"><i style="background:{tema[k]}"></i>{k.replace("_", " ")} {tema[k]}</span>'
        for k in ("fundo", "texto", "botao", "botao_premido", "texto_botao")
    )


def _linhas(faixa, artista, album):
    return (
        "SPOTIFY\n\n"
        f"{faixa or ''}\n{artista or ''}\n\n{album or ''}\n\n"
        "PLAYING   1:23 / 3:45"
    )


def gerar(capas, argumentos):
    """`capas` vem do `capas_log.ler_capas()`; `argumentos` do URL."""
    p = tema_service.parametros(
        **{k: argumentos.get(k) for k in tema_service.PARAMETROS if k in argumentos}
    )

    barra = argumentos.get("barra")
    barra = barra if barra in CORES_BARRA else "dormido"
    premido = argumentos.get("premido") == "1"

    cartoes = []
    contagem_recurso = {}
    piores = {}

    # Referência: o tema que está hoje no firmware.
    hoje = dict(tema_service.TEMA_HOJE)
    cartoes.append(
        '<div class="cartao referencia">'
        + _lcd(hoje, None, _linhas("Faixa", "Artista", "Álbum"), barra, premido)
        + '<div class="legenda"><span class="nome">Hoje, no firmware</span>'
        " — o texto dos botões é o branco do tema do LVGL"
        f'<div class="amostras">{_amostras(hoje)}</div>'
        f'<div class="contrastes">{_numeros(tema_service.contrastes_de(hoje), p)}</div>'
        "</div></div>"
    )

    for capa in capas:
        try:
            tema = tema_service.calcular_tema(capa, p)
        except ValueError as erro:
            cartoes.append(
                f'<div class="cartao"><div class="legenda falha">{escape(str(erro))}</div></div>'
            )
            continue

        for r in tema["recurso"]:
            contagem_recurso[r] = contagem_recurso.get(r, 0) + 1

        for k, v in tema["contrastes"].items():
            piores[k] = min(piores.get(k, v), v)

        etiquetas = "".join(
            f'<span class="etiqueta">recurso: {escape(r)}</span>' for r in tema["recurso"]
        )

        cartoes.append(
            '<div class="cartao">'
            + _lcd(
                tema,
                capa.get("capa"),
                _linhas(capa.get("faixa"), capa.get("artista"), capa.get("album")),
                barra,
                premido,
            )
            + '<div class="legenda">'
            f'<span class="nome">{escape(capa.get("artista") or "")} — '
            f'{escape(capa.get("album") or capa.get("faixa") or "")}</span>{etiquetas}'
            f'<div class="amostras">{_amostras(tema)}</div>'
            f'<div class="contrastes">{_numeros(tema["contrastes"], p)}</div>'
            "</div></div>"
        )

    campos = "".join(
        f'<label class="campo">{rotulo}'
        f'<input type="number" name="{nome}" step="{passo}" value="{p[nome]:g}"></label>'
        for nome, rotulo, passo in PARAMETROS_FORMULARIO
    )

    variantes = "".join(
        f'<option value="{v}"{" selected" if v == p["variante"] else ""}>{v}</option>'
        for v in tema_service.VARIANTES
    )

    barras = "".join(
        f'<option value="{b}"{" selected" if b == barra else ""}>{b}</option>'
        for b in CORES_BARRA
    )

    recurso_texto = (
        ", ".join(f"{k} {v}" for k, v in sorted(contagem_recurso.items()))
        or "nenhum"
    )

    piores_texto = " · ".join(
        f"{k.replace('_', ' ')} <b>{v:.2f}</b>" for k, v in piores.items()
    )

    return f"""<!doctype html>
<html lang="pt-PT">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tema do LCD</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400&display=swap" rel="stylesheet">
<style>{ESTILO}</style>
</head>
<body>
<h1>Tema do LCD</h1>
<p class="sub">Fase 8.b, passo 2. O LCD da BOX simulado a 1:1 para as
{len(capas)} capas do <code>capas.jsonl</code>. Os números ficam no URL. O ecrã
do browser não é o LCD: a escolha final confirma-se na BOX.</p>

<form method="get">
  <label class="campo">Variante<select name="variante">{variantes}</select></label>
  {campos}
  <label class="campo">Barra de voz<select name="barra">{barras}</select></label>
  <label class="marca"><input type="checkbox" name="premido" value="1"{" checked" if premido else ""}> botões premidos</label>
  <button class="aplicar" type="submit">Aplicar</button>
  <a class="repor" href="/tema">repor</a>
</form>

<div class="resumo">
  <span>Capas: <b>{len(capas)}</b></span>
  <span>Recurso: <b>{escape(recurso_texto)}</b></span>
  <span>Piores contrastes: {piores_texto or "—"}</span>
</div>

<div class="grelha">
{"".join(cartoes)}
</div>
</body>
</html>"""
