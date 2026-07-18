import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from .driver import TuyaPower, load_tuya_device, require_device_fields
from jumpstarter.client.core import DriverError
from jumpstarter.common.utils import serve

LIVE_DEVICES_FILE = Path("/wip/tuya/devices.json")


def _write_devices(path: Path, devices: list[dict]) -> None:
    path.write_text(json.dumps(devices), encoding="utf-8")


def test_load_tuya_device_by_name_and_id(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    _write_devices(
        devices_file,
        [
            {
                "name": "Mini Plug",
                "id": "eba482e5de2a9b8e26dcv9",
                "ip": "192.168.4.119",
                "key": "secret-key",
                "version": "3.3",
            }
        ],
    )

    by_name = load_tuya_device(str(devices_file), "mini plug")
    assert by_name["id"] == "eba482e5de2a9b8e26dcv9"

    by_id = load_tuya_device(str(devices_file), "eba482e5de2a9b8e26dcv9")
    assert by_id["name"] == "Mini Plug"


def test_load_tuya_device_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError, match="not found"):
        load_tuya_device(str(tmp_path / "missing.json"), "Mini Plug")


def test_load_tuya_device_unknown_device(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    _write_devices(devices_file, [{"name": "Other", "id": "abc", "ip": "1.2.3.4", "key": "k", "version": 3.3}])
    with pytest.raises(ValueError, match="not found"):
        load_tuya_device(str(devices_file), "Mini Plug")


def test_require_device_fields_missing_key():
    with pytest.raises(ValueError, match="missing required field 'key'"):
        require_device_fields(
            {"id": "abc", "ip": "1.2.3.4", "key": "", "version": 3.3},
            "devices.json",
        )


def test_drivers_tuya_power(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    _write_devices(
        devices_file,
        [
            {
                "name": "Mini Plug",
                "id": "dev-id-1",
                "ip": "192.168.4.119",
                "key": "local-key",
                "version": "3.3",
            }
        ],
    )

    outlet = MagicMock()
    outlet.turn_on.return_value = {"dps": {"1": True}}
    outlet.turn_off.return_value = {"dps": {"1": False}}

    with patch("jumpstarter_driver_tuya.driver.tinytuya.OutletDevice", return_value=outlet) as outlet_cls:
        instance = TuyaPower(
            device="Mini Plug",
            devices_file=str(devices_file),
            switch_dp=1,
            timeout=5.0,
        )

        outlet_cls.assert_called_once_with("dev-id-1", "192.168.4.119", "local-key")
        outlet.set_version.assert_called_once_with(3.3)
        outlet.set_socketTimeout.assert_called_once_with(5.0)

        with serve(instance) as client:
            assert hasattr(client, "on")
            assert hasattr(client, "off")
            assert hasattr(client, "read")

            client.on()
            client.off()

            outlet.turn_on.assert_called_once_with(switch=1)
            # serve()/Driver teardown also calls close() -> off()
            outlet.turn_off.assert_any_call(switch=1)
            assert outlet.turn_off.call_count >= 1

            with pytest.raises(NotImplementedError, match="does not support electrical power readings"):
                list(client.read())


def test_tuya_power_propagates_device_error(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    _write_devices(
        devices_file,
        [{"name": "Mini Plug", "id": "dev-id-1", "ip": "192.168.4.119", "key": "local-key", "version": "3.3"}],
    )

    outlet = MagicMock()
    outlet.turn_on.return_value = {"Error": "Check device key or version", "Err": "914", "Payload": None}
    outlet.turn_off.return_value = {"dps": {"1": False}}

    with patch("jumpstarter_driver_tuya.driver.tinytuya.OutletDevice", return_value=outlet):
        instance = TuyaPower(device="Mini Plug", devices_file=str(devices_file))
        with serve(instance) as client:
            with pytest.raises(DriverError, match="Tuya on failed"):
                client.on()


def test_tuya_power_close_calls_off(tmp_path: Path):
    devices_file = tmp_path / "devices.json"
    _write_devices(
        devices_file,
        [{"name": "Mini Plug", "id": "dev-id-1", "ip": "192.168.4.119", "key": "local-key", "version": "3.3"}],
    )

    outlet = MagicMock()
    outlet.turn_off.return_value = {"dps": {"1": False}}

    with patch("jumpstarter_driver_tuya.driver.tinytuya.OutletDevice", return_value=outlet):
        instance = TuyaPower(device="Mini Plug", devices_file=str(devices_file))
        instance.close()
        instance.reset()
        assert outlet.turn_off.call_count == 2


@pytest.mark.skipif(not LIVE_DEVICES_FILE.is_file(), reason="requires local TinyTuya devices.json")
def test_tuya_power_live():
    devices = json.loads(LIVE_DEVICES_FILE.read_text(encoding="utf-8"))
    if isinstance(devices, dict) and "devices" in devices:
        devices = devices["devices"]
    assert devices, "devices.json has no devices"

    device_name = devices[0].get("name") or devices[0]["id"]
    instance = TuyaPower(device=device_name, devices_file=str(LIVE_DEVICES_FILE))

    with serve(instance) as client:
        # Capture prior relay state when possible, then cycle and restore.
        prior_on = None
        status = instance._outlet.status()
        if isinstance(status, dict) and "dps" in status:
            prior_on = bool(status["dps"].get("1", False))

        client.on()
        client.off()

        if prior_on is True:
            client.on()
        elif prior_on is False:
            client.off()
