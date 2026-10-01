import os
import secrets
import wave
import time
import math
import struct
from pathlib import Path

from flask import (
    Flask,
    request,
    redirect,
    jsonify,
    render_template,
    Response,
    stream_with_context,
)

from spotify_client import SpotifyClient
from cover_service import CoverService
from mdns_service import MdnsService
from gemini_live_service import stream_gemini_live_reply
from live_voice_ws_server import LiveVoiceWebSocketServer

from dotenv import load_dotenv




# ---------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------

load_dotenv()


CLIENT_ID = os.getenv(
    "SPOTIFY_CLIENT_ID"
)

CLIENT_SECRET = os.getenv(
    "SPOTIFY_CLIENT_SECRET"
)

REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI"
)


BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)


TOKEN_FILE = (
    BASE_DIR
    / ".spotify_token.json"
)


SCOPES = [

    "user-read-currently-playing",

    "user-read-playback-state",

    "user-modify-playback-state",
]


app = Flask(__name__)

# (Havia aqui uma segunda definição de BASE_DIR, que só existia para
# construir o caminho do command.wav. O WAV desapareceu com o ramo de
# transcrição; o BASE_DIR verdadeiro está mais acima, junto ao
# TOKEN_FILE.)


spotify = SpotifyClient(

    client_id=CLIENT_ID,

    client_secret=CLIENT_SECRET,

    redirect_uri=REDIRECT_URI,

    token_file=TOKEN_FILE,
)

cover_service = CoverService()

mdns_service = MdnsService(
    hostname="spotify-service",
    port=8888,
)

voice_ws_server = LiveVoiceWebSocketServer(
    host="0.0.0.0",
    port=8765,
)

state_value = None

def make_audio_ack():
    sample_rate = 16000
    amplitude = 5000

    pcm = bytearray()

    def add_tone(freq, duration_ms):
        samples = int(
            sample_rate * duration_ms / 1000
        )

        for n in range(samples):
            value = int(
                amplitude *
                math.sin(
                    2.0 *
                    math.pi *
                    freq *
                    n /
                    sample_rate
                )
            )

            pcm.extend(
                struct.pack("<h", value)
            )

    def add_silence(duration_ms):
        samples = int(
            sample_rate * duration_ms / 1000
        )

        pcm.extend(
            b"\x00\x00" * samples
        )

    # Dois tons diferentes
    add_tone(880, 140)
    add_silence(80)
    add_tone(1200, 140)

    # Silêncio final para evitar que o microfone
    # seja rearmado enquanto o speaker ainda termina.
    add_silence(180)

    return bytes(pcm)

def load_jarvis_reply():
    wav_path = "jarvis_reply.wav"

    with wave.open(wav_path, "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()

        if channels != 1:
            raise RuntimeError(
                f"jarvis_reply.wav tem {channels} canais; esperado 1"
            )

        if sample_width != 2:
            raise RuntimeError(
                f"jarvis_reply.wav usa {sample_width * 8} bits; esperado 16"
            )

        if sample_rate != 16000:
            raise RuntimeError(
                f"jarvis_reply.wav usa {sample_rate} Hz; esperado 16000"
            )

        return wav.readframes(
            wav.getnframes()
        )


# ---------------------------------------------------------
# INTERFACE
# ---------------------------------------------------------

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ---------------------------------------------------------
# LOGIN
# ---------------------------------------------------------

@app.route("/login")
def login():

    global state_value

    state_value = (
        secrets.token_urlsafe(16)
    )


    url = spotify.authorization_url(
        state_value,
        SCOPES,
    )


    return redirect(url)


# ---------------------------------------------------------
# CALLBACK OAUTH
# ---------------------------------------------------------

@app.route("/callback")
def callback():

    global state_value


    error = request.args.get(
        "error"
    )

    code = request.args.get(
        "code"
    )

    received_state = (
        request.args.get(
            "state"
        )
    )


    if error:

        return (
            "Spotify recusou "
            f"a autorização: {error}"
        )


    if (
        not state_value
        or received_state
        != state_value
    ):

        return (
            "Erro: state inválido.",
            400
        )


    success, error_message = (
        spotify.exchange_code(
            code
        )
    )


    if not success:

        return (
            "Erro ao obter token: "
            f"{error_message}",
            500
        )


    state_value = None


    print()
    print("==============================")
    print("SPOTIFY AUTENTICADO")
    print("==============================")
    print()


    return redirect("/")

# ---------------------------------------------------------
# STATUS
# ---------------------------------------------------------

@app.route("/api/status")
def api_status():

    # Quanto deste pedido é trabalho nosso (round-trip à API do Spotify) e
    # quanto é rede até à BOX? Sem separar os dois não dá para saber se uma
    # resposta lenta é Wi-Fi ou é o Spotify a demorar.
    started = time.perf_counter()

    # Quem chama pode declarar que tolera um estado ligeiramente antigo.
    # A BOX não passa nada e recebe sempre dados frescos; o action_service
    # usa isto nas respostas de voz, onde um nome de faixa com alguns
    # segundos é indistinguível do actual.
    try:
        max_age = float(
            request.args.get("max_age", 0.0)
        )
    except (TypeError, ValueError):
        max_age = 0.0

    data, status_code = (
        spotify.get_status(
            max_age_seconds=max_age
        )
    )

    elapsed = time.perf_counter() - started

    if elapsed > 0.5:
        print(
            f"[PERF] /api/status: {elapsed:.2f} s do lado do servidor "
            f"(chamada a Spotify)"
        )

    return (
        jsonify(data),
        status_code
    )

# ---------------------------------------------------------
# CAPA
# ---------------------------------------------------------

@app.route("/api/cover.rgb565")
def api_cover():

    # A BOX cronometra este pedido de ponta a ponta e usa-o como teste de
    # débito. Mas o tempo dela inclui trabalho nosso que nada tem a ver com
    # Wi-Fi: uma chamada à API do Spotify, mais o download da imagem ao CDN
    # e a conversão para RGB565 sempre que a capa é nova — e é sempre nova,
    # senão a BOX não a pediria.
    #
    # Sem esta medição, o número da BOX não distingue rede lenta de
    # servidor lento.
    request_started = time.perf_counter()

    # A BOX pede a capa poucas décimas de segundo depois de receber o
    # polling que lhe deu este mesmo URL. Repetir a chamada ao Spotify
    # custava 1,1 a 1,5 s para obter uma resposta que acabámos de ter.
    status, status_code = (
        spotify.get_status(
            max_age_seconds=3.0
        )
    )

    spotify_seconds = time.perf_counter() - request_started

    if status_code != 200:

        return (
            "Não foi possível obter "
            "estado Spotify.",
            status_code
        )


    if not status.get("active"):

        return (
            "Sem reprodução ativa.",
            404
        )


    cover_url = status.get(
        "cover"
    )


    if not cover_url:

        return (
            "Faixa sem capa.",
            404
        )


    try:

        convert_started = time.perf_counter()

        image_data = (
            cover_service.get_rgb565(
                cover_url,
                width=120,
                height=120,
            )
        )

        convert_seconds = (
            time.perf_counter() - convert_started
        )

        total_seconds = (
            time.perf_counter() - request_started
        )

        print()
        print("[PERF] /api/cover.rgb565")
        print(f"[PERF]   Estado Spotify:     {spotify_seconds:.2f} s")
        print(f"[PERF]   CDN + conversao:    {convert_seconds:.2f} s")
        print(f"[PERF]   Total no servidor:  {total_seconds:.2f} s")
        print(
            "[PERF]   (subtrair este total ao tempo medido pela BOX "
            "para obter o tempo de rede)"
        )
        print()

    except Exception as error:

        print(
            "Erro ao processar capa:",
            error
        )

        return (
            "Erro ao processar capa.",
            500
        )


    return Response(
        image_data,
        mimetype="application/octet-stream",

        headers={
            "X-Image-Width": "120",
            "X-Image-Height": "120",
            "X-Image-Format": "RGB565",
            "Cache-Control": "no-store",
        }
    )

# ---------------------------------------------------------
# COMANDOS
# ---------------------------------------------------------

@app.route(
    "/api/play",
    methods=["POST"]
)
def api_play():

    data, status_code = (
        spotify.send_command(
            "PUT",
            "/me/player/play"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/pause",
    methods=["POST"]
)
def api_pause():

    data, status_code = (
        spotify.send_command(
            "PUT",
            "/me/player/pause"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/next",
    methods=["POST"]
)
def api_next():

    data, status_code = (
        spotify.send_command(
            "POST",
            "/me/player/next"
        )
    )

    return jsonify(data), status_code


@app.route(
    "/api/previous",
    methods=["POST"]
)
def api_previous():

    data, status_code = (
        spotify.send_command(
            "POST",
            "/me/player/previous"
        )
    )

    return jsonify(data), status_code

@app.post("/api/voice")
def api_voice():
    pcm_data = request.get_data(cache=False)

    if not pcm_data:
        return jsonify({
            "ok": False,
            "error": "Nenhum audio recebido"
        }), 400

    # PCM 16-bit tem sempre 2 bytes por amostra.
    if len(pcm_data) % 2 != 0:
        return jsonify({
            "ok": False,
            "error": "Tamanho PCM invalido para audio 16-bit"
        }), 400

    # Limite defensivo.
    # A BOX atualmente grava no máximo ~384 KB.
    if len(pcm_data) > 512000:
        return jsonify({
            "ok": False,
            "error": "Audio demasiado grande"
        }), 413

    # O ramo de interpretação por texto foi removido em 2026-09-30.
    #
    # Era: gravar WAV -> transcribe_audio -> understand_command_local ->
    # understand_command -> execute_intent. Nada disso era alcançável: a BOX
    # põe sempre o cabeçalho X-Response-Audio: pcm16 (voice.c l. 1490), e a
    # verificação abaixo devolvia antes de lá chegar.
    #
    # Foi assim que o intent_service acabou com 8 acções e a ferramenta do
    # Gemini com 5. Não divergiram por descuido — divergiram porque metade do
    # código deixou de correr e ninguém deu por isso.
    #
    # O WAV também desapareceu: só servia de entrada à transcrição.
    #
    # Este endpoint existe agora para uma coisa só: o fallback HTTP, para
    # quando o WebSocket Live não chega a armar.
    if request.headers.get("X-Response-Audio") != "pcm16":
        return jsonify({
            "ok": False,
            "error": (
                "Este endpoint só serve o fallback Live. "
                "Falta o cabeçalho X-Response-Audio: pcm16."
            ),
        }), 400

    print()
    print("[LIVE] ===============================")
    print("[LIVE] Modo Gemini Live (fallback HTTP)")
    print("[LIVE] Audio BOX -> Gemini -> BOX")
    print(f"[LIVE] {len(pcm_data)} bytes | "
          f"{len(pcm_data) / 32000.0:.2f} s de fala")
    print("[LIVE] ===============================")
    print()

    return Response(
        stream_with_context(
            stream_gemini_live_reply(
                pcm_data
            )
        ),
        status=200,
        mimetype="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": "16000",
            "X-Audio-Channels": "1",
            "X-Audio-Bits": "16",
        },
    )


# ---------------------------------------------------------
# ARRANQUE
# ---------------------------------------------------------

if __name__ == "__main__":

    if not CLIENT_ID:

        raise RuntimeError(
            "SPOTIFY_CLIENT_ID "
            "não encontrado."
        )


    if not CLIENT_SECRET:

        raise RuntimeError(
            "SPOTIFY_CLIENT_SECRET "
            "não encontrado."
        )


    if not REDIRECT_URI:

        raise RuntimeError(
            "SPOTIFY_REDIRECT_URI "
            "não encontrado."
        )


    print()
    print("==============================")
    print("Spotify Service")
    print("==============================")
    print()


    if spotify.restore_session():

        print(
            "Sessão Spotify "
            "restaurada automaticamente!"
        )

    else:

        print(
            "Não existe sessão Spotify válida."
        )

        print(
            "Se necessário, autentica em /login."
        )


    print()
    print("Interface:")
    print(
        "http://127.0.0.1:8888"
    )

    print()

    print("API:")
    print(
        "http://127.0.0.1:8888/api/status"
    )

    print()


    mdns_service.start()

    try:
        # B5: o servidor de voz tem de subir, ou não arrancamos de todo.
        #
        # Um sistema com Flask vivo e voz morta é pior do que um sistema
        # em baixo: o LCD actualiza, os botões funcionam, o /api/status
        # responde 200 — e nada aponta para a causa. Custou várias horas
        # a 2026-09-22, com uma instância zombie a segurar a 8765
        # enquanto a nova servia a 8888.
        try:
            voice_ws_server.start()

        except Exception as erro:
            print()
            print("==============================")
            print("ARRANQUE ABORTADO")
            print("==============================")
            print()
            print(f"O servidor de voz não subiu: {erro}")
            print()
            print(
                "O Flask NÃO vai arrancar. Sem voz, este serviço não "
                "tem razão de existir, e um arranque parcial só torna "
                "o problema mais difícil de encontrar."
            )
            print()

            raise SystemExit(1) from erro

        app.run(
            host="0.0.0.0",
            port=8888,
            debug=False,
            use_reloader=False,
        )

    finally:
        voice_ws_server.stop()
        mdns_service.stop()