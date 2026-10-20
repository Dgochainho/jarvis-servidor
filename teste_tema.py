"""
T33 — o tema cumpre as próprias regras (Fase 8.b, passo 2).

Corre sem a BOX e sem rede. Para cada capa do `capas.jsonl` (se existir) e
para casos extremos fabricados, nas duas variantes, verifica que o tema:

  1. passa os dois contrastes, medidos depois de RGB565 — ou é o recurso e
     diz que é;
  2. dá as cinco cores em hex válido;
  3. é determinístico: a mesma paleta dá sempre o mesmo tema.

E verifica também as contas de base: branco contra preto dá 21, uma cor
contra ela mesma dá 1, e uma ida e volta por OKLCH devolve a mesma cor.

Não diz se o tema é bonito nem se se lê a 3 m. Isso vê-se na página `/tema` e
depois na BOX.

Correr com:  .\\.venv\\Scripts\\python.exe teste_tema.py
"""

import re
import sys

import capas_log
import tema_service as t


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


falhas = []


def verificar(condicao, descricao):
    if not condicao:
        print(f"  FALHA {descricao}")
        falhas.append(descricao)

    return condicao


def paleta(dominante, realce=None):
    return {
        "dominante": {"rgb": dominante},
        "realce": {"rgb": realce or dominante},
    }


EXTREMOS = {
    "preto": paleta([0, 0, 0]),
    "branco": paleta([255, 255, 255]),
    "cinzento médio": paleta([119, 119, 119]),
    "vermelho puro": paleta([255, 0, 0]),
    "amarelo": paleta([250, 230, 20]),
    "azul escuro com realce amarelo": paleta([10, 20, 70], [250, 230, 20]),
    "branco com realce branco": paleta([250, 250, 250], [245, 245, 245]),
    "verde do OUVE": paleta([0x22, 0xC5, 0x5E]),
    "sem paleta": {},
}

HEX = re.compile(r"^#[0-9a-f]{6}$")


print()
print("T33 · o tema cumpre as próprias regras")
print()

print("1. Contas de base")
verificar(round(t.contraste([255] * 3, [0] * 3), 2) == 21.0, "branco/preto = 21")
verificar(t.contraste([90, 40, 200], [90, 40, 200]) == 1.0, "uma cor contra ela mesma = 1")
idas = [[255, 0, 0], [18, 52, 86], [250, 250, 10], [0, 0, 0], [255, 255, 255]]
verificar(
    all(t.de_oklch(*t.para_oklch(c)) == c for c in idas),
    "ida e volta por OKLCH devolve a mesma cor",
)
print(f"  {'OK' if not falhas else 'FALHA'}")

capas = capas_log.ler_capas()
casos = {**EXTREMOS}
for i, capa in enumerate(capas):
    casos[f"capa {i + 1}: {capa.get('artista')} — {capa.get('album')}"] = capa

for variante in t.VARIANTES:
    p = t.parametros(variante=variante)
    recursos = {}
    antes = len(falhas)

    print()
    print(
        f"2. Variante `{variante}`: {len(EXTREMOS)} extremos + "
        f"{len(capas)} capas do corpus"
    )

    for nome, caso in casos.items():
        tema = t.calcular_tema(caso, p)
        c = tema["contrastes"]

        for r in tema["recurso"]:
            recursos[r] = recursos.get(r, 0) + 1

        verificar(
            all(HEX.match(tema[k]) for k in t.TEMA_HOJE),
            f"{variante} · {nome}: cores em hex",
        )
        verificar(
            c["texto"] >= p["contraste_texto"],
            f"{variante} · {nome}: texto {c['texto']}",
        )
        verificar(
            c["botao"] >= p["contraste_botao"],
            f"{variante} · {nome}: botão/fundo {c['botao']}",
        )
        verificar(
            c["texto_botao"] >= p["contraste_texto"],
            f"{variante} · {nome}: texto do botão {c['texto_botao']}",
        )
        verificar(
            c["texto_premido"] >= p["contraste_texto"]
            or "premido" in tema["recurso"],
            f"{variante} · {nome}: texto premido {c['texto_premido']} sem aviso",
        )
        verificar(
            t.calcular_tema(caso, p) == tema,
            f"{variante} · {nome}: determinístico",
        )

    print(
        f"  {'OK' if len(falhas) == antes else 'FALHA'} · "
        f"recurso: {recursos or 'nenhum'}"
    )

print()
print("3. A variante `escuro` nunca dá fundo claro")
p = t.parametros(variante="escuro")
claros = [
    nome for nome, caso in casos.items()
    if t.para_oklch(t.de_hex(t.calcular_tema(caso, p)["fundo"]))[0]
    > p["fundo_l_max"] + 0.01
]
verificar(not claros, f"fundos acima de L {p['fundo_l_max']}: {claros[:3]}")
print(f"  {'OK' if not claros else 'FALHA'}")

print()
print("4. Parâmetros absurdos no URL não partem nada")
p = t.parametros(contraste_texto="abc", fundo_l_max="9", variante="inventada")
verificar(p["contraste_texto"] == t.PARAMETROS["contraste_texto"], "texto não numérico ignorado")
verificar(p["fundo_l_max"] == 1.0, "número fora do limite encostado ao limite")
verificar(p["variante"] == t.PARAMETROS["variante"], "variante desconhecida ignorada")
print(f"  {'OK' if not falhas else 'FALHA'}")

print()
if falhas:
    print(f"T33 FALHOU — {len(falhas)} verificação(ões)")
    sys.exit(1)

print("T33 PASSA")
