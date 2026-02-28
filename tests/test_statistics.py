"""
Unit Tests for Statistics Module

EPIC 10 - Testing & Reliability
"""

import pytest
import numpy as np
from processing.statistics import RateBandCalculator, calculate_rate_bands


@pytest.fixture
def calculator():
    """Fixture to create a RateBandCalculator instance."""
    return RateBandCalculator()


class TestOutlierRemoval:
    """Tests for outlier removal functionality."""
    
    def test_remove_outliers_basic(self, calculator):
        """Test basic outlier removal."""
        rates = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        trimmed, stats = calculator.remove_outliers(rates)
        
        # 10% trim from each end = remove 1 from each side
        assert len(trimmed) == 8
        assert stats['before_count'] == 10
        assert stats['after_count'] == 8
        assert stats['removed_count'] == 2
    
    def test_outliers_removed_from_both_ends(self, calculator):
        """Test that outliers are removed from both top and bottom."""
        rates = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        trimmed, stats = calculator.remove_outliers(rates)
        
        # Should not include 1 and 10 (extremes)
        assert 1 not in trimmed
        assert 10 not in trimmed
    
    def test_empty_list(self, calculator):
        """Test outlier removal with empty list."""
        trimmed, stats = calculator.remove_outliers([])
        
        assert trimmed == []
        assert stats['before_count'] == 0
        assert stats['after_count'] == 0
    
    def test_custom_trim_percentage(self, calculator):
        """Test outlier removal with custom trim percentage."""
        rates = list(range(1, 101))  # 100 values
        trimmed, stats = calculator.remove_outliers(rates, trim_percentage=20.0)
        
        # 20% trim = 20 from each end = 60 remaining
        assert len(trimmed) == 60
        assert stats['removed_count'] == 40
    
    def test_insufficient_data_for_trim(self, calculator):
        """Test with too few data points to trim."""
        rates = [100, 200, 300]
        trimmed, stats = calculator.remove_outliers(rates)
        
        # Too few points to meaningfully trim
        assert len(trimmed) >= 1


class TestPercentileCalculation:
    """Tests for percentile calculation."""
    
    def test_basic_percentiles(self, calculator):
        """Test basic percentile calculation."""
        rates = [100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]
        result = calculator.calculate_percentiles(rates)
        
        assert result['p25'] is not None
        assert result['median'] is not None
        assert result['p75'] is not None
        assert result['p25'] < result['median'] < result['p75']
    
    def test_percentile_values(self, calculator):
        """Test that percentile values are correct."""
        rates = list(range(1, 101))  # 1 to 100
        result = calculator.calculate_percentiles(rates, remove_outliers=False)
        
        # P25 should be around 25, median around 50, P75 around 75
        assert abs(result['p25'] - 25) < 5
        assert abs(result['median'] - 50) < 5
        assert abs(result['p75'] - 75) < 5
    
    def test_confidence_high(self, calculator):
        """Test high confidence with many data points."""
        rates = list(range(1, 51))  # 50 data points
        result = calculator.calculate_percentiles(rates, remove_outliers=False)
        
        assert result['confidence'] == 'High'
    
    def test_confidence_medium(self, calculator):
        """Test medium confidence with moderate data points."""
        rates = list(range(1, 21))  # 20 data points
        result = calculator.calculate_percentiles(rates, remove_outliers=False)
        
        assert result['confidence'] == 'Medium'
    
    def test_confidence_low(self, calculator):
        """Test low confidence with few data points."""
        rates = [100, 200, 300, 400, 500]  # 5 data points
        result = calculator.calculate_percentiles(rates, remove_outliers=False)
        
        assert result['confidence'] == 'Low'
    
    def test_empty_rates(self, calculator):
        """Test percentile calculation with empty list."""
        result = calculator.calculate_percentiles([])
        
        assert result['p25'] is None
        assert result['median'] is None
        assert result['p75'] is None
        assert result['confidence'] == 'No Data'
    
    def test_statistics_included(self, calculator):
        """Test that additional statistics are included."""
        rates = [100, 200, 300, 400, 500]
        result = calculator.calculate_percentiles(rates, remove_outliers=False)
        
        assert 'min' in result
        assert 'max' in result
        assert 'mean' in result
        assert 'std_dev' in result
        assert result['min'] == 100
        assert result['max'] == 500


class TestRateBandGeneration:
    """Tests for complete rate band generation."""
    
    def test_generate_rate_bands(self, calculator):
        """Test complete rate band generation."""
        rates = [800, 850, 900, 950, 1000, 1050, 1100, 1150, 1200, 1250]
        
        result = calculator.generate_rate_bands(
            rates,
            'AUD',
            'Australia',
            'Software Engineer',
            'Senior'
        )
        
        assert result['country'] == 'Australia'
        assert result['role'] == 'Software Engineer'
        assert result['level'] == 'Senior'
        assert result['currency'] == 'AUD'
        assert result['p25_daily_rate'] is not None
        assert result['median_daily_rate'] is not None
        assert result['p75_daily_rate'] is not None
        assert result['confidence'] in ['Low', 'Medium', 'High']
    
    def test_rate_bands_include_statistics(self, calculator):
        """Test that rate bands include statistics."""
        rates = [100, 200, 300, 400, 500]
        
        result = calculator.generate_rate_bands(
            rates, 'USD', 'Test', 'Role', 'Mid'
        )
        
        assert 'statistics' in result
        assert 'min' in result['statistics']
        assert 'max' in result['statistics']


class TestConvenienceFunction:
    """Tests for convenience function."""
    
    def test_calculate_rate_bands_function(self):
        """Test the convenience function works correctly."""
        rates = [500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400]
        
        result = calculate_rate_bands(
            rates,
            'SGD',
            'Singapore',
            'Data Engineer',
            'Mid'
        )
        
        assert result['country'] == 'Singapore'
        assert result['currency'] == 'SGD'
        assert result['role'] == 'Data Engineer'
        assert result['median_daily_rate'] is not None
