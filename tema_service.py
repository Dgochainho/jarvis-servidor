"""
Tema do LCD a partir da paleta da capa (Fase 8.b, passo 2).

Paleta da 8.a entra, cinco cores saem: `fundo`, `texto`, `botao`,
`botao_premido` e `texto_botao`. Funções puras — sem rede, sem estado — para
se poder correr sobre o corpus inteiro (T33) e sobre a página `/tema`.

Duas medidas, cada uma para o que serve (decisão T2):

  - o CONTRASTE mede-se com a fórmula do WCAG, que dá números comparáveis com
    os 4,10 : 1 do texto de hoje;
  - para MEXER numa cor usa-se OKLCH, onde escurecer um vermelho o deixa
    vermelho. Em HSL não é assim.

O contraste mede-se depois de a cor passar a RGB565, porque é isso que o LCD
mostra.

Os números de PARAMETROS foram escolhidos a 2026-10-20 na página `/tema`,
a olhar para 52 capas reais. Falta vê-los na BOX. Ver
`docs/FASE-8.b-tema.md`.
"""

import math


PARAMETROS = {
    # "escuro": fundo sempre escuro. "segue": capa clara dá fundo claro.
    #
    # "segue" desde 2026-10-20, escolhida na página /tema com 52 capas: dá
    # mais variedade. Os outros números ficaram nos de partida — vistos nas
    # mesmas 52, nenhum pareceu mal. A confirmação final é na BOX (passo 3).
    "variante": "segue",

    # Mínimos de contraste (WCAG). 4,5 é o do texto normal, um pouco acima
    # dos 4,10 de hoje; 3,0 é o dos elementos que não são texto.
    "contraste_texto": 4.5,
    "contraste_botao": 3.0,

    # Fundo (OKLCH): luminosidade máxima e croma máximo.
    "fundo_l_max": 0.30,
    "fundo_c_max": 0.06,

    # Só na "segue": a partir de que luminosidade a capa conta como clara, e
    # o fundo claro mínimo que isso dá.
    "claro_a_partir": 0.65,
    "claro_l_min": 0.88,
}


# Limites aceites pela página, para um valor absurdo no URL não partir nada.
LIMITES = {
    "contraste_texto": (1.0, 21.0),
    "contraste_botao": (1.0, 21.0),
    "fundo_l_max": (0.0, 1.0),
    "fundo_c_max": (0.0, 0.4),
    "claro_a_partir": (0.0, 1.0),
    "claro_l_min": (0.0, 1.0),
}

VARIANTES = ("escuro", "segue")


# Quanto o botão premido se afasta do normal, em luminosidade OKLCH.
DESLOCAMENTO_PREMIDO = 0.08

# O croma máximo do texto: um toque do matiz do fundo, não uma cor.
CROMA_TEXTO = 0.02


# ---------------------------------------------------------
# Cor: sRGB, linear, OKLab / OKLCH, RGB565
# ---------------------------------------------------------

def _para_linear(canal):
    c = canal / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _de_linear(x):
    if x <= 0.0031308:
        return 12.92 * x
    return 1.055 * (x ** (1 / 2.4)) - 0.055


def _rgb_para_oklab(rgb):
    r, g, b = [_para_linear(c) for c in rgb]

    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    l, m, s = [math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s)]

    return (
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    )


def _oklab_para_linear(L, a, b):
    l = L + 0.3963377774 * a + 0.2158037573 * b
    m = L - 0.1055613458 * a - 0.0638541728 * b
    s = L - 0.0894841775 * a - 1.2914855480 * b

    l, m, s = l ** 3, m ** 3, s ** 3

    return (
        +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def para_oklch(rgb):
    L, a, b = _rgb_para_oklab(rgb)
    return L, math.hypot(a, b), math.atan2(b, a)


def de_oklch(L, C, h):
    """
    OKLCH para sRGB de 8 bits.

    Uma cor fora do que o sRGB consegue mostrar perde croma até caber, e não
    luminosidade: a luminosidade é o que o contraste mede, e é ela que a
    procura do botão está a escolher.
    """
    L = min(max(L, 0.0), 1.0)

    def tentar(croma):
        linear = _oklab_para_linear(
            L, croma * math.cos(h), croma * math.sin(h)
        )
        if all(-1e-4 <= v <= 1 + 1e-4 for v in linear):
            return linear
        return None

    linear = tentar(C)

    if linear is None:
        baixo, alto = 0.0, C
        linear = tentar(0.0)

        for _ in range(20):
            meio = (baixo + alto) / 2
            candidato = tentar(meio)

            if candidato is None:
                alto = meio
            else:
                baixo, linear = meio, candidato

    return [
        int(round(min(max(_de_linear(min(max(v, 0.0), 1.0)), 0.0), 1.0) * 255))
        for v in linear
    ]


def para_565(rgb):
    """O que o LCD mostra de facto: 5, 6 e 5 bits, expandidos de volta."""
    r, g, b = rgb
    r5, g6, b5 = r >> 3, g >> 2, b >> 3
    return [(r5 << 3) | (r5 >> 2), (g6 << 2) | (g6 >> 4), (b5 << 3) | (b5 >> 2)]


def luminancia(rgb):
    r, g, b = [_para_linear(c) for c in para_565(rgb)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(cor_a, cor_b):
    """Razão de contraste do WCAG, de 1 a 21, depois de RGB565."""
    claro, escuro = sorted(
        (luminancia(cor_a), luminancia(cor_b)), reverse=True
    )
    return (claro + 0.05) / (escuro + 0.05)


def para_hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def de_hex(texto):
    texto = texto.lstrip("#")
    return [int(texto[i:i + 2], 16) for i in (0, 2, 4)]


# ---------------------------------------------------------
# As cinco cores
# ---------------------------------------------------------

def _texto_para(fundo):
    """
    Texto claro ou escuro, com um toque do matiz de `fundo`: o que tiver
    mais contraste. Devolve (cor, contraste).
    """
    _, croma, matiz = para_oklch(fundo)
    croma = min(croma, CROMA_TEXTO)

    candidatos = [de_oklch(0.97, croma, matiz), de_oklch(0.20, croma, matiz)]

    return max(
        ((cor, contraste(cor, fundo)) for cor in candidatos),
        key=lambda par: par[1],
    )


def _fundo(dominante, p):
    L, C, h = para_oklch(dominante)

    if p["variante"] == "segue" and L >= p["claro_a_partir"]:
        L = max(L, p["claro_l_min"])
    else:
        L = min(L, p["fundo_l_max"])

    return de_oklch(L, min(C, p["fundo_c_max"]), h)


def _botao(origem, fundo, p):
    """
    A luminosidade mais próxima da original que passe os dois contrastes:
    o botão contra o fundo, e o texto do botão contra o botão.

    A mais próxima, para o botão continuar a parecer a cor de realce da capa
    e não uma cor qualquer que por acaso passa. Devolve (botao, texto) ou
    None se nenhuma luminosidade servir.
    """
    L0, C0, h0 = para_oklch(origem)

    for L in sorted((i / 100 for i in range(3, 99)), key=lambda x: abs(x - L0)):
        cor = de_oklch(L, C0, h0)

        if contraste(cor, fundo) < p["contraste_botao"]:
            continue

        texto, c_texto = _texto_para(cor)

        if c_texto >= p["contraste_texto"]:
            return cor, texto

    return None


def _premido(botao, texto_botao, p):
    """
    O botão deslocado em luminosidade: escurece, a não ser que já seja tão
    escuro que não dê. Tem de manter o contraste do texto; se não der para
    nenhum dos lados, fica igual ao normal (e o tema diz que ficou).
    """
    L, C, h = para_oklch(botao)

    for passo in (DESLOCAMENTO_PREMIDO, DESLOCAMENTO_PREMIDO / 2):
        for sinal in ((-1, 1) if L >= 0.25 else (1, -1)):
            cor = de_oklch(L + sinal * passo, C, h)

            if contraste(texto_botao, cor) >= p["contraste_texto"]:
                return cor

    return None


CINZENTO = [0x3a, 0x3a, 0x3a]


def parametros(**alteracoes):
    """PARAMETROS com as alterações dadas, já limitadas ao que é aceitável."""
    p = dict(PARAMETROS)

    for chave, valor in alteracoes.items():
        if chave == "variante":
            if valor in VARIANTES:
                p[chave] = valor
            continue

        if chave not in LIMITES:
            continue

        try:
            numero = float(valor)
        except (TypeError, ValueError):
            continue

        if math.isfinite(numero):
            baixo, alto = LIMITES[chave]
            p[chave] = min(max(numero, baixo), alto)

    return p


def calcular_tema(paleta, p=None):
    """
    Paleta da 8.a (com `dominante` e `realce`) para as cinco cores.

    `recurso` lista o que não saiu da capa:
      - "botao"   — o realce não deu nenhum botão que passasse; tentou-se a
                    dominante e, depois dela, o cinzento;
      - "premido" — não houve deslocamento que mantivesse o texto legível;
      - "tudo"    — nem o texto passou sobre o fundo; é o tema neutro (T5).
    """
    p = p or dict(PARAMETROS)
    recurso = []

    dominante = (paleta.get("dominante") or {}).get("rgb") or CINZENTO
    realce = (paleta.get("realce") or {}).get("rgb") or dominante

    fundo = _fundo(dominante, p)
    texto, c_texto = _texto_para(fundo)

    if c_texto < p["contraste_texto"]:
        if dominante == CINZENTO:
            raise ValueError("nem o tema neutro passa com estes parâmetros")

        neutro = calcular_tema({"dominante": {"rgb": CINZENTO}}, p)
        neutro["recurso"] = ["tudo"]
        return neutro

    botao = None

    for origem in (realce, dominante, CINZENTO):
        botao = _botao(origem, fundo, p)

        if botao:
            break

        recurso = ["botao"]

    if botao is None:
        raise ValueError("nenhum botão passa com estes parâmetros")

    botao, texto_botao = botao
    premido = _premido(botao, texto_botao, p)

    if premido is None:
        premido = botao
        recurso.append("premido")

    return {
        "fundo": para_hex(fundo),
        "texto": para_hex(texto),
        "botao": para_hex(botao),
        "botao_premido": para_hex(premido),
        "texto_botao": para_hex(texto_botao),
        "contrastes": {
            "texto": round(c_texto, 2),
            "botao": round(contraste(botao, fundo), 2),
            "texto_botao": round(contraste(texto_botao, botao), 2),
            "texto_premido": round(contraste(texto_botao, premido), 2),
        },
        "recurso": recurso,
        "variante": p["variante"],
    }


def tema_neutro(p=None):
    """
    O tema sem capa: o mesmo cálculo, a partir de um cinzento (T5).

    O firmware tem uma cópia destas cores, para o arranque e para quando o
    servidor não responde (F3). O T34 compara as duas.
    """
    return calcular_tema({"dominante": {"rgb": CINZENTO}}, p)


CORES = ("fundo", "texto", "botao", "botao_premido", "texto_botao")


# O tema que está hoje no display_LCD.c, para comparar. O texto do botão
# não está no firmware: é o branco do tema por omissão do LVGL 9.5.
TEMA_HOJE = {
    "fundo": "#a8a8a8",
    "texto": "#444444",
    "botao": "#dcdcdc",
    "botao_premido": "#999999",
    "texto_botao": "#ffffff",
}


def contrastes_de(tema):
    """Os mesmos números do `calcular_tema`, para um tema dado em hex."""
    c = {nome: de_hex(tema[nome]) for nome in TEMA_HOJE}

    return {
        "texto": round(contraste(c["texto"], c["fundo"]), 2),
        "botao": round(contraste(c["botao"], c["fundo"]), 2),
        "texto_botao": round(contraste(c["texto_botao"], c["botao"]), 2),
        "texto_premido": round(contraste(c["texto_botao"], c["botao_premido"]), 2),
    }
