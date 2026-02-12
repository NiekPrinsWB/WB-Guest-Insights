"""
Tests for NPS calculation engine.
"""
import sys
import os
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.nps import calc_nps, nps_by_group, leaderboard


def make_df(scores):
    """Helper to create a DataFrame with scores."""
    return pd.DataFrame({"score": scores})


class TestCalcNPS:
    def test_all_promoters(self):
        """All scores 9-10 should give NPS +100."""
        df = make_df([9, 10, 10, 9, 10])
        result = calc_nps(df)
        assert result["nps"] == 100.0
        assert result["pct_promoters"] == 100.0
        assert result["pct_detractors"] == 0.0

    def test_all_detractors(self):
        """All scores 0-6 should give NPS -100."""
        df = make_df([1, 2, 3, 4, 5, 6])
        result = calc_nps(df)
        assert result["nps"] == -100.0
        assert result["pct_promoters"] == 0.0
        assert result["pct_detractors"] == 100.0

    def test_all_passives(self):
        """All scores 7-8 should give NPS 0."""
        df = make_df([7, 8, 7, 8])
        result = calc_nps(df)
        assert result["nps"] == 0.0

    def test_mixed_scores(self):
        """Test NPS with mixed scores."""
        # 2 promoters (9,10), 2 passives (7,8), 1 detractor (4)
        df = make_df([9, 10, 7, 8, 4])
        result = calc_nps(df)
        # promoters: 2/5 = 40%, detractors: 1/5 = 20%
        # NPS = 40 - 20 = 20
        assert result["nps"] == 20.0
        assert result["pct_promoters"] == 40.0
        assert result["pct_detractors"] == 20.0
        assert result["n"] == 5

    def test_empty_dataframe(self):
        """Empty DataFrame should return None."""
        df = make_df([])
        result = calc_nps(df)
        assert result is None

    def test_all_nan(self):
        """All NaN scores should return None."""
        df = make_df([float("nan"), float("nan")])
        result = calc_nps(df)
        assert result is None

    def test_min_responses(self):
        """Should return None if below minimum responses threshold."""
        df = make_df([9, 10])
        result = calc_nps(df, min_responses=5)
        assert result is None

    def test_boundary_score_7(self):
        """Score 7 should be passive (not detractor)."""
        df = make_df([7])
        result = calc_nps(df)
        assert result["pct_detractors"] == 0.0
        assert result["pct_passives"] == 100.0

    def test_boundary_score_6(self):
        """Score 6 should be detractor."""
        df = make_df([6])
        result = calc_nps(df)
        assert result["pct_detractors"] == 100.0

    def test_boundary_score_9(self):
        """Score 9 should be promoter."""
        df = make_df([9])
        result = calc_nps(df)
        assert result["pct_promoters"] == 100.0

    def test_boundary_score_8(self):
        """Score 8 should be passive (not promoter)."""
        df = make_df([8])
        result = calc_nps(df)
        assert result["pct_promoters"] == 0.0
        assert result["pct_passives"] == 100.0

    def test_avg_score(self):
        """Average score should be calculated correctly."""
        df = make_df([5, 10])
        result = calc_nps(df)
        assert result["avg_score"] == 7.5

    def test_with_nan_mixed(self):
        """NaN values should be excluded from calculation."""
        df = make_df([10, float("nan"), 1])
        result = calc_nps(df)
        assert result["n"] == 2
        # 1 promoter (10), 1 detractor (1) -> NPS = 50 - 50 = 0
        assert result["nps"] == 0.0


class TestNPSByGroup:
    def test_basic_grouping(self):
        df = pd.DataFrame({
            "score": [10, 10, 1, 1, 10, 10],
            "segment": ["A", "A", "A", "B", "B", "B"],
        })
        result = nps_by_group(df, "segment", min_responses=1)
        assert len(result) == 2

        a_row = result[result["segment"] == "A"].iloc[0]
        b_row = result[result["segment"] == "B"].iloc[0]

        # A: 2 promoters, 1 detractor out of 3 -> NPS = 66.7 - 33.3 = 33.3
        assert round(a_row["nps"], 1) == 33.3
        # B: 2 promoters, 1 detractor out of 3 -> NPS = 66.7 - 33.3 = 33.3
        assert round(b_row["nps"], 1) == 33.3

    def test_min_responses_filter(self):
        df = pd.DataFrame({
            "score": [10, 10, 10, 10, 10, 1],
            "segment": ["A", "A", "A", "A", "A", "B"],
        })
        result = nps_by_group(df, "segment", min_responses=3)
        assert len(result) == 1  # Only A meets threshold


class TestLeaderboard:
    def test_top_best(self):
        df = pd.DataFrame({
            "score": [10] * 10 + [1] * 10 + [7] * 10,
            "objectnaam": ["Good"] * 10 + ["Bad"] * 10 + ["Meh"] * 10,
        })
        top = leaderboard(df, "objectnaam", min_responses=5, top_n=2, ascending=False)
        assert len(top) == 2
        assert top.iloc[0]["objectnaam"] == "Good"

    def test_top_worst(self):
        df = pd.DataFrame({
            "score": [10] * 10 + [1] * 10 + [7] * 10,
            "objectnaam": ["Good"] * 10 + ["Bad"] * 10 + ["Meh"] * 10,
        })
        bottom = leaderboard(df, "objectnaam", min_responses=5, top_n=2, ascending=True)
        assert len(bottom) == 2
        assert bottom.iloc[0]["objectnaam"] == "Bad"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
