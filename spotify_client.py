import base64
import time
from urllib.parse import urlencode

import requests

from token_store import (
    save_refresh_token,
    load_refresh_token,
)


# A BOX mostra a capa a 120x120. Pedir mais do que isso é descarregar
# pixels para os deitar fora na conversão.
COVER_TARGET_PX = 120


def _pick_cover_url(images):
    """
    Escolhe a mais pequena das imagens que ainda chegue para 120x120.

    O código anterior usava images[0]. A documentação do Spotify sugere
    que o array vem da maior para a menor, mas não encontrei garantia
    firme disso — e apanhar a maior significava descarregar a versão de
    640x640 para depois a encolher. Escolher pela largura declarada em
    vez da posição torna isto independente da ordem.

    Cai para a maior disponível se nenhuma chegar aos 120 px, e para o
    primeiro URL se o Spotify não declarar larguras.
    """
    if not images:
        return ""

    with_width = [
        image
        for image in images
        if image.get("url") and image.get("width")
    ]

    if not with_width:
        return images[0].get("url", "")

    big_enough = [
        image
        for image in with_width
        if image["width"] >= COVER_TARGET_PX
    ]

    if big_enough:
        return min(
            big_enough,
            key=lambda image: image["width"],
        )["url"]

    return max(
        with_width,
        key=lambda image: image["width"],
    )["url"]


class SpotifyClient:

    API_BASE_URL = "https://api.spotify.com/v1"

    TOKEN_URL = (
        "https://accounts.spotify.com/api/token"
    )

    AUTHORIZE_URL = (
        "https://accounts.spotify.com/authorize"
    )


    def __init__(
        self,
        client_id,
        client_secret,
        redirect_uri,
        token_file,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file

        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = 0

        # Última resposta de get_status e o instante em que foi obtida.
        # Ver get_status(max_age_seconds=...).
        self._status_cache = None
        self._status_cache_at = 0.0

        # Uma ligação ao api.spotify.com reaproveitada entre pedidos.
        #
        # Medido a 2026-10-21 com o py-spy (docs/FASE-9-servidor.md): sem
        # isto, 98% da CPU do servidor em repouso — 30 a 55% de um núcleo —
        # ia para o ssl_wrap_socket. Cada requests.request() avulso abria
        # uma ligação nova, e cada ligação nova voltava a carregar o pacote
        # inteiro de certificados de confiança, além do TCP e do TLS.
        #
        # É a mesma correcção que o cover_service fez a 2026-09-23 para o
        # CDN das capas; aqui tinha ficado de fora.
        #
        # Partilhada pelas threads do Flask, da voz e da camada visual: o
        # pool de ligações do urllib3 é seguro entre threads, e estes
        # pedidos não usam cookies.
        self._session = requests.Session()


    # -----------------------------------------------------
    # AUTENTICAÇÃO BÁSICA
    # -----------------------------------------------------

    def _basic_auth(self):

        credentials = (
            f"{self.client_id}:"
            f"{self.client_secret}"
        )

        encoded = base64.b64encode(
            credentials.encode()
        ).decode()

        return encoded


    # -----------------------------------------------------
    # URL DE LOGIN
    # -----------------------------------------------------

    def authorization_url(
        self,
        state,
        scopes,
    ):

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
        }

        return (
            self.AUTHORIZE_URL
            + "?"
            + urlencode(params)
        )


    # -----------------------------------------------------
    # TROCAR AUTHORIZATION CODE POR TOKENS
    # -----------------------------------------------------

    def exchange_code(self, code):

        headers = {
            "Authorization":
                f"Basic {self._basic_auth()}",

            "Content-Type":
                "application/x-www-form-urlencoded",
        }

        data = {
            "grant_type":
                "authorization_code",

            "code":
                code,

            "redirect_uri":
                self.redirect_uri,
        }

        try:

            response = requests.post(
                self.TOKEN_URL,
                headers=headers,
                data=data,
                timeout=10,
            )

        except requests.RequestException as error:

            return False, str(error)


        if response.status_code != 200:

            return False, response.text


        token_data = response.json()

        self.access_token = (
            token_data["access_token"]
        )

        self.token_expires_at = (
            time.time()
            + token_data.get(
                "expires_in",
                3600
            )
            - 60
        )


        new_refresh_token = (
            token_data.get(
                "refresh_token"
            )
        )

        if new_refresh_token:

            self.refresh_token = (
                new_refresh_token
            )

            save_refresh_token(
                self.token_file,
                self.refresh_token,
            )


        return True, None


    # -----------------------------------------------------
    # RENOVAR ACCESS TOKEN
    # -----------------------------------------------------

    def refresh_access_token(self):

        if not self.refresh_token:
            return False


        headers = {
            "Authorization":
                f"Basic {self._basic_auth()}",

            "Content-Type":
                "application/x-www-form-urlencoded",
        }


        data = {
            "grant_type":
                "refresh_token",

            "refresh_token":
                self.refresh_token,
        }


        try:

            response = requests.post(
                self.TOKEN_URL,
                headers=headers,
                data=data,
                timeout=10,
            )

        except requests.RequestException as error:

            print(
                "Erro ao renovar token:",
                error
            )

            return False


        if response.status_code != 200:

            print(
                "Erro ao renovar token:",
                response.text
            )

            return False


        token_data = response.json()

        self.access_token = (
            token_data["access_token"]
        )


        self.token_expires_at = (
            time.time()
            + token_data.get(
                "expires_in",
                3600
            )
            - 60
        )


        new_refresh_token = (
            token_data.get(
                "refresh_token"
            )
        )


        if new_refresh_token:

            self.refresh_token = (
                new_refresh_token
            )

            save_refresh_token(
                self.token_file,
                self.refresh_token,
            )


        print(
            "Access token Spotify renovado."
        )

        return True


    # -----------------------------------------------------
    # RESTAURAR SESSÃO AO ARRANCAR
    # -----------------------------------------------------

    def restore_session(self):

        token = load_refresh_token(
            self.token_file
        )

        if not token:
            return False

        self.refresh_token = token

        return self.refresh_access_token()


    # -----------------------------------------------------
    # GARANTIR ACCESS TOKEN VÁLIDO
    # -----------------------------------------------------

    def get_valid_access_token(self):

        if not self.access_token:
            return None


        if (
            time.time()
            >= self.token_expires_at
        ):

            if not self.refresh_access_token():
                return None


        return self.access_token


    # -----------------------------------------------------
    # PEDIDO GENÉRICO À SPOTIFY API
    # -----------------------------------------------------

    def _request(
        self,
        method,
        endpoint,
        params=None,
        json_body=None,
    ):
        """
        Um pedido à API do Spotify, com renovação de token se for preciso.

        `params` vai na query string (ex.: volume_percent, q, type) e
        `json_body` no corpo (ex.: context_uri, uris). Até 2026-10-03 não
        existiam: o send_command só sabia fazer pedidos sem argumentos, e era
        esse o bloqueio real por trás do "ainda não implementado" do
        play_search e do set_volume.

        Os dois argumentos são repetidos na repetição pós-401. Esquecê-los aí
        daria um bug que só aparece quando o token expira a meio — raro, e
        por isso difícil de apanhar em testes.
        """
        token = (
            self.get_valid_access_token()
        )

        if not token:

            return None, "not_authenticated"


        headers = {
            "Authorization":
                f"Bearer {token}"
        }


        url = (
            self.API_BASE_URL
            + endpoint
        )


        try:

            response = self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_body,
                timeout=10,
            )

        except requests.RequestException as error:

            return None, str(error)


        # Token inesperadamente rejeitado.
        # Tentamos renová-lo uma vez.

        if response.status_code == 401:

            if not self.refresh_access_token():

                return (
                    None,
                    "authentication_failed"
                )


            headers = {
                "Authorization":
                    f"Bearer {self.access_token}"
            }


            try:

                response = self._session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=10,
                )

            except requests.RequestException as error:

                return None, str(error)


        return response, None


    # -----------------------------------------------------
    # PESQUISA
    # -----------------------------------------------------

    # O JSON da pesquisa vem agrupado por tipo, no plural.
    CHAVES_PESQUISA = {
        "track": "tracks",
        "artist": "artists",
        "album": "albums",
        "playlist": "playlists",
    }


    # Mercado usado na pesquisa, para os resultados serem reprodutíveis cá.
    #
    # Está escrito à mão em vez de `from_token`, e a razão foi medida a
    # 2026-10-05: com `market=from_token`, o `GET /search` responde
    #
    #     403 {"error": {"status": 403, "message": "Insufficient client scope"}}
    #
    # e com `market=PT`, ou sem market nenhum, responde 200. O `from_token`
    # manda o Spotify ir ver o país do utilizador, e isso exige o scope
    # `user-read-private`, que não pedimos. A prova está no mesmo
    # diagnóstico: o `GET /me` devolve 200 mas com `country` e `product` a
    # None — os campos que esse scope desbloqueia.
    #
    # Havia duas saídas: pedir o scope, o que obriga a reautenticar, ou
    # dizer o país. Enquanto a BOX viver nesta sala, dizer o país é mais
    # barato e não mexe em tokens. Se um dia o serviço sair de Portugal,
    # o caminho certo é o scope e ler o país do `/me`.
    MERCADO = "PT"


    def search(self, query, kind="track", limit=5):
        """
        Pesquisa no catálogo. Devolve `(itens, erro)`.

        Duas notas sobre as alterações de Fevereiro de 2026:

        1. O `limit` passou a ter um **máximo de 10** (era 50) e a omissão
           passou a 5 (era 20). Cinco chega de sobra para "põe X": só
           usamos o primeiro.

        2. O `GET /artists/{id}/top-tracks` foi **removido**. Era a maneira
           óbvia de tocar um artista. A alternativa é pesquisar o artista e
           entregar o URI dele como `context_uri` ao player — a documentação
           confirma que artistas são contextos válidos.

        O `market` existe para os resultados serem reprodutíveis cá. Sem ele,
        a pesquisa devolve conteúdo de todos os mercados e "põe X" pode
        escolher uma faixa que não toca em Portugal. Ver a nota em `MERCADO`
        para saber porque é "PT" à mão e não `from_token`.
        """
        if not query:
            return [], "pesquisa_vazia"

        if kind not in self.CHAVES_PESQUISA:
            return [], f"tipo_desconhecido:{kind}"

        response, error = self._request(
            "GET",
            "/search",
            params={
                "q": query,
                "type": kind,
                "limit": max(1, min(10, limit)),
                "market": self.MERCADO,
            },
        )

        if response is None:
            return [], error

        if response.status_code != 200:
            # O corpo vai junto desde 2026-10-05.
            #
            # Até esse dia isto devolvia só `spotify_403`, e o log do
            # servidor dizia "Pesquisa falhou: spotify_403" — verdade, e
            # inútil. Foi preciso um script à parte para descobrir que o
            # corpo dizia "Insufficient client scope", que é a resposta
            # inteira.
            #
            # É a terceira vez nesta fase que um instrumento guarda o
            # código e deita fora a explicação. Aqui não volta a acontecer.
            corpo = (response.text or "").strip().replace("\n", " ")

            return [], f"spotify_{response.status_code}: {corpo[:200]}"

        try:
            dados = response.json()

        except ValueError:
            return [], "resposta_ilegivel"

        bloco = dados.get(self.CHAVES_PESQUISA[kind]) or {}

        # O Spotify devolve entradas a null na pesquisa de playlists.
        # Filtrar aqui evita um AttributeError lá à frente.
        itens = [
            item
            for item in (bloco.get("items") or [])
            if item
        ]

        return itens, None


    # -----------------------------------------------------
    # ESTADO ATUAL
    # -----------------------------------------------------

    def get_status(self, max_age_seconds=0.0):
        """
        Estado da reprodução.

        Medido em 2026-09-23: cada chamada custa entre 0,6 e 2,0 s, com
        mediana ~1,1 s — é uma ida à API do Spotify pela internet. Esse
        tempo domina três caminhos: o polling da BOX, o download da capa
        (que chamava isto só para saber o URL da imagem) e a resposta de
        voz a "o que está a tocar?".

        max_age_seconds diz quanta desactualização o chamador tolera:

            0   sempre fresco (polling da BOX)
            3   o suficiente para a capa reaproveitar o polling anterior
            8+  perguntas de voz, onde um nome de faixa com alguns
                segundos é indistinguível do actual

        Quem precisa de dados frescos continua a pagar o preço; quem não
        precisa deixa de o pagar.
        """
        if (
            max_age_seconds > 0.0
            and self._status_cache is not None
            and (time.time() - self._status_cache_at) <= max_age_seconds
        ):
            return self._status_cache

        result = self._fetch_status()

        self._status_cache = result
        self._status_cache_at = time.time()

        return result


    def _fetch_status(self):

        # Fase 8.d: quanto demorou a ida ao Spotify. O progress_ms refere-se
        # a um instante a meio dela, não ao fim, que é quando o
        # server_time_ms é carimbado; o visual_service precisa das duas
        # coisas para pôr a letra no sítio. Medir isto não custa nada.
        pedido_inicio = time.time()

        response, error = self._request(
            "GET",
            "/me/player",
        )

        pedido_ms = int((time.time() - pedido_inicio) * 1000)


        if response is None:

            if error == "not_authenticated":

                return {
                    "authenticated": False
                }, 401


            return {
                "error":
                    "spotify_unreachable",

                "details":
                    error,
            }, 503


        if response.status_code == 204:

            return {
                "authenticated": True,
                "active": False,
                "playing": False,
            }, 200


        if response.status_code != 200:

            return {
                "error":
                    "spotify_error",

                "status":
                    response.status_code,

                "details":
                    response.text,
            }, response.status_code


        info = response.json()

        item = info.get("item")


        if not item:

            return {
                "authenticated": True,
                "active": False,
                "playing": False,
            }, 200


        artists = ", ".join(
            artist["name"]
            for artist
            in item.get(
                "artists",
                []
            )
        )


        album_info = (
            item.get(
                "album",
                {}
            )
        )


        images = (
            album_info.get(
                "images",
                []
            )
        )


        cover = _pick_cover_url(images)


        device = (
            info.get("device")
            or {}
        )


        return {

            "authenticated": True,
            "active": True,

            "track":
                item.get(
                    "name",
                    ""
                ),

            "artist":
                artists,

            "album":
                album_info.get(
                    "name",
                    ""
                ),

            "playing":
                info.get(
                    "is_playing",
                    False
                ),

            "progress_ms":
                info.get(
                    "progress_ms"
                )
                or 0,

            "duration_ms":
                item.get(
                    "duration_ms"
                )
                or 0,

            "device":
                device.get(
                    "name",
                    ""
                ),

            "volume_percent":
                device.get(
                    "volume_percent"
                ),

            "cover":
                cover,

            "spotify_timestamp":
                info.get(
                    "timestamp"
                ),

            "server_time_ms":
                int(
                    time.time()
                    * 1000
                ),

            # Fase 8.d — ver o _fetch_status. O track_id é a chave da
            # cache das letras.
            "pedido_ms":
                pedido_ms,

            "track_id":
                item.get(
                    "uri"
                ),

        }, 200


    # -----------------------------------------------------
    # COMANDOS
    # -----------------------------------------------------

    def send_command(
        self,
        method,
        endpoint,
        params=None,
        json_body=None,
    ):

        response, error = self._request(
            method,
            endpoint,
            params=params,
            json_body=json_body,
        )

        # Qualquer comando altera o estado da reprodução, por isso o que
        # está em cache deixa de valer.
        #
        # Sem isto: "Jarvis, passa esta" seguido de "o que está a tocar?"
        # podia responder com o nome da faixa ANTERIOR, porque a cache
        # ainda tinha o estado de antes do salto. Um erro que a cache
        # introduziu e que só aparece na sequência certa de comandos.
        self._status_cache = None
        self._status_cache_at = 0.0


        if response is None:

            return {
                "success": False,
                "error": error,
            }, 401


        # Qualquer 2xx é sucesso.
        #
        # Até 2026-10-05 só o 204 contava, e isso produziu a frase mais
        # absurda que este projecto já disse em voz alta:
        #
        #     tu:     Muda de música, não gosto desta.
        #     tool:   spotify_control({'action': 'next'}) -> FALHOU
        #             O Spotify respondeu com erro 200.
        #
        # O 204 é o que a documentação promete nos endpoints do player, e
        # durante meses foi o que veio. Nesse dia veio 200, e o código
        # tratou a resposta de sucesso mais vulgar que existe como uma
        # falha — o Jarvis pediu desculpa por uma coisa que tinha feito.
        #
        # Isto explica também os `next -> FALHOU` de 10-03 e o
        # `pause -> FALHOU` de 09-30, que ficaram sem causa conhecida.
        #
        # Não vale a pena adivinhar quando é 200 e quando é 204: a regra
        # de HTTP é 2xx, e é essa que fica.
        if 200 <= response.status_code < 300:

            return {
                "success": True
            }, response.status_code


        return {
            "success": False,

            "spotify_status":
                response.status_code,

            "details":
                response.text,

        }, response.status_code