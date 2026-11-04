#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEMO_DIR="$ROOT/demo/observability-kind"
NS="${NS:-jumpstarter-lab}"
CR="${CR:-jumpstarter}"
PROM_NS="${PROM_NS:-prometheus-jumpstarter-demo}"
KUBECTL="${KUBECTL:-kubectl --context kind-jumpstarter}"
PROM_LOCAL_PORT="${PROM_LOCAL_PORT:-19090}"
LOKI_LOCAL_PORT="${LOKI_LOCAL_PORT:-13100}"
PROM_OPERATOR_VERSION="${PROM_OPERATOR_VERSION:-v0.94.2}"
PROM_OPERATOR_URL="https://github.com/prometheus-operator/prometheus-operator/releases/download/${PROM_OPERATOR_VERSION}/bundle.yaml"
PROM_CRDS_URL="https://github.com/prometheus-operator/prometheus-operator/releases/download/${PROM_OPERATOR_VERSION}/stripped-down-crds.yaml"
CONTAINER_TOOL="${CONTAINER_TOOL:-}"
PROM_URL="http://127.0.0.1:${PROM_LOCAL_PORT}"
LOKI_URL="http://127.0.0.1:${LOKI_LOCAL_PORT}"

PROM_PF_PID=""
LOKI_PF_PID=""
PROBE_FILE=""
PROBE_NAME=""
SHIPPER_DS=""

log() { printf '\n==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  set +e
  [[ -n "$PROM_PF_PID" ]] && kill "$PROM_PF_PID" 2>/dev/null || true
  [[ -n "$LOKI_PF_PID" ]] && kill "$LOKI_PF_PID" 2>/dev/null || true
  [[ -n "$PROBE_FILE" ]] && rm -f "$PROBE_FILE"
  if [[ -n "$PROBE_NAME" ]]; then
    $KUBECTL delete pod -n "$NS" "$PROBE_NAME" --ignore-not-found >/dev/null 2>&1 || true
  fi
  if [[ -n "$SHIPPER_DS" ]]; then
    $KUBECTL delete daemonset -n "$NS" "$SHIPPER_DS" --ignore-not-found >/dev/null 2>&1 || true
  fi
  $KUBECTL patch jumpstarter -n "$NS" "$CR" --type=merge \
    -p '{"spec":{"telemetry":{"metrics":{"serviceMonitor":true},"logging":{"shipper":{"type":"vector"}}}}}' \
    >/dev/null 2>&1 || true
}
trap cleanup EXIT

require() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

wait_cr_condition() {
  local type=$1 want=$2
  local current
  for _ in $(seq 1 90); do
    current=$($KUBECTL get jumpstarter -n "$NS" "$CR" -o json 2>/dev/null \
      | jq -r --arg t "$type" '.status.conditions[]? | select(.type==$t) | "\(.status) \(.reason)"' 2>/dev/null || true)
    [[ "$current" == "$want" ]] && return 0
    sleep 2
  done
  fail "timed out waiting for $type=$want (last: ${current:-not found})"
}

wait_http() {
  local url=$1
  for _ in $(seq 1 60); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  fail "timed out waiting for $url"
}

active_targets() {
  curl -fsS "$PROM_URL/api/v1/targets?state=active" \
    | jq --arg ns "$NS" '[.data.activeTargets[] | select(.labels.namespace==$ns)] | length'
}

healthy_targets() {
  curl -fsS "$PROM_URL/api/v1/targets?state=active" \
    | jq --arg ns "$NS" '[.data.activeTargets[] | select(.labels.namespace==$ns and .health=="up")] | length'
}

wait_target_count() {
  local want=$1
  for _ in $(seq 1 60); do
    [[ "$(active_targets)" == "$want" ]] && return 0
    sleep 2
  done
  fail "timed out waiting for $want active targets (got $(active_targets))"
}

wait_healthy_targets() {
  local want=$1
  for _ in $(seq 1 60); do
    [[ "$(healthy_targets)" == "$want" ]] && return 0
    sleep 2
  done
  fail "timed out waiting for $want healthy targets (got $(healthy_targets))"
}

wait_loki_query() {
  local query=$1
  local start_ns=$(( ( $(date +%s) - 900 ) * 1000000000 ))
  local end_ns response
  for _ in $(seq 1 90); do
    end_ns=$(( $(date +%s) * 1000000000 ))
    response=$(curl -fsS --get --data-urlencode "query=$query" \
      --data-urlencode "start=$start_ns" --data-urlencode "end=$end_ns" \
      --data-urlencode 'limit=5' "$LOKI_URL/loki/api/v1/query_range")
    if echo "$response" | jq -e --arg ns "$NS" \
      '[.data.result[] | select(.stream.component=="controller" and .stream.exporter=="demo-board" and .stream.namespace==$ns) | .values[] | select(.[1] | fromjson? | .lease_id != null)] | length > 0' \
      >/dev/null 2>&1; then
      echo "$response" | jq '{status, streams:(.data.result|length), sample:((.data.result // [])[:2] | map({labels:.stream, values:(.values[:2])}))}'
      return 0
    fi
    sleep 2
  done
  echo "timed out waiting for Loki query: $query" >&2
  return 1
}

ensure_prometheus_operator() {
  if $KUBECTL get deployment prometheus-operator -n default >/dev/null 2>&1; then
    log "Prometheus Operator already installed"
    return
  fi
  log "Installing Prometheus Operator ${PROM_OPERATOR_VERSION}"
  $KUBECTL apply --server-side --force-conflicts -f "$PROM_CRDS_URL" >/dev/null
  $KUBECTL apply --server-side --force-conflicts -f "$PROM_OPERATOR_URL" >/dev/null
  $KUBECTL wait --for=condition=available deployment/prometheus-operator -n default --timeout=180s
}

start_port_forwards() {
  local prom_pod
  prom_pod=$($KUBECTL -n "$PROM_NS" get pod -l prometheus=jumpstarter -o jsonpath='{.items[0].metadata.name}')
  [[ -n "$prom_pod" ]] || fail "Prometheus pod not found in $PROM_NS"

  $KUBECTL -n "$PROM_NS" port-forward "pod/$prom_pod" "${PROM_LOCAL_PORT}:9090" \
    >/tmp/jumpstarter-observability-prometheus-port-forward.log 2>&1 &
  PROM_PF_PID=$!
  $KUBECTL -n "$NS" port-forward svc/loki "${LOKI_LOCAL_PORT}:3100" \
    >/tmp/jumpstarter-observability-loki-port-forward.log 2>&1 &
  LOKI_PF_PID=$!

  wait_http "$PROM_URL/api/v1/query?query=1"
  wait_http "$LOKI_URL/loki/api/v1/labels"
}

shipper_config_key() {
  case "$1" in
    vector) echo "vector.yaml" ;;
    alloy) echo "alloy.alloy" ;;
    promtail) echo "promtail.yaml" ;;
    *) fail "unknown shipper: $1" ;;
  esac
}

shipper_daemonset() {
  case "$1" in
    vector) echo "demo-vector-shipper" ;;
    alloy) echo "demo-alloy-shipper" ;;
    promtail) echo "demo-promtail-shipper" ;;
    *) fail "unknown shipper: $1" ;;
  esac
}

set_shipper() {
  local type=$1
  $KUBECTL patch jumpstarter -n "$NS" "$CR" --type=merge \
    -p "{\"spec\":{\"telemetry\":{\"enabled\":true,\"loki\":{\"url\":\"http://loki:3100/loki/api/v1/push\"},\"logging\":{\"shipper\":{\"type\":\"$type\"}},\"metrics\":{\"serviceMonitor\":true}}}}" >/dev/null
  wait_cr_condition LogShipperReady "True Created"
}

create_probe() {
  local shipper=$1 marker=$2 ts
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  PROBE_NAME="demo-log-probe-${shipper}"
  PROBE_FILE=$(mktemp)
  cat >"$PROBE_FILE" <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ${PROBE_NAME}
  namespace: ${NS}
  labels:
    jumpstarter.dev/log-scrape: "true"
    component: controller
spec:
  restartPolicy: Never
  tolerations:
    - key: node-role.kubernetes.io/control-plane
      operator: Exists
      effect: NoSchedule
    - key: node-role.kubernetes.io/master
      operator: Exists
      effect: NoSchedule
  containers:
    - name: log-source
      image: busybox:1.36
      command: ["/bin/sh", "-c"]
      args:
        - |
          while true; do
            printf '%s\n' '{"ts":"${ts}","level":"info","msg":"observability demo ${shipper}","component":"controller","exporter":"demo-board","lease_id":"${marker}","client":"demo-client","build_id":"demo-build"}'
            sleep 2
          done
EOF
  $KUBECTL delete pod -n "$NS" "$PROBE_NAME" --ignore-not-found >/dev/null 2>&1 || true
  $KUBECTL apply -f "$PROBE_FILE" >/dev/null
  $KUBECTL wait -n "$NS" --for=condition=Ready "pod/$PROBE_NAME" --timeout=60s
}

cleanup_probe() {
  if [[ -n "$PROBE_NAME" ]]; then
    $KUBECTL delete pod -n "$NS" "$PROBE_NAME" --ignore-not-found >/dev/null 2>&1 || true
    PROBE_NAME=""
  fi
}

verify_shipper() {
  local shipper=$1 marker key ds
  key=$(shipper_config_key "$shipper")
  ds=$(shipper_daemonset "$shipper")
  marker="demo-${shipper}-$(date +%s)"

  log "Configuring shipper type: $shipper"
  set_shipper "$shipper"

  $KUBECTL get configmap -n "$NS" jumpstarter-log-shipper -o json \
    | jq -e --arg k "$key" '.data[$k] | length > 0' >/dev/null \
    || fail "ConfigMap does not contain $key"

  log "Deploying $shipper DaemonSet"
  SHIPPER_DS="$ds"
  $KUBECTL apply -f "$DEMO_DIR/shippers/${shipper}.yaml" >/dev/null
  $KUBECTL rollout status "daemonset/$ds" -n "$NS" --timeout=180s

  log "Emitting a known log line through $shipper"
  create_probe "$shipper" "$marker"
  wait_loki_query "{component=\"controller\",namespace=\"$NS\"} |= \"$marker\""
  cleanup_probe
  $KUBECTL delete daemonset -n "$NS" "$ds" --ignore-not-found >/dev/null 2>&1 || true
  SHIPPER_DS=""
  echo "PASS: $shipper shipper delivered exact labels and JSON body"
}

check_credentials() {
  local key
  for d in jumpstarter-controller jumpstarter-router-0 jumpstarter-telemetry; do
    if $KUBECTL get deployment -n "$NS" "$d" -o json 2>/dev/null \
      | jq -e '[.spec.template.spec.containers[].env[]?.name] | any(. | test("LOKI"; "i"))' >/dev/null 2>&1; then
      fail "$d contains a Loki credential environment variable"
    fi
  done

  for key in vector.yaml alloy.alloy promtail.yaml; do
    if $KUBECTL get configmap -n "$NS" jumpstarter-log-shipper -o json 2>/dev/null \
      | jq -r --arg k "$key" '.data[$k] // empty' \
      | grep -qiE 'password|token|username|secret'; then
      fail "generated shipper ConfigMap key $key contains credential-like text"
    fi
  done
}

check_metrics() {
  log "Checking Prometheus target health"
  wait_target_count 3
  wait_healthy_targets 3
  curl -fsS "$PROM_URL/api/v1/targets?state=active" \
    | jq --arg ns "$NS" '{targets:[.data.activeTargets[] | select(.labels.namespace==$ns) | {job:.labels.job,health,lastScrape,scrapeUrl}]}'
  echo "PASS: metrics targets are healthy"
}

check_metrics_lifecycle() {
  local start elapsed
  log "Disabling metrics autodiscovery"
  $KUBECTL patch jumpstarter -n "$NS" "$CR" --type=merge \
    -p '{"spec":{"telemetry":{"metrics":{"serviceMonitor":false}}}}' >/dev/null
  wait_cr_condition ServiceMonitorReady "False Disabled"
  wait_target_count 0
  echo "ServiceMonitorReady: False Disabled; active targets: 0"

  log "Re-enabling metrics autodiscovery"
  start=$(date +%s)
  $KUBECTL patch jumpstarter -n "$NS" "$CR" --type=merge \
    -p '{"spec":{"telemetry":{"metrics":{"serviceMonitor":true}}}}' >/dev/null
  wait_cr_condition ServiceMonitorReady "True Created"
  wait_target_count 3
  wait_healthy_targets 3
  elapsed=$(( $(date +%s) - start ))
  echo "target recovery seconds: $elapsed"
  [[ "$elapsed" -le 120 ]] || fail "target recovery exceeded 120 seconds"
  echo "PASS: metrics disable/re-enable recovered within 120 seconds"
}

main() {
  require kubectl
  require curl
  require jq

  if [[ -z "$CONTAINER_TOOL" ]]; then
    if command -v podman >/dev/null 2>&1; then
      CONTAINER_TOOL=podman
    else
      CONTAINER_TOOL=docker
    fi
  fi
  export CONTAINER_TOOL

  if [[ "${SKIP_SETUP:-0}" != "1" ]]; then
    log "Deploying Jumpstarter and its Kind cluster"
    (cd "$ROOT" && make -C controller deploy-ci)
  fi

  $KUBECTL get namespace "$NS" >/dev/null 2>&1 || $KUBECTL create namespace "$NS" >/dev/null
  $KUBECTL get jumpstarter -n "$NS" "$CR" >/dev/null 2>&1 \
    || fail "Jumpstarter CR $NS/$CR not found; run without SKIP_SETUP or deploy the operator first"

  ensure_prometheus_operator
  log "Applying Loki, Prometheus, and shipper RBAC"
  $KUBECTL apply -f "$DEMO_DIR/loki.yaml" >/dev/null
  $KUBECTL apply -f "$DEMO_DIR/prometheus.yaml" >/dev/null
  $KUBECTL apply -f "$DEMO_DIR/shipper-rbac.yaml" >/dev/null
  $KUBECTL rollout status deployment/loki -n "$NS" --timeout=180s
  $KUBECTL wait -n "$PROM_NS" --for=condition=Ready pod -l prometheus=jumpstarter --timeout=180s

  start_port_forwards

  log "Configuring Telemetry, metrics, and Vector"
  $KUBECTL patch jumpstarter -n "$NS" "$CR" --type=merge \
    -p '{"spec":{"telemetry":{"enabled":true,"loki":{"url":"http://loki:3100/loki/api/v1/push"},"metrics":{"serviceMonitor":true},"logging":{"shipper":{"type":"vector"}}}}}' >/dev/null
  wait_cr_condition ServiceMonitorReady "True Created"
  wait_cr_condition LogShipperReady "True Created"

  for shipper in vector alloy promtail; do
    verify_shipper "$shipper"
  done

  check_credentials
  check_metrics
  check_metrics_lifecycle

  echo
  echo "Demo complete. Loki and Prometheus remain running for inspection."
  echo "Clean up with: make -C controller clean"
}

main "$@"
