"""Compare every experimental rating scope against the UFC-only baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from analysis.fightmatrix_validation import (
    build_anomaly_summary,
    build_anomaly_traces,
    build_scope_validation,
)


def _scope(value: str) -> tuple[str, Path]:
    name, _, path = value.partition("=")
    if not name or not path:
        raise argparse.ArgumentTypeError("expected name=path")
    return name, Path(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope", action="append", type=_scope, required=True,
        help="repeatable name=snapshot_dir; one scope must be named ufc_only",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--trace-scope", action="append", type=_scope, default=[],
        help="repeatable name=snapshot_dir to trace per-bout anomaly evidence for",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    scopes = dict(args.scope)
    if "ufc_only" not in scopes:
        raise SystemExit("one scope must be named ufc_only")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    comparison, panel = build_scope_validation(scopes, output)
    traces = build_anomaly_traces_multi(dict(args.trace_scope), output)
    summary = build_anomaly_summary(panel, traces, output)
    print(json.dumps({
        "scopes": sorted(scopes),
        "scope_rows": len(comparison),
        "panel_rows": len(panel),
        "anomaly_trace_rows": len(traces),
        "anomaly_summary_rows": len(summary),
        "output_dir": str(output),
        "production_default_changed": False,
    }, indent=2))


def build_anomaly_traces_multi(trace_scopes: dict[str, Path], output: Path):
    """Concatenate per-scope traces so one artifact covers every rated scope."""
    import pandas as pd

    frames = []
    for name, path in trace_scopes.items():
        frames.append(build_anomaly_traces(path, output, scope_name=name))
    traces = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()
    traces.to_parquet(output / "fightmatrix_anomaly_traces.parquet", index=False)
    return traces


if __name__ == "__main__":
    main()
