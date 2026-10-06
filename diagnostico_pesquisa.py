"""
Porque e que o GET /search devolve 403.

Isto existe por causa de 2026-10-04. O registo de turnos ja dizia
`play_search -> FALHOU` com a mensagem, e o log do servidor ja dizia

    [ACCAO] Pesquisa falhou ('Let It Happen Tame Impala', track): spotify_403

o que fecha o problema dentro do `SpotifyClient.search()`. Mas o `search()`
deita fora o corpo da resposta e guarda so o codigo -- e e no corpo que o
Spotify explica o 403 por palavras.

Este script pede a mesma pesquisa de quatro maneiras diferentes e imprime o
corpo inteiro de cada uma. Uma so execucao chega para separar as hipoteses:

  - se as quatro derem 403 com a mesma mensagem, o problema e a aplicacao
    (Development Mode / quota), nao os parametros;
  - se a primeira der 403 e as outras 200, o problema e o `market=from_token`;
  - se der 403 so com `type=track`, o problema e o tipo.

Correr com:  python diagnostico_pesquisa.py

Nao escreve nada, nao toca no Spotify do utilizador: sao quatro GETs.
"""

import json
import sys

from spotify_session import spotify


# A consola do Windows e cp1252 e rebenta com acentos vindos do Spotify.
# Ja matou um turno a 2026-10-04 com uma transcricao em devanagari.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


CONSULTA = "Let It Happen Tame Impala"


VARIANTES = [
    (
        "1. exactamente como o codigo faz hoje",
        {
            "q": CONSULTA,
            "type": "track",
            "limit": 5,
            "market": "from_token",
        },
    ),
    (
        "2. sem market nenhum",
        {
            "q": CONSULTA,
            "type": "track",
            "limit": 5,
        },
    ),
    (
        "3. market=PT em vez de from_token",
        {
            "q": CONSULTA,
            "type": "track",
            "limit": 5,
            "market": "PT",
        },
    ),
    (
        "4. o minimo possivel: so q e type",
        {
            "q": "Tame Impala",
            "type": "artist",
        },
    ),
]


def linha():
    print("-" * 70)


def mostrar(titulo, params):
    linha()
    print(titulo)
    print(f"   params: {params}")

    resposta, erro = spotify._request("GET", "/search", params=params)

    if resposta is None:
        print(f"   NAO HOUVE RESPOSTA: {erro}")
        return

    print(f"   HTTP {resposta.status_code}")

    if resposta.status_code == 200:
        dados = resposta.json()
        bloco = dados.get(params["type"] + "s") or {}
        itens = [i for i in (bloco.get("items") or []) if i]

        print(f"   OK -- {len(itens)} resultado(s)")

        if itens:
            primeiro = itens[0]
            print(f"   primeiro: {primeiro.get('name')} / {primeiro.get('uri')}")

        return

    # O que interessa: o corpo do erro.
    print("   CORPO:")
    print("   " + (resposta.text or "<vazio>").replace("\n", "\n   "))


def contexto():
    """Quem e a conta, e um endpoint de controlo que sabemos funcionar."""
    linha()
    print("0. contexto da conta (GET /me)")

    resposta, erro = spotify._request("GET", "/me")

    if resposta is None:
        print(f"   NAO HOUVE RESPOSTA: {erro}")
        return

    print(f"   HTTP {resposta.status_code}")

    if resposta.status_code != 200:
        print("   CORPO:")
        print("   " + (resposta.text or "<vazio>").replace("\n", "\n   "))
        return

    info = resposta.json()

    # So estes tres campos. O /me devolve tambem email e nome, que nao
    # fazem falta nenhuma para este diagnostico.
    print(f"   produto: {info.get('product')}")
    print(f"   pais:    {info.get('country')}")
    print(f"   tipo:    {info.get('type')}")


def abrir_sessao():
    """
    Sem isto, tudo devolve `not_authenticated`.

    O `SpotifyClient` nasce vazio: o `.spotify_token.json` so guarda o
    refresh token, e e o `restore_session()` que o le e troca por um access
    token. Quem o chama e o `app.py` no arranque -- e este script nao e o
    app.py, e um processo novo.

    Foi exactamente isso que falhou na primeira execucao, a 2026-10-05, com
    as cinco chamadas a devolverem `not_authenticated`. O esquecimento foi
    meu, nao do servidor.
    """
    if spotify.restore_session():
        print("Sessao Spotify restaurada a partir do .spotify_token.json")
        return True

    print("NAO FOI POSSIVEL RESTAURAR A SESSAO SPOTIFY.")
    print("Nao ha refresh token valido em .spotify_token.json, ou a")
    print("renovacao foi recusada. Autoriza outra vez em")
    print("http://127.0.0.1:8888 e repete.")

    return False


def main():
    print()
    print("=" * 70)
    print("DIAGNOSTICO: GET /search devolve 403")
    print("=" * 70)
    print()

    if not abrir_sessao():
        return

    contexto()

    for titulo, params in VARIANTES:
        mostrar(titulo, params)

    linha()
    print()


if __name__ == "__main__":
    main()
