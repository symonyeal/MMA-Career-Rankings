"""The site builder's serialiser: plotly typed arrays decode, and non-finite values become null."""
import base64

import numpy as np
import pandas as pd

from analysis.build_site import plain


def test_plain_decodes_plotly_typed_arrays():
    v = np.array([1.234, 2.5])
    spec = {"dtype": "f8", "bdata": base64.b64encode(v.tobytes()).decode()}
    assert plain({"x": spec}) == {"x": [1.23, 2.5]}


def test_plain_maps_missing_values_to_null_and_rounds_to_integers():
    assert plain([np.nan, pd.NaT, pd.Timestamp("2020-01-02"), np.float64(2.6)], 0) == [None, None, "2020-01-02", 3]
