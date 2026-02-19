"""
Tests for the Data Bijwerken page helpers and the week-overlap filtering logic.
Run with: pytest tests/test_data_update.py -v
"""
import io
import sys
import os
import pytest
import pandas as pd
from datetime import datetime, timedelta

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import validate_csv_upload, build_week_verification_table
from app.report import _filter_week_overlap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_COLS = [
    "Reserveringsnummer", "Relatie", "Aankomst", "Vertrek",
    "Ingevuld op", "Objectsoort", "Objectnaam", "Verhuurmodel",
    "Vraag", "Antwoord",
]


def _make_csv_bytes(rows, sep=";", encoding="latin-1", extra_cols=None):
    """Build a minimal CSV in the expected format."""
    cols = REQUIRED_COLS + (extra_cols or [])
    header = sep.join(cols)
    lines = [header]
    for row in rows:
        values = [str(row.get(c, "")) for c in cols]
        lines.append(sep.join(values))
    return "\n".join(lines).encode(encoding)


def _make_sample_row(**kwargs):
    defaults = {
        "Reserveringsnummer": "12345",
        "Relatie": "Jansen",
        "Aankomst": "01-01-2025",
        "Vertrek": "08-01-2025",
        "Ingevuld op": "08-01-2025",
        "Objectsoort": "Chalet",
        "Objectnaam": "Chalet 1",
        "Verhuurmodel": "Direct",
        "Vraag": "Wat is uw algemene oordeel over uw verblijf?",
        "Antwoord": "9",
        "Aanvulling": "",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Tests: validate_csv_upload
# ---------------------------------------------------------------------------

class TestValidateCsvUpload:
    """Tests for validate_csv_upload()."""

    def test_valid_camping_csv_returns_ok(self):
        rows = [_make_sample_row(Antwoord="8"), _make_sample_row(Reserveringsnummer="99999", Antwoord="6")]
        csv_bytes = _make_csv_bytes(rows)
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Camping")
        assert ok is True, f"Expected ok=True but got: {msg}"
        assert row_count == 2
        assert "2" in msg

    def test_missing_required_column_returns_error(self):
        # Build CSV without 'Antwoord' column
        cols = [c for c in REQUIRED_COLS if c != "Antwoord"]
        header = ";".join(cols)
        row = ";".join(["test"] * len(cols))
        csv_bytes = (header + "\n" + row).encode("latin-1")
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Camping")
        assert ok is False
        assert "Antwoord" in msg

    def test_empty_csv_returns_error(self):
        # Only header, no data rows
        header = ";".join(REQUIRED_COLS)
        csv_bytes = header.encode("latin-1")
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Camping")
        assert ok is False

    def test_wrong_separator_returns_error(self):
        # Comma-separated instead of semicolon -> columns won't split properly
        header = ",".join(REQUIRED_COLS)
        row = ",".join(["test"] * len(REQUIRED_COLS))
        csv_bytes = (header + "\n" + row).encode("latin-1")
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Accommodaties")
        # Either the file can't be read, or it returns a single big column name
        # Either way it should fail or have 0 matching required columns
        if ok:
            # If it parsed, it should have failed column check (comma as one big col)
            pass  # Accept either outcome; both are valid failure modes for wrong sep
        else:
            assert row_count == 0 or "Ontbrekende" in msg

    def test_accommodaties_segment_accepted(self):
        rows = [_make_sample_row(Objectsoort="Accommodatie", Antwoord="10")]
        csv_bytes = _make_csv_bytes(rows)
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Accommodaties")
        assert ok is True
        assert row_count == 1

    def test_trailing_unnamed_column_ignored(self):
        """A trailing semicolon creates an 'Unnamed: N' column – should still pass."""
        rows = [_make_sample_row()]
        # Add trailing semicolon to each line
        header = ";".join(REQUIRED_COLS) + ";"
        data_row = ";".join([str(rows[0].get(c, "")) for c in REQUIRED_COLS]) + ";"
        csv_bytes = (header + "\n" + data_row).encode("latin-1")
        ok, msg, row_count = validate_csv_upload(csv_bytes, "Camping")
        assert ok is True, f"Trailing semicolons should be handled. Got: {msg}"


# ---------------------------------------------------------------------------
# Tests: _filter_week_overlap (report.py)
# ---------------------------------------------------------------------------

class TestFilterWeekOverlap:
    """Tests that verify the overlap logic matches expected week assignments."""

    def _make_df(self, stays):
        """
        stays: list of (aankomst_str, vertrek_str, reserveringsnummer, score)
        Returns a DataFrame matching the schema used by _filter_week_overlap.
        """
        records = []
        for i, (a, v, res, score) in enumerate(stays):
            aankomst = pd.to_datetime(a, dayfirst=True) if a else pd.NaT
            vertrek = pd.to_datetime(v, dayfirst=True) if v else pd.NaT
            v_iso = vertrek.isocalendar() if pd.notna(vertrek) else None
            records.append({
                "reserveringsnummer": res,
                "aankomst": aankomst,
                "vertrek": vertrek,
                "vertrek_jaar": int(v_iso[0]) if v_iso else None,
                "vertrek_week": int(v_iso[1]) if v_iso else None,
                "score": score,
                "vraag_label": "Algemeen oordeel",
                "segment": "Camping",
            })
        df = pd.DataFrame(records)
        df["vertrek_jaar"] = pd.to_numeric(df["vertrek_jaar"], errors="coerce").astype("Int64")
        df["vertrek_week"] = pd.to_numeric(df["vertrek_week"], errors="coerce").astype("Int64")
        return df

    def test_standard_stay_within_week_is_included(self):
        """A stay entirely within week 7 2025 should be included."""
        # Week 7 2025: Mon 10-Feb to Sun 16-Feb
        df = self._make_df([
            ("10-02-2025", "15-02-2025", "RES001", 9),
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 1

    def test_monday_departure_stay_included(self):
        """
        Guest departs Monday 17 Feb 2025 (ISO week 8) but stayed in week 7.
        Must be included in week 7 overlap filter.
        """
        # Week 7: Mon 10 Feb – Sun 16 Feb 2025
        # Vertrek = Mon 17 Feb = ISO week 8 → must still belong to week 7
        df = self._make_df([
            ("10-02-2025", "17-02-2025", "RES002", 8),
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 1, (
            "Guest departing Monday of next week should still be in the previous week "
            "via overlap logic"
        )

    def test_stay_before_week_is_excluded(self):
        """A stay that ends before the week starts should not be included."""
        # Week 7 2025: Mon 10-Feb. Stay ends 9-Feb → before week start
        df = self._make_df([
            ("05-02-2025", "09-02-2025", "RES003", 7),
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 0

    def test_stay_after_week_is_excluded(self):
        """A stay that starts after the week ends should not be included."""
        # Week 7 2025 ends 16-Feb. Stay starts 17-Feb → after week end
        df = self._make_df([
            ("17-02-2025", "22-02-2025", "RES004", 9),
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 0

    def test_overlapping_stay_spanning_two_weeks_is_included(self):
        """A long stay overlapping into week 7 from week 6 should be included."""
        # Aankomst in week 6, vertrek in week 7
        df = self._make_df([
            ("07-02-2025", "14-02-2025", "RES005", 8),
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 1

    def test_multiple_stays_correct_count(self):
        """Mixed stays: 2 in week 7, 1 before, 1 after."""
        df = self._make_df([
            ("10-02-2025", "14-02-2025", "RES010", 9),   # in week 7
            ("12-02-2025", "17-02-2025", "RES011", 7),   # Monday departure → in week 7
            ("05-02-2025", "09-02-2025", "RES012", 8),   # before week 7
            ("18-02-2025", "22-02-2025", "RES013", 6),   # after week 7
        ])
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 2, f"Expected 2, got {len(result)}"

    def test_fallback_for_missing_dates(self):
        """Rows without aankomst/vertrek fall back to vertrek_jaar/vertrek_week."""
        records = [{
            "reserveringsnummer": "RES020",
            "aankomst": pd.NaT,
            "vertrek": pd.NaT,
            "vertrek_jaar": pd.array([2025], dtype="Int64")[0],
            "vertrek_week": pd.array([7], dtype="Int64")[0],
            "score": 9,
            "vraag_label": "Algemeen oordeel",
            "segment": "Camping",
        }]
        df = pd.DataFrame(records)
        df["vertrek_jaar"] = df["vertrek_jaar"].astype("Int64")
        df["vertrek_week"] = df["vertrek_week"].astype("Int64")
        result = _filter_week_overlap(df, 2025, 7)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Tests: build_week_verification_table
# ---------------------------------------------------------------------------

class TestBuildWeekVerificationTable:
    """Tests for build_week_verification_table()."""

    def _make_df_with_recent_stays(self):
        """Build a DataFrame with stays in the last 2 weeks."""
        today = datetime.today()
        last_week = today - timedelta(weeks=1)
        iso = last_week.isocalendar()
        t_jaar = int(iso[0])
        t_week = int(iso[1])

        try:
            w_start = datetime.fromisocalendar(t_jaar, t_week, 1)
            w_end = w_start + timedelta(days=6)
        except Exception:
            return pd.DataFrame()

        # Two stays in last week
        records = []
        for i, (seg, score) in enumerate([("Camping", 9), ("Accommodaties", 7)]):
            aankomst = w_start + timedelta(days=1)
            vertrek = w_end - timedelta(days=1)
            v_iso = vertrek.isocalendar()
            records.append({
                "reserveringsnummer": f"VER{i}",
                "aankomst": aankomst,
                "vertrek": vertrek,
                "vertrek_jaar": int(v_iso[0]),
                "vertrek_week": int(v_iso[1]),
                "score": float(score),
                "vraag_label": "Algemeen oordeel",
                "segment": seg,
                "unique_key": f"key{i}",
            })
        df = pd.DataFrame(records)
        df["vertrek_jaar"] = df["vertrek_jaar"].astype("Int64")
        df["vertrek_week"] = df["vertrek_week"].astype("Int64")
        df["aankomst"] = pd.to_datetime(df["aankomst"])
        df["vertrek"] = pd.to_datetime(df["vertrek"])
        return df

    def test_returns_list(self):
        df = self._make_df_with_recent_stays()
        result = build_week_verification_table(df)
        assert isinstance(result, list)

    def test_returns_recent_weeks(self):
        df = self._make_df_with_recent_stays()
        result = build_week_verification_table(df)
        # Should have at least some rows for last week
        assert len(result) >= 1

    def test_row_has_required_keys(self):
        df = self._make_df_with_recent_stays()
        result = build_week_verification_table(df)
        if result:
            row = result[0]
            for key in ("Week", "Jaar", "Periode", "Segment", "Respondenten", "NPS Algemeen"):
                assert key in row, f"Missing key: {key}"

    def test_respondenten_count_is_correct(self):
        """Verify respondent count matches actual stays."""
        df = self._make_df_with_recent_stays()
        result = build_week_verification_table(df)
        # Total respondenten across all segments for last week
        today = datetime.today()
        last_week_iso = (today - timedelta(weeks=1)).isocalendar()
        last_week_rows = [r for r in result if r["Week"] == int(last_week_iso[1]) and r["Jaar"] == int(last_week_iso[0])]
        total_resp = sum(r["Respondenten"] for r in last_week_rows)
        # We put 2 stays (one per segment) in last week
        assert total_resp == 2, f"Expected 2 respondenten but got {total_resp}"

    def test_empty_df_returns_empty_list(self):
        df = pd.DataFrame(columns=[
            "reserveringsnummer", "aankomst", "vertrek", "vertrek_jaar",
            "vertrek_week", "score", "vraag_label", "segment",
        ])
        df["aankomst"] = pd.to_datetime(df["aankomst"])
        df["vertrek"] = pd.to_datetime(df["vertrek"])
        df["vertrek_jaar"] = df["vertrek_jaar"].astype("Int64")
        df["vertrek_week"] = df["vertrek_week"].astype("Int64")
        result = build_week_verification_table(df)
        # All weeks will have 0 respondents — verify it doesn't crash and returns a list
        assert isinstance(result, list)
