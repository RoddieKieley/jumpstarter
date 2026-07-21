from dataclasses import dataclass

import click

from jumpstarter.client import DriverClient
from jumpstarter.client.decorators import driver_click_group


@dataclass(kw_only=True)
class WakeOnLanClient(DriverClient):
    """Client interface for the Wake-on-LAN driver."""

    def wake(self) -> str:
        """Send a Wake-on-LAN magic packet to the configured MAC address."""
        return self.call("wake")

    def cli(self):
        @driver_click_group(self)
        def wol():
            """Wake-on-LAN commands"""
            pass

        @wol.command()
        def wake():
            """Send a Wake-on-LAN magic packet"""
            click.echo(self.wake())

        return wol
