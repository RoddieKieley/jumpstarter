# Tuya Power Driver

`jumpstarter-driver-tuya` provides a power driver for Tuya-compatible smart plugs using
[TinyTuya](https://github.com/jasonacox/tinytuya) LAN control.

Credentials (device id, IP, local key, protocol version) are loaded from a TinyTuya
`devices.json` file (`tinytuya.DEVICEFILE`). Generate that file with the TinyTuya wizard
after pairing the plug in the Tuya / Smart Life app and linking the account to a Tuya IoT
Cloud project.

Do **not** commit `devices.json`, `tinytuya.json`, or local keys to git.

## Installation

```{code-block} console
:substitutions:
$ pip3 install --extra-index-url {{index_url}} jumpstarter-driver-tuya
```

## Configuration

Example configuration:

```yaml
export:
  power:
    type: jumpstarter_driver_tuya.driver.TuyaPower
    config:
      device: Mini Plug
      devices_file: /path/to/devices.json
```

### Config parameters

| Parameter       | Description                                                                 | Default              |
|-----------------|-----------------------------------------------------------------------------|----------------------|
| `device`        | Device name (case-insensitive) or device id from `devices.json`             | Required             |
| `devices_file`  | Path to TinyTuya devices file                                               | `devices.json` (`tinytuya.DEVICEFILE`) |
| `switch_dp`     | Data point (DPS) id for the switch                                          | `1`                  |
| `timeout`       | TinyTuya socket timeout in seconds                                          | TinyTuya default     |

The selected `devices.json` entry must include `id`, `ip`, `key`, and `version`.

### Preparing devices.json

```{code-block} console
$ python3 -m tinytuya wizard
```

Point `devices_file` at the resulting `devices.json` (for example a local path outside the
repository). TinyTuya also writes `tinytuya.json` (cloud API credentials) and may write
`snapshot.json` / `tuya-raw.json`; only `devices.json` is required by this driver.

## Usage

With an exporter that exports this driver as `power`:

```{code-block} console
$ jmp shell -l ...
$$ j power on
$$ j power off
$$ j power cycle
```

`cycle` is provided by the shared `PowerClient` (`off`, wait, `on`).

Electrical `read()` measurements are not implemented for this driver (many Tuya mini plugs
do not expose voltage/current DPs).

## API Reference

```{eval-rst}
.. autoclass:: jumpstarter_driver_power.client.PowerClient()
    :no-index:
    :members: on, off, cycle, read
```
