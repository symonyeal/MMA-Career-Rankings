"""Persist a UFC-only versus FightMatrix-public source-scope comparison."""
from __future__ import annotations

import argparse
from pathlib import Path

from analysis.source_scope import build_scope_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufc-snapshot", required=True)
    parser.add_argument("--public-snapshot", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build_scope_comparison(
        Path(args.ufc_snapshot), Path(args.public_snapshot), output_path=Path(args.output)
    )
    print(f"[scope comparison] rows={len(result):,} output={Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
