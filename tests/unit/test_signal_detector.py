"""Tests for JD hidden-signal detection (core/jd/signal_detector.py)."""

from core.jd.signal_detector import SignalDetector


def _phrases(signals):
    return " | ".join(s.phrase for s in signals)


class TestSignalDetector:
    def setup_method(self):
        self.detector = SignalDetector()

    def test_detects_996(self):
        signals = self.detector.detect("我们施行996工作制,拥抱变化")
        assert any("996" in s.phrase for s in signals)

    def test_year_1996_not_flagged(self):
        signals = self.detector.detect("公司成立于1996年,行业领先")
        assert not any("996" in s.phrase for s in signals)

    def test_negation_suppressed(self):
        signals = self.detector.detect("我们不加班,无996文化")
        assert not any("加班" in s.phrase for s in signals)
        assert not any("996" in s.phrase for s in signals)

    def test_fast_paced_wildcard_fixed(self):
        # "." used to match any char, so "fastXpaced" was a false positive.
        hit = self.detector.detect("We are a fast-paced startup")
        miss = self.detector.detect("The fastXpaced metric")
        assert any("fast" in s.phrase.lower() for s in hit)
        assert not any("fast" in s.phrase.lower() for s in miss)

    def test_signal_shape(self):
        signals = self.detector.detect("需要抗压能力强的候选人")
        assert signals, "抗压 signal should be detected"
        s = signals[0]
        assert s.phrase and s.interpretation
        assert s.risk_level in ("info", "warning", "caution")
