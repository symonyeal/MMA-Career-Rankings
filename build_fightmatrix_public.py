"""Build a local ranked-cohort copy of public FightMatrix profile data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from loaders.fightmatrix_profiles import DEFAULT_PROFILE_CACHE_DIR, build_public_profile_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--cache-dir", default=str(DEFAULT_PROFILE_CACHE_DIR))
    parser.add_argument("--refresh", action="store_true", help="Re-fetch already cached profiles.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--max-profiles", type=int, default=None)
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification only for networks with a managed interception certificate.",
    )
    args = parser.parse_args()
    summary = build_public_profile_snapshot(
        Path(args.snapshot_dir),
        cache_dir=Path(args.cache_dir),
        refresh=args.refresh,
        sleep_seconds=args.sleep_seconds,
        verify_tls=not args.insecure,
        max_profiles=args.max_profiles,
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
