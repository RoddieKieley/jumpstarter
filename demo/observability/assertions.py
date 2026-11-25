"""Helpers for the JEP-0013 observability demo.

Everything here shells out to kubectl/curl so the recorded commands and the
verification path use exactly the same interfaces a viewer would.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
NAMESPACE = os.environ.get("DEMO_NAMESPACE", "jumpstarter-lab")
CR = os.environ.get("DEMO_CR", "jumpstarter")


class DemoFailure(RuntimeError):
    pass


def run(cmd: list[str], timeout: int = 120, check: bool = True) -> str:
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=timeout)
    if check and proc.returncode != 0:
        raise DemoFailure(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
    return proc.stdout


def kubectl(*args: str, **kw) -> str:
    return run(["kubectl", "-n", NAMESPACE, *args], **kw)


def kubectl_global(*args: str, **kw) -> str:
    return run(["kubectl", *args], **kw)


def reachable(url: str, timeout: int = 10) -> bool:
    """True when an HTTP endpoint answers; used for preflight, not assertions."""
    proc = subprocess.run(
        ["curl", "-sf", "-o", "/dev/null", url],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return proc.returncode == 0


def check_kube_context() -> None:
    script = REPO.parent / ".opencode" / "scripts" / "check-kube-context.sh"
    if script.exists():
        run(["bash", str(script)])


def condition(cond: str) -> str:
    out = kubectl(
        "get",
        f"jumpstarter/{CR}",
        "-o",
        "jsonpath={.status.conditions[?(@.type==\"" + cond + "\")].reason}",
    )
    return out.strip()


def require_condition(cond: str, reason: str = "Created") -> None:
    got = condition(cond)
    if got != reason:
        raise DemoFailure(f"{cond} is {got!r}, expected {reason!r}")


def service_proxy(service: str, port: int, path: str) -> str:
    return kubectl_global(
        "get",
        "--raw",
        f"/api/v1/namespaces/{NAMESPACE}/services/http:{service}:{port}/proxy/{path.lstrip('/')}",
    )


def prom_query(query: str) -> dict:
    body = service_proxy("prometheus-operated", 9090, f"api/v1/query?query={_quote(query)}")
    return json.loads(body)


def prom_rules() -> dict:
    return json.loads(service_proxy("prometheus-operated", 9090, "api/v1/rules"))


def prom_alerts() -> dict:
    return json.loads(service_proxy("prometheus-operated", 9090, "api/v1/alerts"))


def loki_query(query: str, limit: int = 20) -> dict:
    body = service_proxy(
        "loki",
        3100,
        f"loki/api/v1/query_range?query={_quote(query)}&limit={limit}",
    )
    return json.loads(body)


def telemetry_metrics() -> str:
    return service_proxy("jumpstarter-telemetry", 8080, "metrics")


def require_series(selector: str) -> None:
    if not re.search(re.escape(selector), telemetry_metrics()):
        raise DemoFailure(f"no telemetry series matching {selector!r}")


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


def dashboard_names() -> list[str]:
    return kubectl("get", "persesdashboard", "-o", "name", check=False).split()


def rule_names() -> list[str]:
    data = prom_rules()
    names = []
    for group in data.get("data", {}).get("groups", []):
        for rule in group.get("rules", []):
            if rule.get("name", "").startswith("Jumpstarter"):
                names.append(rule["name"])
    return names
