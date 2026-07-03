---
description: Peer-review an existing run for weaknesses, using only computed outputs
argument-hint: <run-id>
---

Peer-review run `$1` adversarially — the job is to find weaknesses, not
confirm the fit looks fine. Base every observation on a file already under
`runs/$1/`; if a file you'd need doesn't exist yet, say which command
would produce it rather than reasoning about output you don't have. Never
speculate about the underlying data or real-world portfolio beyond what
those files show.

Look specifically for:

- **Unresolved flags** — any `diagnostics.json: tests[].verdict == "warn"`
  whose `prescribed_actions` haven't actually been run (check
  `manifest.json: outputs` for whether `sensitivity.json` exists yet).
- **Sensitivity range width** — if `sensitivity.json` exists, how large is
  `range.ibnr_max - range.ibnr_min` relative to `range.base_ibnr`? State the
  numbers plainly; don't editorialize about what counts as "too wide"
  beyond what the `sensitivity-analysis` skill already frames.
- **Null totals** — any `null` in `fit.json`/`sensitivity.json` totals.
  Per `sensitivity-analysis`: null means undefined, never zero — name which
  parameter and which origin/transition made it inestimable, and frame it
  as a data-thinness finding, not a fit failure.
- **Data-thinness generally** — origins with few observed periods
  (`fit.json: by_origin[]` cross-referenced against `validation.json:
  dimensions`) drive the largest standard errors and the least reliable
  perturbation results; call these out by origin.

For each weakness found, propose the specific additional `reserve`
invocation that would probe it further — not "investigate more." If
nothing in the run's own files supports a concern, don't invent one to
seem thorough.
