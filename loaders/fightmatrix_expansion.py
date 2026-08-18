"""Bounded, resumable breadth-first expansion of public FightMatrix profiles."""
from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import pandas as pd
import requests

from loaders.fightmatrix_organizations import normalize_organization
from loaders.fightmatrix_profiles import (
    BASE_URL,
    DEFAULT_PROFILE_CACHE_DIR,
    USER_AGENT,
    _id_from_url,
    _profile_cache_path,
    parse_profile_html,
)


PARSER_VERSION = "fightmatrix-profile-2026-08-14.1"
QUEUE_FILE = "fightmatrix_profile_queue.parquet"
PROFILES_FILE = "fightmatrix_profiles_expanded.parquet"
BOUTS_FILE = "fightmatrix_bouts_expanded.parquet"
PROVENANCE_FILE = "fightmatrix_profile_provenance.parquet"

QUEUE_COLUMNS = [
    "profile_id", "canonical_name", "profile_url", "discovery_depth",
    "referring_profile_id", "discovery_date", "discovery_count", "priority_score",
    "fetch_status", "parse_status", "retry_count", "last_error", "http_status",
    "stated_professional_record", "stated_professional_total", "parsed_history_count",
    "completeness_classification", "http_success", "record_reconciled",
    "modeling_complete", "eligible_for_expansion", "expansion_stop_reason",
    "last_attempt_utc", "parsed_at_utc",
]


@dataclass(frozen=True)
class ExpansionConfig:
    max_depth: int = 1
    max_profiles: int = 5_000
    max_new_profiles_per_run: int = 1_000
    request_budget: int = 1_000
    wall_clock_seconds: float = 3_600.0
    min_priority: float = 0.0
    earliest_fight_date: str = "1990-01-01"
    min_professional_bouts: int = 1
    max_organization_tier: int = 4
    max_unresolved_profile_pct: float = 1.0
    target_graph_closure: float = 1.0
    target_weighted_edge_support: float = 1.0
    sleep_seconds: float = 1.0
    max_retries: int = 3
    verify_tls: bool = True
    retry_failed: bool = False
    checkpoint_every: int = 10


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    next_path = path.with_name(path.name + ".next")
    frame.to_parquet(next_path, index=False)
    os.replace(next_path, path)


def _record_parts(record: str | None) -> tuple[int, int, int, int | None] | None:
    """Return stated W/L/D and optional NC without inventing an NC count."""
    if not isinstance(record, str):
        return None
    import re
    match = re.search(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)(?:\s*,\s*(\d+)\s+NC)?", record)
    if match is None:
        return None
    win, loss, draw, nc = match.groups()
    return int(win), int(loss), int(draw), (int(nc) if nc is not None else None)


def _record_total(record: str | None) -> int | None:
    parts = _record_parts(record)
    if parts is None:
        return None
    win, loss, draw, nc = parts
    return win + loss + draw + (nc or 0)


def classify_profile(profile: dict, parsed_history) -> dict:
    """Separate parse success, record reconciliation, and modeling completeness."""
    parts = _record_parts(profile.get("pro_record"))
    total = _record_total(profile.get("pro_record"))
    if isinstance(parsed_history, pd.DataFrame):
        parsed_history_count = len(parsed_history)
        counts = parsed_history.get("result", pd.Series(dtype=str)).value_counts()
        parsed_wld = (int(counts.get("win", 0)), int(counts.get("loss", 0)), int(counts.get("draw", 0)))
        parsed_nc = int(counts.get("nc", 0))
    else:
        parsed_history_count = int(parsed_history)
        parsed_wld = None
        parsed_nc = None
    if not profile.get("fighter"):
        label = "failed"
        reconciled = False
    elif total is None:
        label = "unresolved"
        reconciled = False
    elif parts is not None and parsed_wld == parts[:3] and (parts[3] is None or parsed_nc == parts[3]):
        # FightMatrix often omits NC from the headline W-L-D string. A row-level
        # W/L/D reconciliation plus any parsed NC is stronger evidence than
        # assuming W+L+D must equal the number of history rows.
        label = "complete"
        reconciled = True
    elif parsed_wld is None and parsed_history_count == total:
        label = "complete"
        reconciled = True
    elif parsed_history_count < total:
        label = "partial"
        reconciled = False
    else:
        label = "conflicting"
        reconciled = False
    return {
        "stated_professional_record": profile.get("pro_record"),
        "stated_professional_total": total,
            "parsed_history_count": int(parsed_history_count),
        "completeness_classification": label,
        "record_reconciled": bool(reconciled),
        "modeling_complete": bool(reconciled and parsed_history_count > 0),
    }


def _priority(group: pd.DataFrame) -> float:
    """Impact score: recurrence + adverse seed result + org/title/rank evidence."""
    refs = int(group["fighter_profile_id"].nunique())
    score = 2.0 * math.log1p(refs)
    result = group.get("result", pd.Series(dtype=str)).astype(str)
    score += 2.0 * float(result.isin(["loss", "draw"]).any())
    tiers = [
        normalize_organization(org, date)["organization_tier"]
        for org, date in zip(group.get("org"), group.get("event_date"))
    ]
    best_tier = min(tiers) if tiers else 4
    score += {1: 2.0, 2: 1.25, 3: 0.5, 4: 0.0}.get(best_tier, 0.0)
    score += 1.5 * float(group.get("is_title_fight", pd.Series(False, index=group.index)).fillna(False).any())
    ranks = pd.to_numeric(group.get("opponent_prefight_rank"), errors="coerce").dropna()
    if not ranks.empty:
        score += max(0.0, 1.0 - min(float(ranks.min()), 100.0) / 100.0)
    return round(score, 6)


def _queue_row(
    profile_id: str,
    name: str,
    url: str,
    depth: int,
    referrer: str | None,
    priority: float,
) -> dict:
    return {
        "profile_id": str(profile_id), "canonical_name": name, "profile_url": url,
        "discovery_depth": int(depth), "referring_profile_id": referrer,
        "discovery_date": utc_now(), "discovery_count": 1, "priority_score": float(priority),
        "fetch_status": "pending", "parse_status": "pending", "retry_count": 0,
        "last_error": None, "http_status": None, "stated_professional_record": None,
        "stated_professional_total": None, "parsed_history_count": None,
        "completeness_classification": "unresolved", "http_success": False,
        "record_reconciled": False, "modeling_complete": False,
        "eligible_for_expansion": True, "expansion_stop_reason": None,
        "last_attempt_utc": None, "parsed_at_utc": None,
    }


def initialize_queue(
    snapshot_dir: Path,
    queue_path: Path,
    cache_dir: Path = DEFAULT_PROFILE_CACHE_DIR,
) -> pd.DataFrame:
    """Create depth-zero seed state and discover depth-one stable profile IDs."""
    if queue_path.exists():
        return pd.read_parquet(queue_path).reindex(columns=QUEUE_COLUMNS)
    profiles_path = Path(snapshot_dir) / "fightmatrix_profiles.parquet"
    bouts_path = Path(snapshot_dir) / "fightmatrix_bouts.parquet"
    if not profiles_path.exists() or not bouts_path.exists():
        raise FileNotFoundError("ranked-cohort fightmatrix_profiles/bouts artifacts are required")
    profiles = pd.read_parquet(profiles_path)
    bouts = pd.read_parquet(bouts_path)
    rows: dict[str, dict] = {}
    for profile in profiles.to_dict("records"):
        pid = str(profile["profile_id"])
        row = _queue_row(pid, profile["fighter"], profile["profile_url"], 0, None, 100.0)
        cache_path = _profile_cache_path(Path(cache_dir), profile["profile_url"])
        if cache_path.exists():
            _, complete_history = parse_profile_html(
                cache_path.read_text(encoding="utf-8", errors="replace"), profile["profile_url"]
            )
            state = classify_profile(profile, complete_history)
        else:
            state = classify_profile(profile, int(profile.get("profile_bout_count") or 0))
        row.update(state)
        row.update({
            "fetch_status": "cached", "parse_status": "parsed", "http_status": 200,
            "http_success": True, "parsed_at_utc": utc_now(),
        })
        rows[pid] = row
    stable = bouts.dropna(subset=["opponent_profile_id", "opponent_profile_url"])
    for pid, group in stable.groupby(stable["opponent_profile_id"].astype(str), sort=False):
        if pid in rows:
            continue
        first = group.iloc[0]
        row = _queue_row(
            pid, str(first["opponent"]), str(first["opponent_profile_url"]), 1,
            str(first["fighter_profile_id"]), _priority(group),
        )
        row["discovery_count"] = int(group["fighter_profile_id"].nunique())
        rows[pid] = row
    queue = pd.DataFrame(rows.values()).reindex(columns=QUEUE_COLUMNS)
    _atomic_parquet(queue, queue_path)
    return queue


def _session(config: ExpansionConfig) -> requests.Session:
    session = requests.Session()
    if not config.verify_tls:
        from urllib3 import disable_warnings
        from urllib3.exceptions import InsecureRequestWarning
        disable_warnings(InsecureRequestWarning)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def _fetch(
    session: requests.Session,
    url: str,
    cache_dir: Path,
    config: ExpansionConfig,
) -> tuple[str, dict]:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"fightmatrix.com", "www.fightmatrix.com"}:
        raise ValueError(f"refusing non-FightMatrix profile URL: {url}")
    path = _profile_cache_path(cache_dir, url)
    if path.exists():
        html = path.read_text(encoding="utf-8", errors="replace")
        return html, {
            "cache_hit": True, "http_status": 200,
            "fetch_timestamp": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "raw_cache_path": str(path),
        }
    cache_dir.mkdir(parents=True, exist_ok=True)
    response = session.get(url, timeout=30, verify=config.verify_tls)
    response.raise_for_status()
    path.write_text(response.text, encoding="utf-8")
    if config.sleep_seconds > 0:
        time.sleep(config.sleep_seconds)
    return response.text, {
        "cache_hit": False, "http_status": int(response.status_code),
        "fetch_timestamp": utc_now(), "raw_cache_path": str(path),
    }


def _append_discoveries(
    queue: pd.DataFrame,
    bouts: pd.DataFrame,
    parent_depth: int,
    parent_id: str,
    config: ExpansionConfig,
) -> pd.DataFrame:
    if bouts.empty:
        return queue
    known = set(queue["profile_id"].astype(str))
    candidates = bouts.dropna(subset=["opponent_profile_id", "opponent_profile_url"]).copy()
    additions = []
    for pid, group in candidates.groupby(candidates["opponent_profile_id"].astype(str), sort=False):
        if pid in known:
            match = queue.index[queue["profile_id"].astype(str).eq(pid)]
            if len(match) == 1:
                index = match[0]
                refs = {
                    value for value in str(queue.loc[index, "referring_profile_id"] or "").split("|")
                    if value and value != "nan"
                }
                refs.add(parent_id)
                queue.loc[index, "referring_profile_id"] = "|".join(sorted(refs, key=lambda value: int(value) if value.isdigit() else value))
                queue.loc[index, "discovery_count"] = len(refs)
                local_score = _priority(group)
                queue.loc[index, "priority_score"] = max(
                    float(queue.loc[index, "priority_score"]),
                    local_score - 2.0 * math.log1p(1) + 2.0 * math.log1p(len(refs)),
                )
            continue
        score = _priority(group)
        best_tier = min(
            normalize_organization(org, date)["organization_tier"]
            for org, date in zip(group["org"], group["event_date"])
        )
        dates = pd.to_datetime(group["event_date"], errors="coerce")
        accepted_date = bool(dates.ge(pd.Timestamp(config.earliest_fight_date)).any())
        child_depth = parent_depth + 1
        if child_depth > config.max_depth:
            stop_reason = "maximum_depth"
        elif not accepted_date:
            stop_reason = "earliest_fight_date"
        elif score < config.min_priority:
            stop_reason = "minimum_priority"
        elif best_tier > config.max_organization_tier:
            stop_reason = "organization_tier"
        else:
            stop_reason = None
        first = group.iloc[0]
        row = _queue_row(
            pid, str(first["opponent"]), str(first["opponent_profile_url"]),
            child_depth, parent_id, score,
        )
        if stop_reason:
            row.update({
                "fetch_status": "not_eligible", "eligible_for_expansion": False,
                "expansion_stop_reason": stop_reason,
            })
        additions.append(row)
        known.add(pid)
    if additions:
        queue = pd.concat([queue, pd.DataFrame(additions)], ignore_index=True)
    return queue.reindex(columns=QUEUE_COLUMNS)


def refresh_discoveries(
    queue: pd.DataFrame,
    raw_bouts: pd.DataFrame,
    config: ExpansionConfig,
) -> pd.DataFrame:
    """Rebuild the discovered boundary from every successfully parsed profile."""
    if raw_bouts.empty:
        return queue
    parsed_depth = {
        str(row.profile_id): int(row.discovery_depth)
        for row in queue[queue["parse_status"].eq("parsed")].itertuples(index=False)
    }
    source = raw_bouts[
        raw_bouts["fighter_profile_id"].astype(str).isin(parsed_depth)
        & raw_bouts["opponent_profile_id"].notna()
        & raw_bouts["opponent_profile_url"].notna()
    ].copy()
    if source.empty:
        return queue
    known_index = {str(value): index for index, value in queue["profile_id"].items()}
    additions = []
    for pid, group in source.groupby(source["opponent_profile_id"].astype(str), sort=False):
        parent_ids = sorted(
            set(group["fighter_profile_id"].astype(str)),
            key=lambda value: int(value) if value.isdigit() else value,
        )
        child_depth = min(parsed_depth[parent] for parent in parent_ids) + 1
        score = _priority(group)
        tiers = [
            normalize_organization(org, date)["organization_tier"]
            for org, date in zip(group["org"], group["event_date"])
        ]
        dates = pd.to_datetime(group["event_date"], errors="coerce")
        if child_depth > config.max_depth:
            stop_reason = "maximum_depth"
        elif not dates.ge(pd.Timestamp(config.earliest_fight_date)).any():
            stop_reason = "earliest_fight_date"
        elif score < config.min_priority:
            stop_reason = "minimum_priority"
        elif min(tiers or [4]) > config.max_organization_tier:
            stop_reason = "organization_tier"
        else:
            stop_reason = None
        if pid in known_index:
            index = known_index[pid]
            existing_refs = {
                value for value in str(queue.loc[index, "referring_profile_id"] or "").split("|")
                if value and value != "nan"
            }
            existing_refs.update(parent_ids)
            queue.loc[index, "referring_profile_id"] = "|".join(sorted(
                existing_refs, key=lambda value: int(value) if value.isdigit() else value
            ))
            queue.loc[index, "discovery_count"] = len(existing_refs)
            queue.loc[index, "priority_score"] = max(float(queue.loc[index, "priority_score"]), score)
            continue
        first = group.iloc[0]
        row = _queue_row(
            pid, str(first["opponent"]), str(first["opponent_profile_url"]),
            child_depth, "|".join(parent_ids), score,
        )
        row["discovery_count"] = len(parent_ids)
        if stop_reason:
            row.update({
                "fetch_status": "not_eligible", "eligible_for_expansion": False,
                "expansion_stop_reason": stop_reason,
            })
        additions.append(row)
        known_index[pid] = len(queue) + len(additions) - 1
    if additions:
        queue = pd.concat([queue, pd.DataFrame(additions)], ignore_index=True)
    return queue.reindex(columns=QUEUE_COLUMNS)


def _closure(queue: pd.DataFrame) -> float:
    if queue.empty:
        return 0.0
    return float(queue["parse_status"].eq("parsed").mean())


def _weighted_edge_support(queue: pd.DataFrame, bouts: pd.DataFrame) -> float:
    """Share of seed-edge importance with successfully parsed endpoints."""
    if bouts is None or bouts.empty:
        return 0.0
    parsed = set(queue.loc[queue["parse_status"].eq("parsed"), "profile_id"].astype(str))
    weights = []
    supported = []
    for row in bouts.to_dict("records"):
        weight = 1.0 + 0.75 * bool(row.get("is_title_fight"))
        result = str(row.get("result") or "")
        weight += 0.5 * (result in {"loss", "draw"})
        weights.append(weight)
        supported.append(
            str(row.get("fighter_profile_id")) in parsed
            and str(row.get("opponent_profile_id")) in parsed
        )
    return float(sum(w for w, ok in zip(weights, supported) if ok) / sum(weights))


def run_expansion(
    snapshot_dir: Path,
    output_dir: Path,
    *,
    cache_dir: Path = DEFAULT_PROFILE_CACHE_DIR,
    config: ExpansionConfig = ExpansionConfig(),
    progress: bool = True,
) -> dict:
    """Resume one bounded expansion run and persist state after every profile."""
    snapshot_dir = Path(snapshot_dir).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "FIGHTMATRIX_SNAPSHOT_FINALIZED").exists():
        raise FileExistsError(f"finalized snapshot is immutable: {output_dir}")
    queue_path = output_dir / QUEUE_FILE
    queue = initialize_queue(snapshot_dir, queue_path, Path(cache_dir))

    base_profiles = pd.read_parquet(snapshot_dir / "fightmatrix_profiles.parquet")
    base_bouts = pd.read_parquet(snapshot_dir / "fightmatrix_bouts.parquet")
    profiles_path = output_dir / PROFILES_FILE
    bouts_path = output_dir / BOUTS_FILE
    provenance_path = output_dir / PROVENANCE_FILE
    profiles = pd.read_parquet(profiles_path) if profiles_path.exists() else base_profiles.copy()
    if "completeness_classification" not in profiles:
        state_columns = [
            "profile_id", "stated_professional_record", "stated_professional_total",
            "parsed_history_count", "completeness_classification", "record_reconciled",
            "modeling_complete",
        ]
        profiles = profiles.merge(queue[state_columns], on="profile_id", how="left")
    raw_bouts = pd.read_parquet(bouts_path) if bouts_path.exists() else base_bouts.copy()
    queue = refresh_discoveries(queue, raw_bouts, config)
    provenance = pd.read_parquet(provenance_path) if provenance_path.exists() else pd.DataFrame()
    if provenance.empty:
        seed_provenance = []
        for row in profiles.itertuples(index=False):
            path = _profile_cache_path(Path(cache_dir), row.profile_url)
            if not path.exists():
                continue
            html = path.read_text(encoding="utf-8", errors="replace")
            seed_provenance.append({
                "source_name": "FightMatrix public profile", "public_url": row.profile_url,
                "fetch_timestamp": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "http_status": 200, "content_sha256": hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
                "parser_version": PARSER_VERSION, "snapshot_date": output_dir.name,
                "profile_id": str(row.profile_id), "discovery_depth": 0,
                "referring_profile_id": None, "raw_cache_path": str(path),
                "parse_warnings": None, "tls_verification": bool(config.verify_tls), "cache_hit": True,
            })
        provenance = pd.DataFrame(seed_provenance)
    parsed_ids = set(profiles["profile_id"].astype(str))
    started = time.monotonic()
    session = _session(config)
    new_profiles = 0
    requests_used = 0
    attempts_processed = 0
    stop_reason = "queue_exhausted"
    weighted_support = _weighted_edge_support(queue, raw_bouts)

    while True:
        elapsed = time.monotonic() - started
        if elapsed >= config.wall_clock_seconds:
            stop_reason = "wall_clock_budget"
            break
        if new_profiles >= config.max_new_profiles_per_run:
            stop_reason = "new_profile_budget"
            break
        if len(parsed_ids) >= config.max_profiles:
            stop_reason = "profile_budget"
            break
        unresolved_pct = float(queue["parse_status"].ne("parsed").mean()) if len(queue) else 1.0
        if _closure(queue) >= config.target_graph_closure:
            stop_reason = "target_graph_closure"
            break
        if weighted_support >= config.target_weighted_edge_support:
            stop_reason = "target_weighted_edge_support"
            break
        if unresolved_pct > config.max_unresolved_profile_pct:
            stop_reason = "maximum_unresolved_percentage"
            break
        retryable_status = queue["fetch_status"].isin(["pending", "retry"])
        if config.retry_failed:
            # One recovery attempt is allowed for failures inherited from a
            # prior run (for example, after fixing a managed-network TLS
            # setting). A genuinely failing profile must not loop forever.
            retryable_status = retryable_status | (
                queue["fetch_status"].eq("failed")
                & queue["retry_count"].eq(config.max_retries)
            )
        pending = queue[
            retryable_status
            & (
                queue["eligible_for_expansion"].fillna(False)
                | (
                    config.retry_failed
                    & queue["fetch_status"].eq("failed")
                    & queue["retry_count"].eq(config.max_retries)
                )
            )
            & queue["discovery_depth"].le(config.max_depth)
            & queue["priority_score"].ge(config.min_priority)
        ].sort_values(["discovery_depth", "priority_score", "discovery_date"], ascending=[True, False, True])
        if pending.empty:
            break
        idx = pending.index[0]
        row = queue.loc[idx]
        if (
            requests_used >= config.request_budget
            and not _profile_cache_path(Path(cache_dir), row["profile_url"]).exists()
        ):
            stop_reason = "request_budget"
            break
        queue.loc[idx, "last_attempt_utc"] = utc_now()
        html = None
        fetch_meta = None
        try:
            cache_path = _profile_cache_path(Path(cache_dir), row["profile_url"])
            was_cached = cache_path.exists()
            requests_used += int(not was_cached)
            prior_error = row.get("last_error")
            html, fetch_meta = _fetch(session, row["profile_url"], Path(cache_dir), config)
            profile, bouts = parse_profile_html(html, row["profile_url"])
            if not profile.get("fighter"):
                raise ValueError("profile page parsed without fighter heading")
            state = classify_profile(profile, bouts)
            profile.update({
                "profile_bout_count": int(len(bouts)), "seed_divisions": None,
                "seed_sources": None, "seed_rank_min": None,
                "discovery_depth": int(row["discovery_depth"]),
                "referring_profile_id": row["referring_profile_id"], **state,
            })
            profiles = profiles[profiles["profile_id"].astype(str).ne(str(row["profile_id"]))]
            profiles = pd.concat([profiles, pd.DataFrame([profile])], ignore_index=True, sort=False)
            raw_bouts = raw_bouts[raw_bouts["fighter_profile_id"].astype(str).ne(str(row["profile_id"]))]
            raw_bouts = pd.concat([raw_bouts, bouts], ignore_index=True, sort=False)
            parsed_ids.add(str(row["profile_id"]))
            eligible = (
                int(row["discovery_depth"]) < config.max_depth
                and (state["stated_professional_total"] or 0) >= config.min_professional_bouts
            )
            queue.loc[idx, list(state)] = list(state.values())
            queue.loc[idx, [
                "canonical_name", "fetch_status", "parse_status", "http_status", "http_success",
                "eligible_for_expansion", "expansion_stop_reason", "parsed_at_utc", "last_error",
            ]] = [
                profile["fighter"], "cached" if was_cached else "fetched", "parsed",
                fetch_meta["http_status"], True, eligible,
                None if eligible else ("maximum_depth" if int(row["discovery_depth"]) >= config.max_depth else "minimum_professional_bouts"),
                utc_now(), None,
            ]
            digest = hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()
            prov = {
                "source_name": "FightMatrix public profile", "public_url": row["profile_url"],
                "fetch_timestamp": fetch_meta["fetch_timestamp"], "http_status": fetch_meta["http_status"],
                "content_sha256": digest, "parser_version": PARSER_VERSION,
                "snapshot_date": output_dir.name, "profile_id": str(row["profile_id"]),
                "discovery_depth": int(row["discovery_depth"]),
                "referring_profile_id": row["referring_profile_id"],
                "raw_cache_path": fetch_meta["raw_cache_path"],
                "parse_warnings": f"Recovered after: {prior_error}" if prior_error else None,
                "tls_verification": bool(config.verify_tls), "cache_hit": bool(fetch_meta["cache_hit"]),
            }
            if provenance.empty or "profile_id" not in provenance:
                provenance = pd.DataFrame([prov])
            else:
                provenance = provenance[provenance["profile_id"].astype(str).ne(str(row["profile_id"]))]
                provenance = pd.concat([provenance, pd.DataFrame([prov])], ignore_index=True)
            queue = _append_discoveries(
                queue, bouts, int(row["discovery_depth"]), str(row["profile_id"]), config
            )
            new_profiles += 1
        except Exception as exc:
            retry_count = int(queue.loc[idx, "retry_count"] or 0) + 1
            response = getattr(exc, "response", None)
            status = getattr(response, "status_code", None)
            queue.loc[idx, ["retry_count", "last_error", "http_success"]] = [
                retry_count, f"{type(exc).__name__}: {exc}", False,
            ]
            if status is not None:
                queue.loc[idx, "http_status"] = int(status)
            if html is not None and fetch_meta is not None:
                failed_prov = {
                    "source_name": "FightMatrix public profile", "public_url": row["profile_url"],
                    "fetch_timestamp": fetch_meta["fetch_timestamp"],
                    "http_status": fetch_meta["http_status"],
                    "content_sha256": hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest(),
                    "parser_version": PARSER_VERSION, "snapshot_date": output_dir.name,
                    "profile_id": str(row["profile_id"]), "discovery_depth": int(row["discovery_depth"]),
                    "referring_profile_id": row["referring_profile_id"],
                    "raw_cache_path": fetch_meta["raw_cache_path"],
                    "parse_warnings": f"{type(exc).__name__}: {exc}",
                    "tls_verification": bool(config.verify_tls), "cache_hit": bool(fetch_meta["cache_hit"]),
                }
                if provenance.empty or "profile_id" not in provenance:
                    provenance = pd.DataFrame([failed_prov])
                else:
                    provenance = provenance[provenance["profile_id"].astype(str).ne(str(row["profile_id"]))]
                    provenance = pd.concat([provenance, pd.DataFrame([failed_prov])], ignore_index=True)
            if retry_count >= config.max_retries:
                queue.loc[idx, ["fetch_status", "parse_status", "eligible_for_expansion", "expansion_stop_reason"]] = [
                    "failed", "failed", False, "retry_limit",
                ]
            else:
                queue.loc[idx, "fetch_status"] = "retry"
                retry_after = None
                if response is not None:
                    retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after is not None else 2 ** (retry_count - 1)
                except ValueError:
                    delay = 2 ** (retry_count - 1)
                time.sleep(min(max(delay, 1.0), 60.0))
        attempts_processed += 1
        if attempts_processed % max(1, config.checkpoint_every) == 0:
            _atomic_parquet(queue.reindex(columns=QUEUE_COLUMNS), queue_path)
            _atomic_parquet(profiles, profiles_path)
            _atomic_parquet(raw_bouts, bouts_path)
            if not provenance.empty:
                _atomic_parquet(provenance, provenance_path)
        if progress and new_profiles and new_profiles % 25 == 0:
            weighted_support = _weighted_edge_support(queue, raw_bouts)
            print(
                f"[fightmatrix expansion] new={new_profiles:,} parsed={len(parsed_ids):,} "
                f"discovered={len(queue):,} closure={_closure(queue):.1%} "
                f"weighted_support={weighted_support:.1%}", flush=True,
            )

    queue = refresh_discoveries(queue, raw_bouts, config)
    _atomic_parquet(queue.reindex(columns=QUEUE_COLUMNS), queue_path)
    _atomic_parquet(profiles, profiles_path)
    _atomic_parquet(raw_bouts, bouts_path)
    if not provenance.empty:
        _atomic_parquet(provenance, provenance_path)
    depth = queue.groupby("discovery_depth").agg(
        discovered=("profile_id", "size"),
        parsed=("parse_status", lambda values: int(values.eq("parsed").sum())),
        failed=("parse_status", lambda values: int(values.eq("failed").sum())),
    ).reset_index()
    return {
        "config": asdict(config), "stop_reason": stop_reason,
        "new_profiles_this_run": int(new_profiles), "live_requests_this_run": int(requests_used),
        "profiles_discovered": int(len(queue)), "profiles_parsed": int(queue["parse_status"].eq("parsed").sum()),
        "graph_closure": _closure(queue),
        "weighted_edge_support": _weighted_edge_support(queue, raw_bouts),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "profiles_by_depth": depth.to_dict("records"),
    }


def profile_url(profile_id: str, name: str) -> str:
    """Construct only the documented public profile URL shape."""
    return f"{BASE_URL}/fighter-profile/{quote(name)}/{profile_id}/"
