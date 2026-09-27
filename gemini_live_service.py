import asyncio
import os
import queue
import threading
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

# O que este caminho partilha com o WebSocket persistente vive em
# jarvis_live.py. Ver o cabeçalho desse módulo para o porquê.
from jarvis_live import (
    MODEL,
    Pcm24kTo16k,
    build_live_config,
    dispatch_tool_calls,
)
from turn_log import registar_turno, segundos


load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY não encontrada no .env"
    )


INPUT_SAMPLE_RATE = 16000
INPUT_BYTES_PER_SECOND = INPUT_SAMPLE_RATE * 2

# 100 ms de PCM16 mono a 16 kHz:
# 16000 amostras/s * 2 bytes/amostra * 0,1 s = 3200 bytes.
INPUT_CHUNK_BYTES = 3200

# Evita que uma sessão fique indefinidamente presa sem resposta.
RECEIVE_TIMEOUT_SECONDS = 90

_END = object()


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

    # Acumuladores do registo de turnos. Declarados aqui, antes do try,
    # para que o finally os encontre mesmo se a sessão nem chegar a abrir.
    turno_inicio = time.perf_counter()
    turno = {
        "resultado": "erro",
        "erro": None,
        "ouvido": "",
        "dito": "",
        "ferramentas": [],
        "bytes_out": 0,
        "t_primeiro_audio": None,
        "t_ferramentas": 0.0,
    }

    try:
        client = genai.Client(
            api_key=API_KEY
        )

        config = build_live_config()

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
                        # Cronometrado à parte: está dentro do
                        # t_primeiro_audio mas não é latência do modelo.
                        ferramentas_inicio = time.perf_counter()

                        function_responses, registos = (
                            await dispatch_tool_calls(
                                response.tool_call,
                                "[LIVE]",
                            )
                        )

                        turno["t_ferramentas"] += (
                            time.perf_counter() - ferramentas_inicio
                        )

                        turno["ferramentas"].extend(registos)

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

                    # B2, corrigido em 2026-09-26.
                    #
                    # O ramo de entrada fazia `if text:` sem nunca atribuir
                    # `text` — a única atribuição estava no ramo de saída,
                    # a seguir. Como a primeira transcrição de ENTRADA de
                    # cada sessão chega antes de o Gemini falar, a primeira
                    # passagem por aqui levantava UnboundLocalError.
                    #
                    # O erro era apanhado pelo except lá em baixo e
                    # relançado pelo gerador, matando o pedido HTTP sem
                    # áudio. Ou seja: este caminho de fallback nunca
                    # funcionou desde que a transcrição de entrada foi
                    # ligada. Nomes distintos para não voltar a acontecer.
                    if content.input_transcription:
                        heard = content.input_transcription.text

                        if heard:
                            turno["ouvido"] += heard

                            print(
                                f"[LIVE] Tu: {heard}"
                            )

                    if content.output_transcription:
                        spoken = content.output_transcription.text

                        if spoken:
                            turno["dito"] += spoken

                            print(
                                f"[LIVE] Jarvis: {spoken}"
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

                            turno["t_primeiro_audio"] = latency

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

                        turno["bytes_out"] = total_16k

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

            turno["resultado"] = "done"

    except TimeoutError:
        exc = RuntimeError(
            "Timeout à espera da resposta Gemini Live"
        )

        print(
            f"[LIVE] ERRO: {exc}"
        )

        turno["erro"] = str(exc)
        output_queue.put(exc)

    except Exception as exc:
        print(
            f"[LIVE] ERRO: {exc}"
        )

        turno["erro"] = f"{type(exc).__name__}: {exc}"
        output_queue.put(exc)

    finally:
        output_queue.put(_END)

        # fallback=True é o campo que fecha a decisão D1: sem ele não
        # há como saber se este caminho alguma vez é usado em campo.
        registar_turno({
            "conversa": "",
            "turno": 1,
            "resultado": turno["resultado"],
            "erro": turno["erro"],
            "fallback": True,

            "t_fala": segundos(len(pcm16) / INPUT_BYTES_PER_SECOND),
            "t_primeiro_audio": segundos(turno["t_primeiro_audio"]),
            "t_ferramentas": segundos(turno["t_ferramentas"]),
            "t_modelo": segundos(
                None if turno["t_primeiro_audio"] is None
                else max(
                    0.0,
                    turno["t_primeiro_audio"] - turno["t_ferramentas"],
                )
            ),
            "t_total": segundos(time.perf_counter() - turno_inicio),

            "bytes_in": len(pcm16),
            "bytes_out": turno["bytes_out"],

            "ouvido": turno["ouvido"],
            "dito": turno["dito"],
            "ferramentas": turno["ferramentas"],
        })


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
