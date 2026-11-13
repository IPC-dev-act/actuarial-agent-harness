"""`reserve` CLI — parsing, exit codes, dispatch (docs/cli-spec.md).

`--format` and `--out` are added wherever a command's signature lists them.
`--dry-run` is on every writing command's *signature* as of v0.1.12 — `fit`,
`diagnostics`, `sensitivity`, `report` — per the Global section's own rule
("`--dry-run` on any writing command"); an earlier phase had wired it into
`fit` only, on a too-literal reading of each command's individual v0.1
signature rather than that global rule. `validate` remains the one writing
command without it, matching its own signature in docs/cli-spec.md, which
has never listed `--dry-run` — left as-is here rather than guessed at.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from engine.chainladder_adapter import ChainladderAdapter, parse_tail_param
from harness import factor_analysis, manifest, model_runner, runs, selection_sets, sensitivity, triangle_io, triangle_projection, validation
from harness.render import report_html
from harness.runs import RunNotFoundError
from harness.workbench import decisions as workbench_decisions
from harness.workbench import io as workbench_io
from harness.workbench import handoff as workbench_handoff
from harness.workbench import scenarios as workbench_scenarios
from harness.workbench import review_snapshots as workbench_review_snapshots
from harness.workbench import state as workbench_state
from harness.workbench import schemas as workbench_schemas
from harness.workbench import tasks as workbench_tasks

EXIT_SUCCESS = 0
EXIT_INTERNAL_ERROR = 1
EXIT_VALIDATION_FAILURE = 2
EXIT_MODEL_WARNING = 3
EXIT_USAGE_ERROR = 4


def _json_safe(obj):
    """Recursively replaces non-finite floats (NaN/Infinity) with None.

    A perturbed fit can genuinely produce these — e.g. excluding the one
    origin that has data for a given development transition leaves that
    LDF (and everything downstream of it, including total mack_se)
    undefined. json.dumps emits the bare tokens NaN/Infinity for such
    floats by default, which is not valid JSON (RFC 8259); every command's
    --format json output must parse in a strict JSON parser, not just
    Python's own permissive one.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    return obj


def _dump_json(payload: dict) -> str:
    return json.dumps(_json_safe(payload), indent=2)


def _add_format_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--format", choices=["json", "text"], default="text")


def _add_out_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, default=runs.DEFAULT_RUNS_ROOT)


class _ArgumentParser(argparse.ArgumentParser):
    """argparse's own error() hardcodes sys.exit(2) — collides with
    docs/cli-spec.md's exit code 2 ("data validation failure"). A bad
    --averaging value or a missing --method is a usage error (exit 4), not
    a data problem; an agent branching on exit code per CLAUDE.md's table
    would otherwise misread "you typed the command wrong" as "your
    triangle is bad" and try to act on structured validation errors that
    were never produced. Applies to every subcommand — passed as
    parser_class to every add_subparsers() call below.

    `allow_abbrev=False`: argparse's default prefix-abbreviation matching
    let a stale `reserve report --format html` silently succeed as an alias
    for `--format-out`, since `report` has no separate `--format` flag of
    its own and `--format` is an unambiguous prefix of `--format-out` —
    undermining the exact reason `--format-out` exists as a distinct flag
    (docs/cli-spec.md's `report` section, "Why `--format-out`, not
    `--format`"). Found re-verifying README commands verbatim against this
    CLI.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE_ERROR)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="reserve")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)

    p_validate = subparsers.add_parser("validate", help="Structural checks on a triangle CSV")
    p_validate.add_argument("triangle_csv", type=Path)
    p_validate.add_argument("--basis", choices=["cumulative", "incremental"], default=None)
    _add_format_arg(p_validate)
    _add_out_arg(p_validate)
    p_validate.set_defaults(handler=cmd_validate)

    p_fit = subparsers.add_parser("fit", help="Fit a reserving method to a triangle")
    p_fit.add_argument("triangle_csv", type=Path)
    p_fit.add_argument("--method", required=True)
    p_fit.add_argument("--averaging", choices=["volume", "simple"], default="volume")
    p_fit.add_argument("--tail", default="none")
    p_fit.add_argument("--n-periods", type=int, default=None)
    p_fit.add_argument("--exclude-origins", default="")
    p_fit.add_argument("--exclude-valuations", default="")
    p_fit.add_argument("--basis", choices=["cumulative", "incremental"], default=None)
    p_fit.add_argument(
        "--sigma-interpolation",
        choices=["mack", "log-linear"],
        default="mack",
    )
    # Not a supported feature (docs/cli-spec.md roadmap: "selections" is
    # declared, not governed) — recognized here only so cmd_fit can give a
    # specific, informative rejection instead of argparse's generic
    # "unrecognized arguments" error.
    p_fit.add_argument("--selections", default=None)
    _add_format_arg(p_fit)
    _add_out_arg(p_fit)
    p_fit.add_argument("--dry-run", action="store_true")
    p_fit.set_defaults(handler=cmd_fit)

    p_diag = subparsers.add_parser("diagnostics", help="Run assumption tests against an existing fit")
    p_diag.add_argument("run_id")
    _add_format_arg(p_diag)
    _add_out_arg(p_diag)
    p_diag.add_argument("--dry-run", action="store_true")
    p_diag.set_defaults(handler=cmd_diagnostics)

    p_sens = subparsers.add_parser("sensitivity", help="Re-run a fit over a perturbation grid")
    p_sens.add_argument("run_id")
    p_sens.add_argument("--grid", default="default")
    p_sens.add_argument("--exclude-origins", default="")
    p_sens.add_argument("--exclude-valuations", default="")
    _add_format_arg(p_sens)
    _add_out_arg(p_sens)
    p_sens.add_argument("--dry-run", action="store_true")
    p_sens.set_defaults(handler=cmd_sensitivity)

    p_factor_analysis = subparsers.add_parser(
        "factor-analysis",
        help="Build deterministic BCL link-ratio influence and review-suggestion artifacts",
    )
    p_factor_analysis.add_argument("run_id")
    _add_format_arg(p_factor_analysis)
    _add_out_arg(p_factor_analysis)
    p_factor_analysis.add_argument("--dry-run", action="store_true")
    p_factor_analysis.set_defaults(handler=cmd_factor_analysis)

    p_runs = subparsers.add_parser("runs", help="Inventory of the runs root")
    runs_subparsers = p_runs.add_subparsers(
        dest="runs_action", required=True, parser_class=_ArgumentParser
    )

    p_runs_list = runs_subparsers.add_parser("list")
    _add_format_arg(p_runs_list)
    _add_out_arg(p_runs_list)
    p_runs_list.set_defaults(handler=cmd_runs_list)

    p_runs_show = runs_subparsers.add_parser("show")
    p_runs_show.add_argument("run_id")
    _add_format_arg(p_runs_show)
    _add_out_arg(p_runs_show)
    p_runs_show.set_defaults(handler=cmd_runs_show)

    p_report = subparsers.add_parser("report", help="Render a deterministic HTML review of an existing run")
    p_report.add_argument("run_id")
    p_report.add_argument("--format-out", choices=["html", "md"], default="html")
    p_report.add_argument("--require-approval", action="store_true")
    _add_out_arg(p_report)
    p_report.add_argument("--dry-run", action="store_true")
    p_report.set_defaults(handler=cmd_report)

    p_tasks = subparsers.add_parser("tasks", help="Build/list pending workbench validation tasks")
    p_tasks.add_argument("run_id")
    _add_format_arg(p_tasks)
    _add_out_arg(p_tasks)
    p_tasks.add_argument("--dry-run", action="store_true")
    p_tasks.set_defaults(handler=cmd_tasks)

    p_status = subparsers.add_parser("status", help="Show derived workbench run status")
    p_status.add_argument("run_id")
    _add_format_arg(p_status)
    _add_out_arg(p_status)
    p_status.set_defaults(handler=cmd_status)

    p_handoff = subparsers.add_parser("handoff", help="Build the structured AI-to-actuary review handoff")
    p_handoff.add_argument("run_id")
    _add_format_arg(p_handoff)
    _add_out_arg(p_handoff)
    p_handoff.add_argument("--dry-run", action="store_true")
    p_handoff.set_defaults(handler=cmd_handoff)

    p_scenarios = subparsers.add_parser("scenarios", help="Build/list workbench scenario candidates")
    p_scenarios.add_argument("run_id")
    _add_format_arg(p_scenarios)
    _add_out_arg(p_scenarios)
    p_scenarios.add_argument("--dry-run", action="store_true")
    p_scenarios.set_defaults(handler=cmd_scenarios)

    p_compare = subparsers.add_parser("compare", help="Compare a scenario candidate against the base run")
    p_compare.add_argument("run_id")
    p_compare.add_argument("--scenario-id", required=True)
    _add_format_arg(p_compare)
    _add_out_arg(p_compare)
    p_compare.add_argument("--dry-run", action="store_true")
    p_compare.set_defaults(handler=cmd_compare)

    p_selection_sets = subparsers.add_parser("selection-sets", help="List, preview, and commit governed selection sets")
    selection_set_subparsers = p_selection_sets.add_subparsers(
        dest="selection_sets_action", required=True, parser_class=_ArgumentParser
    )

    p_selection_sets_list = selection_set_subparsers.add_parser("list")
    p_selection_sets_list.add_argument("run_id")
    _add_format_arg(p_selection_sets_list)
    _add_out_arg(p_selection_sets_list)
    p_selection_sets_list.set_defaults(handler=cmd_selection_sets_list)

    p_selection_sets_show = selection_set_subparsers.add_parser("show")
    p_selection_sets_show.add_argument("run_id")
    p_selection_sets_show.add_argument("selection_set_id")
    _add_format_arg(p_selection_sets_show)
    _add_out_arg(p_selection_sets_show)
    p_selection_sets_show.set_defaults(handler=cmd_selection_sets_show)

    p_selection_sets_preview = selection_set_subparsers.add_parser("preview")
    p_selection_sets_preview.add_argument("run_id")
    p_selection_sets_preview.add_argument("--request-file", type=Path, required=True)
    _add_format_arg(p_selection_sets_preview)
    _add_out_arg(p_selection_sets_preview)
    p_selection_sets_preview.add_argument("--dry-run", action="store_true")
    p_selection_sets_preview.set_defaults(handler=cmd_selection_sets_preview)

    p_selection_sets_commit = selection_set_subparsers.add_parser("commit")
    p_selection_sets_commit.add_argument("run_id")
    p_selection_sets_commit.add_argument("--selection-set-id", required=True)
    p_selection_sets_commit.add_argument("--decision-file", type=Path, required=True)
    _add_format_arg(p_selection_sets_commit)
    _add_out_arg(p_selection_sets_commit)
    p_selection_sets_commit.add_argument("--dry-run", action="store_true")
    p_selection_sets_commit.set_defaults(handler=cmd_selection_sets_commit)

    p_dashboard = subparsers.add_parser("dashboard", help="Start the local workbench dashboard")
    _add_out_arg(p_dashboard)
    p_dashboard.add_argument("--host", default="127.0.0.1")
    p_dashboard.add_argument("--port", type=int, default=8000)
    p_dashboard.set_defaults(handler=cmd_dashboard)

    p_decide = subparsers.add_parser("decide", help="Commit an immutable workbench decision artifact")
    p_decide.add_argument("run_id")
    p_decide.add_argument("--decision-file", type=Path, required=True)
    _add_format_arg(p_decide)
    _add_out_arg(p_decide)
    p_decide.add_argument("--dry-run", action="store_true")
    p_decide.set_defaults(handler=cmd_decide)

    return parser


def _split_list_arg(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _invocation_string(command: str, args: argparse.Namespace) -> str:
    """Reconstructs the effective invocation for the manifest's `command`
    field. Every flag a subcommand can take is represented — `hasattr`
    naturally scopes each one to the subcommands that declare it (e.g.
    `--averaging` only ever appears for `fit`) — so a non-default `fit`
    (custom averaging, tail, exclusions, sigma-interpolation) is fully
    legible from the manifest alone, not just the ones that happened to
    differ from argparse's own defaults. Found by independent review
    (v0.1.14): an earlier version of this function recorded only
    `triangle_csv`/`run_id`/`--method`/`--basis`/`--format`/`--out`/
    `--dry-run`, silently dropping every other `fit` parameter from the
    audit trail's command string (the *effective* parameters were always
    safe — they live in `fit.json`/manifest `parameters`, independent of
    this string — but the human/agent-facing command narration was not).
    """
    parts = [f"reserve {command}"]
    if getattr(args, "triangle_csv", None) is not None:
        parts.append(str(args.triangle_csv))
    if getattr(args, "run_id", None) is not None:
        parts.append(str(args.run_id))
    if hasattr(args, "method"):
        parts.append(f"--method {args.method}")
    if hasattr(args, "averaging"):
        parts.append(f"--averaging {args.averaging}")
    if hasattr(args, "tail"):
        parts.append(f"--tail {args.tail}")
    if getattr(args, "n_periods", None) is not None:
        parts.append(f"--n-periods {args.n_periods}")
    if getattr(args, "exclude_origins", ""):
        parts.append(f"--exclude-origins {args.exclude_origins}")
    if getattr(args, "exclude_valuations", ""):
        parts.append(f"--exclude-valuations {args.exclude_valuations}")
    if getattr(args, "basis", None) is not None:
        parts.append(f"--basis {args.basis}")
    if hasattr(args, "sigma_interpolation"):
        parts.append(f"--sigma-interpolation {args.sigma_interpolation}")
    if hasattr(args, "grid"):
        parts.append(f"--grid {args.grid}")
    parts.append(f"--format {args.format}")
    if hasattr(args, "out"):
        parts.append(f"--out {args.out}")
    if getattr(args, "dry_run", False):
        parts.append("--dry-run")
    return " ".join(parts)


def _basis_parameters(result: validation.ValidationResult) -> dict:
    """Manifest `parameters.basis` (v0.1.13): the basis actually used and
    whether it was declared (`--basis`) or inferred — recorded whichever way
    it was determined, per docs/cli-spec.md's `validate`/`fit` sections.
    """
    return {"value": result.basis, "source": result.basis_source}


def cmd_validate(args: argparse.Namespace) -> int:
    result = validation.validate_triangle_csv(args.triangle_csv, declared_basis=args.basis)
    payload = result.to_dict()
    exit_code = EXIT_VALIDATION_FAILURE if result.verdict == "fail" else EXIT_SUCCESS

    run_id = runs.new_run_id(args.triangle_csv.stem, "validate")
    _write_run(
        run_id=run_id,
        out_root=args.out,
        dry_run=False,  # validate has no --dry-run flag (docs/cli-spec.md)
        files={"validation.json": payload},
        manifest_kwargs=dict(
            command=_invocation_string("validate", args),
            inputs=_inputs_for(args.triangle_csv, result.input_sha256),
            engine=None,
            parameters={"basis": _basis_parameters(result)},
            outputs=["validation.json"],
            exit_code=exit_code,
        ),
    )
    _log_run(run_id, args.out, False, ["validation.json"])
    _print_payload(args.format, payload, lambda p: _render_validation_text(p, run_id))
    return exit_code


def _render_validation_text(payload: dict, run_id: str) -> str:
    lines = [
        f"run_id:     {run_id}",
        f"input:      {payload['input']['path']}",
        f"basis:      {payload['basis']} ({payload['basis_source']})",
        f"dimensions: {payload['dimensions']}",
        "checks:",
    ]
    for check in payload["checks"]:
        lines.append(f"  [{check['verdict'].upper():4}] {check['check_id']}")
        if check["details"]:
            lines.append(f"         {check['details']}")
    lines.append(f"verdict: {payload['verdict'].upper()}")
    return "\n".join(lines)


def _render_basis_mismatch_text(payload: dict, run_id: str) -> str:
    lines = [
        f"run_id: {run_id}",
        f"error: {payload['error']}",
        f"message: {payload['message']}",
        f"adapter_supported_basis: {payload['adapter_supported_basis']}",
        f"inferred_basis: {payload['inferred_basis']}",
    ]
    if "basis_source" in payload:
        lines.append(f"basis_source: {payload['basis_source']}")
    return "\n".join(lines)


def cmd_fit(args: argparse.Namespace) -> int:
    if args.selections is not None:
        # Roadmap surfacing, not a feature (docs/cli-spec.md v0.1.11): a
        # pure usage rejection, checked before anything data-dependent —
        # quotes the declared roadmap status rather than a generic
        # argparse error, so the reason it's refused is legible.
        roadmap_status = ChainladderAdapter().capabilities()["roadmap"]["selections"]
        print(
            f"usage error: --selections is not implemented — roadmap status: "
            f"{roadmap_status}",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    try:
        tail = parse_tail_param(args.tail)
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    validation_result = validation.validate_triangle_csv(args.triangle_csv, declared_basis=args.basis)
    run_id = runs.new_run_id(args.triangle_csv.stem, args.method)

    if validation_result.verdict == "fail":
        # Hard rule (docs/cli-spec.md v0.1.1): fit's internal validate-first
        # check persists the same audit trail a standalone `validate` would.
        payload = validation_result.to_dict()
        _write_run(
            run_id=run_id,
            out_root=args.out,
            dry_run=args.dry_run,
            files={"validation.json": payload},
            manifest_kwargs=dict(
                command=_invocation_string("fit", args),
                inputs=_inputs_for(args.triangle_csv, validation_result.input_sha256),
                engine=None,
                parameters={"basis": _basis_parameters(validation_result)},
                outputs=["validation.json"],
                exit_code=EXIT_VALIDATION_FAILURE,
            ),
            snapshot_source=args.triangle_csv,
        )
        _log_run(run_id, args.out, args.dry_run, ["validation.json"])
        _print_payload(args.format, payload, lambda p: _render_validation_text(p, run_id))
        return EXIT_VALIDATION_FAILURE

    adapter = ChainladderAdapter()
    capabilities = adapter.capabilities()
    if args.method not in capabilities["methods"]:
        print(
            f"usage error: method '{args.method}' not in adapter capabilities "
            f"{capabilities['methods']} (roadmap: {capabilities['roadmap_methods']})",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    if validation_result.basis not in capabilities["basis"]:
        # docs/cli-spec.md v0.1.10: the adapter's load_triangle has always
        # hardcoded cumulative=True — this closes the silent-fabrication
        # path that would otherwise fit genuinely incremental input as if
        # it were cumulative. Persists the same audit trail as a validate
        # failure (Q2 convention: validation.json + manifest, exit 2, no
        # fit.json), even though validate's own verdict was pass/warn — the
        # refusal is about adapter capability, not a structural data defect.
        if validation_result.basis_source == "declared":
            # The declared value is authoritative and already agrees with
            # inference (a conflict there would have failed basis_consistent
            # above) — this refusal is purely about adapter capability.
            message = (
                f"engine adapter supports {' or '.join(capabilities['basis'])} input only; "
                f"declared basis: {validation_result.basis}"
            )
        else:
            message = (
                f"engine adapter supports {' or '.join(capabilities['basis'])} "
                f"input only; inferred basis: {validation_result.basis}"
            )
        error_payload = {
            "error": "unsupported_basis",
            "message": message,
            "adapter_supported_basis": capabilities["basis"],
            "inferred_basis": validation_result.basis,
        }
        if validation_result.basis_source == "declared":
            error_payload["basis_source"] = "declared"
        _write_run(
            run_id=run_id,
            out_root=args.out,
            dry_run=args.dry_run,
            files={"validation.json": validation_result.to_dict()},
            manifest_kwargs=dict(
                command=_invocation_string("fit", args),
                inputs=_inputs_for(args.triangle_csv, validation_result.input_sha256),
                engine=None,
                parameters={"basis": _basis_parameters(validation_result)},
                outputs=["validation.json"],
                exit_code=EXIT_VALIDATION_FAILURE,
            ),
            snapshot_source=args.triangle_csv,
        )
        _log_run(run_id, args.out, args.dry_run, ["validation.json"])
        _print_payload(args.format, error_payload, lambda p: _render_basis_mismatch_text(p, run_id))
        return EXIT_VALIDATION_FAILURE

    params = {
        "averaging": args.averaging,
        "tail": tail,
        "n_periods": args.n_periods,
        "excluded_origins": _split_list_arg(args.exclude_origins),
        "excluded_valuations": _split_list_arg(args.exclude_valuations),
        "sigma_interpolation": args.sigma_interpolation,
    }

    tri_handle, fit_result = model_runner.fit_triangle(
        args.triangle_csv,
        args.method,
        params,
        adapter=adapter,
    )
    fit_warnings = _detect_fit_warnings(fit_result)
    exit_code = EXIT_MODEL_WARNING if fit_warnings else EXIT_SUCCESS

    fit_payload = fit_result.to_fit_json(run_id)

    # triangle.json (v0.1.9): actual cells straight from the input CSV
    # (independent re-read via harness.triangle_io, same as validate's own
    # parse — engine-agnostic, no chainladder) plus projected cells
    # reconstructed from fit.json's own development_factors LDFs.
    actual_cells, _triangle_error = triangle_io.load_and_normalize(args.triangle_csv)
    triangle_payload = {
        "run_id": run_id,
        "basis": tri_handle.basis,
        "cells": triangle_projection.build_cells(
            actual_cells.to_dict("records"), fit_result.development_factors
        ),
    }

    validation_payload = validation_result.to_dict()

    _write_run(
        run_id=run_id,
        out_root=args.out,
        dry_run=args.dry_run,
        files={
            "validation.json": validation_payload,
            "fit.json": fit_payload,
            "triangle.json": triangle_payload,
        },
        manifest_kwargs=dict(
            command=_invocation_string("fit", args),
            inputs=_inputs_for(args.triangle_csv, validation_result.input_sha256),
            engine={
                "adapter": capabilities["adapter"],
                "package": capabilities["package"],
                "version": capabilities["version"],
            },
            parameters={**fit_result.parameters, "basis": _basis_parameters(validation_result)},
            outputs=["validation.json", "fit.json", "triangle.json"],
            exit_code=exit_code,
        ),
        snapshot_source=args.triangle_csv,
    )
    _log_run(run_id, args.out, args.dry_run, ["validation.json", "fit.json", "triangle.json"])
    _print_payload(args.format, fit_payload, lambda p: _render_fit_text(p, run_id))
    return exit_code


def _detect_fit_warnings(fit_result) -> list[dict]:
    """Fit-time computational health only (finite, well-defined numbers) —
    statistical assumption checking is `reserve diagnostics`'s job, not
    fit's. Kept deliberately narrow to avoid duplicating Stage 4 scope.
    """
    warnings_found = []
    for field_name, value in fit_result.totals.items():
        if value is None:
            continue
        if not math.isfinite(value):
            warnings_found.append({"warning": "non_finite_total", "field": field_name})
    for row in fit_result.by_origin:
        for field_name in ("ultimate", "ibnr", "mack_se"):
            if row[field_name] is None:
                continue
            if not math.isfinite(row[field_name]):
                warnings_found.append(
                    {"warning": "non_finite_by_origin", "origin": row["origin"], "field": field_name}
                )
    return warnings_found


def _inputs_for(path: Path, sha256: str | None) -> list[dict]:
    if sha256:
        return [{"path": str(path), "sha256": sha256}]
    return [{"path": str(path), "sha256": None}]


class InputIntegrityError(Exception):
    """Raised when a run's replay input can't be trusted (v0.1.12) — either
    the snapshot under runs/<run-id>/inputs/ or, for a pre-snapshot legacy
    folder, the originally recorded path, has a sha256 that no longer
    matches what the manifest recorded at fit time. Carries a structured
    payload so cmd_diagnostics/cmd_sensitivity can print it like any other
    structured error rather than a bare traceback.
    """

    def __init__(self, payload: dict):
        super().__init__(payload["message"])
        self.payload = payload


def _snapshot_input(run_dir: Path, source_path: Path, expected_sha256: str) -> str:
    """Copies the fitted input CSV into runs/<run-id>/inputs/ (v0.1.12) so
    the run folder is self-contained: diagnostics/sensitivity replay never
    again depends on the original file still existing, unmoved, unchanged.
    Verifies the copy landed intact before recording it — a mismatch here
    means the filesystem misbehaved mid-copy, not a normal operating
    condition, so it's raised rather than swallowed. Returns the manifest's
    "snapshot" value: the run-folder-relative path to the copy.
    """
    inputs_dir = run_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = inputs_dir / source_path.name
    snapshot_path.write_bytes(Path(source_path).read_bytes())
    copy_sha256 = manifest.sha256_file(snapshot_path)
    if copy_sha256 != expected_sha256:
        raise RuntimeError(
            f"input snapshot integrity check failed immediately after copy: "
            f"{source_path} -> {snapshot_path} (expected sha256 {expected_sha256}, got {copy_sha256})"
        )
    return f"inputs/{source_path.name}"


def _resolve_replay_input(run_dir: Path, run_manifest: dict) -> Path:
    """Resolves the triangle CSV diagnostics/sensitivity replay a fit
    against (v0.1.12). Uses the run's own snapshot when the manifest
    recorded one — never the originally recorded path, which may since have
    moved, changed, or been deleted. Pre-snapshot (legacy) run folders fall
    back to that recorded path, but only after the same check: either way,
    the file's current sha256 must match the manifest's recorded hash
    before any recompute runs against it, or an InputIntegrityError is
    raised instead of silently replaying against different data than what
    was actually fit.
    """
    input_entry = run_manifest["inputs"][0]
    expected_sha256 = input_entry["sha256"]
    snapshot_rel = input_entry.get("snapshot")
    path = (run_dir / snapshot_rel) if snapshot_rel else Path(input_entry["path"])

    if not path.is_file():
        raise InputIntegrityError(
            {
                "error": "input_integrity_violation",
                "message": (
                    f"input file for replay not found at {path} — the run's audit trail "
                    "cannot be trusted; has it moved or been deleted since the fit?"
                ),
                "path_checked": str(path),
                "expected_sha256": expected_sha256,
                "actual_sha256": None,
            }
        )
    actual_sha256 = manifest.sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise InputIntegrityError(
            {
                "error": "input_integrity_violation",
                "message": (
                    f"input file at {path} does not match the sha256 recorded in this run's "
                    "manifest — refusing to replay against data that may not be what was "
                    "actually fit"
                ),
                "path_checked": str(path),
                "expected_sha256": expected_sha256,
                "actual_sha256": actual_sha256,
            }
        )
    return path


def _render_integrity_error_text(payload: dict, run_id: str) -> str:
    return "\n".join(
        [
            f"run_id: {run_id}",
            f"error: {payload['error']}",
            f"message: {payload['message']}",
            f"path_checked: {payload['path_checked']}",
            f"expected_sha256: {payload['expected_sha256']}",
            f"actual_sha256: {payload['actual_sha256']}",
        ]
    )


def _write_run(*, run_id, out_root, dry_run, files: dict, manifest_kwargs, snapshot_source: Path | None = None) -> None:
    if dry_run:
        return
    run_dir = runs.create_run_dir(run_id, out_root=out_root)
    if snapshot_source is not None:
        input_entry = manifest_kwargs["inputs"][0]
        if input_entry.get("sha256"):
            input_entry["snapshot"] = _snapshot_input(run_dir, snapshot_source, input_entry["sha256"])
    for filename, payload in files.items():
        (run_dir / filename).write_text(_dump_json(payload) + "\n")
    m = manifest.build_manifest(run_id=run_id, **manifest_kwargs)
    manifest.write_manifest(run_dir, m)


def _log_run(run_id: str, out_root: Path, dry_run: bool, filenames: list[str]) -> None:
    prefix = "[dry-run] would write" if dry_run else "wrote"
    print(f"run_id: {run_id}", file=sys.stderr)
    for filename in filenames:
        print(f"{prefix} {Path(out_root) / run_id / filename}", file=sys.stderr)


def _print_payload(fmt: str, payload: dict, text_renderer) -> None:
    if fmt == "json":
        print(_dump_json(payload))
    else:
        print(text_renderer(payload))


def _format_number_text(value, *, decimals: int = 1) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and not math.isfinite(value):
        return "undefined"
    return f"{value:.{decimals}f}"


def _render_fit_text(payload: dict, run_id: str) -> str:
    lines = [
        f"run_id:  {run_id}",
        f"method:  {payload['method']}",
        f"params:  {payload['parameters']}",
        "development_factors:",
    ]
    for f in payload["development_factors"]:
        lines.append(f"  {f['from_dev']:>3} -> {f['to_dev']:<4} ldf={f['ldf']:.4f} sigma={f['sigma']}")
    lines.append("by_origin:")
    for row in payload["by_origin"]:
        lines.append(
            f"  {row['origin']}: latest={_format_number_text(row['latest'])} "
            f"ultimate={_format_number_text(row['ultimate'])} "
            f"ibnr={_format_number_text(row['ibnr'])} "
            f"mack_se={_format_number_text(row['mack_se'])}"
        )
    t = payload["totals"]
    lines.append(
        f"totals: latest={_format_number_text(t['latest'])} "
        f"ultimate={_format_number_text(t['ultimate'])} "
        f"ibnr={_format_number_text(t['ibnr'])} "
        f"mack_se={_format_number_text(t['mack_se'])}"
    )
    return "\n".join(lines)


def cmd_diagnostics(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    run_manifest = manifest.read_manifest(run_dir)
    if "fit.json" not in run_manifest["outputs"]:
        print(
            f"usage error: run '{args.run_id}' has no fit.json — diagnostics runs against an "
            "existing fit, not a bare validate run",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    fit_payload = json.loads((run_dir / "fit.json").read_text())
    try:
        triangle_csv = _resolve_replay_input(run_dir, run_manifest)
    except InputIntegrityError as exc:
        print(f"run_id: {args.run_id}", file=sys.stderr)
        _print_payload(args.format, exc.payload, lambda p: _render_integrity_error_text(p, args.run_id))
        return EXIT_INTERNAL_ERROR

    adapter = ChainladderAdapter()
    tri_handle = adapter.load_triangle(triangle_csv)
    fit_result = adapter.fit(
        tri_handle, fit_payload["method"], _params_from_fit_payload(fit_payload["parameters"])
    )
    diag_result = adapter.diagnostics(tri_handle, fit_result)

    payload = diag_result.to_diagnostics_json(args.run_id)
    exit_code = EXIT_MODEL_WARNING if diag_result.overall != "pass" else EXIT_SUCCESS

    if not args.dry_run:
        (run_dir / "diagnostics.json").write_text(_dump_json(payload) + "\n")
        manifest.update_manifest(run_dir, add_outputs=["diagnostics.json"], exit_code=exit_code)

    _log_run(args.run_id, args.out, args.dry_run, ["diagnostics.json"])
    _print_payload(args.format, payload, lambda p: _render_diagnostics_text(p, args.run_id))
    return exit_code


def _params_from_fit_payload(parameters: dict) -> dict:
    return {
        "averaging": parameters["averaging"],
        "tail": parse_tail_param(parameters["tail"]),
        "n_periods": parameters["n_periods"],
        "excluded_origins": parameters["excluded_origins"],
        "excluded_valuations": parameters["excluded_valuations"],
        # .get(), not [] — a fit.json persisted before this parameter
        # existed won't have the key; falls back to the current default.
        "sigma_interpolation": parameters.get("sigma_interpolation", "mack"),
        "selected_factors": parameters.get("selected_factors", []),
    }


def _render_diagnostics_text(payload: dict, run_id: str) -> str:
    lines = [f"run_id: {run_id}", "tests:"]
    for t in payload["tests"]:
        lines.append(
            f"  [{t['verdict'].upper():4}] {t['test_id']:<24} "
            f"statistic={t['statistic']:.3f} threshold={t['threshold']}"
        )
        if t["prescribed_actions"]:
            for action in t["prescribed_actions"]:
                lines.append(f"         -> {action}")
    lines.append(f"overall: {payload['overall'].upper()}")
    return "\n".join(lines)


def cmd_sensitivity(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if args.grid != "default":
        print("usage error: custom --grid files are not supported yet (only 'default')", file=sys.stderr)
        return EXIT_USAGE_ERROR

    run_manifest = manifest.read_manifest(run_dir)
    if "fit.json" not in run_manifest["outputs"]:
        print(
            f"usage error: run '{args.run_id}' has no fit.json — sensitivity runs against an "
            "existing fit, not a bare validate run",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR

    fit_payload = json.loads((run_dir / "fit.json").read_text())
    try:
        triangle_csv = _resolve_replay_input(run_dir, run_manifest)
    except InputIntegrityError as exc:
        print(f"run_id: {args.run_id}", file=sys.stderr)
        _print_payload(args.format, exc.payload, lambda p: _render_integrity_error_text(p, args.run_id))
        return EXIT_INTERNAL_ERROR
    base_params = dict(fit_payload["parameters"])

    # --exclude-origins/--exclude-valuations here layer onto every grid
    # scenario as an additional baseline constraint, same semantics as on
    # `fit` — not a substitute for the grid, and not a standalone scenario.
    cli_excluded_origins = _split_list_arg(args.exclude_origins)
    if cli_excluded_origins:
        base_params["excluded_origins"] = list(
            dict.fromkeys(list(base_params.get("excluded_origins") or []) + cli_excluded_origins)
        )
    cli_excluded_valuations = _split_list_arg(args.exclude_valuations)
    if cli_excluded_valuations:
        base_params["excluded_valuations"] = list(
            dict.fromkeys(list(base_params.get("excluded_valuations") or []) + cli_excluded_valuations)
        )

    all_origins, all_valuations = sensitivity.triangle_origins_and_valuations(triangle_csv)
    grid = sensitivity.build_default_grid(base_params, all_origins, all_valuations)

    adapter = ChainladderAdapter()
    tri_handle = adapter.load_triangle(triangle_csv)

    base_ibnr = fit_payload["totals"]["ibnr"]
    scenario_ibnr_values = []
    scenario_rows = []
    for entry in grid:
        scenario_params = sensitivity.apply_overrides(base_params, entry["param_overrides"])
        result = adapter.fit(tri_handle, fit_payload["method"], _params_from_fit_payload(scenario_params))
        scenario_rows.append(
            {
                "scenario_id": entry["scenario_id"],
                "delta_from_base": entry["delta_from_base"],
                "totals": {
                    "ultimate": result.totals["ultimate"],
                    "ibnr": result.totals["ibnr"],
                    "mack_se": result.totals["mack_se"],
                },
            }
        )
        scenario_ibnr_values.append(result.totals["ibnr"])

    payload = {
        "run_id": args.run_id,
        # v0.1.14: the base fit's parameters *as perturbed by this call's own*
        # --exclude-origins/--exclude-valuations (base_params, not
        # fit_payload["parameters"]) — without this, those CLI-supplied
        # baseline exclusions were not reconstructable from sensitivity.json
        # alone; every scenario's delta_from_base was relative to a baseline
        # the file never actually recorded. Found by independent review.
        "base_parameters": base_params,
        "scenarios": scenario_rows,
        "range": sensitivity.compute_range(base_ibnr, scenario_ibnr_values),
    }

    if not args.dry_run:
        (run_dir / "sensitivity.json").write_text(_dump_json(payload) + "\n")
        # sensitivity computes supplementary scenarios over an existing fit;
        # unlike fit/diagnostics it carries no pass/warn verdict of its own
        # (always exit 0 — docs/cli-spec.md). update_manifest's normal
        # contract overwrites exit_code with "the latest command's code",
        # which is correct for a genuine new assessment but was silently
        # erasing a real diagnostics warning (exit 3) once sensitivity ran
        # afterwards — a warned run could then read as clean from `reserve
        # runs list`. Found by independent review (v0.1.14). Fixed the same
        # way `report` already handles this (see cmd_report): carry the
        # run's current exit_code forward instead of overwriting it.
        current = manifest.read_manifest(run_dir)
        manifest.update_manifest(
            run_dir, add_outputs=["sensitivity.json"], exit_code=current["exit_code"]
        )

    _log_run(args.run_id, args.out, args.dry_run, ["sensitivity.json"])
    _print_payload(args.format, payload, lambda p: _render_sensitivity_text(p, args.run_id))
    return EXIT_SUCCESS


def _render_sensitivity_text(payload: dict, run_id: str) -> str:
    lines = [f"run_id: {run_id}", "scenarios:"]
    for row in payload["scenarios"]:
        delta = row["delta_from_base"]
        t = row["totals"]
        lines.append(
            f"  {row['scenario_id']:<22} {delta['parameter']}={delta['value']!r:<14} "
            f"ultimate={_format_number_text(t['ultimate'])} "
            f"ibnr={_format_number_text(t['ibnr'])} "
            f"mack_se={_format_number_text(t['mack_se'])}"
        )
    r = payload["range"]
    lines.append(
        f"range: base_ibnr={_format_number_text(r['base_ibnr'])} "
        f"ibnr_min={_format_number_text(r['ibnr_min'])} "
        f"ibnr_max={_format_number_text(r['ibnr_max'])}"
    )
    return "\n".join(lines)


def cmd_runs_list(args: argparse.Namespace) -> int:
    run_ids = runs.list_run_ids(out_root=args.out)
    manifests = [manifest.read_manifest(runs.run_dir_path(rid, args.out)) for rid in run_ids]
    payload = {"runs": manifests}
    _print_payload(args.format, payload, _render_runs_list_text)
    return EXIT_SUCCESS


def _render_runs_list_text(payload: dict) -> str:
    if not payload["runs"]:
        return "no runs found"
    lines = []
    for m in payload["runs"]:
        lines.append(
            f"{m['run_id']}  exit={m['exit_code']}  outputs={','.join(m['outputs'])}  {m['command']}"
        )
    return "\n".join(lines)


def cmd_runs_show(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    payload = manifest.read_manifest(run_dir)
    _print_payload(args.format, payload, _render_runs_show_text)
    return EXIT_SUCCESS


def _render_runs_show_text(payload: dict) -> str:
    lines = [
        f"run_id:      {payload['run_id']}",
        f"created_utc: {payload['created_utc']}",
        f"command:     {payload['command']}",
        f"engine:      {payload['engine']}",
        f"parameters:  {payload['parameters']}",
        f"outputs:     {payload['outputs']}",
        f"exit_code:   {payload['exit_code']}",
    ]
    return "\n".join(lines)


def cmd_report(args: argparse.Namespace) -> int:
    if args.format_out == "md":
        print("usage error: --format-out md is not implemented yet (only 'html')", file=sys.stderr)
        return EXIT_USAGE_ERROR

    run_dir = runs.run_dir_path(args.run_id, out_root=args.out)
    incomplete_reason = report_html.check_complete(run_dir)
    if incomplete_reason is not None:
        print(f"usage error: {incomplete_reason}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    if args.require_approval:
        approval_error = _report_approval_gate_error(args.run_id, run_dir)
        if approval_error is not None:
            print(f"usage error: {approval_error}", file=sys.stderr)
            return EXIT_USAGE_ERROR

    html_text = report_html.render(args.run_id, run_dir)
    report_path = run_dir / "report.html"

    if not args.dry_run:
        report_path.write_text(html_text)
        # Append to outputs without disturbing exit_code — report is a
        # rendering step over an already-assessed run, not a new assessment;
        # overwriting exit_code here would erase a genuine warning from
        # diagnostics/sensitivity the way update_manifest's normal contract
        # (used by those commands) is meant to reflect the latest *assessment*.
        current = manifest.read_manifest(run_dir)
        manifest.update_manifest(run_dir, add_outputs=["report.html"], exit_code=current["exit_code"])

    _log_run(args.run_id, args.out, args.dry_run, ["report.html"])
    print(str(report_path))
    return EXIT_SUCCESS


def _active_decisions_by_type(run_dir: Path, decision_type: str) -> list[dict]:
    return [
        decision
        for decision in workbench_io.active_decisions(workbench_io.load_decisions(run_dir))
        if decision.get("decision_type") == decision_type
        and decision.get("status") in {"accepted", "modified"}
    ]


def _decision_artifacts_are_current(run_dir: Path, decision: dict) -> bool:
    reviewed = decision.get("source_artifacts_reviewed", [])
    if not isinstance(reviewed, list):
        return False
    material_reviewed = [name for name in reviewed if name != "manifest.json"]
    expected = {
        name: digest
        for name, digest in (decision.get("input_hashes") or {}).items()
        if name in material_reviewed
    }
    return workbench_io.artifact_hashes(run_dir, material_reviewed) == expected


def _report_approval_gate_error(run_id: str, run_dir: Path) -> str | None:
    task_payload = workbench_tasks.build_validation_tasks(run_id, run_dir)
    pending = [task for task in task_payload.get("tasks", []) if task.get("status") == "pending"]
    prerequisite_pending = [
        task
        for task in pending
        if task.get("task_type") in {"warning_review", "scenario_selection", "bcl_review"}
    ]
    if prerequisite_pending:
        titles = "; ".join(task.get("title", task["task_id"]) for task in prerequisite_pending)
        return f"unresolved required workbench tasks remain: {titles}"

    committed_selection_sets = [
        selection_set
        for selection_set in selection_sets.list_selection_sets(run_dir)
        if selection_set.get("status") == "committed"
    ]
    all_decisions = workbench_io.load_decisions(run_dir)
    active_selection_approvals = _active_decisions_by_type(run_dir, "selection_set_approval")
    approved_selection_ids = {
        decision.get("selection_set_id")
        for decision in all_decisions
        if decision.get("decision_type") == "selection_set_approval"
        and decision.get("status") in {"accepted", "modified"}
        if decision.get("selection_set_id")
    }
    missing_selection_approvals = [
        selection_set.get("selection_set_id")
        for selection_set in committed_selection_sets
        if selection_set.get("selection_set_id") not in approved_selection_ids
    ]
    if missing_selection_approvals:
        return (
            "committed selection set exists without active selection_set_approval decision: "
            + ", ".join(str(selection_id) for selection_id in missing_selection_approvals)
        )

    if len(active_selection_approvals) > 1:
        return "multiple active selection_set_approval decisions exist; the reporting basis is ambiguous"

    stale_selection_approvals = [
        decision.get("decision_id")
        for decision in active_selection_approvals
        if not _decision_artifacts_are_current(run_dir, decision)
    ]
    if stale_selection_approvals:
        return (
            "selection_set_approval decision source artifacts are stale; recommit approval: "
            + ", ".join(str(decision_id) for decision_id in stale_selection_approvals)
        )

    report_approvals = _active_decisions_by_type(run_dir, "report_approval")
    if not report_approvals:
        return "report approval decision is required; commit a report_approval decision before using --require-approval"

    stale_report_approvals = [
        decision.get("decision_id")
        for decision in report_approvals
        if not _decision_artifacts_are_current(run_dir, decision)
    ]
    if stale_report_approvals:
        return (
            "report_approval decision source artifacts are stale; recommit report approval: "
            + ", ".join(str(decision_id) for decision_id in stale_report_approvals)
        )

    for approval in report_approvals:
        snapshot_id = str(approval.get("review_snapshot_id") or "").strip()
        if not snapshot_id:
            return "report_approval decision is not bound to a review snapshot; recommit report approval"
        try:
            snapshot = workbench_review_snapshots.load_review_snapshot(run_dir, snapshot_id)
        except workbench_review_snapshots.ReviewSnapshotError as exc:
            return str(exc)
        if snapshot is None:
            return f"report approval review snapshot is missing: {snapshot_id}"
        try:
            workbench_review_snapshots.validate_review_snapshot(run_id, run_dir, snapshot)
        except workbench_review_snapshots.ReviewSnapshotError as exc:
            return f"report approval review snapshot is stale: {exc}"

    if pending:
        titles = "; ".join(task.get("title", task["task_id"]) for task in pending)
        return f"unresolved workbench tasks remain: {titles}"
    return None


def _append_outputs_preserving_exit(run_dir: Path, outputs: list[str]) -> None:
    manifest_path = Path(run_dir) / "manifest.json"
    if not manifest_path.is_file():
        return
    current = manifest.read_manifest(run_dir)
    manifest.update_manifest(run_dir, add_outputs=outputs, exit_code=current["exit_code"])


def cmd_tasks(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if args.dry_run:
        payload = workbench_tasks.build_validation_tasks(args.run_id, run_dir)
    else:
        payload = workbench_tasks.write_validation_tasks(args.run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, ["validation_tasks.json"])

    _log_run(args.run_id, args.out, args.dry_run, ["validation_tasks.json"])
    _print_payload(args.format, payload, _render_tasks_text)
    return EXIT_SUCCESS


def _render_tasks_text(payload: dict) -> str:
    lines = [f"run_id: {payload['run_id']}", f"status: {payload['status']}", "tasks:"]
    if not payload["tasks"]:
        lines.append("  none")
        return "\n".join(lines)
    for task in payload["tasks"]:
        lines.append(
            f"  [{task['status'].upper():9}] {task['task_id']} "
            f"{task['task_type']} {task['title']}"
        )
    return "\n".join(lines)


def cmd_status(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    payload = workbench_state.derive_status(args.run_id, run_dir)
    _print_payload(args.format, payload, _render_status_text)
    return EXIT_SUCCESS


def _render_status_text(payload: dict) -> str:
    lines = [
        f"run_id: {payload['run_id']}",
        f"status: {payload['status']}",
        f"unresolved_tasks: {payload['unresolved_task_count']}",
        f"completed_decisions: {payload['completed_decision_count']}",
    ]
    if payload["missing_required_artifacts"]:
        lines.append(f"missing_required_artifacts: {', '.join(payload['missing_required_artifacts'])}")
    return "\n".join(lines)


def cmd_handoff(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    payload = (
        workbench_handoff.build_review_handoff(args.run_id, run_dir)
        if args.dry_run
        else workbench_handoff.write_review_handoff(args.run_id, run_dir)
    )
    if not args.dry_run:
        _append_outputs_preserving_exit(run_dir, [workbench_schemas.HANDOFF_FILENAME])
    _log_run(args.run_id, args.out, args.dry_run, [workbench_schemas.HANDOFF_FILENAME])
    _print_payload(args.format, payload, _render_handoff_text)
    return EXIT_SUCCESS


def _render_handoff_text(payload: dict) -> str:
    lines = [
        f"run_id: {payload['run_id']}",
        f"phase: {payload['phase']}",
        f"method: {payload['display_method']}",
        f"report_readiness: {payload['report_readiness']}",
        f"resume_command: {payload['resume_command']}",
        "pending_judgment:",
    ]
    for task in payload.get("pending_judgment", []):
        lines.append(f"  {task['task_id']}: {task['title']}")
    if not payload.get("pending_judgment"):
        lines.append("  none")
    return "\n".join(lines)


def cmd_scenarios(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if args.dry_run:
        payload = workbench_scenarios.build_scenario_index(args.run_id, run_dir)
    else:
        payload = workbench_scenarios.write_scenario_index(args.run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, ["scenario_index.json"])

    _log_run(args.run_id, args.out, args.dry_run, ["scenario_index.json"])
    _print_payload(args.format, payload, _render_scenarios_text)
    return EXIT_SUCCESS


def cmd_factor_analysis(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
        if args.dry_run:
            analysis = factor_analysis.build_factor_analysis(args.run_id, run_dir)
            suggestions = factor_analysis.build_review_suggestions(analysis)
        else:
            analysis, suggestions = factor_analysis.write_factor_analysis(args.run_id, run_dir)
            _append_outputs_preserving_exit(
                run_dir,
                [
                    workbench_schemas.FACTOR_ANALYSIS_FILENAME,
                    workbench_schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
                ],
            )
    except (RunNotFoundError, factor_analysis.FactorAnalysisError) as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    filenames = [
        workbench_schemas.FACTOR_ANALYSIS_FILENAME,
        workbench_schemas.FACTOR_REVIEW_SUGGESTIONS_FILENAME,
    ]
    _log_run(args.run_id, args.out, args.dry_run, filenames)
    payload = {
        "run_id": args.run_id,
        "analysis": analysis,
        "review_suggestions": suggestions,
    }
    _print_payload(args.format, payload, _render_factor_analysis_text)
    return EXIT_SUCCESS


def _render_factor_analysis_text(payload: dict) -> str:
    analysis = payload["analysis"]
    suggestions = payload["review_suggestions"].get("suggestions", [])
    return "\n".join(
        [
            f"run_id: {payload['run_id']}",
            f"analysis_id: {analysis['analysis_id']}",
            f"development_periods: {len(analysis.get('development_periods', []))}",
            f"influence_points: {len(analysis.get('influence_ranking', []))}",
            f"review_suggestions: {len(suggestions)}",
            "governance: suggestions are exploratory; preview and committed approval remain required",
        ]
    )


def _render_scenarios_text(payload: dict) -> str:
    lines = [f"run_id: {payload['run_id']}", f"status: {payload['status']}", "scenarios:"]
    if not payload["scenarios"]:
        lines.append("  none")
        return "\n".join(lines)
    for scenario in payload["scenarios"]:
        metrics = scenario.get("key_metrics", {})
        ibnr = metrics.get("ibnr")
        ibnr_text = "n/a" if ibnr is None else f"{ibnr:.1f}"
        lines.append(
            f"  [{scenario['status']:<10}] {scenario['scenario_id']:<22} "
            f"{scenario['scenario_type']:<12} ibnr={ibnr_text}"
        )
    return "\n".join(lines)


def cmd_compare(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        if args.dry_run:
            payload = workbench_scenarios.build_comparison(args.run_id, run_dir, args.scenario_id)
        else:
            workbench_scenarios.write_scenario_index(args.run_id, run_dir)
            payload = workbench_scenarios.write_comparison(args.run_id, run_dir, args.scenario_id)
            _append_outputs_preserving_exit(
                run_dir,
                [
                    "scenario_index.json",
                    f"comparisons/{payload['comparison_id']}.json",
                ],
            )
    except workbench_scenarios.ScenarioValidationError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    filenames = ["scenario_index.json", f"comparisons/{payload['comparison_id']}.json"]
    _log_run(args.run_id, args.out, args.dry_run, filenames)
    _print_payload(args.format, payload, _render_comparison_text)
    return EXIT_SUCCESS


def _render_comparison_text(payload: dict) -> str:
    lines = [
        f"comparison_id: {payload['comparison_id']}",
        f"base_run_id: {payload['base_run_id']}",
        f"candidate_scenario_id: {payload['candidate_scenario_id']}",
        "deltas:",
    ]
    for name, value in payload["deltas"].items():
        text = "n/a" if value is None else f"{value:.1f}"
        lines.append(f"  {name}: {text}")
    return "\n".join(lines)


def cmd_selection_sets_list(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    payload = {
        "schema_version": "0.1",
        "run_id": args.run_id,
        "selection_sets": selection_sets.list_selection_sets(run_dir),
    }
    _print_payload(args.format, payload, _render_selection_sets_list_text)
    return EXIT_SUCCESS


def _render_selection_sets_list_text(payload: dict) -> str:
    lines = [f"run_id: {payload['run_id']}", "selection_sets:"]
    if not payload["selection_sets"]:
        lines.append("  none")
        return "\n".join(lines)
    for selection_set in payload["selection_sets"]:
        lines.append(
            f"  [{selection_set.get('status', 'unknown'):<9}] "
            f"{selection_set.get('selection_set_id')} "
            f"scenario={selection_set.get('preview_scenario_id')}"
        )
    return "\n".join(lines)


def cmd_selection_sets_show(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    selection_set = selection_sets.load_selection_set(run_dir, args.selection_set_id)
    if selection_set is None:
        print(f"usage error: selection_set_id does not exist: {args.selection_set_id}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    _print_payload(args.format, selection_set, _render_selection_set_text)
    return EXIT_SUCCESS


def _load_selection_set_request(path: Path, run_id: str) -> dict:
    request = json.loads(Path(path).read_text())
    if not isinstance(request, dict):
        raise ValueError("selection-set request file must contain a JSON object")
    schema_version = request.get("schema_version")
    if schema_version is not None and schema_version != "0.1":
        raise ValueError(f"unsupported selection-set request schema_version: {schema_version}")
    request_run_id = request.get("run_id")
    if request_run_id is not None and request_run_id != run_id:
        raise ValueError(f"selection-set request run_id does not match target run_id: {request_run_id}")
    return request


def cmd_selection_sets_preview(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
        request = _load_selection_set_request(args.request_file, args.run_id)
        preview = selection_sets.build_selection_set_preview(
            args.run_id,
            run_dir,
            request,
            command=f"reserve selection-sets preview {args.run_id} --request-file {args.request_file}",
            dry_run=args.dry_run,
        )
    except (RunNotFoundError, OSError, json.JSONDecodeError, ValueError, selection_sets.SelectionSetError) as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    if not args.dry_run:
        _append_outputs_preserving_exit(run_dir, [preview["selection_set_artifact"]])
    _log_run(args.run_id, args.out, args.dry_run, [preview["selection_set_artifact"]])
    _print_payload(args.format, preview, _render_selection_set_text)
    return EXIT_SUCCESS


def cmd_selection_sets_commit(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        decision_candidate = workbench_io.read_json(args.decision_file)
        if decision_candidate.get("decision_type") != "selection_set_approval":
            raise workbench_decisions.DecisionValidationError(
                "selection-sets commit requires a selection_set_approval decision file"
            )
        if str(decision_candidate.get("selection_set_id") or "") != str(args.selection_set_id):
            raise workbench_decisions.DecisionValidationError(
                "decision selection_set_id does not match --selection-set-id"
            )
        original_selection_set = selection_sets.load_selection_set(run_dir, args.selection_set_id)
        if original_selection_set is None:
            raise selection_sets.SelectionSetError(f"selection_set_id does not exist: {args.selection_set_id}")
        committed = selection_sets.commit_selection_set(
            args.run_id,
            run_dir,
            args.selection_set_id,
            {
                "global_rationale": original_selection_set.get("global_rationale"),
                "created_by": decision_candidate.get("user") or original_selection_set.get("created_by") or {},
            },
            # The decision validator intentionally requires the selection-set
            # artifact to be committed. For CLI dry-runs, write that temporary
            # state, validate the decision with dry_run=True, then restore the
            # original preview before returning.
            dry_run=False,
        )
        decision = workbench_decisions.commit_decision_payload(
            args.run_id,
            run_dir,
            decision_candidate,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            path = selection_sets.selection_set_path(run_dir, args.selection_set_id)
            workbench_io.write_json(path, original_selection_set)
    except (
        OSError,
        json.JSONDecodeError,
        selection_sets.SelectionSetError,
        workbench_decisions.DecisionValidationError,
        FileExistsError,
    ) as exc:
        if "original_selection_set" in locals() and original_selection_set is not None:
            path = selection_sets.selection_set_path(run_dir, args.selection_set_id)
            current = selection_sets.load_selection_set(run_dir, args.selection_set_id)
            if current and current.get("status") == "committed":
                workbench_io.write_json(path, original_selection_set)
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    filenames = [
        committed["selection_set_artifact"],
        f"decisions/{decision['decision_id']}.json",
        "validation_tasks.json",
    ]
    if not args.dry_run:
        workbench_tasks.write_validation_tasks(args.run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, filenames)
    _log_run(args.run_id, args.out, args.dry_run, filenames)
    payload = {
        "schema_version": "0.1",
        "run_id": args.run_id,
        "selection_set": committed,
        "decision": decision,
        "status": workbench_state.derive_status(args.run_id, run_dir),
    }
    _print_payload(args.format, payload, _render_selection_set_commit_text)
    return EXIT_SUCCESS


def _render_selection_set_text(payload: dict) -> str:
    return "\n".join(
        [
            f"selection_set_id: {payload.get('selection_set_id')}",
            f"run_id: {payload.get('run_id')}",
            f"status: {payload.get('status')}",
            f"preview_scenario_id: {payload.get('preview_scenario_id')}",
            f"factor_selections: {len(payload.get('factor_selections', []))}",
            f"exclusions: {len(payload.get('exclusions', []))}",
        ]
    )


def _render_selection_set_commit_text(payload: dict) -> str:
    selection_set = payload["selection_set"]
    decision = payload["decision"]
    return "\n".join(
        [
            f"selection_set_id: {selection_set['selection_set_id']}",
            f"selection_set_status: {selection_set['status']}",
            f"decision_id: {decision['decision_id']}",
            f"decision_type: {decision['decision_type']}",
            f"run_status: {payload['status']['status']}",
        ]
    )


def cmd_dashboard(args: argparse.Namespace) -> int:
    try:
        import uvicorn
        from harness.workbench.api import create_app
    except ImportError as exc:
        print(f"usage error: dashboard dependencies are not installed: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    app = create_app(args.out)
    print(f"dashboard: http://{args.host}:{args.port}/workbench-v2/", file=sys.stderr)
    print(f"runs_root: {args.out}", file=sys.stderr)
    uvicorn.run(app, host=args.host, port=args.port)
    return EXIT_SUCCESS


def cmd_decide(args: argparse.Namespace) -> int:
    try:
        run_dir = runs.resolve_run_dir(args.run_id, out_root=args.out)
    except RunNotFoundError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    try:
        payload = workbench_decisions.commit_decision(
            args.run_id, run_dir, args.decision_file, dry_run=args.dry_run
        )
    except (
        workbench_decisions.DecisionValidationError,
        FileExistsError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    filenames = [f"decisions/{payload['decision_id']}.json", "validation_tasks.json"]
    if payload.get("review_snapshot_id"):
        filenames.append(
            workbench_review_snapshots.snapshot_artifact(payload["review_snapshot_id"])
        )
    if not args.dry_run:
        workbench_tasks.write_validation_tasks(args.run_id, run_dir)
        _append_outputs_preserving_exit(run_dir, filenames)

    _log_run(args.run_id, args.out, args.dry_run, filenames)
    _print_payload(args.format, payload, _render_decision_text)
    return EXIT_SUCCESS


def _render_decision_text(payload: dict) -> str:
    return "\n".join(
        [
            f"decision_id: {payload['decision_id']}",
            f"run_id: {payload['run_id']}",
            f"task_id: {payload.get('task_id')}",
            f"decision_type: {payload['decision_type']}",
            f"status: {payload['status']}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except Exception as exc:  # internal error — exit 1, traceback to stderr
        import traceback

        traceback.print_exc(file=sys.stderr)
        print(f"internal error: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR


if __name__ == "__main__":
    sys.exit(main())
