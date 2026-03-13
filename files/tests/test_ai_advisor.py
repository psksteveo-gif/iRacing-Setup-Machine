"""Tests for core.ai_advisor — rate limiter and rule-based fallback."""
import time
import pytest

import core.ai_advisor as ai_advisor
from core.analysis_engine import AnalysisEngine, AnalysisReport
from core.ibt_parser import load_demo_data


# ── Rate limiter ────────────────────────────────────────────────────

class TestRateLimiter:
    def setup_method(self):
        # Reset module-level state before each test
        ai_advisor._last_call_time = 0.0

    def test_first_call_allowed(self):
        assert ai_advisor._check_rate_limit() is True

    def test_rapid_second_call_blocked(self):
        ai_advisor._check_rate_limit()
        assert ai_advisor._check_rate_limit() is False

    def test_after_interval_allowed(self):
        ai_advisor._last_call_time = time.monotonic() - ai_advisor._MIN_INTERVAL_S - 1
        assert ai_advisor._check_rate_limit() is True


# ── Rule-based recommendations ──────────────────────────────────────

class TestRuleBasedRecommendations:
    @pytest.fixture
    def report(self):
        data = load_demo_data()
        return AnalysisEngine().analyze(data)

    def test_returns_string(self, report):
        result = ai_advisor._rule_based_recommendations(
            report, "ferrari_296_gt3", "Sebring"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_understeer_advice(self):
        rpt = AnalysisReport()
        rpt.balance_score = -0.5
        result = ai_advisor._rule_based_recommendations(rpt, "car", "track")
        assert "understeer" in result.lower() or "front" in result.lower()

    def test_oversteer_advice(self):
        rpt = AnalysisReport()
        rpt.balance_score = 0.5
        result = ai_advisor._rule_based_recommendations(rpt, "car", "track")
        assert "oversteer" in result.lower() or "rear" in result.lower()


# ── Sync function with empty key → rule-based fallback ──────────────

class TestSyncFallback:
    def setup_method(self):
        ai_advisor._last_call_time = 0.0

    def test_empty_key_returns_rule_based(self):
        data = load_demo_data()
        report = AnalysisEngine().analyze(data)
        result = ai_advisor.get_ai_recommendations_sync(
            report, "ferrari_296_gt3", "Sebring", api_key=""
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_rate_limit_message(self):
        data = load_demo_data()
        report = AnalysisEngine().analyze(data)
        # First call — consumes rate limit
        ai_advisor._check_rate_limit()
        # Second call with a key should be rate-limited
        result = ai_advisor.get_ai_recommendations_sync(
            report, "car", "track", api_key="sk-fake-key"
        )
        assert "wait" in result.lower()
