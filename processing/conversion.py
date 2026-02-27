"""
Salary to Contractor Conversion Module

Handles conversion from annual salary to daily contractor rates.
EPIC 3 - Salary to Contractor Conversion
"""

import yaml
import os
from typing import Dict, Optional


class SalaryConverter:
    """Converts annual salary to daily contractor rates using country-specific multipliers."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the salary converter.
        
        Args:
            config_path: Path to multipliers.yaml. If None, uses default location.
        """
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'config',
                'multipliers.yaml'
            )
        
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.multipliers = self.config.get('multipliers', {})
        self.currencies = self.config.get('currencies', {})
    
    def get_multiplier(self, country: str) -> float:
        """
        Get the conversion multiplier for a country.
        
        Args:
            country: Country name
            
        Returns:
            Multiplier value
            
        Raises:
            ValueError: If country not found in config
        """
        if country not in self.multipliers:
            raise ValueError(f"Country '{country}' not found in multipliers configuration")
        
        return self.multipliers[country]['multiplier']
    
    def get_working_days(self, country: str) -> int:
        """
        Get the working days per year for a country.
        
        Args:
            country: Country name
            
        Returns:
            Working days per year
        """
        if country not in self.multipliers:
            return 220  # Default
        
        return self.multipliers[country].get('working_days_per_year', 220)
    
    def get_currency(self, country: str) -> str:
        """
        Get the currency code for a country.
        
        Args:
            country: Country name
            
        Returns:
            Currency code (e.g., 'AUD', 'SGD')
        """
        return self.currencies.get(country, 'USD')
    
    def annual_to_daily(
        self,
        annual_salary: float,
        country: str,
        exclude_superannuation: bool = True
    ) -> Dict[str, any]:
        """
        Convert annual salary to daily contractor rate.
        
        Formula: daily_rate = (annual_salary × multiplier) / working_days_per_year
        
        Args:
            annual_salary: Annual salary amount
            country: Country name
            exclude_superannuation: For Australia, whether to exclude super (default: True)
            
        Returns:
            Dictionary with daily_rate, currency, rate_type ('Derived'), and metadata
        """
        if annual_salary <= 0:
            raise ValueError("Annual salary must be positive")
        
        multiplier = self.get_multiplier(country)
        working_days = self.get_working_days(country)
        currency = self.get_currency(country)
        
        # For Australia, annual_salary should already exclude superannuation if needed
        # This is noted in the output metadata
        daily_rate = (annual_salary * multiplier) / working_days
        
        return {
            'daily_rate': round(daily_rate, 2),
            'currency': currency,
            'rate_type': 'Derived',
            'source_annual_salary': annual_salary,
            'country': country,
            'multiplier_used': multiplier,
            'working_days': working_days,
            'superannuation_excluded': exclude_superannuation if country == 'Australia' else None
        }
    
    def hourly_to_daily(
        self,
        hourly_rate: float,
        hours_per_day: int = 8,
        country: Optional[str] = None
    ) -> Dict[str, any]:
        """
        Convert hourly rate to daily rate.
        
        Args:
            hourly_rate: Hourly rate
            hours_per_day: Hours per working day (default: 8)
            country: Optional country name for currency info
            
        Returns:
            Dictionary with daily_rate, currency, and rate_type ('Observed')
        """
        if hourly_rate <= 0:
            raise ValueError("Hourly rate must be positive")
        
        daily_rate = hourly_rate * hours_per_day
        currency = self.get_currency(country) if country else 'USD'
        
        return {
            'daily_rate': round(daily_rate, 2),
            'currency': currency,
            'rate_type': 'Observed',
            'source_hourly_rate': hourly_rate,
            'hours_per_day': hours_per_day
        }
    
    def mark_as_observed(
        self,
        daily_rate: float,
        country: str
    ) -> Dict[str, any]:
        """
        Mark a daily rate as directly observed (not derived from salary).
        
        Args:
            daily_rate: Observed daily rate
            country: Country name
            
        Returns:
            Dictionary with daily_rate, currency, and rate_type ('Observed')
        """
        return {
            'daily_rate': round(daily_rate, 2),
            'currency': self.get_currency(country),
            'rate_type': 'Observed',
            'country': country
        }


def load_converter(config_path: Optional[str] = None) -> SalaryConverter:
    """
    Factory function to load a SalaryConverter instance.
    
    Args:
        config_path: Optional path to multipliers.yaml
        
    Returns:
        SalaryConverter instance
    """
    return SalaryConverter(config_path)
