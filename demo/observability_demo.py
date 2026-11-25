#!/usr/bin/env python3
"""JEP-0013 Phase 4-6 observability demo.

Drives an exporter, then walks the telemetry, log, and dashboard artifacts for
each phase. Reuses demo/human_shell.py so the same script records a cast or
verifies without one.

    demo/observability_demo.py --phase 4          # record the phase 4 cast
    demo/observability_demo.py --phase all --no-cast --speed 8
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import uuid
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
REPO = DEMO_DIR.parent
sys.path.insert(0, str(DEMO_DIR))
sys.path.insert(0, str(DEMO_DIR / "observability"))

from human_shell import JMP_PROMPT, Asciicast, HumanShell  # noqa: E402
from observability import assertions as A  # noqa: E402

CAST_DIR = REPO / "docs" / "source" / "_static" / "casts"
CASTS = {
    "4": "jep-0013-phase4-driver-telemetry.cast",
    "5": "jep-0013-phase5-log-scraping.cast",
    "6": "jep-0013-phase6-dashboards-alerting.cast",
    "all": "jep-0013-phase456-integration.cast",
}

JMP = os.environ.get("DEMO_JMP", "jmp")
CLIENT = os.environ.get("DEMO_CLIENT", "demo-client")
EXPORTER = os.environ.get("DEMO_EXPORTER", "demo-power")
SELECTOR = os.environ.get("DEMO_SELECTOR", "example.com/demo=power")
LEASE = os.environ.get("DEMO_LEASE") or f"demo-{uuid.uuid4().hex[:4]}"
LEASE2 = os.environ.get("DEMO_LEASE2") or f"demo-{uuid.uuid4().hex[:4]}"
NS = A.NAMESPACE

PROXY = f"/api/v1/namespaces/{NS}/services"
TELEMETRY = f"kubectl -n {NS} get --raw {PROXY}/http:jumpstarter-telemetry:8080/proxy/metrics"
PROM_BASE = f"{PROXY}/http:prometheus-operated:9090/proxy"
LOKI_BASE = f"{PROXY}/http:loki:3100/proxy"
METRICS_GREP = (
    "jumpstarter_operations_total|jumpstarter_operation_duration_seconds_count|"
    "jumpstarter_operation_errors_total|jumpstarter_driver_power_transitions_total|"
    "jumpstarter_active_sessions"
)
LOKI_QUERY = (
    "%7Bnamespace%3D%22jumpstarter-lab%22%2Ccomponent%3D%22controller%22%7D"
)


def jq(program: str) -> str:
    """Pipe stdin through jq -r, quoting the program for the shell."""
    return " | jq -r " + shlex.quote(program)


def raw(path: str) -> str:
    """kubectl get --raw for one absolute API path, quoted for the shell."""
    return f"kubectl -n {NS} get --raw " + shlex.quote(path)


def preflight(phase: str) -> None:
    A.check_kube_context()
    if not (Path.home() / ".config/jumpstarter/clients" / f"{CLIENT}.yaml").exists():
        raise A.DemoFailure(f"missing client config {CLIENT}; run the login from quickstart.md")
    required = {
        "4": ["ServiceMonitorReady"],
        "5": ["ServiceMonitorReady"],
        "6": ["ServiceMonitorReady", "PrometheusRulesReady", "DashboardsReady"],
        "all": ["ServiceMonitorReady", "PrometheusRulesReady", "DashboardsReady"],
    }[phase]
    for cond in required:
        A.require_condition(cond)
    try:
        A.run(["jmp", "delete", "lease", LEASE], check=False, timeout=60)
    except FileNotFoundError:
        pass
    if phase == "all" and not A.reachable("http://localhost:8088/api/v1/health"):
        raise A.DemoFailure(
            "the Perses API is not reachable on http://localhost:8088; "
            "`make demo-observability-setup` leaves a forward running"
        )
    if A.kubectl("get", "exporter", EXPORTER, "-o",
                 'jsonpath={.status.conditions[?(@.type=="Online")].status}').strip() != "True":
        raise A.DemoFailure(
            f"exporter {EXPORTER} is not Online; start it with `jmp run --exporter {EXPORTER}`"
        )


def segment_phase4(sh: HumanShell) -> None:
    sh.marker("phase 4 - driver telemetry")
    sh.comment("this demo client skips TLS verification; a real deployment trusts the cluster CA")
    sh.comment("the exporter advertises itself, with labels a client can select on")
    sh.run(f"{JMP} get exporters -l {shlex.quote(SELECTOR)}", expect=[EXPORTER], timeout=120)
    sh.comment("a lease is the right to drive that machine for a while")
    sh.run(
        f"{JMP} create lease -l {shlex.quote(SELECTOR)} --duration 10m --lease-id {LEASE}",
        expect=[LEASE],
        timeout=300,
    )
    sh.enter(f"{JMP} shell --lease {LEASE}", prompt=JMP_PROMPT, timeout=300)
    sh.comment("a real driver operation: power on, then off")
    sh.run("j power on", timeout=120, allow_failure=True)
    sh.run("j power off", timeout=120, allow_failure=True)
    sh.leave()
    sh.run(f"{JMP} delete lease {LEASE}", timeout=120, allow_failure=True)

    sh.comment("what the exporter recorded for that operation")
    sh.run(
        f"{TELEMETRY} | grep -E {shlex.quote(METRICS_GREP)} | head -12",
        expect=["jumpstarter_operations_total"],
        timeout=120,
    )
    sh.comment("every operation is counted, labelled by driver type and result")
    sh.run(
        f"{TELEMETRY} | grep -E 'jumpstarter_driver_power_' | head -6",
        expect=["jumpstarter_driver_power_"],
        timeout=120,
    )
    sh.comment("driver-declared instruments sit next to the generic ones")
    sh.run(
        f"{TELEMETRY} | grep -A1 'jumpstarter_operations_total' | head -4",
        allow_failure=True,
        timeout=120,
    )


def segment_phase5(sh: HumanShell) -> None:
    sh.marker("phase 5 - logs, collected in the cluster")
    sh.comment("the operator labels the pods whose logs should be collected")
    sh.run(
        f"kubectl -n {NS} get pods -l jumpstarter.dev/log-scrape=true "
        "-L jumpstarter.dev/log-format --no-headers | head -5",
        expect=["json"],
        timeout=120,
    )
    sh.comment("the controller writes one JSON object per line")
    sh.run(
        f"kubectl -n {NS} logs deploy/jumpstarter-controller --tail=50 | grep '^{{' | tail -1 | jq -c .",
        expect=['"component"'],
        timeout=120,
    )
    sh.comment("the operator owns no shipper configuration; the cluster does")
    sh.run(f"kubectl -n {NS} get cm | grep -i shipper", refute="shipper", allow_failure=True,
           timeout=120)
    sh.comment("the shipper selects those labels and sends to the log store")
    sh.run(
        f"kubectl -n {NS} get cm vector -o jsonpath='{{.data.vector\\.yaml}}' | "
        "grep -E 'log-scrape|type: loki' | head -4",
        expect=["log-scrape", "type: loki"],
        timeout=120,
    )
    sh.comment("the store returns the record with the labels it promoted")
    sh.run(
        raw(f"{LOKI_BASE}/loki/api/v1/query_range?query={LOKI_QUERY}&limit=2")
        + jq(r'.data.result[0] | "labels: \(.stream|tojson)", '
             r'"message: \(.values[0][1]|fromjson|.message)"'),
        expect=["labels:", "message:", '"component":"controller"'],
        timeout=120,
    )


def segment_phase6(sh: HumanShell) -> None:
    sh.marker("phase 6 - dashboards and alerting")
    sh.comment("the operator reports which integrations it created")
    sh.run(
        f"kubectl -n {NS} get jumpstarter jumpstarter -o jsonpath="
        "'{range .status.conditions[*]}{.type}={.reason}{\"\\n\"}{end}' | "
        "grep -E 'ServiceMonitor|PrometheusRules|Dashboards'",
        expect=["ServiceMonitorReady=Created", "PrometheusRulesReady=Created",
                "DashboardsReady=Created"],
        timeout=120,
    )
    sh.comment("a service monitor, alert rules, and a dashboard")
    sh.run(
        f"kubectl -n {NS} get servicemonitor,prometheusrule,persesdashboard -o name",
        expect=["servicemonitor", "prometheusrule", "persesdashboard"],
        timeout=120,
    )
    sh.comment("Prometheus has loaded the starter alerts")
    sh.run(
        raw(f"{PROM_BASE}/api/v1/rules") + jq(
            '.data.groups[].rules[] | select(.name|startswith("Jumpstarter")) | .name'
        ),
        expect=["JumpstarterOperationErrors"],
        timeout=120,
    )
    sh.comment("the dashboard Perses serves queries the same metrics")
    sh.run(
        f"kubectl -n {NS} get persesdashboard jumpstarter-overview -o json | "
        "jq -r '.spec.config.panels | keys | length'",
        expect=["10"],
        timeout=120,
    )


def segment_integration(sh: HumanShell) -> None:
    sh.marker("phases 4, 5 and 6 - one operation, end to end")
    sh.comment("this demo client skips TLS verification; a real deployment trusts the cluster CA")
    sh.comment("one lease, one driver operation, seen four ways")
    sh.run(f"{JMP} create lease -l {shlex.quote(SELECTOR)} --duration 10m --lease-id {LEASE2}",
           expect=[LEASE2], timeout=300)
    sh.enter(f"{JMP} shell --lease {LEASE2}", prompt=JMP_PROMPT, timeout=300)
    sh.run("j power on", timeout=120, allow_failure=True)
    sh.run("j power off", timeout=120, allow_failure=True)
    sh.leave()
    sh.run(f"{JMP} delete lease {LEASE2}", timeout=120, allow_failure=True)

    sh.comment("phase 4: the exporter counts the operation and its result")
    sh.run(
        f"{TELEMETRY} | grep -E 'jumpstarter_operations_total' | head -4",
        expect=["jumpstarter_operations_total"],
        timeout=120,
    )
    sh.comment("phase 6: the same series is in Prometheus, where the rules query it")
    sh.run(
        raw(f'{PROM_BASE}/api/v1/query?query=jumpstarter_operations_total{{exporter="demo-power"}}')
        + jq(r'.data.result[] | "\(.metric.operation) \(.metric.result) \(.value[1])"'),
        expect=["on success", "off success"],
        timeout=120,
    )
    sh.comment("phase 6: the exporter is idle again, so its alert is now pending")
    sh.run(
        raw(f"{PROM_BASE}/api/v1/alerts")
        + jq(r'.data.alerts[]? | "\(.labels.alertname) \(.state)"'),
        expect=["JumpstarterExporterIdle"],
        retry_budget=180,
        retry_delay=15,
        timeout=120,
    )
    sh.comment("phase 6: Perses serves the dashboard built from those queries")
    sh.run(
        "curl -s http://localhost:8088/api/v1/projects/jumpstarter/dashboards/"
        "jumpstarter-overview | jq -r '.metadata.name, (.spec.panels | length)'",
        expect=["jumpstarter-overview", "10"],
        timeout=120,
    )
    sh.comment("phase 5: the log store has the same lease, tagged by exporter")
    sh.run(
        raw(f"{LOKI_BASE}/loki/api/v1/query_range"
            f'?query=%7Bexporter%3D%22{EXPORTER}%22%7D&limit=2')
        + jq(r'.data.result[0] | "labels: \(.stream|tojson)", '
             r'"message: \(.values[0][1]|fromjson|.message)"'),
        expect=["labels:", "message:"],
        timeout=120,
    )


SEGMENTS = {"4": segment_phase4, "5": segment_phase5, "6": segment_phase6,
            "all": lambda sh: (segment_phase4(sh), segment_phase5(sh), segment_phase6(sh),
                               segment_integration(sh))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phase", required=True, choices=list(SEGMENTS))
    parser.add_argument("--cast", default=None)
    parser.add_argument("--no-cast", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--keep", action="store_true", help="leave the lease/resources in place")
    args = parser.parse_args()

    cast_path = args.cast or str(CAST_DIR / CASTS[args.phase])
    cast = None if args.no_cast else Asciicast(cast_path, cols=110, rows=32)
    if cast:
        Path(cast_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        preflight(args.phase)
        venv_bin = str(REPO / "python" / ".venv" / "bin")
        env = dict(os.environ)
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
        sh = HumanShell(cast=cast, cols=110, rows=32, speed=args.speed, env=env)
        try:
            SEGMENTS[args.phase](sh)
        finally:
            sh.close()
    except A.DemoFailure as err:
        print(f"demo failed: {err}", file=sys.stderr)
        return 1
    finally:
        if cast:
            cast.close()
            print(f"recording written to {cast_path}")
    print("demo completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
