---
name: data-validation
description: Interpreting reserve validate's check_ids and exit codes — what fired, what it means, what to do next.
---

# Data validation

`reserve validate` runs seven engine-agnostic structural checks against a triangle
CSV, before any model ever touches the data. Two are warn-class; five are
fail-class. This skill maps each `check_id` to interpretation and next action —
never invent a check or a meaning not listed here (`docs/cli-spec.md` is the
frozen contract; this skill is how you talk about its output).

## Reading the output

`validation.json` has `basis`, `dimensions`, a `checks` array, and a top-level
`verdict` (`pass`/`warn`/`fail`). Checks short-circuit: a fail upstream means
downstream checks don't run at all and won't appear in the array — seeing only
2 entries instead of 7 is expected, not a bug, when `file_readable` or
`origin_dev_parseable` fails. `basis`/`dimensions` stay `null` until parsing
succeeds.

Exit codes: **0** — all pass, or warn-only. **2** — any fail-class check fired.
(3/4/1 don't apply to `validate`; see `docs/cli-spec.md`'s harness-wide table.)

## check_id reference

| check_id | class | fires when | what it means | your next action |
|---|---|---|---|---|
| `file_readable` | fail | path missing, unreadable, or no data rows | can't open the input at all | report `details.error`; nothing else ran |
| `origin_dev_parseable` | fail | required columns missing, or origin/development/value not numeric | not shaped like a triangle CSV | report `details.missing_columns` or `details.unparseable_rows`; do not attempt a fit |
| `shape_triangular` | fail | a newer origin has *more* development than an older one | not a staircase — scrambled file, wrong sort, or a genuinely rectangular dataset | report the origin pair from `details.violations`; ask for a corrected export, don't guess the fix yourself |
| `no_gaps` | fail | an origin has a hole *inside* its own history | a missing valuation, not a missing future (which is normal and expected) | report `details.violations` (origin + missing dev); blocks `fit` (exit 2) |
| `basis_consistent` | fail | cumulative-vs-incremental vote ties across origins | genuinely ambiguous, not a one-line fix | report `details.votes_cumulative`/`votes_incremental`; **ask the user, in conversation**† — do not guess |
| `monotone_cumulative` | **warn** | a cumulative value decreases between two valuations | legitimate on incurred data (case reserve reduction) by default, not automatically a defect | narrate as a feature under review, not an error (see `mack-diagnostics`' RAA example) — does not block `fit` |
| `nonneg_incrementals` | **warn** | an implied incremental is negative | the same underlying signal as `monotone_cumulative`, viewed incrementally | usually fires alongside it on the same cell; same treatment |

† `basis_consistent`'s "ask" is not resolvable by re-reading the file, running
another command, or inferring harder — it is a direct question to the human
you're working with ("is this cumulative or incremental data?"), the same way
you'd ask about any other genuinely ambiguous instruction.

`monotone_cumulative`/`nonneg_incrementals` details: `{"origin", "dev",
"values"/"incremental"}`. Fail-class details vary by check — see the table
above for which field to read.

## Citation discipline

Every claim here traces to a file (CLAUDE.md rule 1). Cite as
`[runs/<run-id>/validation.json: checks[i].details]`, not "the data looks
inconsistent" or similar unsourced language. If a validate run hasn't been
executed for the input in front of you, you don't have this information yet —
run it (CLAUDE.md rule 4: always, even if you validated this file earlier in
the session).

## What NOT to do

- Never treat a warn-class fire as if it were fail-class, or vice versa —
  the exit code already tells you which it is.
- Never "fix" the input yourself (CLAUDE.md rule 3) — report the check and
  its details; a correction to the source data is someone else's call.
- Never proceed past a fail-class check to a fit — `fit` already refuses
  internally (exit 2) and persists the same `validation.json`, so there is
  no reason to try to route around it.
