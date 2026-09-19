import io
import struct

import requests
from PIL import Image


class CoverService:

    def __init__(self):
        self.cached_url = None
        self.cached_size = None
        self.cached_rgb565 = None


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


        response = requests.get(
            image_url,
            timeout=10,
        )

        response.raise_for_status()


        image = Image.open(
            io.BytesIO(
                response.content
            )
        )

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


        self.cached_url = image_url
        self.cached_size = requested_size
        self.cached_rgb565 = result


        return result