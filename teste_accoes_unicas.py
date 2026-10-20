"""
T31 — uma só lista de acções (Fase 2.1).

Corre sem a BOX e sem rede: o `send_command` é substituído por um que só
regista o que lhe pediram e devolve o código que o teste escolhe. Nada chega
ao Spotify.

Prova cinco coisas:

  1. o enum que o Gemini vê É a lista do action_service, não uma cópia;
  2. cada acção tem a sua linha `- nome:` na descrição que o Gemini lê —
     sem ela o modelo engana-se (falha em campo de 2026-10-03);
  3. cada botão chama o método e o endpoint certos, os mesmos da voz;
  4. com o Spotify a devolver 204, o botão responde 200 com corpo e
     `success: true` — o defeito latente que a Fase 2.1 encontrou;
  5. com o Spotify a devolver 404, o botão responde 404, `success: false`,
     e a recusa fica no log `[ACCAO]`.

Correr com:  .\\.venv\\Scripts\\python.exe teste_accoes_unicas.py
"""

import io
import sys
from contextlib import redirect_stdout

from spotify_session import spotify
import action_service
import jarvis_live
import app as servidor


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


ESPERADO_POR_BOTAO = {
    "play": ("PUT", "/me/player/play"),
    "pause": ("PUT", "/me/player/pause"),
    "next": ("POST", "/me/player/next"),
    "previous": ("POST", "/me/player/previous"),
}


falhas = []


def verificar(condicao, descricao):
    print(f"  {'OK   ' if condicao else 'FALHA'} {descricao}")

    if not condicao:
        falhas.append(descricao)


def simular_spotify(codigo):
    """Troca o send_command por um que regista e devolve `codigo`."""
    pedidos = []

    def falso(metodo, endpoint, params=None, json_body=None):
        pedidos.append((metodo, endpoint))

        if 200 <= codigo < 300:
            return {"success": True}, codigo

        return {"success": False, "error": "simulado"}, codigo

    spotify.send_command = falso

    return pedidos


def carregar_botao(url):
    log = io.StringIO()

    with redirect_stdout(log):
        resposta = servidor.app.test_client().post(f"/api/{url}")

    return resposta, log.getvalue()


print()
print("T31 · uma só lista de acções")
print()

print("1. O enum do Gemini vem do action_service")
verificar(
    jarvis_live.SPOTIFY_ACTIONS is action_service.ACCOES,
    "SPOTIFY_ACTIONS é o próprio ACCOES",
)
enum = (
    jarvis_live.SPOTIFY_CONTROL_DECLARATION
    ["parameters"]["properties"]["action"]["enum"]
)
verificar(
    enum == action_service.ACCOES,
    f"o enum declarado ao Gemini é {enum}",
)

print()
print("2. Cada acção está explicada ao Gemini")
descricao = (
    jarvis_live.SPOTIFY_CONTROL_DECLARATION
    ["parameters"]["properties"]["action"]["description"]
)
for accao in action_service.ACCOES:
    verificar(f"- {accao}:" in descricao, f"descrição de `{accao}`")

print()
print("3. Cada botão faz o mesmo que a voz")
verificar(
    set(servidor.BOTOES) == set(ESPERADO_POR_BOTAO),
    f"os botões são {sorted(servidor.BOTOES)}",
)
for url, esperado in ESPERADO_POR_BOTAO.items():
    pedidos = simular_spotify(204)
    carregar_botao(url)

    verificar(
        pedidos == [esperado],
        f"/api/{url} -> {pedidos}",
    )

print()
print("4. Spotify devolve 204: o botão responde 200, com corpo")
for url in ESPERADO_POR_BOTAO:
    simular_spotify(204)
    resposta, _log = carregar_botao(url)
    corpo = resposta.get_json(silent=True)

    verificar(
        resposta.status_code == 200
        and corpo is not None
        and corpo.get("success") is True,
        f"/api/{url} -> HTTP {resposta.status_code}, corpo {corpo}",
    )

print()
print("5. Spotify devolve 404: o botão passa o 404 e deixa rasto")
for url in ESPERADO_POR_BOTAO:
    simular_spotify(404)
    resposta, log = carregar_botao(url)
    corpo = resposta.get_json(silent=True) or {}

    verificar(
        resposta.status_code == 404 and corpo.get("success") is False,
        f"/api/{url} -> HTTP {resposta.status_code}, "
        f"success={corpo.get('success')}",
    )
    verificar(
        "[ACCAO]" in log and "recusado com 404" in log,
        f"/api/{url} deixou no log: {log.strip()!r}",
    )

print()
print("6. A voz continua a devolver o mesmo")
simular_spotify(200)
resultado = action_service.execute_spotify_action("next")
verificar(
    resultado == {
        "ok": True,
        "action": "next",
        "message": "Passei para a próxima música.",
    },
    f"execute_spotify_action('next') -> {resultado}",
)

print()
if falhas:
    print(f"T31 FALHOU — {len(falhas)} verificação(ões):")
    for f in falhas:
        print(f"  - {f}")
    sys.exit(1)

print("T31 PASSA")
