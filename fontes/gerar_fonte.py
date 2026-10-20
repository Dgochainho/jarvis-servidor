"""
Converte uma fonte BDF na tabela que a camada visual usa (Fase 8.d, Q1).

A tabela é a MESMA para os três lados:

  - o servidor (lyrics_service) lê dela o conjunto de caracteres que pode
    mandar ao nó — o que não estiver aqui é transliterado ou desiste;
  - a matriz virtual (/matriz) desenha com ela;
  - o nó (Matrix Portal) vai levar a mesma tabela, convertida para C.

Uma fonte só, para a matriz virtual não mentir sobre o que cabe numa fila.

Origem: `5x8.bdf` do X11 (misc-fixed), domínio público — "Public domain
font. Share and enjoy." —, de gitlab.freedesktop.org/xorg/font/misc-misc.
Descarregada a 2026-10-20.

Uso:  .\\.venv\\Scripts\\python.exe fontes\\gerar_fonte.py <caminho do .bdf>
"""

import json
import sys
from pathlib import Path


# Latin-1 imprimível: 0x20–0x7E e 0xA0–0xFF. É o conjunto que o português
# precisa (ã, õ, ç…) e que a fonte por omissão da Adafruit GFX (CP437) não tem.
CONJUNTO = list(range(0x20, 0x7F)) + list(range(0xA0, 0x100))

SAIDA = Path(__file__).with_name("fonte_5x8.json")


def ler_bdf(caminho):
    linhas = Path(caminho).read_text(encoding="latin-1").splitlines()

    propriedades = {}
    glifos = {}
    i = 0

    while i < len(linhas):
        partes = linhas[i].split()

        if partes and partes[0] in ("FONTBOUNDINGBOX", "FONT_ASCENT", "FONT_DESCENT", "COPYRIGHT"):
            propriedades[partes[0]] = partes[1:]

        if partes and partes[0] == "STARTCHAR":
            codigo, bbx, linhas_bitmap = None, None, []
            i += 1

            while linhas[i] != "ENDCHAR":
                campos = linhas[i].split()

                if campos[0] == "ENCODING":
                    codigo = int(campos[1])
                elif campos[0] == "BBX":
                    bbx = [int(v) for v in campos[1:5]]
                elif campos[0] == "BITMAP":
                    i += 1
                    while linhas[i] != "ENDCHAR":
                        linhas_bitmap.append(int(linhas[i], 16))
                        i += 1
                    continue

                i += 1

            glifos[codigo] = (bbx, linhas_bitmap)

        i += 1

    return propriedades, glifos


def para_celula(bbx, bitmap, largura, altura, ascendente):
    """
    Põe um glifo na célula de `largura` × `altura`, linha 0 em cima.

    Cada linha sai como um inteiro de `largura` bits, com o bit mais alto à
    esquerda — o formato mais fácil de levar para C no nó.
    """
    w, h, xoff, yoff = bbx
    celula = [0] * altura

    # O BDF guarda cada linha alinhada ao byte, com o píxel 0 no bit mais alto.
    bits_linha = ((w + 7) // 8) * 8
    topo = ascendente - (yoff + h)

    for y, valor in enumerate(bitmap):
        linha = topo + y
        if not 0 <= linha < altura:
            continue

        for x in range(w):
            if valor & (1 << (bits_linha - 1 - x)):
                coluna = x + xoff
                if 0 <= coluna < largura:
                    celula[linha] |= 1 << (largura - 1 - coluna)

    return celula


def main():
    if len(sys.argv) != 2:
        sys.exit("uso: gerar_fonte.py <caminho do .bdf>")

    propriedades, glifos = ler_bdf(sys.argv[1])

    largura, altura = [int(v) for v in propriedades["FONTBOUNDINGBOX"][:2]]
    ascendente = int(propriedades["FONT_ASCENT"][0])

    em_falta = [c for c in CONJUNTO if c not in glifos]
    if em_falta:
        sys.exit(f"a fonte não tem {len(em_falta)} caracteres do Latin-1: {em_falta[:10]}")

    tabela = {
        "origem": "X11 misc-fixed 5x8.bdf (domínio público)",
        "copyright": " ".join(propriedades.get("COPYRIGHT", [])).strip('"'),
        "largura": largura,
        "altura": altura,
        # Um píxel de intervalo entre caracteres: 128 / 6 = 21 por fila (PDF).
        "avanco": largura + 1,
        "glifos": {
            str(codigo): para_celula(*glifos[codigo], largura, altura, ascendente)
            for codigo in CONJUNTO
        },
    }

    SAIDA.write_text(
        json.dumps(tabela, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    print(f"{len(tabela['glifos'])} glifos de {largura}×{altura} em {SAIDA.name}")


if __name__ == "__main__":
    main()
