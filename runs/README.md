# runs/

Output of `reserve` commands: one folder per run, named `<run_id>/`, each
holding that run's JSON outputs (`validation.json`, `fit.json`,
`diagnostics.json`, `sensitivity.json`), a rendered `report.html` if
`reserve report` has been run, a `manifest.json` audit record (schema in
[ARCHITECTURE.md](../ARCHITECTURE.md#manifest)), and — for a `fit`-written
run — an `inputs/` folder holding a snapshot copy of the input CSV
(`ARCHITECTURE.md`'s `inputs[].snapshot`).

Everything under this directory except this file is gitignored — run output
is regenerable from `examples/` and is not committed.
