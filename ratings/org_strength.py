"""Organization-strength and source-reliability weight candidates.

Production ratings should not carry a hand-authored promotion ladder. The
admissible question is narrower: does a data-derived, bout-level evidence
weight improve out-of-sample behavior and top-100 sanity checks without leaking
future fighter quality into past bouts?

The default model is therefore ``unit``. The bridge-reliability candidate below
is not "UFC is better, Bellator is worse"; it is "how much direct UFC bridge
support identifies this organization's rows inside the combined table?"
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


UFC_CORPORA = {"ufc", "pre_unified"}


@dataclass(frozen=True)
class OrgWeightSpec:
    """One mathematically named way to turn an org row into evidence weight."""

    name: str
    model: str = "unit"
    floor: float = 0.5
    prior: float = 60.0
    non_ufc_weight: float = 1.0

    def label(self) -> str:
        if self.model == "unit":
            return "unit"
        if self.model == "constant_non_ufc":
            return f"constant_non_ufc_{self.non_ufc_weight:g}"
        if self.model == "bridge_reliability":
            return f"bridge_floor_{self.floor:g}_prior_{self.prior:g}"
        return self.name


def _as_long_fighters(fights: pd.DataFrame) -> pd.DataFrame:
    if fights is None or fights.empty:
        return pd.DataFrame(columns=["fighter", "org", "source_corpus", "fight_url"])
    corpus = fights.get("source_corpus", fights.get("source", "ufc"))
    base = fights.assign(source_corpus=pd.Series(corpus, index=fights.index).fillna("ufc"))
    a = base[["fight_url", "fighter_a", "org", "source_corpus"]].rename(
        columns={"fighter_a": "fighter"}
    )
    b = base[["fight_url", "fighter_b", "org", "source_corpus"]].rename(
        columns={"fighter_b": "fighter"}
    )
    return pd.concat([a, b], ignore_index=True, sort=False).dropna(subset=["fighter"])


def organization_bridge_table(
    fights: pd.DataFrame,
    *,
    floor: float = 0.5,
    prior: float = 60.0,
) -> pd.DataFrame:
    """Estimate each non-UFC organization's bridge support to the UFC graph.

    Let ``n_eff = sqrt(crossover_fighters * crossover_bouts)``. The candidate
    weight is:

    ``floor + (1 - floor) * n_eff / (n_eff + prior)``

    This is a shrinkage/reliability weight, not an asserted quality discount.
    An org with many fighters and bouts connected to the UFC graph approaches
    1.0; thin or isolated orgs shrink toward ``floor``.
    """
    if not 0.0 < float(floor) <= 1.0:
        raise ValueError("floor must lie in (0, 1]")
    if float(prior) < 0.0:
        raise ValueError("prior must be non-negative")
    if fights is None or fights.empty:
        return pd.DataFrame(
            columns=[
                "org",
                "bouts",
                "fighters",
                "crossover_fighters",
                "crossover_bouts",
                "n_eff",
                "evidence_weight",
            ]
        )

    long = _as_long_fighters(fights)
    ufc_fighters = set(long.loc[long["source_corpus"].isin(UFC_CORPORA), "fighter"])
    non_ufc = long[~long["source_corpus"].isin(UFC_CORPORA)].copy()
    if non_ufc.empty:
        return pd.DataFrame(
            columns=[
                "org",
                "bouts",
                "fighters",
                "crossover_fighters",
                "crossover_bouts",
                "n_eff",
                "evidence_weight",
            ]
        )
    non_ufc["has_ufc_bridge"] = non_ufc["fighter"].isin(ufc_fighters)
    by_org = (
        non_ufc.groupby("org", dropna=False)
        .agg(
            bouts=("fight_url", "nunique"),
            fighters=("fighter", "nunique"),
            crossover_fighters=("has_ufc_bridge", "sum"),
            crossover_bouts=("fight_url", lambda s: s[non_ufc.loc[s.index, "has_ufc_bridge"]].nunique()),
        )
        .reset_index()
    )
    # ``crossover_fighters`` above is counted per appearance; replace it with a
    # true unique-fighter count after the compact groupby.
    unique_cross = (
        non_ufc[non_ufc["has_ufc_bridge"]]
        .groupby("org", dropna=False)["fighter"]
        .nunique()
        .rename("crossover_fighters")
    )
    by_org = by_org.drop(columns="crossover_fighters").merge(unique_cross, on="org", how="left")
    by_org["crossover_fighters"] = by_org["crossover_fighters"].fillna(0).astype(int)
    by_org["n_eff"] = (by_org["crossover_fighters"] * by_org["crossover_bouts"]).pow(0.5)
    if float(prior) == 0.0:
        bridge = by_org["n_eff"].gt(0).astype(float)
    else:
        bridge = by_org["n_eff"] / (by_org["n_eff"] + float(prior))
    by_org["evidence_weight"] = float(floor) + (1.0 - float(floor)) * bridge
    return by_org.sort_values(["evidence_weight", "bouts"], ascending=[False, False]).reset_index(drop=True)


def apply_org_weight_model(fights: pd.DataFrame, spec: OrgWeightSpec) -> pd.DataFrame:
    """Attach ``org_weight`` for one candidate model without mutating input."""
    if fights is None or fights.empty:
        return fights.copy()
    out = fights.copy()
    corpus = out.get("source_corpus", out.get("source", "ufc"))
    out["source_corpus"] = pd.Series(corpus, index=out.index).fillna("ufc").astype(str)
    out["org_weight"] = 1.0
    out["org_weight_model"] = spec.label()
    non_ufc = ~out["source_corpus"].isin(UFC_CORPORA)

    if spec.model == "unit":
        return out
    if spec.model == "constant_non_ufc":
        if not 0.0 < float(spec.non_ufc_weight) <= 1.0:
            raise ValueError("non_ufc_weight must lie in (0, 1]")
        out.loc[non_ufc, "org_weight"] = float(spec.non_ufc_weight)
        return out
    if spec.model == "bridge_reliability":
        bridge = organization_bridge_table(out, floor=spec.floor, prior=spec.prior)
        weights = bridge.set_index("org")["evidence_weight"] if not bridge.empty else pd.Series(dtype=float)
        out.loc[non_ufc, "org_weight"] = (
            out.loc[non_ufc, "org"].map(weights).fillna(float(spec.floor)).astype(float)
        )
        return out
    raise ValueError(f"unknown org weight model: {spec.model!r}")


def default_org_weight_specs() -> list[OrgWeightSpec]:
    """Small, interpretable candidate set for top-100/outlier audits."""
    return [
        OrgWeightSpec("unit", model="unit"),
        OrgWeightSpec("non_ufc_075", model="constant_non_ufc", non_ufc_weight=0.75),
        OrgWeightSpec("bridge_050_060", model="bridge_reliability", floor=0.50, prior=60.0),
        OrgWeightSpec("bridge_035_060", model="bridge_reliability", floor=0.35, prior=60.0),
    ]
