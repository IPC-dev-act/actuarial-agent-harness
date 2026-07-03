# VALIDATION

Record of manual verification of the harness's deterministic outputs against
published literature figures. Verification performed 2026-07-02 by Ivan Perincic,
assisted by an independent reproduction in a clean environment
(chainladder==0.9.2, separate from this repository's code).

## Provenance of the sample triangles

- **RAA** (`examples/raa.csv`): the Reinsurance Association of America general
  liability triangle. Canonical stochastic reserving benchmark from
  **Mack (1994), "Measuring the variability of chain ladder reserve estimates",
  CAS Spring Forum** — *not* Mack (1993), a common misattribution corrected here.
  Data export eyeballed against published sources, including the negative
  cumulative development at origin 1982 (15,599 → 15,496 at the 1987→1988
  valuation), a legitimate feature of incurred data (case reserve release) and
  the reason `monotone_cumulative` is a warn-class check (spec v0.1.2).
- **GenIns** (`examples/genins.csv`): the Taylor & Ashe (1983) triangle, and the
  first worked example in **Mack (1993), "Distribution-free calculation of the
  standard error of chain ladder reserve estimates", ASTIN Bulletin 23(2)**,
  Tables 1–3.

## RAA — verified against the published Mack results

Volume-weighted development, no tail.

- **Development factors**: computed 2.999, 1.624, 1.271, 1.172, 1.113, 1.042,
  1.033, 1.017, 1.009 — identical to the published factors.
- **Reserves (IBNR) per origin**: computed 0; 154; 617; 1,636; 2,747; 3,649;
  5,435; 10,907; 10,650; 16,339 — identical to the published figures for all
  ten origins. Total IBNR 52,135; total ultimate 213,122 — identical.
- **Mack standard errors**: match the published figures **exactly** (206; 623;
  747; 1,469; 2,002; 2,209; 5,358; 6,333; 24,566; total 26,909) **when the
  last-development-period sigma uses Mack's minimum rule**
  (`sigma_interpolation="mack"` in chainladder). chainladder's default
  (`"log-linear"`) yields slightly lower SEs concentrated in the earliest open
  origins (e.g. 143 vs 206 for 1982; total 26,881 vs 26,909), because those
  origins depend most heavily on the extrapolated final sigma. The adapter
  therefore pins `sigma_interpolation="mack"` as the default (spec changelog),
  with the alternative available as an explicit parameter. Both treatments are
  legitimate; the choice is documented rather than silent.

## GenIns — verified against Mack (1993) Tables 2–3

Per-origin chain ladder reserves (in 1000s): 95; 470; 710; 985; 1,419; 2,178;
3,920; 4,279; 4,626; overall 18,681 — matching the paper's Table 2 chain ladder
column. Overall standard error ≈ 13% of the reserve per Table 3.

## Status of automated literature tests

- `tests/test_mack_vs_literature.py` RAA reserve assertions: verified, xfail
  markers removed.
- RAA standard error assertions: verified with `sigma_interpolation="mack"`;
  test asserts the published values under that setting.
- GenIns vs Mack (1993): added as a second literature test.

## Known caveats (unchanged)

- The five diagnostics tests are reference-implementation approximations of the
  concepts named in Mack (1993/1994) — pooled Pearson/Fisher-z correlations and
  a simplified diagonal approximation for the calendar-year test — not certified
  reproductions of the papers' exact test statistics. They are screening
  indicators; the language the agent uses to narrate them says so.
