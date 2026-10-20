"""
Executa as acções Spotify pedidas pelo Gemini.

Até 2026-10-01 este módulo falava com o Spotify **através do próprio Flask**:
fazia `requests.post("http://127.0.0.1:8888/api/pause")`, o Flask recebia, e o
Flask chamava o SpotifyClient. Um salto de rede para dentro do mesmo processo.

Três razões para o tirar:

  - **Acoplamento.** O servidor de voz (porta 8765) ficava dependente de o
    Flask (8888) estar de pé. É a mesma família do bug B5, em que o Flask
    sobrevivia à morte do servidor de voz e o sistema parecia vivo sem o ser.

  - **Parâmetros.** As acções novas desta fase (`play_search`, `set_volume`)
    levam argumentos. Passá-los pelo salto obrigava a inventar endpoints REST
    internos que só o próprio processo chamaria — trabalho sem retorno.

  - **Latência.** Um pedido HTTP, com ligação, por cada comando de voz.

Agora chama o `SpotifyClient` directamente. A instância é partilhada com o
Flask através do `spotify_session`, o que importa para a cache funcionar — ver
o cabeçalho desse módulo.
"""

from spotify_session import spotify


# Quanto desactualizado pode estar o estado devolvido a uma pergunta de voz.
#
# Esta chamada acontece com o utilizador à espera, e uma ida fresca à API do
# Spotify custa entre 1 e 5 s. Para dizer que música está a tocar, uma resposta
# com alguns segundos é indistinguível da actual.
#
# 15 s e não 8 porque o polling da BOX fica suspenso durante a voz: quando este
# pedido chega, o último polling já tem a idade do turno inteiro.
#
# Seguro porque o `send_command` invalida a cache — depois de um "passa esta" a
# resposta seguinte é sempre fresca.
ESTADO_MAX_IDADE_SEGUNDOS = 15


# Cada acção simples é (método HTTP, endpoint da API, o que dizer se correr bem).
#
# Esta tabela é agora a única lista de acções de transporte do projecto. As
# outras três — intent_service, local_intent_service e o ramo de texto do
# /api/voice — foram apagadas em 2026-09-30 por serem inalcançáveis.
#
# > **2026-10-20 · Fase 2.1.** Não era a única: os botões (`/api/play` e
# > companhia, no `app.py`) tinham o método e o endpoint escritos outra vez, e
# > o `jarvis_live.py` tinha a sua própria lista para o enum do Gemini. Agora
# > os botões passam por `executar_para_botao` e o enum vem de `ACCOES`. Ver
# > `docs/FASE-2.1-desenho.md`.
COMANDOS_SIMPLES = {
    "pause": ("PUT", "/me/player/pause", "Reprodução pausada."),
    "resume": ("PUT", "/me/player/play", "Reprodução retomada."),
    "next": ("POST", "/me/player/next", "Passei para a próxima música."),
    "previous": ("POST", "/me/player/previous", "Voltei à música anterior."),
}


def _erro(accao, mensagem):
    return {
        "ok": False,
        "action": accao,
        "message": mensagem,
    }


def _registar_recusa(accao, resposta, estado):
    """
    Escreve no log o que o Spotify respondeu de facto.

    A `message` de um `_erro` vai para o Gemini e acaba dita em voz alta, por
    isso tem de ser uma frase; o corpo da resposta não cabe lá. Mas é o corpo
    que explica a recusa, e sem ele ficam no registo linhas como
    `next -> FALHOU` que não se conseguem investigar dias depois — foi o que
    aconteceu a 09-30 e a 10-03.

    Frase para o utilizador, corpo para o log. Os dois.
    """
    detalhe = (
        resposta.get("details")
        or resposta.get("error")
        or ""
    )

    print(
        f"[ACCAO] {accao} recusado com {estado}: "
        f"{str(detalhe).strip()[:300]}"
    )


def _executar_comando_simples(accao):
    """
    Devolve (resultado, código HTTP do Spotify).

    A voz só quer o resultado. O código existe para os botões, que o passam à
    BOX quando o Spotify recusa — ver `executar_para_botao`.
    """
    metodo, endpoint, mensagem_ok = COMANDOS_SIMPLES[accao]

    resposta, estado = spotify.send_command(metodo, endpoint)

    if resposta.get("success"):
        return {
            "ok": True,
            "action": accao,
            "message": mensagem_ok,
        }, estado

    _registar_recusa(accao, resposta, estado)

    # O Spotify recusou. Os casos que acontecem na prática merecem uma
    # resposta que o Jarvis possa dizer em voz alta; o resto fica genérico
    # mas com o código, para o registo de turnos servir de alguma coisa.
    #
    # O 404 é o mais provável: é o que o Spotify devolve quando não há
    # nenhum dispositivo activo. Decisão D7 — dizer e parar, sem tentar
    # adivinhar um dispositivo e pôr música a tocar noutro sítio da casa.
    if estado == 404:
        return _erro(
            accao,
            "Não há nenhum dispositivo Spotify activo. "
            "Abre o Spotify no telemóvel.",
        ), estado

    if estado == 403:
        return _erro(
            accao,
            "O Spotify recusou esse comando neste dispositivo.",
        ), estado

    if estado == 401:
        return _erro(
            accao,
            "A sessão Spotify expirou e não foi possível renová-la.",
        ), estado

    return _erro(
        accao,
        f"O Spotify respondeu com erro {estado}.",
    ), estado


def _definir_volume(accao, volume):
    """
    PUT /me/player/volume?volume_percent=N

    O Spotify aceita 0–100. Limitamos antes de enviar em vez de deixar a API
    recusar: o modelo pode dizer 150 se o utilizador disser "põe no máximo",
    e 100 é o que ele quer dizer.
    """
    try:
        pedido = int(volume)

    except (TypeError, ValueError):
        return _erro(
            accao,
            "Não percebi para que valor queres o volume.",
        )

    valor = max(0, min(100, pedido))

    resposta, estado = spotify.send_command(
        "PUT",
        "/me/player/volume",
        params={"volume_percent": valor},
    )

    if resposta.get("success"):
        if pedido > 100:
            mensagem = "Volume no máximo."

        elif pedido < 0:
            mensagem = "Volume no mínimo."

        else:
            mensagem = f"Volume a {valor}."

        return {
            "ok": True,
            "action": accao,
            "volume": valor,
            "message": mensagem,
        }

    _registar_recusa(accao, resposta, estado)

    if estado == 404:
        return _erro(
            accao,
            "Não há nenhum dispositivo Spotify activo. "
            "Abre o Spotify no telemóvel.",
        )

    # Nem todos os dispositivos Spotify Connect aceitam controlo de volume
    # — vários altifalantes e televisões recusam com 403. Vale a pena dizer
    # porquê, senão parece que o comando não foi percebido.
    if estado == 403:
        return _erro(
            accao,
            "Este dispositivo não deixa mudar o volume daqui. "
            "Tens de o mudar no próprio aparelho.",
        )

    return _erro(
        accao,
        f"Não consegui mudar o volume: erro {estado}.",
    )


def _artistas(item):
    """Nomes dos artistas de uma faixa ou álbum, juntos por vírgula."""
    nomes = [
        a.get("name", "")
        for a in (item.get("artists") or [])
        if a and a.get("name")
    ]

    return ", ".join(nomes)


def _descrever(item, tipo):
    """O que o Jarvis diz depois de pôr alguma coisa a tocar."""
    nome = item.get("name", "")

    if tipo == "track":
        artista = _artistas(item)
        return f"A tocar {nome}, de {artista}." if artista else f"A tocar {nome}."

    if tipo == "artist":
        return f"A tocar {nome}."

    if tipo == "album":
        artista = _artistas(item)
        return (
            f"A tocar o álbum {nome}, de {artista}."
            if artista
            else f"A tocar o álbum {nome}."
        )

    return f"A tocar a playlist {nome}."


def _tocar_pesquisa(accao, query, tipo):
    """
    Pesquisa e põe a tocar. É o `"põe Arctic Monkeys"`.

    O `tipo` vem do Gemini (decisão D3). Ele sabe que "Tame Impala" é um
    artista e que "Do I Wanna Know" é uma faixa; uma regra fixa deste lado
    errava sempre num dos dois casos.

    Faixas tocam-se por `uris`; artistas, álbuns e playlists por
    `context_uri` — que é a única via desde que o `top-tracks` foi removido
    em Fevereiro de 2026.
    """
    if not query:
        return _erro(accao, "Não percebi o que queres ouvir.")

    if tipo not in ("track", "artist", "album", "playlist"):
        # O modelo não preencheu ou inventou. A faixa é o palpite menos mau.
        tipo = "track"

    itens, erro = spotify.search(query, kind=tipo)

    if erro:
        print(f"[ACCAO] Pesquisa falhou ({query!r}, {tipo}): {erro}")

        return _erro(
            accao,
            "Não consegui pesquisar no Spotify agora.",
        )

    if not itens:
        return {
            "ok": True,
            "action": accao,
            "query": query,
            "message": f"Não encontrei nada com o nome {query}.",
        }

    escolhido = itens[0]
    uri = escolhido.get("uri")

    if not uri:
        return _erro(accao, f"Não consegui pôr {query} a tocar.")

    corpo = (
        {"uris": [uri]}
        if tipo == "track"
        else {"context_uri": uri}
    )

    resposta, estado = spotify.send_command(
        "PUT",
        "/me/player/play",
        json_body=corpo,
    )

    if resposta.get("success"):
        return {
            "ok": True,
            "action": accao,
            "query": query,
            "tipo": tipo,
            "uri": uri,

            # O que o Spotify escolheu, em campos próprios.
            #
            # Acrescentado a 2026-10-14 para a Fase 4.a. O nome já existia
            # dentro da `message` ("A tocar Çanakkale, de CVRTOON"), mas só
            # em prosa — e a Fase 4.b vai precisar de comparar o que foi
            # pedido com o que foi tocado, em centenas de turnos. Tirar isso
            # de uma frase, meses depois, é frágil e irrepetível.
            #
            # Não se guarda aqui nenhuma distância nem veredicto. A análise
            # de 14-10 mostrou que nenhuma das métricas candidatas separava
            # os casos reais dos falsos positivos; registar um número
            # calculado hoje seria congelar uma escolha que ainda não há
            # dados para fazer. Guarda-se a matéria-prima.
            "escolhido": {
                "nome": escolhido.get("name"),
                "artista": _artistas(escolhido),
                "uri": uri,
            },

            "message": _descrever(escolhido, tipo),
        }

    _registar_recusa(accao, resposta, estado)

    if estado == 404:
        return _erro(
            accao,
            "Não há nenhum dispositivo Spotify activo. "
            "Abre o Spotify no telemóvel.",
        )

    if estado == 403:
        return _erro(
            accao,
            "O Spotify não deixou começar a reprodução. "
            "Confirma que tens Premium e um dispositivo disponível.",
        )

    return _erro(
        accao,
        f"Não consegui pôr {query} a tocar: erro {estado}.",
    )


def _estado_actual(accao):
    estado, codigo = spotify.get_status(
        max_age_seconds=ESTADO_MAX_IDADE_SEGUNDOS
    )

    if codigo != 200:
        return _erro(
            accao,
            "Não consegui saber o que está a tocar.",
        )

    if not estado.get("active"):
        return {
            "ok": True,
            "action": accao,
            "message": "Não há nenhuma música a tocar.",
        }

    faixa = estado.get("track", "")
    artista = estado.get("artist", "")

    return {
        "ok": True,
        "action": accao,
        "track": faixa,
        "artist": artista,
        "message": f"Está a tocar {faixa}, de {artista}.",
    }


# As acções que não cabem no COMANDOS_SIMPLES, porque levam argumentos ou não
# são um comando ao player.
_ACCOES_COMPOSTAS = {
    "current_track": lambda accao, volume, query, tipo: _estado_actual(accao),
    "set_volume": lambda accao, volume, query, tipo: _definir_volume(
        accao, volume
    ),
    "play_search": lambda accao, volume, query, tipo: _tocar_pesquisa(
        accao, query, tipo
    ),
}


# Todas as acções, pela ordem do enum que o Gemini vê.
#
# Tirada das duas tabelas de despacho, e não escrita à parte: uma acção nova
# só existe se alguém a souber executar, e o `jarvis_live` lê daqui (Fase 2.1).
ACCOES = list(COMANDOS_SIMPLES) + list(_ACCOES_COMPOSTAS)


def execute_spotify_action(action, volume=None, query=None, tipo=None):
    """
    Ponto de entrada único, chamado pela ferramenta `spotify_control`.

    Nunca levanta excepção: uma falha aqui derrubava a conversa inteira, e o
    Gemini sabe explicar ao utilizador um resultado com ok=False.
    """
    try:
        if action in COMANDOS_SIMPLES:
            resultado, _estado = _executar_comando_simples(action)
            return resultado

        if action in _ACCOES_COMPOSTAS:
            return _ACCOES_COMPOSTAS[action](action, volume, query, tipo)

        return _erro(action, "Comando não reconhecido.")

    except Exception as erro:
        print(f"[ACCAO] Falha inesperada em {action}: {erro}")

        return _erro(
            action,
            "Não consegui falar com o Spotify.",
        )


def executar_para_botao(accao):
    """
    Ponto de entrada dos botões — os da BOX e os da página web.

    Devolve (corpo, código HTTP). Os dois clientes lêem coisas diferentes, e
    é por isso que isto não é só o `execute_spotify_action`:

      - a BOX só olha para o código: 2xx é sucesso, o corpo é ignorado;
      - a página web só olha para o `success` do corpo.

    Sucesso é sempre 200, nunca o código do Spotify. Com 204 a Flask manda a
    resposta sem corpo, e o `response.json()` da página rebentava depois de o
    comando ter corrido (medido a 2026-10-20, Flask 3.1.3).

    Uma recusa passa o código do Spotify tal e qual: o `HTTP 404` no log da
    BOX é a única pista que fica do lado do firmware.
    """
    try:
        resultado, estado = _executar_comando_simples(accao)

    except Exception as erro:
        print(f"[ACCAO] Falha inesperada em {accao} (botão): {erro}")

        resultado = _erro(accao, "Não consegui falar com o Spotify.")
        estado = 500

    corpo = {"success": resultado["ok"], **resultado}

    return corpo, (200 if resultado["ok"] else estado)
