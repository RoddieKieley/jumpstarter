import re
import socket
from dataclasses import dataclass, field

from jumpstarter.driver import Driver, export

_MAC_RE = re.compile(r"^([0-9a-fA-F]{2}([:-]))(?:[0-9a-fA-F]{2}\2){4}[0-9a-fA-F]{2}$|^([0-9a-fA-F]{12})$")


class WakeOnLanError(Exception):
    """Base exception for Wake-on-LAN errors."""


def normalize_mac(mac: str) -> bytes:
    """Validate and convert a MAC address string to 6 raw bytes."""
    value = mac.strip()
    if not _MAC_RE.match(value):
        raise ValueError(
            f"invalid MAC address {mac!r}; expected formats like "
            "aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff, or aabbccddeeff"
        )
    hex_part = re.sub(r"[:-]", "", value)
    return bytes.fromhex(hex_part)


def build_magic_packet(mac: str) -> bytes:
    """Build a standard Wake-on-LAN magic packet for ``mac``."""
    mac_bytes = normalize_mac(mac)
    return b"\xff" * 6 + mac_bytes * 16


def send_magic_packet(packet: bytes, broadcast: str, port: int) -> None:
    """Send ``packet`` as a UDP broadcast to ``broadcast:port``."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, int(port)))


@dataclass(kw_only=True)
class WakeOnLan(Driver):
    """Wake-on-LAN driver that sends a magic packet to a target MAC address."""

    mac: str
    broadcast: str = "255.255.255.255"
    port: int = 9
    _mac_bytes: bytes = field(init=False, repr=False)

    def __post_init__(self):
        if hasattr(super(), "__post_init__"):
            super().__post_init__()
        self._mac_bytes = normalize_mac(self.mac)
        if not (1 <= int(self.port) <= 65535):
            raise ValueError(f"port must be between 1 and 65535, got {self.port}")

    @classmethod
    def client(cls) -> str:
        return "jumpstarter_driver_wake_on_lan.client.WakeOnLanClient"

    @export
    def wake(self) -> str:
        """Send a Wake-on-LAN magic packet to the configured MAC address."""
        packet = b"\xff" * 6 + self._mac_bytes * 16
        self.logger.info(
            "Sending Wake-on-LAN packet to %s via %s:%s",
            self.mac,
            self.broadcast,
            self.port,
        )
        try:
            send_magic_packet(packet, self.broadcast, int(self.port))
        except OSError as exc:
            raise WakeOnLanError(
                f"failed to send Wake-on-LAN packet to {self.mac} via {self.broadcast}:{self.port}: {exc}"
            ) from exc
        return f"Wake-on-LAN packet sent to {self.mac}"
