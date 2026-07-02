# runs/

Output of `reserve` commands: one folder per run, named `<run_id>/`, each
holding that run's JSON outputs (`validation.json`, `fit.json`,
`diagnostics.json`, `sensitivity.json`) and a `manifest.json` audit record
(schema in [ARCHITECTURE.md](../ARCHITECTURE.md#manifest)).

Everything under this directory except this file is gitignored — run output
is regenerable from `examples/` and is not committed.
