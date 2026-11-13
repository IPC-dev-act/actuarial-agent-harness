# Peter England Stochastic Reserving Reference

## Source reviewed

- Repository: <https://github.com/DrPeterEngland/StochasticReserving>
- Release: `v1.0.0`
- Commit: `e7ed85a29dba64db1192140e504f4e09cf149134`
- Author: Dr Peter David England, EMC Actuarial and Analytics Ltd
- License: MIT
- Reviewed: 2026-07-10

The repository is an educational implementation and explicitly states that it
is provided as-is and may contain errors. It is a methodological and validation
reference for this project, not a runtime dependency or production engine.

No source code, notebooks, data, or images from the reference repository are
copied into this project. If implementation material is used later, retain the
MIT copyright notice and cite the software and underlying papers as requested
by its `CITATION.cff`.

## Material reviewed

- `Python_Examples/Example_Modus_Operandi.ipynb`
- `Python_Examples/EV_2006_PredictiveDistributions.ipynb`
- `Python_Examples/EVW_2019.ipynb`
- `Python_Examples/StochResFunctions.py`
- `Python_Examples/StochResFunctions_MCMC.py`
- the example exhibit images for triangles, link ratios, analytic Mack,
  residuals, bootstrap summaries, one-year CDR, and fan charts

## Concepts to carry into the harness

The most useful contribution is the review sequence, not the calculation code:

1. Inspect incremental and cumulative claims before interpreting a model.
2. Inspect individual link ratios and fitted development factors.
3. Establish an analytic Mack baseline.
4. Inspect unscaled and standardized residuals by origin, development, and
   calendar period.
5. Inspect Mack sigma by development period and relate unusual values back to
   observed link ratios and claim movements.
6. Exclude each eligible link ratio in turn and rank its effect on reserve,
   standard error, and coefficient of variation.
7. Treat influential-point exclusion as an exploratory scenario, never an
   automatic recommendation.
8. Re-run residual and sigma analysis after any proposed exclusion.
9. Reconcile bootstrap mean and standard deviation to the corresponding
   analytic model before relying on the predictive distribution.
10. Use reserve-development fan charts to identify where forecast uncertainty
    expands.
11. Distinguish lifetime uncertainty from one-year claims development result
    risk.
12. Choose between Mack and incremental models such as ODP with regard to data
    basis, negative incrementals, and forecast behavior.
13. Treat user-defined variance parameters and scaling to target ultimates as
    explicit governed judgments with separate provenance.

## Gap map for this project

Already available:

- cumulative, incremental, and link-ratio triangle views;
- fitted and candidate development factors;
- Mack reserve and standard error by origin and total;
- governed factor selections and factor-point exclusions;
- exploratory scenarios, immutable decisions, and report gating.

Next analytic capabilities:

- detailed residual artifacts rather than scalar diagnostic verdicts only;
- a Mack sigma curve with observation counts by development period;
- process-versus-parameter uncertainty where the engine exposes it;
- deterministic leave-one-link-ratio-out influence analysis;
- backend-computed coefficient of variation and influence ranks;
- report exhibits linking influential observations to proposed scenarios.

Later stochastic capabilities:

- seeded Mack bootstrap with a complete configuration artifact;
- predictive summaries by origin and total: mean, standard deviation,
  coefficient of variation, percentiles, minimum, and maximum;
- analytic-versus-bootstrap reconciliation checks;
- backend fan-chart data;
- lifetime and one-year CDR views;
- ODP and negative-binomial alternatives after independent validation;
- risk-margin and IFRS 17 bridges only after the stochastic layer is governed.

## Proposed deterministic artifacts

### `mack_diagnostics_detail.json`

- run id and method;
- residual rows with origin, development transition, calendar position,
  observed link ratio, unscaled residual, and standardized residual;
- sigma by development period with contributing observation count;
- process and parameter error by origin and total when available;
- source artifacts, input hashes, engine version, and command.

### `influence_analysis.json`

- base IBNR, Mack standard error, and coefficient of variation;
- one row per eligible link ratio;
- origin, development transition, observed ratio, and source cell references;
- exclusion-scenario IBNR, standard error, and coefficient of variation;
- persisted deltas and ranks calculated by the backend;
- undefined-result reasons rather than zero substitution;
- source artifacts, input hashes, engine version, and command.

### `review_snapshots/<review_snapshot_id>.json`

- exact active reporting selection;
- warning and diagnostics acknowledgements;
- influence analysis reviewed;
- selected scenario and selection-set approval;
- hashes of all material artifacts;
- report renderer/template version;
- snapshot id referenced by the report-approval decision.

Implemented in workbench v0.2.8 so an old report approval cannot authorize a
later selection or analysis.

## Dashboard direction

Add a focused Mack Review or Diagnostics surface containing:

- reserve, standard error, and coefficient of variation by origin and total;
- sigma by development period;
- residual views by origin, development, and calendar period;
- residual triangle and selected-point inspection;
- influential-link-ratio ranking;
- base-versus-exclusion impact for the selected point;
- a stage-scenario action, not an automatic exclusion action;
- governed rationale and acknowledgement paths.

The AI may explain artifact-backed drivers, identify high-ranked observations,
and prepare scenarios. It must not decide that an observation is erroneous,
exclude it, override sigma, choose a stochastic model, or approve a report.

## Implementation order

1. Persist detailed Mack residual and sigma outputs.
2. Implement deterministic link-ratio influence analysis and tests.
3. Add Mack Review dashboard and report exhibits.
4. Add governed review tasks for diagnostics and influence analysis.
5. Implement a seeded Mack bootstrap only after the analytic workflow is
   stable and validated.
6. Add one-year and alternative-model capabilities as separate later phases.

## Validation use

The reference examples can be cloned again at the recorded commit when needed
as external validation material. Any numerical adoption must be independently
reproduced through this project's engine adapter, checked against the cited
papers or another authoritative implementation, and covered by deterministic
tests. Notebook output alone is not sufficient validation evidence.

## Citations

- England, P. D. and Verrall, R. J. (2006), *Predictive distributions of
  outstanding liabilities in general insurance*, Annals of Actuarial Science,
  1(2), 221-270. <https://doi.org/10.1017/S1748499500000142>
- England, P. D., Verrall, R. J. and Wuthrich, M. V. (2019), *On the lifetime
  and one-year views of reserve risk, with application to IFRS 17 and Solvency
  II risk margins*, Insurance: Mathematics and Economics.
  <https://doi.org/10.1016/j.insmatheco.2018.12.002>
