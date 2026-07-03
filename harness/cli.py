"""`reserve` CLI — parsing, exit codes, dispatch (docs/cli-spec.md).

Flag policy is per-command, taken literally from each command's signature in
docs/cli-spec.md rather than applied blanket across every writing command:
`--format` and `--out` are added wherever a command's signature lists them;
`--dry-run` only where the signature explicitly lists it (`fit` only, as of
v0.1.3 — `validate`/`diagnostics`/`sensitivity` also write to runs/ but
don't have it).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from engine.chainladder_adapter import ChainladderAdapter, parse_tail_param
from harness import manifest, runs, sensitivity, triangle_io, triangle_projection, validation
from harness.render import report_html
from harness.runs import RunNotFoundError

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
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        sys.exit(EXIT_USAGE_ERROR)


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(prog="reserve")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_ArgumentParser)

    p_validate = subparsers.add_parser("validate", help="Structural checks on a triangle CSV")
    p_validate.add_argument("triangle_csv", type=Path)
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
    p_fit.add_argument(
        "--sigma-interpolation",
        choices=["mack", "log-linear"],
        default="mack",
    )
    _add_format_arg(p_fit)
    _add_out_arg(p_fit)
    p_fit.add_argument("--dry-run", action="store_true")
    p_fit.set_defaults(handler=cmd_fit)

    p_diag = subparsers.add_parser("diagnostics", help="Run assumption tests against an existing fit")
    p_diag.add_argument("run_id")
    _add_format_arg(p_diag)
    _add_out_arg(p_diag)
    p_diag.set_defaults(handler=cmd_diagnostics)

    p_sens = subparsers.add_parser("sensitivity", help="Re-run a fit over a perturbation grid")
    p_sens.add_argument("run_id")
    p_sens.add_argument("--grid", default="default")
    p_sens.add_argument("--exclude-origins", default="")
    p_sens.add_argument("--exclude-valuations", default="")
    _add_format_arg(p_sens)
    _add_out_arg(p_sens)
    p_sens.set_defaults(handler=cmd_sensitivity)

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
    _add_out_arg(p_report)
    p_report.set_defaults(handler=cmd_report)

    return parser


def _split_list_arg(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _invocation_string(command: str, args: argparse.Namespace) -> str:
    parts = [f"reserve {command}"]
    if getattr(args, "triangle_csv", None) is not None:
        parts.append(str(args.triangle_csv))
    if getattr(args, "run_id", None) is not None:
        parts.append(str(args.run_id))
    if hasattr(args, "method"):
        parts.append(f"--method {args.method}")
    parts.append(f"--format {args.format}")
    if hasattr(args, "out"):
        parts.append(f"--out {args.out}")
    if getattr(args, "dry_run", False):
        parts.append("--dry-run")
    return " ".join(parts)


def cmd_validate(args: argparse.Namespace) -> int:
    result = validation.validate_triangle_csv(args.triangle_csv)
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
            parameters={},
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
        f"basis:      {payload['basis']}",
        f"dimensions: {payload['dimensions']}",
        "checks:",
    ]
    for check in payload["checks"]:
        lines.append(f"  [{check['verdict'].upper():4}] {check['check_id']}")
        if check["details"]:
            lines.append(f"         {check['details']}")
    lines.append(f"verdict: {payload['verdict'].upper()}")
    return "\n".join(lines)


def cmd_fit(args: argparse.Namespace) -> int:
    try:
        tail = parse_tail_param(args.tail)
    except ValueError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        return EXIT_USAGE_ERROR

    validation_result = validation.validate_triangle_csv(args.triangle_csv)
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
                parameters={},
                outputs=["validation.json"],
                exit_code=EXIT_VALIDATION_FAILURE,
            ),
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

    params = {
        "averaging": args.averaging,
        "tail": tail,
        "n_periods": args.n_periods,
        "excluded_origins": _split_list_arg(args.exclude_origins),
        "excluded_valuations": _split_list_arg(args.exclude_valuations),
        "sigma_interpolation": args.sigma_interpolation,
    }

    tri_handle = adapter.load_triangle(args.triangle_csv)
    fit_result = adapter.fit(tri_handle, args.method, params)
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
            parameters=fit_result.parameters,
            outputs=["validation.json", "fit.json", "triangle.json"],
            exit_code=exit_code,
        ),
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
        if not math.isfinite(value):
            warnings_found.append({"warning": "non_finite_total", "field": field_name})
    for row in fit_result.by_origin:
        for field_name in ("ultimate", "ibnr", "mack_se"):
            if not math.isfinite(row[field_name]):
                warnings_found.append(
                    {"warning": "non_finite_by_origin", "origin": row["origin"], "field": field_name}
                )
    return warnings_found


def _inputs_for(path: Path, sha256: str | None) -> list[dict]:
    if sha256:
        return [{"path": str(path), "sha256": sha256}]
    return [{"path": str(path), "sha256": None}]


def _write_run(*, run_id, out_root, dry_run, files: dict, manifest_kwargs) -> None:
    if dry_run:
        return
    run_dir = runs.create_run_dir(run_id, out_root=out_root)
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
            f"  {row['origin']}: latest={row['latest']:.1f} ultimate={row['ultimate']:.1f} "
            f"ibnr={row['ibnr']:.1f} mack_se={row['mack_se']:.1f}"
        )
    t = payload["totals"]
    lines.append(
        f"totals: latest={t['latest']:.1f} ultimate={t['ultimate']:.1f} "
        f"ibnr={t['ibnr']:.1f} mack_se={t['mack_se']:.1f}"
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
    triangle_csv = Path(run_manifest["inputs"][0]["path"])

    adapter = ChainladderAdapter()
    tri_handle = adapter.load_triangle(triangle_csv)
    fit_result = adapter.fit(
        tri_handle, fit_payload["method"], _params_from_fit_payload(fit_payload["parameters"])
    )
    diag_result = adapter.diagnostics(tri_handle, fit_result)

    payload = diag_result.to_diagnostics_json(args.run_id)
    exit_code = EXIT_MODEL_WARNING if diag_result.overall != "pass" else EXIT_SUCCESS

    (run_dir / "diagnostics.json").write_text(_dump_json(payload) + "\n")
    manifest.update_manifest(run_dir, add_outputs=["diagnostics.json"], exit_code=exit_code)

    print(f"run_id: {args.run_id}", file=sys.stderr)
    print(f"wrote {run_dir / 'diagnostics.json'}", file=sys.stderr)
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
    triangle_csv = Path(run_manifest["inputs"][0]["path"])
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
        "scenarios": scenario_rows,
        "range": sensitivity.compute_range(base_ibnr, scenario_ibnr_values),
    }

    (run_dir / "sensitivity.json").write_text(_dump_json(payload) + "\n")
    manifest.update_manifest(run_dir, add_outputs=["sensitivity.json"], exit_code=EXIT_SUCCESS)

    print(f"run_id: {args.run_id}", file=sys.stderr)
    print(f"wrote {run_dir / 'sensitivity.json'}", file=sys.stderr)
    _print_payload(args.format, payload, lambda p: _render_sensitivity_text(p, args.run_id))
    return EXIT_SUCCESS


def _render_sensitivity_text(payload: dict, run_id: str) -> str:
    lines = [f"run_id: {run_id}", "scenarios:"]
    for row in payload["scenarios"]:
        delta = row["delta_from_base"]
        t = row["totals"]
        lines.append(
            f"  {row['scenario_id']:<22} {delta['parameter']}={delta['value']!r:<14} "
            f"ultimate={t['ultimate']:.1f} ibnr={t['ibnr']:.1f} mack_se={t['mack_se']:.1f}"
        )
    r = payload["range"]
    lines.append(
        f"range: base_ibnr={r['base_ibnr']:.1f} ibnr_min={r['ibnr_min']:.1f} ibnr_max={r['ibnr_max']:.1f}"
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

    html_text = report_html.render(args.run_id, run_dir)
    report_path = run_dir / "report.html"
    report_path.write_text(html_text)

    # Append to outputs without disturbing exit_code — report is a
    # rendering step over an already-assessed run, not a new assessment;
    # overwriting exit_code here would erase a genuine warning from
    # diagnostics/sensitivity the way update_manifest's normal contract
    # (used by those commands) is meant to reflect the latest *assessment*.
    current = manifest.read_manifest(run_dir)
    manifest.update_manifest(run_dir, add_outputs=["report.html"], exit_code=current["exit_code"])

    print(f"run_id: {args.run_id}", file=sys.stderr)
    print(f"wrote {report_path}", file=sys.stderr)
    print(str(report_path))
    return EXIT_SUCCESS


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
