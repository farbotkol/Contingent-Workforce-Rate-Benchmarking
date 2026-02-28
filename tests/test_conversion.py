"""
Unit Tests for Salary Conversion Module

EPIC 10 - Testing & Reliability
"""

import pytest
from processing.conversion import SalaryConverter


@pytest.fixture
def converter():
    """Fixture to create a SalaryConverter instance."""
    return SalaryConverter()


class TestMultipliers:
    """Tests for country-specific multipliers."""
    
    def test_get_australia_multiplier(self, converter):
        """Test getting Australia multiplier."""
        multiplier = converter.get_multiplier('Australia')
        assert multiplier == 1.35
    
    def test_get_singapore_multiplier(self, converter):
        """Test getting Singapore multiplier."""
        multiplier = converter.get_multiplier('Singapore')
        assert multiplier == 1.30
    
    def test_get_india_multiplier(self, converter):
        """Test getting India multiplier."""
        multiplier = converter.get_multiplier('India')
        assert multiplier == 1.25
    
    def test_get_philippines_multiplier(self, converter):
        """Test getting Philippines multiplier."""
        multiplier = converter.get_multiplier('Philippines')
        assert multiplier == 1.28
    
    def test_invalid_country(self, converter):
        """Test that invalid country raises error."""
        with pytest.raises(ValueError):
            converter.get_multiplier('InvalidCountry')


class TestCurrency:
    """Tests for currency retrieval."""
    
    def test_australia_currency(self, converter):
        """Test Australia currency code."""
        assert converter.get_currency('Australia') == 'AUD'
    
    def test_singapore_currency(self, converter):
        """Test Singapore currency code."""
        assert converter.get_currency('Singapore') == 'SGD'
    
    def test_india_currency(self, converter):
        """Test India currency code."""
        assert converter.get_currency('India') == 'INR'
    
    def test_philippines_currency(self, converter):
        """Test Philippines currency code."""
        assert converter.get_currency('Philippines') == 'PHP'
    
    def test_default_currency(self, converter):
        """Test default currency for unknown country."""
        assert converter.get_currency('Unknown') == 'USD'


class TestAnnualToDailyConversion:
    """Tests for annual salary to daily rate conversion."""
    
    def test_basic_conversion(self, converter):
        """Test basic salary to daily rate conversion."""
        result = converter.annual_to_daily(100000, 'Australia')
        
        assert result['daily_rate'] > 0
        assert result['currency'] == 'AUD'
        assert result['rate_type'] == 'Derived'
        assert result['country'] == 'Australia'
    
    def test_australia_conversion(self, converter):
        """Test Australia specific conversion."""
        # 120,000 * 1.35 / 220 = 736.36
        result = converter.annual_to_daily(120000, 'Australia')
        
        assert abs(result['daily_rate'] - 736.36) < 0.01
        assert result['currency'] == 'AUD'
        assert result['superannuation_excluded'] is True
    
    def test_singapore_conversion(self, converter):
        """Test Singapore conversion."""
        # 100,000 * 1.30 / 220 = 590.91
        result = converter.annual_to_daily(100000, 'Singapore')
        
        assert abs(result['daily_rate'] - 590.91) < 0.01
        assert result['currency'] == 'SGD'
    
    def test_negative_salary(self, converter):
        """Test that negative salary raises error."""
        with pytest.raises(ValueError):
            converter.annual_to_daily(-50000, 'Australia')
    
    def test_zero_salary(self, converter):
        """Test that zero salary raises error."""
        with pytest.raises(ValueError):
            converter.annual_to_daily(0, 'Australia')
    
    def test_conversion_metadata(self, converter):
        """Test that conversion includes proper metadata."""
        result = converter.annual_to_daily(100000, 'India')
        
        assert 'source_annual_salary' in result
        assert 'multiplier_used' in result
        assert 'working_days' in result
        assert result['source_annual_salary'] == 100000


class TestHourlyToDailyConversion:
    """Tests for hourly to daily rate conversion."""
    
    def test_basic_hourly_conversion(self, converter):
        """Test basic hourly to daily conversion."""
        result = converter.hourly_to_daily(50.0)
        
        # 50 * 8 = 400
        assert result['daily_rate'] == 400.00
        assert result['rate_type'] == 'Observed'
    
    def test_custom_hours(self, converter):
        """Test hourly conversion with custom hours per day."""
        result = converter.hourly_to_daily(50.0, hours_per_day=10)
        
        # 50 * 10 = 500
        assert result['daily_rate'] == 500.00
    
    def test_hourly_with_country(self, converter):
        """Test hourly conversion with country for currency."""
        result = converter.hourly_to_daily(50.0, country='Australia')
        
        assert result['currency'] == 'AUD'
        assert result['daily_rate'] == 400.00
    
    def test_negative_hourly_rate(self, converter):
        """Test that negative hourly rate raises error."""
        with pytest.raises(ValueError):
            converter.hourly_to_daily(-50.0)


class TestObservedRates:
    """Tests for marking observed rates."""
    
    def test_mark_as_observed(self, converter):
        """Test marking a rate as observed."""
        result = converter.mark_as_observed(800.0, 'Australia')
        
        assert result['daily_rate'] == 800.00
        assert result['currency'] == 'AUD'
        assert result['rate_type'] == 'Observed'
        assert result['country'] == 'Australia'
    
    def test_observed_rounding(self, converter):
        """Test that observed rates are rounded to 2 decimals."""
        result = converter.mark_as_observed(799.999, 'Singapore')
        
        assert result['daily_rate'] == 800.00
