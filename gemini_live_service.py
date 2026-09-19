import asyncio
import os
import queue
import struct
import threading
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types
from action_service import execute_spotify_action


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


MODEL = "gemini-3.1-flash-live-preview"

INPUT_SAMPLE_RATE = 16000
INPUT_BYTES_PER_SECOND = INPUT_SAMPLE_RATE * 2

# 100 ms de PCM16 mono a 16 kHz:
# 16000 amostras/s * 2 bytes/amostra * 0,1 s = 3200 bytes.
INPUT_CHUNK_BYTES = 3200

# Evita que uma sessão fique indefinidamente presa sem resposta.
RECEIVE_TIMEOUT_SECONDS = 90

_END = object()


class Pcm24kTo16k:
    """
    Conversor stateful simples:
    PCM16 mono 24 kHz -> PCM16 mono 16 kHz.

    A razão é exatamente 3:2:
    3 amostras de entrada produzem 2 amostras de saída.

    O atributo carry conserva bytes incompletos entre chunks,
    permitindo converter uma resposta recebida por streaming.
    """

    def __init__(self):
        self.carry = b""

    def convert(self, pcm24):
        data = self.carry + pcm24

        # 3 amostras PCM16 = 6 bytes.
        usable = (len(data) // 6) * 6

        if usable == 0:
            self.carry = data
            return b""

        output = bytearray()

        for offset in range(0, usable, 6):
            a, b, c = struct.unpack_from(
                "<hhh",
                data,
                offset,
            )

            # Pontos de saída aproximados nas posições 0 e 1,5.
            out1 = a
            out2 = int((int(b) + int(c)) / 2)

            output.extend(
                struct.pack(
                    "<hh",
                    out1,
                    out2,
                )
            )

        self.carry = data[usable:]

        return bytes(output)


async def _live_worker(pcm16, output_queue):
    """
    Abre uma sessão Gemini Live para uma única fala já delimitada
    pela BOX.

    A BOX já executou WakeNet + VAD, por isso usamos VAD manual:
        activity_start
        áudio
        activity_end

    Com VAD automático desativado NÃO se envia audio_stream_end.
    """

    try:
        client = genai.Client(
            api_key=API_KEY
        )

        config = {
            "response_modalities": ["AUDIO"],

            "tools": [
                {
                    "function_declarations": [
                        {
                            "name": "spotify_control",
                            "description": (
                                "Controla a reprodução Spotify do utilizador. "
                                "Usa esta função sempre que o utilizador pedir "
                                "para pausar, retomar, avançar, voltar à música "
                                "anterior ou perguntar o que está a tocar."
                            ),
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string",
                                        "enum": [
                                            "pause",
                                            "resume",
                                            "next",
                                            "previous",
                                            "current_track",
                                        ],
                                        "description": (
                                            "A ação Spotify a executar."
                                        ),
                                    }
                                },
                                "required": ["action"],
                            },
                        }
                    ]
                }
            ],

            "input_audio_transcription": {},
            "output_audio_transcription": {},

            # A BOX já sabe exatamente onde a fala começa e termina.
            "realtime_input_config": {
                "automatic_activity_detection": {
                    "disabled": True
                }
            },

            "system_instruction": {
                "parts": [
                    {
                        "text": (
                            "És Jarvis, um assistente pessoal de "
                            "inteligência artificial. "
                            "Fala em português de Portugal, salvo se "
                            "o utilizador pedir outra língua. "
                            "Responde de forma natural e útil. "
                            "Como estás num assistente de voz, prefere "
                            "respostas relativamente concisas, exceto "
                            "quando o utilizador pedir mais detalhe."
                            "Quando o utilizador pedir para controlar "
                            "a reprodução Spotify, usa obrigatoriamente "
                            "a ferramenta spotify_control. "
                            "Usa-a também quando perguntarem que música "
                            "está atualmente a tocar. "
                            "Nunca afirmes que executaste uma ação Spotify "
                            "sem primeiro chamares a ferramenta."
                        )
                    }
                ]
            },
        }

        print(
            f"[LIVE] A abrir sessão {MODEL}..."
        )

        async with client.aio.live.connect(
            model=MODEL,
            config=config,
        ) as session:

            print("[LIVE] Sessão ligada")

            # CORREÇÃO CRÍTICA:
            # antes estava activity_end aqui. O primeiro sinal tem
            # obrigatoriamente de ser activity_start.
            await session.send_realtime_input(
                activity_start=types.ActivityStart()
            )

            print("[LIVE] Início de atividade enviado")
            print("[LIVE] A enviar áudio...")

            for offset in range(
                0,
                len(pcm16),
                INPUT_CHUNK_BYTES,
            ):
                chunk = pcm16[
                    offset:
                    offset + INPUT_CHUNK_BYTES
                ]

                await session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type="audio/pcm;rate=16000",
                    )
                )

                # Neste estágio intermédio, o áudio já foi gravado pela
                # BOX. Enviamo-lo ao ritmo real para preservar a ordem e
                # reproduzir o comportamento do teste que já funcionou.
                await asyncio.sleep(
                    len(chunk) / INPUT_BYTES_PER_SECOND
                )

            # CORREÇÃO CRÍTICA:
            # com automatic_activity_detection.disabled=True, o turno
            # termina com activity_end e não com audio_stream_end.
            response_start = time.perf_counter()

            await session.send_realtime_input(
                activity_end=types.ActivityEnd()
            )

            print(
                "[LIVE] Fim de atividade enviado; "
                "a receber resposta..."
            )

            converter = Pcm24kTo16k()
            first_audio = True
            total_16k = 0

            async with asyncio.timeout(
                RECEIVE_TIMEOUT_SECONDS
            ):
                async for response in session.receive():
                    # -----------------------------------------
                    # TOOL CALLS / CONTROLO SPOTIFY
                    # -----------------------------------------

                    if response.tool_call:
                        function_responses = []

                        for fc in response.tool_call.function_calls:
                            print(
                                f"[LIVE] Tool call: "
                                f"{fc.name}({fc.args})"
                            )

                            if fc.name == "spotify_control":
                                args = dict(fc.args or {})

                                action = args.get("action")

                                # action_service usa requests síncrono.
                                # Executamo-lo fora do event loop para não
                                # bloquear a ligação Gemini Live.
                                result = await asyncio.to_thread(
                                    execute_spotify_action,
                                    action,
                                )

                                print(
                                    f"[LIVE] Spotify: "
                                    f"{action} -> {result}"
                                )

                            else:
                                result = {
                                    "ok": False,
                                    "message": (
                                        f"Ferramenta desconhecida: "
                                        f"{fc.name}"
                                    ),
                                }

                            function_responses.append(
                                types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={
                                        "result": result
                                    },
                                )
                            )

                        await session.send_tool_response(
                            function_responses=
                                function_responses
                        )

                        print(
                            "[LIVE] Resultado da ferramenta "
                            "devolvido ao Gemini"
                        )

                        continue

                    # -----------------------------------------
                    # RESPOSTA NORMAL DO GEMINI
                    # -----------------------------------------

                    content = response.server_content

                    if content is None:
                        continue

                    if content.input_transcription:

                        if text:
                            print(
                                f"[LIVE] Tu: {text}"
                            )

                    if content.output_transcription:
                        text = content.output_transcription.text

                        if text:
                            print(
                                f"[LIVE] Jarvis: {text}"
                            )

                    if content.model_turn is None:
                        continue

                    for part in content.model_turn.parts:
                        if (
                            part.inline_data is None
                            or part.inline_data.data is None
                        ):
                            continue

                        pcm24 = part.inline_data.data

                        pcm16_out = converter.convert(
                            pcm24
                        )

                        if not pcm16_out:
                            continue

                        if first_audio:
                            latency = (
                                time.perf_counter()
                                - response_start
                            )

                            print(
                                "[LIVE] >>> primeiro chunk "
                                "de voz recebido <<<"
                            )

                            print(
                                f"[PERF] Primeiro áudio Gemini: "
                                f"{latency:.2f} s"
                            )

                            first_audio = False

                        total_16k += len(
                            pcm16_out
                        )

                        # Usa uma thread auxiliar para que uma BOX/cliente
                        # HTTP momentaneamente lento não bloqueie o event
                        # loop que recebe o WebSocket do Gemini.
                        await asyncio.to_thread(
                            output_queue.put,
                            pcm16_out,
                        )

            if first_audio:
                raise RuntimeError(
                    "Gemini Live terminou sem devolver áudio"
                )

            print(
                f"[LIVE] Resposta terminada | "
                f"{total_16k} bytes a 16 kHz"
            )

    except TimeoutError:
        exc = RuntimeError(
            "Timeout à espera da resposta Gemini Live"
        )

        print(
            f"[LIVE] ERRO: {exc}"
        )

        output_queue.put(exc)

    except Exception as exc:
        print(
            f"[LIVE] ERRO: {exc}"
        )

        output_queue.put(exc)

    finally:
        output_queue.put(_END)


def stream_gemini_live_reply(pcm16):
    """
    Gerador síncrono usado pelo Flask.

    A sessão Gemini corre numa thread/event loop própria e os chunks
    PCM16 a 16 kHz são encaminhados para a resposta HTTP assim que
    ficam disponíveis.
    """

    if not pcm16:
        raise ValueError(
            "O áudio PCM recebido está vazio"
        )

    output_queue = queue.Queue(
        maxsize=64
    )

    def runner():
        asyncio.run(
            _live_worker(
                pcm16,
                output_queue,
            )
        )

    thread = threading.Thread(
        target=runner,
        daemon=True,
        name="gemini-live",
    )

    thread.start()

    while True:
        item = output_queue.get()

        if item is _END:
            break

        if isinstance(
            item,
            BaseException,
        ):
            raise item

        yield item
