# Wake-on-LAN Driver

`jumpstarter-driver-wake-on-lan` sends a standard [Wake-on-LAN](https://en.wikipedia.org/wiki/Wake-on-LAN)
magic packet to a configured MAC address. It is intentionally a sibling driver to power
control (Option C): power on the DUT first, wait if needed, then wake.

## Installation

```{code-block} console
:substitutions:
$ pip3 install --extra-index-url {{index_url}} jumpstarter-driver-wake-on-lan
```

## Configuration

Example configuration (export name `wol` yields `j wol …`):

```yaml
export:
  wol:
    type: jumpstarter_driver_wake_on_lan.driver.WakeOnLan
    config:
      mac: "50:7b:9d:07:eb:98"
      # broadcast: "255.255.255.255"   # optional
      # port: 9                       # optional
```

### Config parameters

| Parameter   | Description                                      | Default             |
|-------------|--------------------------------------------------|---------------------|
| `mac`       | Target NIC MAC address                           | Required            |
| `broadcast` | IPv4 broadcast / directed-broadcast destination  | `255.255.255.255`   |
| `port`      | UDP destination port                             | `9`                 |

Accepted MAC formats: `aa:bb:cc:dd:ee:ff`, `aa-bb-cc-dd-ee-ff`, or `aabbccddeeff`.

## Usage

With an exporter that exports this driver as `wol`:

```{code-block} console
$ jmp shell -l ...
$$ j wol wake
```

### Sibling power + WoL (Option C)

When a separate power driver is also exported (for example Tuya as `power`), wake after
power is applied:

```{code-block} console
$$ j power on
$$ sleep 5
$$ j wol wake
```

A helper script is shipped at `examples/power-on-with-wol.sh`:

```{code-block} console
$$ WAIT=5 ./examples/power-on-with-wol.sh
```

This requires both `j power` and `j wol` in the current Jumpstarter shell.

## API Reference

```{eval-rst}
.. autoclass:: jumpstarter_driver_wake_on_lan.client.WakeOnLanClient()
    :members: wake
```
