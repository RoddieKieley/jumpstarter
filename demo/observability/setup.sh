#!/usr/bin/env bash
# Bring a Kind cluster to the JEP-0013 observability demo state.
#
# Installs: Prometheus Operator (pinned), a Prometheus instance, single-binary
# Loki, the Vector shipper, the PersesDashboard CRD, and a telemetry-enabled
# Jumpstarter CR with metrics, starter rules, and dashboards enabled.
#
# Prerequisites: podman + kind, the workspace's pinned KUBECONFIG, and the
# operator image buildable from this tree (the script deploys the controller
# when no Jumpstarter CR exists yet).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFESTS="$REPO_ROOT/demo/observability/manifests"
NS=jumpstarter-lab
CR=jumpstarter

PROM_OPERATOR_URL="https://github.com/prometheus-operator/prometheus-operator/releases/download/v0.94.2/bundle.yaml"
PROM_CRDS_URL="https://github.com/prometheus-operator/prometheus-operator/releases/download/v0.94.2/stripped-down-crds.yaml"
PROM_OPERATOR_SHA256="045754c91469cccb27d7832168a5b5f0448188bcb3513f74a13c76c9079d654b"
PROM_CRDS_SHA256="e02e48c760e86aa1b5888205d1670c7baa42abe86211f8408b7fb18651203ede"

log() { printf '\033[0;32m[setup]\033[0m %s\n' "$*"; }
fail() { printf '\033[0m[setup] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -n "${KUBECONFIG:-}" ]] || fail "KUBECONFIG is unset; source .opencode/session-env.sh"
bash "$REPO_ROOT/../.opencode/scripts/check-kube-context.sh" >/dev/null \
  || fail "pinned kube context check failed"

TMPDIR_DL="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_DL"' EXIT

fetch_pinned() {
  local url=$1 sha=$2 out=$3
  # The demo shell may carry SSL_CERT_FILE from the e2e env (the dex CA), which
  # does not sign public hosts; use the system trust store for the downloads.
  env -u SSL_CERT_FILE -u REQUESTS_CA_BUNDLE curl -fsSL "$url" -o "$out"
  printf '%s  %s\n' "$sha" "$out" | sha256sum -c - >/dev/null \
    || fail "checksum mismatch for $url"
}

log "installing the Prometheus Operator (v0.94.2, pinned)"
fetch_pinned "$PROM_OPERATOR_URL" "$PROM_OPERATOR_SHA256" "$TMPDIR_DL/operator.yaml"
fetch_pinned "$PROM_CRDS_URL" "$PROM_CRDS_SHA256" "$TMPDIR_DL/crds.yaml"
kubectl apply --server-side -f "$TMPDIR_DL/crds.yaml" >/dev/null
kubectl apply --server-side -f "$TMPDIR_DL/operator.yaml" >/dev/null
kubectl -n default rollout status deploy/prometheus-operator --timeout=300s >/dev/null

log "ensuring the Jumpstarter operator and CR exist"
if ! kubectl -n "$NS" get "jumpstarter/$CR" >/dev/null 2>&1; then
  OPERATOR_ENABLE_TELEMETRY=true make -C "$REPO_ROOT/controller" deploy
fi

log "installing Prometheus, Loki, and Vector"
kubectl apply -f "$MANIFESTS/prometheus.yaml" >/dev/null
kubectl apply -f "$MANIFESTS/loki.yaml" >/dev/null
kubectl apply -f "$MANIFESTS/vector.yaml" >/dev/null

log "installing the Perses server (chart 0.24.0 / Perses v0.55.0)"
helm repo add perses https://perses.github.io/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null
helm upgrade --install perses perses/perses -n "$NS" --version 0.24.0 \
  --set fullnameOverride=perses --wait --timeout 5m >/dev/null

log "refreshing the Jumpstarter CRD so the telemetry fields are accepted"
kubectl apply -f "$REPO_ROOT/controller/deploy/operator/config/crd/bases/operator.jumpstarter.dev_jumpstarters.yaml" >/dev/null

log "enabling metrics autodiscovery, starter rules, and dashboards on the CR"
kubectl -n "$NS" patch "jumpstarter/$CR" --type merge -p '{
  "spec": {"telemetry": {"metrics": {
    "serviceMonitor": true,
    "prometheusRules": true,
    "dashboards": true,
    "persesInstanceSelector": {"app.kubernetes.io/name": "perses"}
  }}}
}' >/dev/null

log "waiting for the stack"
kubectl -n "$NS" rollout status deploy/loki --timeout=300s >/dev/null
kubectl -n "$NS" rollout status ds/vector --timeout=300s >/dev/null
kubectl -n "$NS" wait --for=condition=Ready pod -l app.kubernetes.io/name=prometheus --timeout=300s >/dev/null

for cond in ServiceMonitorReady PrometheusRulesReady DashboardsReady; do
  for _ in $(seq 1 60); do
    state=$(kubectl -n "$NS" get "jumpstarter/$CR" \
      -o jsonpath="{.status.conditions[?(@.type==\"$cond\")].reason}" 2>/dev/null || true)
    [[ "$state" == "Created" ]] && break
    sleep 2
  done
  [[ "$state" == "Created" ]] || fail "$cond is '$state', expected Created"
  log "$cond=Created"
done

log "waiting for the generated PersesDashboard"
for _ in $(seq 1 60); do
  kubectl -n "$NS" get persesdashboard jumpstarter-overview >/dev/null 2>&1 && break
  sleep 2
done
kubectl -n "$NS" get persesdashboard jumpstarter-overview >/dev/null 2>&1 \
  || fail "PersesDashboard jumpstarter-overview was not created"

log "provisioning the dashboard and datasources into Perses"
if curl -sf -o /dev/null http://localhost:8088/api/v1/health; then
  log "reusing the Perses forward on http://localhost:8088"
else
  # The demo and provision-perses.sh both talk to the API through this address,
  # so the forward is started in the background and left running.
  kubectl -n "$NS" port-forward svc/perses 8088:8080 >/dev/null 2>&1 &
  for _ in $(seq 1 30); do
    curl -sf -o /dev/null http://localhost:8088/api/v1/health && break
    sleep 1
  done
  curl -sf -o /dev/null http://localhost:8088/api/v1/health \
    || fail "Perses is not reachable on http://localhost:8088"
  log "started a background forward to svc/perses on http://localhost:8088"
fi
PERSES_URL=http://localhost:8088 bash "$REPO_ROOT/demo/observability/provision-perses.sh"

log "ready: Perses http://localhost:8088 (forward), Prometheus prometheus-operated.$NS:9090, Loki loki.$NS:3100"
log "the Perses forward is left running; stop it with: pkill -f 'port-forward svc/perses'"
