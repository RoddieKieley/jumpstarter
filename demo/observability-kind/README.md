# JEP-0013 Phase 5 — Kind observability demo

This demo exercises the complete JEP-0013 Phase 5 integration on a disposable
Kind cluster:

1. Prometheus Operator autodiscovery through `ServiceMonitor` resources.
2. Controller, Router, and Telemetry metrics targets.
3. Controller/Router log delivery through **Vector**, **Grafana Alloy**, and
   **Promtail**, one shipper at a time, using the operator-generated ConfigMap.
4. Exact Loki stream labels: `component`, `exporter` when present, and
   `namespace`.
5. JSON body preservation and credential separation.
6. Metrics disable/re-enable recovery.

The shipper DaemonSets are deliberately deployed by this demo from the
operator-generated ConfigMaps. The Jumpstarter operator publishes the
configuration and labels; it does not deploy or manage the shipper runtime.

## Prerequisites

- Linux or macOS with Docker or Podman
- `kind`, `kubectl`, `curl`, `jq`
- Network access to pull:
  - `kindest/node` for the Kind cluster
  - Prometheus Operator `v0.94.2`
  - Loki `3.7.9`
  - Vector `0.61.0`
  - Grafana Alloy `v1.21.3`
  - Promtail `v3.6.0`
  - BusyBox `1.36`

The demo uses the `jumpstarter` Kind cluster and the `jumpstarter-lab`
namespace. It assumes the repository is checked out at this demo branch.

## Run

From the repository root:

```sh
./demo/observability-kind/run.sh
```

The script:

- creates/deploys the Kind cluster and Jumpstarter operator through
  `make -C controller deploy-ci`, unless `SKIP_SETUP=1` is set;
- installs the pinned Prometheus Operator, Loki, and shipper RBAC;
- patches the Jumpstarter CR for the demo;
- runs Vector, Alloy, and Promtail sequentially;
- checks Loki labels/body and the generated ConfigMap for each shipper;
- checks metrics target health and disable/re-enable recovery;
- removes the temporary probe and shipper DaemonSets.

If the Jumpstarter operator and CR are already deployed and you only want to
run the observability part:

```sh
SKIP_SETUP=1 ./demo/observability-kind/run.sh
```

Useful overrides:

```sh
CONTAINER_TOOL=podman SKIP_SETUP=1 ./demo/observability-kind/run.sh
KUBECTL="kubectl --context kind-jumpstarter" ./demo/observability-kind/run.sh
```

## Expected result

The script prints a `PASS` line for each shipper:

```text
PASS: vector shipper delivered exact labels and JSON body
PASS: alloy shipper delivered exact labels and JSON body
PASS: promtail shipper delivered exact labels and JSON body
PASS: metrics targets are healthy
PASS: metrics disable/re-enable recovered within 120 seconds
```

It also prints the generated ConfigMap keys and the observed Loki stream
labels for each shipper.

## Cleanup

The demo leaves Loki, Prometheus Operator, and the Jumpstarter deployment in
place for inspection. To remove the cluster:

```sh
make -C controller clean
```

## Scope note

This is a generic Kubernetes/Kind demo. It does not require OpenShift, OLM,
RHOBS, or user-workload monitoring. It is intended to give PR reviewers a
repeatable local run of the Phase 5 log-shipper and Prometheus autodiscovery
paths.
