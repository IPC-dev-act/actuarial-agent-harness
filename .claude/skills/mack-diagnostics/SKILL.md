---
name: mack-diagnostics
description: Fixed narration for every narrative_key reserve diagnostics emits — screening indicators, not certified Mack tests.
---

# Mack diagnostics

`reserve diagnostics` runs five assumption screens against an existing fit.
**These are reference-implementation approximations of the concepts Mack
(1993/1994) describes** — pooled Pearson/Fisher-z correlations and a
simplified diagonal-clustering check, not independently verified reproductions
of his exact test statistics (`VALIDATION.md`, "known caveats"). Narrate them
as **screening indicators per this harness's reference implementation**, never
as "Mack's test says X" or any language implying certified statistical
authority. All five report a `statistic` against `threshold=1.96`, verdict
`pass`/`warn` only — there is no `fail` here (CLAUDE.md rule 5 already treats
warn and fail identically: surface it, propose the prescribed action, don't
proceed to a headline figure unresolved).

## narrative_key reference

Each test emits `{test_id}_pass` or a test-specific `_warn` key (one,
`calendar_year_effect`, abbreviates to `cy_effect_*`). Fixed narration below —
recite verbatim, don't paraphrase into stronger or weaker language than shown.

| test_id | narrative_key (pass) | narrative_key (warn) |
|---|---|---|
| `dev_correlation` | `dev_correlation_pass` | `dev_correlation_warn` |
| `calendar_year_effect` | `cy_effect_pass` | `cy_effect_warn` |
| `residual_pattern_dev` | `residual_pattern_dev_pass` | `residual_pattern_dev_warn` |
| `residual_pattern_origin` | `residual_pattern_origin_pass` | `residual_pattern_origin_warn` |
| `outlier_link_ratios` | `outlier_link_ratios_pass` | `outlier_link_ratios_warn` |

**`dev_correlation_pass`**: "No significant correlation detected between
adjacent development-period link ratios — no evidence against the assumption
that consecutive factors develop independently."
**`dev_correlation_warn`**: "Adjacent development-period link ratios are
correlated beyond this screen's threshold — evidence against the chain
ladder's independence assumption between development periods."

**`cy_effect_pass`**: "No significant calendar-year clustering detected in
standardized residuals."
**`cy_effect_warn`**: "Standardized residuals cluster by sign on at least one
calendar-year diagonal beyond this screen's threshold — consistent with a
calendar-year effect (something hitting every open origin at the same
valuation date)."

**`residual_pattern_dev_pass`**: "No significant trend detected between
standardized residuals and development period."
**`residual_pattern_dev_warn`**: "Standardized residuals trend with
development period beyond this screen's threshold — the fitted development
pattern may not fit uniformly across the whole triangle."

**`residual_pattern_origin_pass`**: "No significant trend detected between
standardized residuals and origin year."
**`residual_pattern_origin_warn`**: "Standardized residuals trend with origin
year beyond this screen's threshold — suggests an origin-year effect the
single chain-ladder pattern doesn't capture."

**`outlier_link_ratios_pass`**: "No individual link ratio beyond this
screen's threshold relative to its own column's average."
**`outlier_link_ratios_warn`**: "At least one individual link ratio is
unusually far from its column's average — one origin's development is
disproportionately driving that period's factor."

> **Scope note:** Narration in this reference implementation is deliberately
> factual-only; causal interpretation of warnings is reserved for the
> reviewing actuary. The `_warn` lines above state the statistical fact
> only — no illustrative "plausible causes" (a claims process change, a
> large settlement, a reserving exercise, an inflation shock, a change in
> business mix or reserving philosophy by underwriting year, and so on).
> Naming a specific real-world cause is actuarial judgment this harness
> doesn't offer; that step belongs to the human reviewing the output, not
> to fixed prose recited by an agent.

`prescribed_actions` come from the adapter, not from this skill — recite them
as given, with placeholders (`<run-id>`, `<flagged-origin>`) filled from
context. They are the only menu (`docs/cli-spec.md`): `dev_correlation` and
`residual_pattern_dev` propose `sensitivity --grid default` (plus an averaging
retry for the latter); `calendar_year_effect` proposes excluding the flagged
valuation or reducing `--n-periods`; `residual_pattern_origin` and
`outlier_link_ratios` propose excluding the flagged origin/valuation.

## Worked example: RAA's monotone_cumulative warn (incurred-data feature)

This lives here rather than in `data-validation` because interpreting it
correctly needs Mack-methodology context — recognizing it as a legitimate
incurred-data feature rather than a defect, and distinguishing it from a
genuine calendar-year effect, are both this skill's job; `data-validation`
only owns the mechanical check_id-to-action mapping.

`examples/raa.csv` genuinely trips `monotone_cumulative` (warn) at `reserve
validate`, not a synthetic defect: origin 1982's cumulative value decreases
from 15,599 to 15,496 **at the 1987→1988 valuation** (development rank 6→7).
Cite it as `[runs/<run-id>/validation.json: checks[?].details]` →
`{"origin": "1982", "dev": 7, "values": [15599.0, 15496.0]}` — `dev: 7` is the
rank of the later (1988) valuation in that pair.

**Correct narration**: "Origin 1982 shows a legitimate reduction in incurred
losses between the 1987 and 1988 valuations (consistent with a case reserve
release); flagged for visibility per v0.1.2, not a blocking data issue." Do
**not** call this a data quality problem, and do not treat it as evidence of a
calendar-year effect by itself — that's a different, separate signal
(`cy_effect_*`, above), and a single isolated dip on one origin at one
valuation is not the same thing as residuals clustering across an entire
diagonal.

Separately (and confirmed by actually running it, not asserted from memory):
RAA's `outlier_link_ratios` *does* warn in diagnostics — an early, large
individual link ratio (statistic ≈ 2.6). That's a distinct finding from the
1982 negative-development case above; don't conflate the two when narrating
a RAA review.

## What NOT to do

- Never call these "Mack's tests" or imply certified statistical authority —
  "screening indicators" only.
- Never let a warn (or several) get silently dropped from a review — CLAUDE.md
  rule 5: surface every flag, propose the prescribed sensitivities, don't
  proceed to a headline reserve figure while flags are unresolved and
  unacknowledged.
- Never invent a `narrative_key` or prose not listed above.
