#!/usr/bin/env bash
# Push the operator-generated dashboard and the demo datasources into the
# Perses chart server. Requires a reachable Perses API (PERSES_URL) and the
# PersesDashboard CR created by the Jumpstarter operator.
set -euo pipefail

NS=${PERSES_NAMESPACE:-jumpstarter-lab}
URL=${PERSES_URL:-http://localhost:8088}
DASHBOARD=${PERSES_DASHBOARD:-jumpstarter-overview}
PROJECT=${PERSES_PROJECT:-jumpstarter}

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

kubectl -n "$NS" get persesdashboard "$DASHBOARD" -o jsonpath='{.spec.config}' > "$tmp"
[[ -s "$tmp" ]] || { echo "dashboard $DASHBOARD has no spec.config" >&2; exit 1; }

python3 - "$URL" "$PROJECT" "$tmp" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base, project, config_path = sys.argv[1], sys.argv[2], sys.argv[3]
config = json.load(open(config_path))


def post(path: str, obj: dict) -> None:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"{path}: {resp.status}")
    except urllib.error.HTTPError as err:
        if err.code == 409:
            print(f"{path}: exists")
            return
        print(f"{path}: {err.code} {err.read()[:300]!r}", file=sys.stderr)
        raise


post("/api/v1/projects", {"kind": "Project", "metadata": {"name": project}, "spec": {}})
post(
    "/api/v1/globaldatasources",
    {
        "kind": "GlobalDatasource",
        "metadata": {"name": "prometheus"},
        "spec": {
            "default": True,
            "plugin": {
                "kind": "PrometheusDatasource",
                "spec": {"directUrl": "http://prometheus-operated.jumpstarter-lab.svc.cluster.local:9090"},
            },
        },
    },
)
post(
    "/api/v1/globaldatasources",
    {
        "kind": "GlobalDatasource",
        "metadata": {"name": "loki"},
        "spec": {
            "default": False,
            "plugin": {
                "kind": "LokiDatasource",
                "spec": {"directUrl": "http://loki.jumpstarter-lab.svc.cluster.local:3100"},
            },
        },
    },
)
post(
    f"/api/v1/projects/{project}/dashboards",
    {
        "kind": "Dashboard",
        "metadata": {"name": "jumpstarter-overview", "project": project},
        "spec": config,
    },
)
PY

echo "perses provisioning complete: $URL/projects/$PROJECT/dashboards/$DASHBOARD"
