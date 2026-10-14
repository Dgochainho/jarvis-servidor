"""
T25 — pesquisa sem resultados.

PORQUE E QUE ISTO NAO E UM TESTE DE VOZ

O enunciado original dizia: dizer "Jarvis, poe zxqwverty" e esperar que o
Jarvis responda que nao encontrou. Nao funciona por voz, porque "zxqwverty"
dito em voz alta chega ao servidor como outra coisa qualquer.

MEDIDO A 2026-10-07: tambem nao funciona por escrito.

Quatro strings de consoantes aleatorias, entre elas 'qzxjvwkprthgnbm' e
'zzzqqqxxxvvvwww', devolveram todas pelo menos um resultado. A pesquisa do
Spotify e difusa e o catalogo e enorme: ha sempre alguma coisa que se
parece o suficiente.

Conclusao: **o ramo "nao encontrei nada" pode ser inalcancavel atraves da
API real.** Isso nao o torna irrelevante -- se um dia for alcancado, tem de
se comportar bem -- mas torna-o impossivel de exercitar por observacao.

Por isso este script tem duas fases:

  FASE 1 — tenta a serio, com strings mais longas e varios tipos. Se
           alguma devolver zero, corre o caminho real e temos uma prova de
           campo.

  FASE 2 — se nenhuma devolver zero, substitui o `search` por um que
           devolve lista vazia e corre o MESMO `execute_spotify_action`.
           Deixa de ser prova de que o Spotify alguma vez devolve vazio, e
           passa a ser prova de que o NOSSO codigo trata o vazio como deve.
           E essa a parte que nos pertence.

O resultado diz sempre qual das duas aconteceu. Um "PASSA (simulado)" nao
e a mesma coisa que um "PASSA (em campo)", e o guiao nao deve fingir que e.

SEGURANCA: as sondagens nao tocam em nada. A chamada final so chega ao
player se houver resultados -- e o objectivo e nao haver.

Correr com:  .\\.venv\\Scripts\\python.exe teste_sem_resultados.py
"""

import sys

from spotify_session import spotify
from action_service import execute_spotify_action


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# Mais longas do que as de 2026-10-07, que falharam todas. A ideia e dar ao
# motor difuso cada vez menos a que se agarrar.
CANDIDATAS = [
    ("qzxjvwkprthgnbmzxjvwkprthgnbmqzxjv", "track"),
    ("xxqqzzjjvvwwkkpprrtthhggnnbbmmxxqq", "track"),
    ("zqxjvwkprthgnbmzqxjvwkprthgnbmzqxjvwkprthgnbm", "track"),
    ("qzxjvwkprthgnbmzxjvwkprthgnbmqzxjv", "album"),
    ("qzxjvwkprthgnbmzxjvwkprthgnbmqzxjv", "artist"),
    ("qzxjvwkprthgnbmzxjvwkprthgnbmqzxjv", "playlist"),
]


def avaliar(resultado):
    """
    O criterio, igual nas duas fases.

    Nao encontrar **nao e uma falha do sistema**: o Jarvis tem de o dizer
    com naturalidade e a conversa tem de continuar. Por isso ok=True, e nao
    ok=False -- se fosse erro, ele pedia desculpa de uma avaria que nao ha.
    """
    print()
    for chave, valor in resultado.items():
        print(f"  {chave}: {valor}")
    print()

    mensagem = (resultado.get("message") or "").lower()

    if resultado.get("ok") is not True:
        print("FALHA: devolveu ok=False.")
        print("Nao encontrar nao e um erro do sistema.")
        return False

    if "não encontrei" not in mensagem:
        print("FALHA: ok=True mas a mensagem nao diz que nao encontrou.")
        print(f"Mensagem: {resultado.get('message')!r}")
        return False

    print("Criterio cumprido: ok=True e mensagem dizivel em voz alta.")
    return True


def fase_1():
    """Procura uma string que o Spotify realmente recuse."""
    print("-" * 70)
    print("FASE 1 - sondagem na API real")
    print("-" * 70)

    for texto, tipo in CANDIDATAS:
        itens, erro = spotify.search(texto, kind=tipo)

        if erro:
            print(f"  [{tipo}] a pesquisa falhou -- {erro}")
            print("  (isso e um problema do T28, nao deste teste)")
            return None

        print(f"  [{tipo}] {len(itens)} resultado(s)  {texto[:28]}...")

        if not itens:
            return texto, tipo

    return None


def fase_2():
    """
    Forca o vazio e corre o caminho real.

    Substitui so o `search` da instancia partilhada. Tudo o resto --
    `execute_spotify_action`, `_tocar_pesquisa`, as mensagens -- e o codigo
    verdadeiro, o mesmo que a ferramenta do Gemini chama.
    """
    print()
    print("-" * 70)
    print("FASE 2 - vazio simulado, codigo real")
    print("-" * 70)
    print("O Spotify nao devolveu vazio para nenhuma candidata.")
    print("A substituir `spotify.search` por um que devolve lista vazia,")
    print("para exercitar o ramo que nos pertence.")

    original = spotify.search

    try:
        spotify.search = lambda *args, **kwargs: ([], None)

        return execute_spotify_action(
            "play_search",
            query="uma coisa que nao existe",
            tipo="track",
        )

    finally:
        spotify.search = original


def main():
    print()
    print("=" * 70)
    print("T25 - PESQUISA SEM RESULTADOS")
    print("=" * 70)
    print()

    if not spotify.restore_session():
        print("NAO FOI POSSIVEL RESTAURAR A SESSAO SPOTIFY.")
        print("Autoriza em http://127.0.0.1:8888 e repete.")
        return

    print("Sessao Spotify restaurada.")
    print()

    achado = fase_1()

    if achado is not None:
        texto, tipo = achado

        print()
        print(f"Encontrada: {texto!r} ({tipo})")
        print("A correr o caminho real.")

        resultado = execute_spotify_action(
            "play_search",
            query=texto,
            tipo=tipo,
        )

        print()
        print("-" * 70)

        if avaliar(resultado):
            print()
            print(">>> PASSA (em campo).")
            print("O Spotify devolveu zero resultados e o codigo tratou-o bem.")

        return

    resultado = fase_2()

    print()
    print("-" * 70)

    if avaliar(resultado):
        print()
        print(">>> PASSA (simulado).")
        print()
        print("O que isto prova: o nosso codigo trata o vazio como deve.")
        print("O que NAO prova: que a API real alguma vez devolva vazio.")
        print("Registar no TESTES.md como 'OK (simulado)', nao como 'OK'.")


if __name__ == "__main__":
    main()
