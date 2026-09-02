# JEP-0013 Phase 3 lab demo

This note records a live lab run of [JEP-0013](docs/source/contributing/jeps/JEP-0013-observability-telemetry-logs.md) Phase 3: exporter **PushLogs**, **MetricsStream** reverse-scrape, **lease correlation**, and **parse-error observability** when OpenMetrics exemplars fail `parseMetricFamilies`. Phase 3 does not export traces.

The session was captured as a single asciinema recording of the whole `jumpstarter:demo` tmux window (three panes). Playback is at the end of this file.

Controller / telemetry image for this run: `jumpstarter-controller:0.10.0-dev-44-g0f6b0970`. Exporter venv: `jumpstarter 0.10.0.dev44+g0f6b09704`.

After rebasing the demo onto `#1058` (exporter name is no longer a Register label), MetricsStream must register with `identity=exporter_name`. The first `jmp run` in this recording used `identity=self.name` (`unknown`) and never appeared on reverse-scrape; the exporter was restarted with `identity=self.exporter_name` and then **MetricsStream registered**.

## Recording the whole window

Asciinema records one PTY. A tmux **client** attached to `jumpstarter:demo` is one PTY that already contains all three panes, borders, and titles. You do **not** need a recording per pane. A recording started **inside** a pane only captures that pane.

This lab used asciinema 3 with a second client at the same size as the existing attach (`211x55`, tmux `window-size latest`) so the layout did not shrink:

```bash
TERM=xterm-256color asciinema rec --headless --window-size 211x55 \
  --idle-time-limit 3 \
  --title "JEP-0013 Phase 3: PushLogs + MetricsStream parse-error observability" \
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

1. Exporter came **Available**; telemetry attached; after the identity restart, **MetricsStream registered**.
2. Interactive lease (30m) until `python ⚡sidekick-t450s`.
3. TFTP `10.0.0.212:69` and HTTP `http://10.0.0.212:8080`.
4. `j power on` then `j wol wake` (DUT MAC `50:7b:9d:07:eb:98`).
5. DUT PXE: TFTP `undionly.kpxe`, then iPXE `GET /boot.ipxe`, `/vmlinuz`, `/initrd.img`, `/rootfs.img` from `10.0.0.211`.
6. `j power off`, `exit` (afterLease + lease release).

Lease **`01a062ed-5395-7644-a80d-5ca018428637`** (`p16v` → `sidekick-t450s`) was released at the end of the recorded run.

| Step | Result |
|------|--------|
| TFTP/HTTP | `10.0.0.212:69` / `http://10.0.0.212:8080` |
| `j power on` / `j wol wake` | both exit 0 |
| PXE | iPXE on `10.0.0.211` pulled `boot.ipxe`, `vmlinuz`, `initrd.img`, `rootfs.img` |
| MetricsStream | registered for `sidekick-t450s`; `jumpstarter_scrape_timeouts_total` **0** |

## MetricsStream during the lease

Local exporter `/metrics` was scraped on the sidekick (`127.0.0.1:37479` for this run). Telemetry reverse-scrape was `GET /metrics` on `svc/jumpstarter-telemetry` via `oc port-forward` (stopped after each scrape).

Local series still label `exporter="unknown"` (Session still reads `Metadata.name` from labels, which `#1058` no longer sets). Reverse-scrape relabels the snapshot with the authenticated exporter name.

| When | Local exporter `:37479` | Telemetry reverse-scrape |
|------|-------------------------|--------------------------|
| Idle, not leased | `active_sessions=0` | same (`exporter="sidekick-t450s"`), two scrapes in a row |
| Leased, before driver ops | `active_sessions=1` | **same** |
| After `start` / `on` / `wake` | `operations_*` + duration histograms + `lease_id` **exemplars**, `active_sessions=1` | snapshot **omitted**; `jumpstarter_metrics_parse_errors_total{exporter="sidekick-t450s"}` **3**, then **4** on the wrap scrape; `scrape_timeouts=0`, `dropped=0` |

The stream stays up (`scrape_timeouts` never incremented). After the first operation series with OpenMetrics exemplars (`# {lease_id="01a062ed-…"} …`), telemetry `parseMetricFamilies` fails. The snapshot is still skipped so one exporter cannot 500 `/metrics`, but the failure is no longer silent: telemetry logs **error** `exporter metrics snapshot omitted` (exporter name + parse err) and increments `jumpstarter_metrics_parse_errors_total{exporter}`.

Parse-error counters on this telemetry pod were already **2** from the prior lab scrape; this run added two more (**3** after the first post-op scrape, **4** on wrap).

Until the OpenMetrics exemplar parse is fixed, treat exporter pane logs / local `/metrics` as the operation ledger and ground truth for series. Reverse-scrape is reliable for `active_sessions` **until** exemplar-bearing operation metrics appear.

See: 
[JEP-0013 DD-3: Metrics: Prometheus scrape of /metrics as the reference path](https://jumpstarter.dev/main/contributing/jeps/JEP-0013-observability-telemetry-logs.html#dd-3-metrics-prometheus-scrape-of-metrics-as-the-reference-path):
 **Exemplar trade-offs and details:**
 ..."Library support. Go client support is mature (prometheus/client_golang ≥ 1.16). The Python prometheus_client library is used on the exporter side to maintain local registries and produce generate_latest() output for the reverse-scrape path (see API / Protocol Changes). **Exemplar support in the Python library is functional but less complete than Go; if limitations arise, exemplar data can be sent as a sidecar field in MetricsScrapeResponse for the Telemetry service to merge server-side**"

## PushLogs (lease-correlated operation counts)

Exporter pane 1 (and local `/metrics` exemplars) carried the lease-correlated counts during the reverse-scrape gap:

- `operation`: `start`, `on`, `wake`, `get_host`, `get_port`, `get_url`, `off`
- `result`: `success`
- `driver_type`: `storage`, `network`, `power`, `other` (WoL)
- correlation: `lease=01a062ed-5395-7644-a80d-5ca018428637`, `exporter=sidekick-t450s`, `namespace=jumpstarter-lab`

Telemetry health for the run: `jumpstarter_telemetry_dropped_total{destination="loki"}` **0**, `jumpstarter_scrape_timeouts_total` **0**.

## Asciinema recording

```bash
asciinema play -i 3 jep-0013-phase3-demo.cast
```

The file is asciicast v3, `211x55`, about 14 minutes of wall time (idle capped at 3s on play, ~2.2 minutes).

[`jep-0013-phase3-demo.cast`](jep-0013-phase3-demo.cast)

## Disclaimer

This demo was generated using Cursor Grok 4.6.
