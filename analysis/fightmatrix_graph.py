"""Audit, reconcile, and stage completeness-aware FightMatrix graph inputs."""
from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from loaders.fightmatrix_identity import build_identity_artifacts
from loaders.fightmatrix_organizations import annotate_organizations, build_organization_map
from loaders.sherdog_loader import compute_fight_weights, to_canonical_fights
from project_helpers import normalize_name_key


REFERENCE_FIELDS = frozenset({
    "rank", "points", "rating_points", "quality_performance_pct", "opponent_540_metric",
    "combat_age", "opponent_prefight_rank", "fightmatrix_reference_rank",
    "fightmatrix_reference_points", "current_ranking_text",
})
MODEL_RESULT_FIELDS = frozenset({
    "fight_url", "event_url", "event_name", "event_date", "event_location",
    "bout_string", "fighter_a", "fighter_b", "fighter_a_outcome", "fighter_b_outcome",
    "winner", "loser", "is_draw", "is_nc", "is_excluded", "exclusion_reason",
    "weight_class", "is_title_fight", "method_raw", "method_class",
    "method_score_winner", "end_round", "end_time_seconds", "time_format", "referee",
    "details_text", "ped_confirmed", "ped_flagged_fighter", "ped_confirmation_source",
    "ped_confirmation_detail", "org", "source", "org_weight", "final_model_weight",
    "fighter_a_profile_id", "fighter_b_profile_id", "fighter_a_completeness",
    "fighter_b_completeness", "eligibility_decision", "source_bout_identifier",
    "deduplication_key", "deduplication_decision", "initial_uncertainty_multiplier",
    "base_org_weight", "event_country_code", "result", "is_cross_organization",
    "source_profile_url", "source_profile_id", "canonical_organization",
})


@dataclass(frozen=True)
class PolicyConfig:
    policy: str = "reliability"
    minimum_completeness: float = 0.8
    boundary_floor: float = 0.25
    burn_in_bouts: int = 3
    minimum_component_size: int = 10
    earliest_fight_date: str = "2000-11-17"


def _name_key(value) -> str:
    return normalize_name_key(value, compact=True)


def _pair_key(row) -> str:
    ids = [str(row.get("fighter_profile_id") or ""), str(row.get("opponent_profile_id") or "")]
    if all(value and value != "nan" for value in ids):
        return "::".join(sorted(ids, key=lambda value: int(value) if value.isdigit() else value))
    return "::".join(sorted([_name_key(row.get("fighter")), _name_key(row.get("opponent"))]))


def _event_key(row) -> str:
    event_id = row.get("event_id")
    if pd.notna(event_id) and str(event_id).strip():
        return f"event:{str(event_id).strip()}"
    date = pd.to_datetime(row.get("event_date"), errors="coerce")
    return f"date:{date:%Y%m%d}" if pd.notna(date) else "date:unknown"


def _winner_id(row) -> str:
    result = str(row.get("result") or "").lower()
    if result == "win":
        return f"id:{row.get('fighter_profile_id')}"
    if result == "loss":
        return f"id:{row.get('opponent_profile_id')}"
    return result


NAME_ALIAS_PATH = (
    Path(__file__).resolve().parent.parent
    / "data" / "external" / "fightmatrix" / "name_aliases.csv"
)
_NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv"})


@lru_cache(maxsize=2)
def load_name_aliases(path: str | None = None) -> dict[str, str]:
    """Committed public-name to UFC-name map for cases no rule can derive.

    Ring names that replace a family name (``Renato Carneiro`` is
    ``Renato Moicano``), married names, mononyms and compound family names
    cannot be inferred from the strings themselves, so they are recorded by
    hand with the number of shared event dates that evidenced each pair.
    Name-order permutations and generational suffixes are handled by rule and
    are deliberately absent from this file.
    """
    target = Path(path) if path else NAME_ALIAS_PATH
    if not target.exists():
        return {}
    table = pd.read_csv(target, dtype=str).dropna(subset=["public_name", "ufc_name"])
    return {
        normalize_name_key(row.public_name): normalize_name_key(row.ufc_name)
        for row in table.itertuples(index=False)
    }


def _name_tokens(value) -> tuple[str, ...]:
    key = normalize_name_key(value)
    key = load_name_aliases().get(key, key)
    # A hyphen is punctuation, not a name boundary: the public source writes
    # "Georges St. Pierre" where the UFC source writes "Georges St-Pierre".
    stripped = [token.strip(".,'") for token in key.replace("-", " ").split()]
    tokens = tuple(token for token in stripped if token and token not in _NAME_SUFFIXES)
    return tokens or tuple(token for token in stripped if token)


def _names_compatible(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Deterministic same-person test for UFC-versus-public name variants.

    Accepts ``Rob Emerson``/``Robert Emerson``, ``Manny``/``Manvel Gamburyan``
    and ``Antonio Rogerio Nogueira``/``Rogerio Nogueira``. It requires an
    identical family name in every case, so it cannot merge two different
    fighters; a nickname that replaces the family name (``Mirko Cro Cop``
    versus ``Mirko Filipovic``) is deliberately left unmatched rather than
    guessed.
    """
    if left == right:
        return True
    if not left or not right:
        return False
    # A name-order permutation is the same person: public sources render
    # Chinese names given-name-first where the UFC source renders them
    # family-name-first (``Jingliang Li`` / ``Li Jingliang``).
    if sorted(left) == sorted(right):
        return True
    if left[-1] != right[-1]:
        return False
    if set(left) <= set(right) or set(right) <= set(left):
        return True
    first_left, first_right = left[0], right[0]
    shared = min(len(first_left), len(first_right), 3)
    return shared == 3 and first_left[:3] == first_right[:3]


def _family_close(left: str, right: str) -> bool:
    """Family names equal, or one transcription apart (Kosaka / Kohsaka)."""
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False
    longer, shorter = (left, right) if len(left) >= len(right) else (right, left)
    if len(longer) == len(shorter):
        return sum(a != b for a, b in zip(longer, shorter)) == 1
    for index in range(len(longer)):
        if longer[:index] + longer[index + 1:] == shorter:
            return True
    return False


def _names_similar(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    """Weaker than :func:`_names_compatible`: same family name, any first name.

    This admits ``Tank Abbott`` / ``David Abbott`` and ``Tsuyoshi Kosaka`` /
    ``Tsuyoshi Kohsaka``. It is only ever applied to the second fighter of a
    bout whose first fighter already matched strictly on the same event day,
    so it cannot merge two unrelated careers.
    """
    if _names_compatible(left, right):
        return True
    return bool(left) and bool(right) and _family_close(left[-1], right[-1])


def _ufc_overlap_index(canonical_ufc: pd.DataFrame | None) -> dict:
    """Index UFC bouts by event day.

    Public profiles record some events one calendar day away from the UFC
    source (an Asian card crossing the date line), so the lookup below scans a
    one-day window rather than demanding an identical date string.
    """
    if canonical_ufc is None or canonical_ufc.empty:
        return {}
    dates = pd.to_datetime(canonical_ufc["event_date"], errors="coerce")
    index: dict = {}
    for date, a, b in zip(dates, canonical_ufc["fighter_a"], canonical_ufc["fighter_b"]):
        if pd.isna(date):
            continue
        tokens_a, tokens_b = _name_tokens(a), _name_tokens(b)
        if not tokens_a or not tokens_b:
            continue
        index.setdefault(date.strftime("%Y%m%d"), []).append((tokens_a, tokens_b))
    return index


def _pairs_match(left, right, ufc_left, ufc_right) -> bool:
    """One side must match strictly; the other may be a known name variant."""
    return (
        (_names_compatible(left, ufc_left) and _names_similar(right, ufc_right))
        or (_names_similar(left, ufc_left) and _names_compatible(right, ufc_right))
    )


def _is_ufc_overlap(index: dict, dates, fighter, opponent) -> bool:
    if not index:
        return False
    tokens_a, tokens_b = _name_tokens(fighter), _name_tokens(opponent)
    if not tokens_a or not tokens_b:
        return False
    for date in dates:
        for offset in (-1, 0, 1):
            candidates = index.get((date + pd.Timedelta(days=offset)).strftime("%Y%m%d"))
            for left, right in candidates or ():
                if _pairs_match(tokens_a, tokens_b, left, right) or _pairs_match(
                    tokens_a, tokens_b, right, left
                ):
                    return True
    return False


def reconcile_bouts(
    bouts: pd.DataFrame,
    canonical_ufc: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classify every perspective and choose one deterministic row per public bout."""
    if bouts is None or bouts.empty:
        return bouts.copy(), pd.DataFrame()
    work = bouts.copy().reset_index(drop=True)
    work["source_row_number"] = range(len(work))
    work["_pair_key"] = [_pair_key(row) for row in work.to_dict("records")]
    work["deduplication_key"] = [f"{_event_key(row)}::{row['_pair_key']}" for row in work.to_dict("records")]
    # Some public perspectives differ by one calendar day or event spelling.
    # Same-pair bouts cannot be legitimate rematches within 24 hours, so group
    # those as auditable likely duplicates when neither side has an event ID.
    for _, pair_group in work.groupby("_pair_key", sort=False):
        no_id = pair_group[pair_group["event_id"].isna() | pair_group["event_id"].astype(str).str.strip().eq("")].copy()
        no_id["_date"] = pd.to_datetime(no_id["event_date"], errors="coerce")
        no_id = no_id.sort_values(["_date", "source_row_number"])
        cluster_start = None
        cluster_key = None
        for index, row in no_id.iterrows():
            date = row["_date"]
            if cluster_start is None or pd.isna(date) or abs((date - cluster_start).days) > 1:
                cluster_start = date
                date_key = f"{date:%Y%m%d}" if pd.notna(date) else "unknown"
                cluster_key = f"likely-date:{date_key}::{row['_pair_key']}"
            work.loc[index, "deduplication_key"] = cluster_key
    work["source_bout_identifier"] = work.get("fight_key", work["deduplication_key"])
    overlaps = _ufc_overlap_index(canonical_ufc)
    decisions = []
    selected = []
    for key, group in work.groupby("deduplication_key", sort=True, dropna=False):
        winner_ids = {_winner_id(row) for row in group.to_dict("records")}
        reciprocal = len(group) > 1 and group["fighter_profile_id"].astype(str).nunique() > 1
        conflict = len(winner_ids) > 1
        dates = pd.to_datetime(group["event_date"], errors="coerce")
        overlap = _is_ufc_overlap(
            overlaps, dates.dropna(), group.iloc[0]["fighter"], group.iloc[0]["opponent"],
        )
        ordered = group.assign(
            _decisive=group["result"].isin(["win", "loss"]).astype(int),
            _profile=pd.to_numeric(group["fighter_profile_id"], errors="coerce").fillna(10**12),
        ).sort_values(["_decisive", "_profile", "source_row_number"], ascending=[False, True, True])
        chosen_index = int(ordered.index[0])
        if conflict:
            classification = "conflicting_records"
        elif overlap:
            classification = "ufc_source_overlap"
        elif reciprocal:
            classification = "reciprocal_profile_records"
        elif len(group) > 1:
            same_date = pd.to_datetime(group["event_date"], errors="coerce").nunique() <= 1
            same_event = group["event_name"].fillna("").map(_name_key).nunique() <= 1
            classification = "exact_duplicate" if same_date and same_event else "likely_duplicate"
        else:
            classification = "unique"
        for index, row in group.iterrows():
            keep = index == chosen_index and not conflict and not overlap
            decisions.append({
                "source_row_number": int(row["source_row_number"]),
                "source_bout_identifier": row["source_bout_identifier"],
                "deduplication_key": key,
                "deduplication_classification": classification,
                "deduplication_decision": "selected" if keep else "excluded",
                "conflict_detail": "inconsistent winner/result perspectives" if conflict else None,
                "perspective_count": int(len(group)),
            })
        if not conflict and not overlap:
            chosen = work.loc[chosen_index].to_dict()
            chosen["deduplication_decision"] = classification
            selected.append(chosen)
    return pd.DataFrame(selected).drop(columns=["source_row_number", "_pair_key"], errors="ignore"), pd.DataFrame(decisions)


def _completeness_score(row) -> float:
    label = str(row.get("completeness_classification") or "unresolved")
    if label == "complete":
        return 1.0
    if label in {"conflicting", "unresolved", "failed"}:
        return 0.0
    stated = pd.to_numeric(row.get("stated_professional_total"), errors="coerce")
    observed = pd.to_numeric(row.get("parsed_history_count", row.get("profile_bout_count")), errors="coerce")
    if pd.notna(stated) and stated > 0 and pd.notna(observed):
        return float(max(0.0, min(1.0, observed / stated)))
    return 0.0


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[b] = a


def _graph_components(bouts: pd.DataFrame) -> tuple[dict[str, int], list[int]]:
    uf = _UnionFind()
    for row in bouts.to_dict("records"):
        left = str(row.get("fighter_profile_id") or f"name:{_name_key(row.get('fighter'))}")
        right = str(row.get("opponent_profile_id") or f"name:{_name_key(row.get('opponent'))}")
        uf.union(left, right)
    groups: dict[str, list[str]] = {}
    for node in uf.parent:
        groups.setdefault(uf.find(node), []).append(node)
    sizes = sorted((len(nodes) for nodes in groups.values()), reverse=True)
    size_by_node = {node: len(nodes) for nodes in groups.values() for node in nodes}
    return size_by_node, sizes


def _importance(row) -> float:
    weight = 1.0
    if str(row.get("result")) in {"loss", "draw"}:
        weight += 0.5
    if bool(row.get("is_title_fight")):
        weight += 0.75
    tier = pd.to_numeric(row.get("organization_tier"), errors="coerce")
    if pd.notna(tier):
        weight += max(0.0, (4.0 - float(tier)) * 0.25)
    rank = pd.to_numeric(row.get("opponent_prefight_rank"), errors="coerce")
    if pd.notna(rank):
        weight += max(0.0, 0.5 * (1.0 - min(float(rank), 100.0) / 100.0))
    return weight


def graph_audit(
    queue: pd.DataFrame,
    profiles: pd.DataFrame,
    bouts: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Calculate explicit graph, profile, opponent, and edge-support metrics."""
    annotated = annotate_organizations(bouts)
    profile_state = profiles.copy()
    if "completeness_classification" not in profile_state:
        profile_state["completeness_classification"] = "unresolved"
    profile_state["completeness_score"] = profile_state.apply(_completeness_score, axis=1)
    score_by_id = dict(zip(profile_state["profile_id"].astype(str), profile_state["completeness_score"]))
    parsed_ids = set(queue.loc[queue["parse_status"].eq("parsed"), "profile_id"].astype(str))
    degree: dict[str, set[str]] = {}
    fighter_rows = []
    for pid, group in annotated.groupby(annotated["fighter_profile_id"].astype(str), sort=False):
        opponents = group.dropna(subset=["opponent_profile_id"]).copy()
        opponent_ids = set(opponents["opponent_profile_id"].astype(str))
        fetched = opponent_ids.intersection(parsed_ids)
        weights = opponents.apply(_importance, axis=1) if not opponents.empty else pd.Series(dtype=float)
        covered_weights = weights[opponents["opponent_profile_id"].astype(str).isin(fetched)] if not opponents.empty else weights
        degree[pid] = opponent_ids
        own = profile_state[profile_state["profile_id"].astype(str).eq(pid)]
        own_score = float(own.iloc[0]["completeness_score"]) if not own.empty else 0.0
        queue_own = queue[queue["profile_id"].astype(str).eq(pid)]
        stated_total = pd.to_numeric(queue_own.iloc[0]["stated_professional_total"], errors="coerce") if not queue_own.empty else None
        parsed_count = pd.to_numeric(queue_own.iloc[0]["parsed_history_count"], errors="coerce") if not queue_own.empty else None
        fighter_rows.append({
            "profile_id": pid,
            "fighter": group.iloc[0]["fighter"],
            "discovery_depth": int(queue.loc[queue["profile_id"].astype(str).eq(pid), "discovery_depth"].min())
                if queue["profile_id"].astype(str).eq(pid).any() else None,
            "observed_unique_opponents": int(len(opponent_ids)),
            "fetched_unique_opponents": int(len(fetched)),
            "opponent_coverage": float(len(fetched) / len(opponent_ids)) if opponent_ids else 1.0,
            "weighted_opponent_coverage": float(covered_weights.sum() / weights.sum()) if weights.sum() else 1.0,
            "profile_completeness_score": own_score,
            "stated_professional_total": stated_total,
            "parsed_history_count": parsed_count,
            "observed_minus_stated": (parsed_count - stated_total) if pd.notna(parsed_count) and pd.notna(stated_total) else None,
            "record_reconciled": bool(queue_own.iloc[0]["record_reconciled"]) if not queue_own.empty else False,
            "observed_edge_count": int(len(group)),
            "one_observed_edge": bool(len(group) == 1),
        })
    fighter_completeness = pd.DataFrame(fighter_rows)
    components_by_node, component_sizes = _graph_components(bouts)
    if not fighter_completeness.empty:
        fighter_completeness["component_size"] = fighter_completeness["profile_id"].map(components_by_node).fillna(1).astype(int)
    ids = set(queue["profile_id"].astype(str))
    supported = []
    edge_weights = []
    for row in bouts.to_dict("records"):
        supported.append(
            score_by_id.get(str(row.get("fighter_profile_id")), 0.0) >= 0.8
            and score_by_id.get(str(row.get("opponent_profile_id")), 0.0) >= 0.8
        )
        edge_weights.append(_importance(row))
    graph_degree: dict[str, set[str]] = {}
    stable_appearances = 0
    total_appearances = 0
    for row in bouts.to_dict("records"):
        left_id = row.get("fighter_profile_id")
        right_id = row.get("opponent_profile_id")
        left = str(left_id) if pd.notna(left_id) else f"name:{_name_key(row.get('fighter'))}"
        right = str(right_id) if pd.notna(right_id) else f"name:{_name_key(row.get('opponent'))}"
        graph_degree.setdefault(left, set()).add(right)
        graph_degree.setdefault(right, set()).add(left)
        stable_appearances += int(pd.notna(left_id)) + int(pd.notna(right_id))
        total_appearances += 2
    complete_counts = queue["completeness_classification"].value_counts()
    audit = pd.DataFrame([{
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed_profiles": int(queue["discovery_depth"].eq(0).sum()),
        "discovered_fighter_identities": int(len(queue)),
        "fetched_profiles": int(queue["http_success"].fillna(False).sum()),
        "parsed_profiles": int(queue["parse_status"].eq("parsed").sum()),
        "opponents_without_fetched_profiles": int(queue["parse_status"].ne("parsed").sum()),
        "opponents_without_fetched_profiles_pct": float(queue["parse_status"].ne("parsed").mean()) if len(queue) else 0.0,
        "complete_profiles": int(complete_counts.get("complete", 0)),
        "partial_profiles": int(complete_counts.get("partial", 0)),
        "conflicting_profiles": int(complete_counts.get("conflicting", 0)),
        "unresolved_profiles": int(complete_counts.get("unresolved", 0)),
        "failed_profiles": int(queue["parse_status"].eq("failed").sum()),
        "unique_bouts": int(reconciliation["deduplication_key"].nunique()) if not reconciliation.empty else int(len(bouts)),
        "reconciled_non_ufc_overlap_bouts": int(len(bouts)),
        "duplicate_bout_records": int(reconciliation["deduplication_classification"].isin([
            "exact_duplicate", "reciprocal_profile_records"
        ]).sum()) if not reconciliation.empty else 0,
        "conflicting_bout_records": int(reconciliation["deduplication_classification"].eq("conflicting_records").sum()) if not reconciliation.empty else 0,
        "connected_components": int(len(component_sizes)),
        "largest_connected_component_size": int(component_sizes[0] if component_sizes else 0),
        "isolated_fighters": int(sum(size == 1 for size in component_sizes)),
        "small_components_le_5": int(sum(size <= 5 for size in component_sizes)),
        "fighters_with_one_observed_edge": int(sum(len(neighbors) == 1 for neighbors in graph_degree.values())),
        "profile_coverage": float(queue["parse_status"].eq("parsed").mean()) if len(queue) else 0.0,
        "graph_closure": float(queue["parse_status"].eq("parsed").mean()) if len(queue) else 0.0,
        "edge_support": float(pd.Series(supported).mean()) if supported else 0.0,
        "weighted_edge_support": float(
            sum(weight for weight, ok in zip(edge_weights, supported) if ok) / sum(edge_weights)
        ) if edge_weights and sum(edge_weights) else 0.0,
        "unknown_organization_bouts": int(annotated["canonical_organization"].eq("Unknown").sum()),
        "profile_id_coverage": float(stable_appearances / total_appearances) if total_appearances else 0.0,
        "bouts_excluded_as_ufc_overlap": int(reconciliation["deduplication_classification"].eq("ufc_source_overlap").sum()) if not reconciliation.empty else 0,
    }])
    component_table = pd.DataFrame({
        "component_rank": range(1, len(component_sizes) + 1), "component_size": component_sizes,
    })
    degree_table = pd.Series(
        [len(neighbors) for neighbors in graph_degree.values()], name="fighter_count"
    ).value_counts().sort_index().rename_axis("degree").reset_index()
    return audit, fighter_completeness, component_table, degree_table


def assert_no_reference_leakage(frame: pd.DataFrame) -> None:
    """Fail closed if FightMatrix-derived diagnostic fields enter model input."""
    forbidden = REFERENCE_FIELDS.intersection(frame.columns)
    if forbidden:
        raise ValueError(f"FightMatrix reference fields present in model input: {sorted(forbidden)}")


def _canonical_name_maps(identity: pd.DataFrame, base_snapshot: Path) -> tuple[dict[str, str], dict[str, str]]:
    names = {}
    divisions = {}
    for row in identity.itertuples(index=False):
        display = row.ufc_fighter if isinstance(row.ufc_fighter, str) and row.ufc_fighter else row.canonical_display_name
        names[_name_key(row.canonical_display_name)] = display
    current_path = base_snapshot / "ratings_current.parquet"
    if current_path.exists():
        current = pd.read_parquet(current_path)
        for row in current.itertuples(index=False):
            name = getattr(row, "fighter", None)
            if not isinstance(name, str):
                continue
            names[_name_key(name)] = name
            division = getattr(row, "recent_division", None) or getattr(row, "career_division", None)
            if isinstance(division, str):
                divisions[_name_key(name)] = division
    return names, divisions


def build_model_input(
    resolved: pd.DataFrame,
    profiles: pd.DataFrame,
    identity: pd.DataFrame,
    base_snapshot: Path,
    *,
    config: PolicyConfig = PolicyConfig(),
) -> pd.DataFrame:
    """Create canonical cross-org rows under one transparent completeness policy."""
    if resolved.empty:
        return pd.DataFrame(columns=sorted(MODEL_RESULT_FIELDS))
    scores = profiles.copy()
    scores["completeness_score"] = scores.apply(_completeness_score, axis=1)
    score_by_id = dict(zip(scores["profile_id"].astype(str), scores["completeness_score"]))
    work = annotate_organizations(resolved)
    work["org"] = work["canonical_organization"]
    work = work[
        pd.to_datetime(work["event_date"], errors="coerce").ge(pd.Timestamp(config.earliest_fight_date))
    ].copy()
    work["fighter_completeness"] = work["fighter_profile_id"].astype(str).map(score_by_id).fillna(0.0)
    work["opponent_completeness"] = work["opponent_profile_id"].astype(str).map(score_by_id).fillna(0.0)
    work["edge_completeness"] = work[["fighter_completeness", "opponent_completeness"]].min(axis=1)
    names, divisions = _canonical_name_maps(identity, Path(base_snapshot))
    canonical = to_canonical_fights(work, names, divisions)
    meta = work.drop_duplicates("fight_key").set_index("fight_key")
    a_id_by_key = {}
    b_id_by_key = {}
    for key, row in meta.iterrows():
        fighter_id, opponent_id = str(row["fighter_profile_id"]), str(row["opponent_profile_id"])
        if str(row["result"]).lower() == "loss":
            a_id_by_key[key], b_id_by_key[key] = opponent_id, fighter_id
        else:
            a_id_by_key[key], b_id_by_key[key] = fighter_id, opponent_id
    canonical["fighter_a_profile_id"] = canonical["fight_url"].map(a_id_by_key)
    canonical["fighter_b_profile_id"] = canonical["fight_url"].map(b_id_by_key)
    canonical["fighter_a_completeness"] = canonical["fighter_a_profile_id"].map(score_by_id).fillna(0.0)
    canonical["fighter_b_completeness"] = canonical["fighter_b_profile_id"].map(score_by_id).fillna(0.0)
    canonical["source_bout_identifier"] = canonical["fight_url"].map(meta["source_bout_identifier"])
    canonical["deduplication_key"] = canonical["fight_url"].map(meta["deduplication_key"])
    canonical["deduplication_decision"] = canonical["fight_url"].map(meta["deduplication_decision"])
    for column in ("event_country_code", "result", "source_profile_url", "fighter_profile_id"):
        if column in meta:
            target = "source_profile_id" if column == "fighter_profile_id" else column
            canonical[target] = canonical["fight_url"].map(meta[column])
    canonical["canonical_organization"] = canonical["org"]
    canonical["is_cross_organization"] = canonical["org"].ne("UFC")
    ufc_current = pd.read_parquet(Path(base_snapshot) / "ratings_current.parquet")
    canonical["org_weight"] = compute_fight_weights(canonical, ufc_current).values
    canonical["base_org_weight"] = canonical["org_weight"]
    edge = canonical[["fighter_a_completeness", "fighter_b_completeness"]].min(axis=1)
    prior_a = canonical.sort_values("event_date").groupby("fighter_a").cumcount()
    prior_b = canonical.sort_values("event_date").groupby("fighter_b").cumcount()
    policy = config.policy
    if policy == "raw":
        eligible = pd.Series(True, index=canonical.index)
        factor = pd.Series(1.0, index=canonical.index)
    elif policy == "complete_edge":
        eligible = edge.ge(config.minimum_completeness)
        factor = pd.Series(1.0, index=canonical.index)
    elif policy == "reliability":
        eligible = edge.gt(0)
        factor = (canonical["fighter_a_completeness"] * canonical["fighter_b_completeness"]).pow(0.5)
    elif policy == "boundary":
        eligible = pd.Series(True, index=canonical.index)
        factor = edge.clip(lower=config.boundary_floor)
    elif policy == "burn_in":
        eligible = edge.ge(config.minimum_completeness) | (
            prior_a.ge(config.burn_in_bouts) & prior_b.ge(config.burn_in_bouts)
        )
        factor = edge.clip(lower=config.boundary_floor)
    else:
        raise ValueError(f"unsupported completeness policy: {policy}")
    canonical["initial_uncertainty_multiplier"] = 1.0 + (1.0 - edge)
    canonical["eligibility_decision"] = eligible.map({True: f"eligible:{policy}", False: f"excluded:{policy}"})
    canonical["exclusion_reason"] = canonical["exclusion_reason"].where(eligible, f"completeness_policy:{policy}")
    canonical["is_excluded"] = canonical["is_excluded"].fillna(False) | ~eligible
    canonical["final_model_weight"] = canonical["org_weight"] * factor
    canonical["org_weight"] = canonical["final_model_weight"]
    allowed = [column for column in canonical.columns if column in MODEL_RESULT_FIELDS]
    canonical = canonical[allowed]
    assert_no_reference_leakage(canonical)
    return canonical.sort_values(["event_date", "fight_url"]).reset_index(drop=True)


def _notebook_data(
    queue: pd.DataFrame,
    fighter_completeness: pd.DataFrame,
    components: pd.DataFrame,
    org_map: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    def add(chart: str, category, value, series="expanded"):
        rows.append({"chart": chart, "series": series, "category": str(category), "value": float(value)})
    for row in queue.groupby("discovery_depth").size().items():
        add("profiles_by_depth", row[0], row[1])
    for row in queue["parse_status"].value_counts().items():
        add("fetch_parse_status", row[0], row[1])
    if not fighter_completeness.empty:
        bins = pd.cut(fighter_completeness["opponent_coverage"], bins=[-0.01, .25, .5, .75, .99, 1.0])
        for category, value in bins.value_counts(sort=False).items():
            add("opponent_completeness", category, value)
    for row in components.head(50).itertuples(index=False):
        add("connected_component_sizes", row.component_rank, row.component_size)
    for row in org_map.groupby("canonical_organization")["bout_count"].sum().sort_values(ascending=False).items():
        add("organization_coverage", row[0], row[1])
    return pd.DataFrame(rows)


def build_headline_eligibility(
    fighter_completeness: pd.DataFrame,
    *,
    minimum_completeness: float = 0.8,
    minimum_component_size: int = 10,
    maximum_missing_exposure: float = 0.2,
) -> pd.DataFrame:
    """Make publication/component/uncertainty policies explicit and auditable."""
    if fighter_completeness.empty:
        return fighter_completeness.copy()
    out = fighter_completeness.copy()
    complete = out["profile_completeness_score"].ge(minimum_completeness)
    connected = out["component_size"].ge(minimum_component_size)
    seed = out["discovery_depth"].eq(0)
    low_exposure = out["weighted_opponent_coverage"].ge(1.0 - maximum_missing_exposure)
    out["complete_edge_headline_eligible"] = complete
    out["component_headline_eligible"] = complete & connected
    out["seed_only_headline_eligible"] = complete & seed
    out["uncertainty_headline_eligible"] = complete & connected & low_exposure
    out["headline_suppression_reason"] = "eligible"
    out.loc[~complete, "headline_suppression_reason"] = "incomplete_profile"
    out.loc[complete & ~connected, "headline_suppression_reason"] = "small_component"
    out.loc[complete & connected & ~low_exposure, "headline_suppression_reason"] = "missing_history_exposure"
    return out


def build_graph_artifacts(
    base_snapshot: Path,
    expansion_dir: Path,
    *,
    policy: PolicyConfig = PolicyConfig(),
) -> dict:
    """Build all audit/identity/reconciliation/model-input artifacts."""
    base_snapshot = Path(base_snapshot).resolve()
    expansion_dir = Path(expansion_dir).resolve()
    if (expansion_dir / "FIGHTMATRIX_SNAPSHOT_FINALIZED").exists():
        raise FileExistsError(f"finalized snapshot is immutable: {expansion_dir}")
    queue = pd.read_parquet(expansion_dir / "fightmatrix_profile_queue.parquet")
    profiles = pd.read_parquet(expansion_dir / "fightmatrix_profiles_expanded.parquet")
    bouts = pd.read_parquet(expansion_dir / "fightmatrix_bouts_expanded.parquet")
    ufc_fighters = pd.read_parquet(base_snapshot / "canonical_fighters.parquet")
    ufc_bouts = pd.read_parquet(base_snapshot / "canonical_fights.parquet")
    identity, exceptions = build_identity_artifacts(profiles, bouts, ufc_fighters)
    # The model pass (UFC overlaps removed) and the graph pass (whole public
    # graph retained) are independent, and each is minutes of single-threaded
    # work, so they run side by side. Results are collected by name, never by
    # completion order, so output stays deterministic.
    with ProcessPoolExecutor(max_workers=2) as pool:
        model_future = pool.submit(reconcile_bouts, bouts, ufc_bouts)
        graph_future = pool.submit(reconcile_bouts, bouts, None)
        resolved, reconciliation = model_future.result()
        graph_bouts, _ = graph_future.result()
    org_map = build_organization_map(graph_bouts)
    audit, fighter_completeness, components, degree_distribution = graph_audit(
        queue, profiles, graph_bouts, reconciliation
    )
    policy_names = ("raw", "complete_edge", "reliability", "boundary", "burn_in")
    policy_configs = {
        name: PolicyConfig(
            policy=name, minimum_completeness=policy.minimum_completeness,
            boundary_floor=policy.boundary_floor, burn_in_bouts=policy.burn_in_bouts,
            minimum_component_size=policy.minimum_component_size,
            earliest_fight_date=policy.earliest_fight_date,
        )
        for name in policy_names
    }
    with ProcessPoolExecutor(max_workers=3) as pool:
        futures = {
            name: pool.submit(
                build_model_input, resolved, profiles, identity, base_snapshot,
                config=policy_configs[name],
            )
            for name in policy_names
        }
        policy_frames = {name: future.result() for name, future in futures.items()}
    policy_rows = []
    for name in policy_names:
        frame = policy_frames[name]
        eligible = frame[~frame["is_excluded"].fillna(False)]
        policy_rows.append({
            "policy": name, "total_bouts": int(len(frame)), "eligible_bouts": int(len(eligible)),
            "eligible_weight_sum": float(eligible["final_model_weight"].sum()),
            "mean_eligible_weight": float(eligible["final_model_weight"].mean()) if len(eligible) else 0.0,
            "mean_initial_uncertainty_multiplier": float(eligible["initial_uncertainty_multiplier"].mean()) if len(eligible) else None,
        })
        frame.to_parquet(expansion_dir / f"fightmatrix_model_bouts_{name}.parquet", index=False)
    model_bouts = policy_frames[policy.policy]
    headline = build_headline_eligibility(
        fighter_completeness,
        minimum_completeness=policy.minimum_completeness,
        minimum_component_size=policy.minimum_component_size,
    )
    identity.to_parquet(expansion_dir / "fightmatrix_identity_map.parquet", index=False)
    exceptions.to_parquet(expansion_dir / "fightmatrix_identity_exceptions.parquet", index=False)
    org_map.to_parquet(expansion_dir / "fightmatrix_organization_map.parquet", index=False)
    reconciliation.to_parquet(expansion_dir / "fightmatrix_bout_reconciliation.parquet", index=False)
    audit.to_parquet(expansion_dir / "fightmatrix_graph_metrics.parquet", index=False)
    fighter_completeness.to_parquet(expansion_dir / "fightmatrix_fighter_completeness.parquet", index=False)
    fighter_completeness[fighter_completeness["discovery_depth"].eq(0)].to_parquet(
        expansion_dir / "fightmatrix_seed_opponent_coverage.parquet", index=False
    )
    components.to_parquet(expansion_dir / "fightmatrix_component_sizes.parquet", index=False)
    degree_distribution.to_parquet(expansion_dir / "fightmatrix_degree_distribution.parquet", index=False)
    model_bouts.to_parquet(expansion_dir / "fightmatrix_model_eligible_bouts.parquet", index=False)
    pd.DataFrame(policy_rows).to_parquet(expansion_dir / "fightmatrix_policy_comparison.parquet", index=False)
    headline.to_parquet(expansion_dir / "fightmatrix_headline_eligibility.parquet", index=False)
    dates = pd.to_datetime(resolved["event_date"], errors="coerce")
    date_exclusions = resolved[
        dates.isna() | dates.lt(pd.Timestamp(policy.earliest_fight_date))
    ][["source_bout_identifier", "deduplication_key"]].assign(
        exclusion_reason="date_before_model_cutoff_or_missing", exclusion_stage="date_filter"
    )
    profile_failures = queue[queue["parse_status"].eq("failed")][[
        "profile_id", "profile_url", "last_error", "expansion_stop_reason"
    ]].rename(columns={"last_error": "exclusion_reason"}).assign(
        exclusion_stage="profile_fetch_or_parse"
    )
    exclusions = pd.concat([
        reconciliation[reconciliation["deduplication_decision"].eq("excluded")].assign(exclusion_stage="reconciliation"),
        model_bouts[model_bouts["is_excluded"].fillna(False)][[
            "source_bout_identifier", "deduplication_key", "exclusion_reason"
        ]].assign(exclusion_stage="model_policy"),
        date_exclusions,
        profile_failures,
    ], ignore_index=True, sort=False)
    exclusions.to_parquet(expansion_dir / "fightmatrix_exclusions.parquet", index=False)
    _notebook_data(queue, fighter_completeness, components, org_map).to_parquet(
        expansion_dir / "fightmatrix_notebook_data.parquet", index=False
    )
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_snapshot": str(base_snapshot), "experimental": True,
        "production_default_changed": False, "policy": policy.__dict__,
        "artifacts": {},
    }
    for path in sorted(expansion_dir.glob("fightmatrix_*.parquet")):
        manifest["artifacts"][path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    (expansion_dir / "fightmatrix_expansion_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {
        **audit.iloc[0].to_dict(), "model_eligible_bouts": int((~model_bouts["is_excluded"]).sum()),
        "identity_exceptions": int(len(exceptions)), "policy": policy.policy,
    }


def finalize_snapshot(expansion_dir: Path) -> Path:
    """Finalize once; future expansion attempts fail closed."""
    expansion_dir = Path(expansion_dir).resolve()
    manifest = expansion_dir / "fightmatrix_expansion_manifest.json"
    if not manifest.exists():
        raise FileNotFoundError("build graph artifacts before finalizing")
    marker = expansion_dir / "FIGHTMATRIX_SNAPSHOT_FINALIZED"
    if marker.exists():
        raise FileExistsError(f"snapshot already finalized: {expansion_dir}")
    marker.write_text(
        f"Finalized {datetime.now(timezone.utc).isoformat()}\nManifest: {manifest.name}\n",
        encoding="utf-8",
    )
    return marker
