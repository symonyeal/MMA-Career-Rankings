"""The published class boards count UFC bouts only (docs/DECISIONS.md, item 13, 2026-10-15).

Certificate: every (fighter, class) row on the committed class board has a UFC bout -- by
:func:`ratings.current_score.is_ufc_bout`, the predicate Current uses -- in that class.
"""
from __future__ import annotations

import pandas as pd

from check_release import PUBLISHED_SNAPSHOT as S
from ratings.current_score import is_ufc_bout
from ratings.division_legacy import weight_class
from ratings.fights import resume_fights


def test_every_class_row_rests_on_a_ufc_bout_in_that_class():
    b = pd.read_parquet(S / "class_board.parquet")
    f = resume_fights(S, "majors,pre_unified")
    f = f[is_ufc_bout(f)]
    g = b.drop_duplicates("fighter").set_index("fighter")["gender"]
    have = {(x, weight_class(w, g.get(x))) for side in ("fighter_a", "fighter_b")
            for x, w in zip(f[side], f["weight_class"]) if x in g.index}
    a = pd.read_parquet(S / "performance_appearances.parquet", columns=["fight_url", "fighter", "division"])
    a = a[a["fight_url"].isin(set(f["fight_url"])) & a["fighter"].isin(g.index)]
    have |= {(x, weight_class(d, g.get(x))) for x, d in zip(a["fighter"], a["division"])}
    missing = [r for r in zip(b["fighter"], b["division"]) if r not in have]
    assert missing == []
