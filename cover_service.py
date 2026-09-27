import io
import struct
import time

import requests
from PIL import Image


class CoverService:

    def __init__(self):
        self.cached_url = None
        self.cached_size = None
        self.cached_rgb565 = None

        # Medido em 2026-09-23: 40 KB do CDN demoravam 1,31 s, o que dá
        # 31 KB/s — lento de mais para ser transferência. O suspeito é o
        # custo de abrir ligação: cada requests.get() avulso faz TCP e TLS
        # de raiz com o i.scdn.co.
        #
        # Uma Session reutiliza essa ligação entre capas. Previsão: a
        # primeira capa depois do arranque continua lenta, as seguintes
        # ficam bastante mais rápidas. Se não for isso que acontece, a
        # hipótese está errada e o tempo é mesmo transferência.
        self._session = requests.Session()


    def get_rgb565(
        self,
        image_url,
        width=120,
        height=120,
    ):
        if not image_url:
            return None

        requested_size = (
            width,
            height,
        )

        # Se for a mesma capa e o mesmo tamanho,
        # reutilizamos o resultado.
        if (
            image_url == self.cached_url
            and requested_size == self.cached_size
            and self.cached_rgb565 is not None
        ):
            return self.cached_rgb565


        # As duas metades deste método custam, juntas, entre 1,1 e 1,9 s.
        # Ainda não sabemos qual delas domina — e optimizar sem saber foi
        # o erro que já se cometeu uma vez nesta investigação.
        download_started = time.perf_counter()

        response = self._session.get(
            image_url,
            timeout=10,
        )

        response.raise_for_status()

        download_seconds = (
            time.perf_counter() - download_started
        )

        convert_started = time.perf_counter()

        image = Image.open(
            io.BytesIO(
                response.content
            )
        )

        # Confirma qual das versões do Spotify foi de facto descarregada.
        # O selector em spotify_client escolhe a mais pequena que chegue
        # para 120 px; isto verifica que escolheu mesmo.
        source_width, source_height = image.size

        image = image.convert("RGB")

        image = image.resize(
            requested_size,
            Image.Resampling.LANCZOS,
        )


        rgb565_data = bytearray()


        for red, green, blue in image.getdata():

            rgb565 = (
                ((red & 0xF8) << 8)
                |
                ((green & 0xFC) << 3)
                |
                (blue >> 3)
            )

            # ESP32 é little-endian.
            rgb565_data.extend(
                struct.pack(
                    "<H",
                    rgb565
                )
            )


        result = bytes(
            rgb565_data
        )

        convert_seconds = (
            time.perf_counter() - convert_started
        )

        print(
            f"[PERF]   -> download CDN:   {download_seconds:.2f} s "
            f"({len(response.content)} bytes, "
            f"{source_width}x{source_height} px)"
        )
        print(
            f"[PERF]   -> PIL + RGB565:   {convert_seconds:.2f} s"
        )


        self.cached_url = image_url
        self.cached_size = requested_size
        self.cached_rgb565 = result


        return result