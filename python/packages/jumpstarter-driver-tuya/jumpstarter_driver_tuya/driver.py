import json
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tinytuya
from jumpstarter_driver_power.common import PowerReading
from jumpstarter_driver_power.driver import PowerInterface

from jumpstarter.driver import Driver, export


def load_tuya_device(devices_file: str, device: str) -> dict[str, Any]:
    """Load a device entry from a TinyTuya devices.json file by name or id."""
    path = Path(devices_file)
    if not path.is_file():
        raise FileNotFoundError(f"TinyTuya devices file not found: {devices_file}")

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "devices" in data:
        data = data["devices"]
    if not isinstance(data, list):
        raise ValueError(f"TinyTuya devices file must contain a list of devices: {devices_file}")

    needle = device.strip()
    if not needle:
        raise ValueError("device must be a non-empty name or id")

    for entry in data:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") == needle:
            return entry
        name = entry.get("name")
        if isinstance(name, str) and name.casefold() == needle.casefold():
            return entry

    raise ValueError(f"Device {device!r} not found in {devices_file}")


def require_device_fields(entry: dict[str, Any], devices_file: str) -> tuple[str, str, str, float]:
    """Validate and return id, ip, key, version from a devices.json entry."""
    for key in ("id", "ip", "key", "version"):
        if key not in entry or entry[key] in (None, ""):
            raise ValueError(f"Device entry in {devices_file} is missing required field {key!r}")

    try:
        version = float(entry["version"])
    except (TypeError, ValueError) as e:
        raise ValueError(f"Device entry in {devices_file} has invalid version: {entry['version']!r}") from e

    return str(entry["id"]), str(entry["ip"]), str(entry["key"]), version


def raise_for_tuya_error(result: Any, action: str) -> None:
    """Raise RuntimeError when TinyTuya returns an error payload."""
    if isinstance(result, dict) and result.get("Error"):
        err = result.get("Err", "")
        detail = result.get("Error")
        raise RuntimeError(f"Tuya {action} failed: {detail} (Err {err})")


@dataclass(kw_only=True)
class TuyaPower(PowerInterface, Driver):
    """Power driver for Tuya-compatible smart plugs via TinyTuya LAN control."""

    device: str
    devices_file: str = field(default_factory=lambda: tinytuya.DEVICEFILE)
    switch_dp: int = 1
    timeout: float | None = None

    _outlet: Any = field(init=False, repr=False)

    def __post_init__(self):
        if hasattr(super(), "__post_init__"):
            super().__post_init__()

        entry = load_tuya_device(self.devices_file, self.device)
        device_id, ip, key, version = require_device_fields(entry, self.devices_file)

        self._outlet = tinytuya.OutletDevice(device_id, ip, key)
        self._outlet.set_version(version)
        if self.timeout is not None:
            self._outlet.set_socketTimeout(self.timeout)

        self.logger.info(
            "TuyaPower initialized for %s (%s) at %s via %s",
            entry.get("name", device_id),
            device_id,
            ip,
            self.devices_file,
        )

    @export
    def on(self) -> None:
        self.logger.info("Powering on Tuya device %s (dp=%s)", self.device, self.switch_dp)
        result = self._outlet.turn_on(switch=self.switch_dp)
        raise_for_tuya_error(result, "on")

    @export
    def off(self) -> None:
        self.logger.info("Powering off Tuya device %s (dp=%s)", self.device, self.switch_dp)
        result = self._outlet.turn_off(switch=self.switch_dp)
        raise_for_tuya_error(result, "off")

    @export
    def read(self) -> Generator[PowerReading, None, None]:
        raise NotImplementedError("TuyaPower does not support electrical power readings")
        yield  # pragma: no cover

    def close(self):
        self.off()

    def reset(self):
        self.off()
