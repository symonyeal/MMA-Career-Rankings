"""Separate the solver from the data in the board movement published on 2026-10-13.

INPUT   RANKINGS.md as published before (c0072b4) and after (c760a2a) the exact WHR solver,
        rankings_exact_solver.md (the exact solver refitted on the original inputs, 2026-10-14),
        and the working-tree RANKINGS.md.
OUTPUT  summary.json beside this file.
Run from the repository root: python docs/validation/solver-refit-2026-10-14/compare_rankings.py

T(s)  : ranking tables in a RANKINGS.md text, {table: [(rank, fighter)]}
A, B  : tables published before and after the exact solver
E     : exact solver on the original inputs;  C : the working-tree RANKINGS.md
M_a   : men's all-time rank by fighter in A;  M_b the same in B
K     : fighters in both men's top 100s
N     : fighters named in docs/DECISIONS.md
"""
from __future__ import annotations

import json
import re
import statistics
import subprocess
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parents[2]
N = ["Donald Cerrone", "Sean Strickland", "Movsar Evloev", "Tom Aspinall", "Neil Magny"]


def T(s: str) -> dict[str, list[tuple[int, str]]]:
    s = s.replace("\r\n", "\n")
    o = {}
    for m in re.finditer(r"<!-- BOARD:(\w+):BEGIN -->(.*?)<!-- BOARD:\1:END -->", s, re.DOTALL):
        o[m.group(1)] = [(int(c[1]), c[2].strip()) for c in
                         (l.split("|") for l in m.group(2).splitlines() if re.match(r"\|\s*\d+\s*\|", l))]
    return o


def g(rev: str) -> str:
    return subprocess.check_output(["git", "show", f"{rev}:RANKINGS.md"], cwd=R, text=True, encoding="utf-8")


A, B = T(g("c0072b4")), T(g("c760a2a"))
E = T((H / "rankings_exact_solver.md").read_text(encoding="utf-8"))
C = T((R / "RANKINGS.md").read_text(encoding="utf-8"))
M_a, M_b = ({f: r for r, f in X["TOP100"]} for X in (A, B))
P_a, P_b = ({f: r for r, f in X["ELITEPRIME50"]} for X in (A, B))
K = set(M_a) & set(M_b)
summary = {
    "working_tree_rankings_equal_published_before": C == A,
    "exact_solver_on_original_inputs_vs_published_after": {
        k: [[list(e), list(b)] for e, b in zip(E[k], B[k]) if e != b] for k in B
    },
    "men_top100_before_to_after": {
        "kept": len(K),
        "same_rank": sum(M_a[f] == M_b[f] for f in K),
        "median_move": statistics.median(abs(M_a[f] - M_b[f]) for f in K),
        "named": {f: [M_a.get(f), M_b.get(f)] for f in N},
    },
    "prime_top50_before_to_after": {f: [P_a.get(f), P_b.get(f)] for f in ["Donald Cerrone", "Khamzat Chimaev"]},
}
(H / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=2))
