import io
import zipfile
from datetime import date

import pytest

from airport_mcp.nasr import archive_url, cycle_effective_date, extract_tables


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 29), date(2026, 10, 29)),  # first day of a cycle
        (date(2026, 11, 25), date(2026, 10, 29)),  # last day of the same cycle
        (date(2026, 11, 26), date(2026, 11, 26)),  # next cycle starts
        (date(2024, 12, 31), date(2024, 12, 26)),  # before the anchor date
    ],
)
def test_cycle_effective_date(day, expected):
    assert cycle_effective_date(day) == expected


def test_archive_url_uses_faa_naming():
    assert archive_url(date(2026, 10, 29)).endswith("/29_Oct_2026_APT_CSV.zip")


def test_extract_tables_matches_exact_file_names():
    from conftest import FIXTURE_ARCHIVE

    tables = extract_tables(FIXTURE_ARCHIVE)
    assert "RWY_END_ID" not in tables["APT_RWY"].columns
    assert "RWY_END_ID" in tables["APT_RWY_END"].columns


def test_extract_tables_reports_missing_tables():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("APT_BASE.csv", "ARPT_ID\nJFK\n")
    with pytest.raises(ValueError, match="APT_RWY"):
        extract_tables(buffer.getvalue())
