"""Classification rules applied when a NASR cycle is turned into a query-ready snapshot."""

from airport_mcp.dataset import is_paved


def test_is_paved_counts_bound_pavement_only():
    """Only CONC, ASPH and PEM are pavement; TRTD is stabilized soil, per the FAA layout."""
    expected = {
        "CONC": True,         # portland cement concrete
        "ASPH": True,         # asphalt or bituminous concrete
        "PEM": True,          # part bitumen-bound macadam
        "asph": True,         # case-insensitive
        "ASPH-CONC": True,    # compound value: both sections paved
        "ASPH-TURF": True,    # compound value: one paved section is enough
        "ASPH/GRVL": True,    # slash also separates sections
        "TRTD": False,        # FAA: oiled, soil cement or lime stabilized
        "TREATED": False,
        "GRVL-TRTD": False,   # a stabilized gravel runway is not paved
        "DIRT-TRTD": False,
        "TURF": False,
        "GRVL": False,
        "WATER": False,
        "MATS": False,
        None: False,
    }

    assert {surface: is_paved(surface) for surface in expected} == expected
