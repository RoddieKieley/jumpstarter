from pathlib import Path
from unittest.mock import patch

import pytest

from .driver import WakeOnLan, build_magic_packet, normalize_mac
from jumpstarter.client.core import DriverError
from jumpstarter.common.utils import serve

LIVE_MAC = "50:7b:9d:07:eb:98"
LIVE_ENABLE = Path("/wip/pxe/wol-live.enable")


def test_normalize_mac_formats():
    expected = bytes.fromhex("507b9d07eb98")
    assert normalize_mac("50:7b:9d:07:eb:98") == expected
    assert normalize_mac("50-7B-9D-07-EB-98") == expected
    assert normalize_mac("507b9d07eb98") == expected


def test_normalize_mac_invalid():
    with pytest.raises(ValueError, match="invalid MAC address"):
        normalize_mac("not-a-mac")
    with pytest.raises(ValueError, match="invalid MAC address"):
        normalize_mac("50:7b:9d:07:eb")


def test_build_magic_packet():
    packet = build_magic_packet("50:7b:9d:07:eb:98")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:] == bytes.fromhex("507b9d07eb98") * 16


def test_wake_on_lan_rejects_invalid_mac():
    with pytest.raises(ValueError, match="invalid MAC address"):
        WakeOnLan(mac="bad-mac")


def test_wake_on_lan_rejects_invalid_port():
    with pytest.raises(ValueError, match="port must be between"):
        WakeOnLan(mac="50:7b:9d:07:eb:98", port=0)


def test_wake_on_lan_sendto():
    instance = WakeOnLan(mac="50:7b:9d:07:eb:98", broadcast="192.168.2.255", port=9)
    with (
        serve(instance) as client,
        patch("jumpstarter_driver_wake_on_lan.driver.send_magic_packet") as send,
    ):
        assert hasattr(client, "wake")
        result = client.wake()
        assert "50:7b:9d:07:eb:98" in result
        send.assert_called_once_with(
            build_magic_packet("50:7b:9d:07:eb:98"),
            "192.168.2.255",
            9,
        )


def test_wake_on_lan_propagates_oserror():
    instance = WakeOnLan(mac="50:7b:9d:07:eb:98")
    with (
        serve(instance) as client,
        patch(
            "jumpstarter_driver_wake_on_lan.driver.send_magic_packet",
            side_effect=OSError("network unreachable"),
        ),
    ):
        with pytest.raises(DriverError, match="failed to send Wake-on-LAN"):
            client.wake()


def test_wake_on_lan_cli_has_wake():
    instance = WakeOnLan(mac="50:7b:9d:07:eb:98")
    with (
        serve(instance) as client,
        patch("jumpstarter_driver_wake_on_lan.driver.send_magic_packet") as send,
    ):
        cli = client.cli()
        assert "wake" in cli.commands
        assert client.wake()
        send.assert_called_once()


@pytest.mark.skipif(not LIVE_ENABLE.is_file(), reason="create /wip/pxe/wol-live.enable to run live WoL test")
def test_wake_on_lan_live():
    instance = WakeOnLan(mac=LIVE_MAC, broadcast="255.255.255.255", port=9)
    with serve(instance) as client:
        result = client.wake()
        assert LIVE_MAC in result
