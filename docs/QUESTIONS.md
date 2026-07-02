# Open questions on docs/cli-spec.md v0.1

Recorded per CLAUDE.md instruction: spec is frozen, so anything not fully
determined by the text is stopped on and asked rather than resolved silently.
Each item below has a proposed default. **Status: Q1–Q3 confirmed by Ivan
Perincic 2026-07-02 — all proposed defaults approved as written. Q2 and Q3
are now codified as normative text in `docs/cli-spec.md` v0.1.1 (see its
changelog); Q1 remains a design decision recorded here only, since it does
not change any command's documented input/output contract.**

## Q1. Do `diagnostics` and `sensitivity` write into the *same* run folder as
the `fit` they operate on, or mint a new run_id each time?

Evidence for "same folder": the ARCHITECTURE.md manifest example shows one
manifest with `"outputs": ["fit.json", "diagnostics.json"]` — both listed
under a single run. Evidence for "method-scoped id": the run_id format
(`timestamp + input tag + short hash`) bakes the method (`mack`) into the
string, which only `fit` would know at generation time.

**Proposed default:** `fit` mints the run_id and folder. `reserve
diagnostics <run-id>` and `reserve sensitivity <run-id>` take that existing
id as their positional argument, write their file into the *same* folder
(`runs/<run-id>/diagnostics.json`, `.../sensitivity.json`), and update the
existing `manifest.json` in place — appending to `outputs` and overwriting
`exit_code` with the latest command's code. `validate` run standalone (not
via `fit`'s internal check) mints its own separate run_id/folder, since it
has no method to embed and no fit to attach to.

## Q2. Does `fit`'s internal hard-rule validation persist anything when it
fails?

`fit` "runs validate first... refuses with exit 2 if validation fails." It's
not stated whether this internal check writes a run folder + `validation.json`
+ manifest (exit_code 2) before refusing, or fails without persisting
anything (no folder created at all).

**Proposed default:** persist. `fit` mints its run_id/folder up front; if
internal validation fails, it writes `validation.json` (identical shape to
the standalone `validate` command's output) into that folder, writes
`manifest.json` with `exit_code: 2` and `outputs: ["validation.json"]`, and
exits 2 — no `fit.json`. This matches rule 1 in CLAUDE.md ("every figure
must come from a file under runs/") and keeps every invocation, including
failed ones, in the audit trail.

## Q3. What does "declared" mean in the `basis_consistent` check ("cumulative
vs incremental **declared**/inferred")?

No command signature in the frozen spec has a `--basis` flag, and no CSV
schema is defined anywhere in the frozen docs, so there is currently no
mechanism by which basis could be *declared* rather than inferred.

**Proposed default:** basis is always inferred (monotone non-decreasing
per origin ⇒ cumulative, else incremental) for v0.1. The `basis_consistent`
check verifies the inference isn't internally contradictory (e.g. mixed
monotone/non-monotone origins that no single basis explains) rather than
checking inferred-vs-declared agreement. "Declared" is read as a forward
hook for a future `--basis` flag, not a v0.1 requirement.

---

Not recorded as spec ambiguity, but flagging as design decisions made in
its silence (input CSV shape is outside the frozen contract, which only
specifies command/output behavior):

- **Triangle CSV schema**: long format, columns `origin,development,value`,
  `cumulative` basis inferred per Q3. Chosen because it round-trips exactly
  against chainladder's own bundled RAA sample
  (`chainladder/utils/data/raa.csv` uses `development,origin,values` with
  plain year integers for both origin and development) and keeps harness-side
  structural checks pure-pandas with no chainladder import.
- **`--exclude-origins` / `--exclude-valuations`**: comma-separated string,
  parsed to a list.
- **CLI framework**: stdlib `argparse` — no extra dependency to pin/audit.
- **`reserve runs`**: deferred out of this phase (not in the agreed stage
  order manifest.py → validation.py+validate → engine adapter+fit →
  diagnostics → sensitivity); to be built alongside `reserve report` later.
