import socket

from zeroconf import (
    IPVersion,
    ServiceInfo,
    Zeroconf,
)


class MdnsService:

    def __init__(
        self,
        hostname="spotify-service",
        port=8888,
    ):
        self.hostname = hostname
        self.port = port

        self.zeroconf = None
        self.info = None


    def _get_local_ip(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            # Não é feita uma ligação real.
            # Serve para descobrir qual interface
            # o Windows usa para chegar à rede.
            sock.connect(
                ("8.8.8.8", 80)
            )

            local_ip = (
                sock.getsockname()[0]
            )

        finally:
            sock.close()

        return local_ip


    def start(self):

        local_ip = (
            self._get_local_ip()
        )

        full_hostname = (
            f"{self.hostname}.local."
        )

        service_type = (
            "_http._tcp.local."
        )

        service_name = (
            "Spotify Service."
            "_http._tcp.local."
        )


        self.info = ServiceInfo(
            service_type,
            service_name,

            addresses=[
                socket.inet_aton(
                    local_ip
                )
            ],

            port=self.port,

            properties={
                "path": "/api/status",
                "service": "spotify",
            },

            server=full_hostname,
        )


        self.zeroconf = Zeroconf(
            ip_version=IPVersion.V4Only
        )


        self.zeroconf.register_service(
            self.info
        )


        print(
            "mDNS ativo:"
        )

        print(
            f"  {self.hostname}.local"
            f" -> {local_ip}:{self.port}"
        )


    def stop(self):

        if (
            self.zeroconf is not None
            and self.info is not None
        ):
            self.zeroconf.unregister_service(
                self.info
            )

        if self.zeroconf is not None:
            self.zeroconf.close()

        print(
            "mDNS terminado."
        )