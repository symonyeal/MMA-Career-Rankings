"""How firmly is a fighter tied to the rest of the rated population?

Whole-sport scope removes the organization weight entirely: there is no
"PRIDE bout is worth 0.8" parameter, because relative promotion strength is an
*output* of one joint fit, read off the fighters who crossed between them. What
replaces the weight is this module.

A weakly connected fighter is not discounted toward the UFC -- that would assume
the answer the scope change exists to test. They are published with a wide
interval, and below a stated floor they are not ranked at all:

    unranked -- insufficiently connected

which says "we have no evidence", not "he was not good". This is the
completeness-abstention rule the engine already applies to missing data,
applied to the shape of the bout graph.

The measure is vertex-disjoint paths into the rated core (Menger), not a raw
count of bridge opponents. Twelve bouts against one crossover fighter is one
path, not twelve: if that fighter's own rating is off, every one of those bouts
is off with it. Disjoint paths count independent ways the scale reaches you.
"""
from __future__ import annotations

from collections import defaultdict, deque

import pandas as pd

# A fighter needs this many vertex-disjoint paths into the core before the board
# will rank them. Three is the smallest number at which a single mis-rated
# intermediary cannot by itself decide the placement.
DEFAULT_MIN_DISJOINT_PATHS = 3

# A bridge whose own record is this thin is not a reliable anchor, so it does
# not count toward the floor.
DEFAULT_MIN_BRIDGE_BOUTS = 3


def _adjacency(bouts: pd.DataFrame, a: str = "fighter_a_id", b: str = "fighter_b_id"):
    adj: dict[str, set[str]] = defaultdict(set)
    for x, y in zip(bouts[a], bouts[b]):
        if x and y and x != y:
            adj[x].add(y)
            adj[y].add(x)
    return adj


def _max_vertex_disjoint_paths(adj, source: str, core: set[str], cap: int) -> int:
    """Menger via unit-vertex-capacity max-flow, stopped once ``cap`` is reached.

    Every non-source, non-core vertex is split into in/out with capacity one, so
    a path may not reuse an intermediary. Counting stops at ``cap`` because the
    floor only asks whether a fighter clears it, not by how much.
    """
    if source in core:
        return cap

    # Residual graph over split vertices: (node, "in") -> (node, "out").
    residual: dict[tuple, dict[tuple, int]] = defaultdict(lambda: defaultdict(int))

    def add(u, v, c):
        residual[u][v] += c
        residual[v][u] += 0

    for node, nbrs in adj.items():
        if node != source and node not in core:
            add((node, "in"), (node, "out"), 1)
        for nbr in nbrs:
            u = (node, "out") if (node == source or node in core) else (node, "out")
            v = (nbr, "in") if (nbr != source and nbr not in core) else (nbr, "in")
            add(u, v, 1)
    for node in core:
        add((node, "in"), (node, "out"), 1)
        add((node, "out"), ("__sink__", "in"), 1)

    src, sink = (source, "out"), ("__sink__", "in")
    flow = 0
    while flow < cap:
        parent: dict[tuple, tuple] = {src: src}
        queue = deque([src])
        while queue and sink not in parent:
            u = queue.popleft()
            for v, c in residual[u].items():
                if c > 0 and v not in parent:
                    parent[v] = u
                    queue.append(v)
        if sink not in parent:
            break
        v = sink
        while v != src:
            u = parent[v]
            residual[u][v] -= 1
            residual[v][u] += 1
            v = u
        flow += 1
    return flow


def bridge_summary(
    crossorg_bouts: pd.DataFrame,
    core_ids: set[str],
    *,
    core_bout_counts: dict[str, int] | None = None,
    min_bridge_bouts: int = DEFAULT_MIN_BRIDGE_BOUTS,
) -> pd.DataFrame:
    """Per fighter: how many distinct, non-trivial bridges reach the core.

    ``core_ids`` are fighters already on the main scale (a UFC record).
    ``core_bout_counts`` gives each core fighter's own record depth, so a bridge
    with two career bouts does not count as an anchor.
    """
    counts = core_bout_counts or {}
    adj = _adjacency(crossorg_bouts)
    rows = []
    for fid, nbrs in adj.items():
        bridges = [n for n in nbrs
                   if n in core_ids and counts.get(n, min_bridge_bouts) >= min_bridge_bouts]
        rows.append({
            "fighter_id": fid,
            "opponents": len(nbrs),
            "bridge_opponents": len(bridges),
            "bridge_median_core_bouts": (
                float(pd.Series([counts.get(n, 0) for n in bridges]).median())
                if bridges else 0.0
            ),
            "in_core": fid in core_ids,
        })
    return pd.DataFrame(rows)


def connectivity(
    crossorg_bouts: pd.DataFrame,
    core_ids: set[str],
    *,
    core_bout_counts: dict[str, int] | None = None,
    min_disjoint_paths: int = DEFAULT_MIN_DISJOINT_PATHS,
    min_bridge_bouts: int = DEFAULT_MIN_BRIDGE_BOUTS,
    fighters: list[str] | None = None,
) -> pd.DataFrame:
    """Bridge counts plus vertex-disjoint path depth and the abstention verdict."""
    summary = bridge_summary(
        crossorg_bouts, core_ids,
        core_bout_counts=core_bout_counts, min_bridge_bouts=min_bridge_bouts,
    )
    adj = _adjacency(crossorg_bouts)
    counts = core_bout_counts or {}
    anchors = {n for n in core_ids if counts.get(n, min_bridge_bouts) >= min_bridge_bouts}

    targets = fighters if fighters is not None else summary["fighter_id"].tolist()
    paths = {
        fid: _max_vertex_disjoint_paths(adj, fid, anchors, min_disjoint_paths)
        for fid in targets
    }
    summary["disjoint_paths"] = summary["fighter_id"].map(paths)
    summary["rankable"] = (
        summary["in_core"]
        | (summary["disjoint_paths"] >= min_disjoint_paths)
    )
    summary["verdict"] = summary["rankable"].map(
        {True: "rankable", False: "unranked - insufficiently connected"}
    )
    return summary.sort_values("disjoint_paths", ascending=False).reset_index(drop=True)
