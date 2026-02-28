"""
Unit Tests for Market Mode Detection Module

EPIC 10 - Testing & Reliability
"""

import pytest
from processing.market_mode import MarketModeDetector, detect_market_mode


@pytest.fixture
def detector():
    """Fixture to create a MarketModeDetector instance."""
    return MarketModeDetector()


class TestGrowthRateCalculation:
    """Tests for growth rate calculation."""
    
    def test_positive_growth(self, detector):
        """Test calculation of positive growth."""
        growth = detector.calculate_growth_rate(110, 100)
        assert growth == 10.0
    
    def test_negative_growth(self, detector):
        """Test calculation of negative growth."""
        growth = detector.calculate_growth_rate(90, 100)
        assert growth == -10.0
    
    def test_no_growth(self, detector):
        """Test zero growth."""
        growth = detector.calculate_growth_rate(100, 100)
        assert growth == 0.0
    
    def test_zero_historical(self, detector):
        """Test that zero historical value returns None."""
        growth = detector.calculate_growth_rate(100, 0)
        assert growth is None
    
    def test_none_historical(self, detector):
        """Test that None historical value returns None."""
        growth = detector.calculate_growth_rate(100, None)
        assert growth is None


class TestInflationaryDetection:
    """Tests for inflationary market mode detection."""
    
    def test_inflationary_both_metrics(self, detector):
        """Test inflationary detection with both rate and posting growth."""
        result = detector.detect_mode(
            current_median_rate=1100,
            historical_median_rate=1000,  # 10% rate growth
            current_posting_count=120,
            historical_posting_count=100,  # 20% posting growth
            data_points=50
        )
        
        assert result['market_mode'] == 'Inflationary'
        assert result['rate_growth_pct'] == 10.0
        assert result['posting_growth_pct'] == 20.0
    
    def test_inflationary_posting_only(self, detector):
        """Test inflationary with posting growth only."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=None,
            current_posting_count=120,
            historical_posting_count=100,  # 20% growth
            data_points=50
        )
        
        assert result['market_mode'] == 'Inflationary'
    
    def test_not_inflationary_insufficient_growth(self, detector):
        """Test that insufficient growth doesn't trigger inflationary."""
        result = detector.detect_mode(
            current_median_rate=1030,
            historical_median_rate=1000,  # 3% rate growth (below 5%)
            current_posting_count=105,
            historical_posting_count=100,  # 5% posting growth (below 15%)
            data_points=50
        )
        
        assert result['market_mode'] != 'Inflationary'


class TestContractionDetection:
    """Tests for contraction market mode detection."""
    
    def test_contraction_posting_decline(self, detector):
        """Test contraction detection with posting decline."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=1000,
            current_posting_count=80,
            historical_posting_count=100,  # 20% decline
            data_points=50
        )
        
        assert result['market_mode'] == 'Contraction'
        assert result['posting_growth_pct'] == -20.0
    
    def test_contraction_threshold(self, detector):
        """Test contraction at exact threshold."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=1000,
            current_posting_count=85,
            historical_posting_count=100,  # Exactly 15% decline
            data_points=50
        )
        
        assert result['market_mode'] == 'Contraction'
    
    def test_not_contraction_small_decline(self, detector):
        """Test that small decline doesn't trigger contraction."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=1000,
            current_posting_count=90,
            historical_posting_count=100,  # 10% decline (below 15%)
            data_points=50
        )
        
        assert result['market_mode'] != 'Contraction'


class TestStableDetection:
    """Tests for stable market mode detection."""
    
    def test_stable_no_significant_change(self, detector):
        """Test stable mode with no significant changes."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=1000,
            current_posting_count=100,
            historical_posting_count=100,
            data_points=50
        )
        
        assert result['market_mode'] == 'Stable'
    
    def test_stable_moderate_changes(self, detector):
        """Test stable with moderate changes."""
        result = detector.detect_mode(
            current_median_rate=1030,
            historical_median_rate=1000,  # 3% growth
            current_posting_count=105,
            historical_posting_count=100,  # 5% growth
            data_points=50
        )
        
        assert result['market_mode'] == 'Stable'
    
    def test_stable_no_historical_data(self, detector):
        """Test stable mode when no historical data available."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=None,
            current_posting_count=100,
            historical_posting_count=None,
            data_points=50
        )
        
        assert result['market_mode'] == 'Stable'


class TestConfidenceCalculation:
    """Tests for confidence level calculation."""
    
    def test_high_confidence(self, detector):
        """Test high confidence with good data."""
        result = detector.detect_mode(
            current_median_rate=1100,
            historical_median_rate=1000,
            current_posting_count=120,
            historical_posting_count=100,
            data_points=50  # High data points
        )
        
        assert result['confidence'] == 'High'
    
    def test_medium_confidence(self, detector):
        """Test medium confidence with moderate data."""
        result = detector.detect_mode(
            current_median_rate=1100,
            historical_median_rate=1000,
            current_posting_count=120,
            historical_posting_count=100,
            data_points=20  # Medium data points
        )
        
        assert result['confidence'] == 'Medium'
    
    def test_low_confidence_few_points(self, detector):
        """Test low confidence with few data points."""
        result = detector.detect_mode(
            current_median_rate=1100,
            historical_median_rate=1000,
            current_posting_count=120,
            historical_posting_count=100,
            data_points=5  # Low data points
        )
        
        assert result['confidence'] == 'Low'
    
    def test_low_confidence_no_historical(self, detector):
        """Test low confidence with no historical data."""
        result = detector.detect_mode(
            current_median_rate=1000,
            historical_median_rate=None,
            current_posting_count=100,
            historical_posting_count=None,
            data_points=50
        )
        
        assert result['confidence'] == 'Low'


class TestConvenienceFunction:
    """Tests for convenience function."""
    
    def test_detect_market_mode_function(self):
        """Test the convenience function works correctly."""
        result = detect_market_mode(
            current_median_rate=1100,
            historical_median_rate=1000,
            current_posting_count=120,
            historical_posting_count=100,
            data_points=50
        )
        
        assert 'market_mode' in result
        assert 'confidence' in result
        assert result['market_mode'] in ['Inflationary', 'Stable', 'Contraction']
    
    def test_custom_thresholds(self):
        """Test with custom threshold values."""
        result = detect_market_mode(
            current_median_rate=1100,
            historical_median_rate=1000,
            current_posting_count=110,
            historical_posting_count=100,
            data_points=50,
            job_growth_threshold=10.0,  # Lower threshold
            rate_growth_threshold=5.0
        )
        
        assert result['market_mode'] == 'Inflationary'
