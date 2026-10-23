"""The vectorised exposure ledger and the memoised normalizer agree bit for bit with the loops they replaced."""
import numpy as np
import pandas as pd

from loaders.fightmatrix_organizations import load_organization_rules, normalize_organization
from ratings.legacy_resume import ORG_FACTOR_BY_TIER, _organization_factor, _top_quartile_means

# v : factor values per bout; g : group (fighter) of each bout; k : size of the top quarter kept
# The reference is the per-fighter Series loop: sort descending, head(k), Series.mean (numpy pairwise add).


def _loop(values: pd.Series) -> float:
    clean = pd.to_numeric(values, errors="coerce").dropna().sort_values(ascending=False)
    if clean.empty:
        return ORG_FACTOR_BY_TIER[4]
    return float(clean.head(max(1, int(np.ceil(len(clean) * 0.25)))).mean())


def test_top_quartile_means_match_series_mean_bit_for_bit():
    rng = np.random.default_rng(3)
    sizes = np.concatenate([rng.integers(0, 40, 300), [0, 1, 7, 8, 9, 31, 32, 33, 127, 128, 129, 600, 1100]])
    g = rng.permutation(np.repeat(np.arange(len(sizes)), sizes))
    v = rng.random(len(g)) * 0.8 + 0.2  # arbitrary doubles: summation order shows in the last bit
    v[rng.random(len(g)) < 0.1] = np.nan
    got = _top_quartile_means(g, v, len(sizes))
    s = pd.Series(v)
    want = np.array([_loop(s[g == i]) for i in range(len(sizes))])
    assert np.array_equal(got.view(np.int64), want.view(np.int64))


def test_top_quartile_means_empty():
    assert len(_top_quartile_means(np.array([], dtype=np.int64), np.array([]), 0)) == 0
    assert _top_quartile_means(np.array([0]), np.array([np.nan]), 1)[0] == ORG_FACTOR_BY_TIER[4]


def test_normalize_organization_cached_path_equals_explicit_rules_path():
    rules = load_organization_rules()
    labels = ["UFC 100", "  pride   fc ", "Bellator 120", "Major Regional", "major regional", "", None, "Nowhere FC"]
    for lab in labels:
        for when in (None, pd.NaT, pd.Timestamp("1999-01-01"), pd.Timestamp("2012-05-05"), "2020-02-02"):
            for ver in (False, True):
                a = normalize_organization(lab, when, verified_label=ver)
                b = normalize_organization(lab, when, rules=rules, verified_label=ver)
                assert a == b and list(a) == list(b)


def test_normalize_organization_returns_a_private_dict():
    first = normalize_organization("UFC 100", "2010-01-01")
    first["canonical_organization"] = "changed"
    assert normalize_organization("UFC 100", "2010-01-01")["canonical_organization"] != "changed"


def test_organization_factor_fast_path_matches_series_round_trip():
    for tier in (1, 2, 3, 4, 5, 0, -1, np.int64(2), np.int32(3), 2.0, "3", None, np.nan, True):
        want = ORG_FACTOR_BY_TIER[4]
        n = pd.to_numeric(pd.Series([tier]), errors="coerce").iloc[0]
        if not pd.isna(n):
            want = ORG_FACTOR_BY_TIER.get(int(n), ORG_FACTOR_BY_TIER[4])
        assert _organization_factor("Some Local Show", tier) == want
