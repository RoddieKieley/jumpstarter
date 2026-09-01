# JEP-0013 Phase 3 lab demo

This note records a live lab run of [JEP-0013](docs/source/contributing/jeps/JEP-0013-observability-telemetry-logs.md) Phase 3: exporter **PushLogs**, **MetricsStream** reverse-scrape, and **lease correlation**. Phase 3 does not export traces.

The session was captured as a single asciinema recording of the whole `jumpstarter:demo` tmux window (three panes). Playback is at the end of this file.

## Recording the whole window

Asciinema records one PTY. A tmux **client** attached to `jumpstarter:demo` is one PTY that already contains all three panes, borders, and titles. You do **not** need a recording per pane. A recording started **inside** a pane only captures that pane.

This lab used asciinema 3 with a second client at the same size as the existing attach (`131x89`, tmux `window-size latest`) so the layout did not shrink:

```bash
TERM=xterm-256color asciinema rec --headless --window-size 131x89 \
  --idle-time-limit 3 \
  --title "JEP-0013 Phase 3: PushLogs operation counts + MetricsStream during lease" \
  --command "tmux -S /tmp/tmux-1000/default attach-session -t jumpstarter \; select-window -t demo" \
  jep-0013-phase3-demo.cast
```

Use `attach-session -t jumpstarter` (session name), not `jumpstarter:demo`. Do not pass `-d` (that detaches the existing client). `--headless` needs `TERM=xterm-256color`; `TERM=dumb` makes tmux exit immediately.

## Pane layout

| Pane | Role | What ran |
|------|------|----------|
| **0** | p16v client | `jmp shell --client p16v --name sidekick-t450s` |
| **1** | sidekick exporter | `jmp run --exporter sidekick-t450s` (telemetry Route `telemetry.jumpstarter.jumpstarter-lab.apps.okd.kieley.io:443`) |
| **2** | metrics + logs | `oc` + `port-forward`, then `curl`, then the forward was stopped after each scrape |

## Sequence

1. Exporter came **Available**; telemetry attached; **MetricsStream registered**.
2. Interactive lease (30m) until `python ⚡sidekick-t450s`.
3. TFTP `10.0.0.212:69` and HTTP `http://10.0.0.212:8080`.
4. `j power on` then `j wol wake` (DUT MAC `50:7b:9d:07:eb:98`).
5. DUT PXE: TFTP `undionly.kpxe`, then iPXE `GET /boot.ipxe`, `/vmlinuz`, `/initrd.img`, `/rootfs.img` from `10.0.0.211`.
6. `j power off`, `exit` (afterLease + lease release).

Lease **`01a05ef5-d830-776a-bdbd-a54b177228ff`** (`p16v` → `sidekick-t450s`) was released at the end of the recorded run.

| Step | Result |
|------|--------|
| TFTP/HTTP | `10.0.0.212:69` / `http://10.0.0.212:8080` |
| `j power on` / `j wol wake` | both exit 0 |
| PXE | iPXE on `10.0.0.211` pulled `boot.ipxe`, `vmlinuz`, `initrd.img`, `rootfs.img` |
| Controller | `jumpstarter_lease_acquisitions_total{result="success"}` **5** |

## MetricsStream during the lease

Local exporter `/metrics` was scraped on the sidekick (`127.0.0.1:34163` for this run). Telemetry reverse-scrape was `GET /metrics` on `svc/jumpstarter-telemetry` via `oc port-forward` (stopped after each scrape).

| When | Local exporter `:34163` | Telemetry reverse-scrape |
|------|-------------------------|--------------------------|
| Idle, not leased | `active_sessions=0` | same (two scrapes in a row) |
| Leased, before driver ops | `active_sessions=1` | **same** |
| After `start` / `on` / `wake` | `operations_*` + duration histograms + `lease_id` **exemplars**, `active_sessions=1` | **dropped** — only `scrape_timeouts=0` and `dropped=0` |

The stream stays up (`scrape_timeouts` never incremented). After the first operation series with OpenMetrics exemplars (`# {lease_id="01a05ef5-…"} …`), telemetry `parseMetricFamilies` fails and **silently skips the whole snapshot** (`continue` on parse error). That is why exporter series disappear from `/metrics` as soon as real work happens.

Until the OpenMetrics exemplar parse is fixed, treat PushLogs as the operation ledger and local exporter `/metrics` as the ground truth for series. Reverse-scrape is reliable for `active_sessions` **until** exemplar-bearing operation metrics appear.

## PushLogs (lease-correlated operation counts)

PushLogs still carried the lease-correlated counts during the reverse-scrape gap:

- `operation`: `start`, `on`, `wake`, `get_host`, `get_port`, `get_url`
- `result`: `success`
- `driver_type`: `storage`, `network`, `power`, `other` (WoL)
- correlation: `lease=01a05ef5-d830-776a-bdbd-a54b177228ff`, `exporter=sidekick-t450s`, `namespace=jumpstarter-lab`

Telemetry health for the run: `jumpstarter_telemetry_dropped_total{destination="loki"}` **0**, `jumpstarter_scrape_timeouts_total` **0**.

## Asciinema recording

```bash
asciinema play -i 3 jep-0013-phase3-demo.cast
```

The file is asciicast v3, `131x89`, about 6.5 minutes of wall time (idle capped at 3s on play).

[`jep-0013-phase3-demo.cast`](jep-0013-phase3-demo.cast)

## Disclaimer

This demo was generated using Cursor Grok 4.6.
