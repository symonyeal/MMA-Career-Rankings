# The notebook retired — 2026-10-29

The site (`site/`, built by `analysis/build_site.py`) is the project's one presentation. The
notebook duplicated it, and its definitions had drifted from the published ones:

- its leaderboard sorted the raw rating column with a 3-bout floor, while the published boards
  use the gated board ranks and a 13-bout floor;
- its "career receipt" used a field-mean bar clipped at zero, so it did not sum to the published
  career skill mass, which the site's receipt is checked against;
- its era heat map read Glicko-2 over all bouts, while the site reads WHR over UFC bouts.

No ranking moved. The full release chain was rerun before and after: every snapshot artifact,
the top-100 audit, RANKINGS.md, README.md and `site/data.js` were identical.

## What is here

- `analysis/build_notebook.py` and `analysis/notebook.ipynb`: the generator and its output.
- `analysis/viz.py`: the module as it stood, 4,226 lines. The live `analysis/viz.py` keeps only
  the 22 definitions `build_site.py` reaches.
- `tests/`: the tests of notebook-only charts. `test_viz_smoke.py` and
  `test_gender_separated_boards.py` are the versions before their notebook-only tests were cut.

## Views the site does not have

The held-out scorecard and ablation forest, rank intervals and tiers, the bar ladder, odds
history per fighter, the striking profile and the streak timeline. Each builder is in
`analysis/viz.py` here; porting one to the site means a frame in `build_site.py` and a section
in `site/app.js`.

`requirements.txt` dropped ipywidgets, anywidget, jupyterlab, ipykernel and jinja2, which only the
notebook used, and python-dateutil, which nothing imports directly.
