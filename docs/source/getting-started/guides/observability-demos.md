# Observability demos

JEP-0013 gives a Jumpstarter deployment three views of the same work: metrics
that drivers publish, structured logs collected by the cluster, and the alerting
and dashboards the operator generates from those metrics. The recordings below
run the commands from the guides against a Kind cluster with the reference mock
exporter, so every command on screen is a command you can run yourself.

Each recording plays with its own narration and is chaptered by phase. To play
one locally, fetch the file from `docs/source/_static/casts/` and run
`asciinema play <file>`. `demo/README.md` describes the harness that produced
them.

## Phase 4: driver telemetry

The exporter publishes what its drivers do. Watch for the exporter advertising
itself with selectable labels, a lease being taken out, and a real power
operation. The metric output then shows the generic operation counters labelled
by driver type and result, the power driver's own instruments beside them, and
an exemplar holding the lease id that produced the sample.

```{raw} html
<div id="cast-phase4"></div>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    AsciinemaPlayer.create(
      '../../_static/casts/jep-0013-phase4-driver-telemetry.cast',
      document.getElementById('cast-phase4'),
      {
        fit: 'width',
        autoPlay: false,
        preload: false,
        idleTimeLimit: 2,
        rows: 25,
        speed: 1,
        loop: false,
        poster: 'npt:2:28'
      }
    );
  });
</script>
```

## Phase 5: logs, collected in the cluster

Jumpstarter does not run a log shipper itself. The operator labels the pods whose
logs should be collected, and a cluster-owned shipper selects those labels. The
recording shows the discovery labels, a structured log record from the
controller, evidence that the operator owns no shipper configuration, and a
query against the log store that returns the labels the shipper promoted.

```{raw} html
<div id="cast-phase5"></div>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    AsciinemaPlayer.create(
      '../../_static/casts/jep-0013-phase5-log-scraping.cast',
      document.getElementById('cast-phase5'),
      {
        fit: 'width',
        autoPlay: false,
        preload: false,
        idleTimeLimit: 2,
        rows: 25,
        speed: 1,
        loop: false,
        poster: 'npt:1:46'
      }
    );
  });
</script>
```

## Phase 6: dashboards and alerting

When the optional integrations are enabled, the operator reports what it created
and keeps it in step with the deployment. The recording shows the readiness
conditions, the generated objects, the starter alerts Prometheus has loaded, and
the dashboard Perses serves.

```{raw} html
<div id="cast-phase6"></div>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    AsciinemaPlayer.create(
      '../../_static/casts/jep-0013-phase6-dashboards-alerting.cast',
      document.getElementById('cast-phase6'),
      {
        fit: 'width',
        autoPlay: false,
        preload: false,
        idleTimeLimit: 2,
        rows: 25,
        speed: 1,
        loop: false,
        poster: 'npt:1:05'
      }
    );
  });
</script>
```

## All three phases together

One lease, one driver operation, followed all the way out: the exporter counts
it, Prometheus has the same series for its rules, the exporter's idle alert
changes state, the dashboard Perses serves is built from those queries, and the
log store holds the same lease with the exporter attached.

```{raw} html
<div id="cast-integration"></div>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    AsciinemaPlayer.create(
      '../../_static/casts/jep-0013-phase456-integration.cast',
      document.getElementById('cast-integration'),
      {
        fit: 'width',
        autoPlay: false,
        preload: false,
        idleTimeLimit: 2,
        rows: 25,
        speed: 1,
        loop: false,
        poster: 'npt:7:44'
      }
    );
  });
</script>
```

## The board workflow

The end-to-end hardware demo, recorded before JEP-0013: a real board is flashed,
booted, tested, and handed back through a lease. It is the workflow the
observability layers above are reporting on.

```{raw} html
<div id="cast-board"></div>
<script>
  document.addEventListener('DOMContentLoaded', function() {
    AsciinemaPlayer.create(
      '../../_static/demo.cast',
      document.getElementById('cast-board'),
      {
        fit: 'width',
        autoPlay: false,
        preload: false,
        idleTimeLimit: 2,
        rows: 25,
        speed: 1,
        loop: false,
        poster: 'npt:0:05'
      }
    );
  });
</script>
```
