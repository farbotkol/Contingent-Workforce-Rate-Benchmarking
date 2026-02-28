"""
Statistical Rate Band Engine

Handles outlier removal and percentile generation for rate bands.
EPIC 4 - Statistical Rate Band Engine
"""

import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)


class RateBandCalculator:
    """Calculate statistical rate bands with outlier removal."""
    
    def __init__(
        self,
        trim_percentage: float = 10.0,
        min_data_points: int = 10
    ):
        """
        Initialize the rate band calculator.
        
        Args:
            trim_percentage: Percentage to trim from top and bottom (default: 10%)
            min_data_points: Minimum data points required for reliable statistics
        """
        self.trim_percentage = trim_percentage
        self.min_data_points = min_data_points
    
    def remove_outliers(
        self,
        rates: List[float],
        trim_percentage: Optional[float] = None
    ) -> Tuple[List[float], Dict[str, int]]:
        """
        Remove outliers by trimming top and bottom percentages.
        
        Args:
            rates: List of daily rates
            trim_percentage: Optional override for trim percentage
            
        Returns:
            Tuple of (trimmed_rates, stats_dict)
            stats_dict contains before_count, after_count, removed_count
        """
        if not rates:
            return [], {'before_count': 0, 'after_count': 0, 'removed_count': 0}
        
        trim_pct = trim_percentage if trim_percentage is not None else self.trim_percentage
        
        before_count = len(rates)
        sorted_rates = sorted(rates)
        
        # Calculate trim indices
        trim_count = int(len(sorted_rates) * (trim_pct / 100))
        
        if trim_count == 0:
            # Not enough data to trim
            return sorted_rates, {
                'before_count': before_count,
                'after_count': before_count,
                'removed_count': 0
            }
        
        # Remove top and bottom trim_percentage
        trimmed_rates = sorted_rates[trim_count:-trim_count] if trim_count > 0 else sorted_rates
        
        after_count = len(trimmed_rates)
        removed_count = before_count - after_count
        
        logger.info(f"Outlier removal: {before_count} → {after_count} rates (removed {removed_count})")
        
        return trimmed_rates, {
            'before_count': before_count,
            'after_count': after_count,
            'removed_count': removed_count
        }
    
    def calculate_percentiles(
        self,
        rates: List[float],
        remove_outliers: bool = True
    ) -> Dict[str, Any]:
        """
        Calculate P25, Median, and P75 for rate bands.
        
        Args:
            rates: List of daily rates
            remove_outliers: Whether to remove outliers first
            
        Returns:
            Dictionary with percentile values and metadata
        """
        if not rates:
            return {
                'p25': None,
                'median': None,
                'p75': None,
                'confidence': 'No Data',
                'data_points': 0,
                'error': 'No data provided'
            }
        
        # Remove outliers if requested
        if remove_outliers:
            working_rates, trim_stats = self.remove_outliers(rates)
        else:
            working_rates = rates
            trim_stats = {
                'before_count': len(rates),
                'after_count': len(rates),
                'removed_count': 0
            }
        
        if not working_rates:
            return {
                'p25': None,
                'median': None,
                'p75': None,
                'confidence': 'No Data',
                'data_points': 0,
                'error': 'All data removed as outliers'
            }
        
        data_points = len(working_rates)
        
        # Determine confidence level
        if data_points < self.min_data_points:
            confidence = 'Low'
        elif data_points < 30:
            confidence = 'Medium'
        else:
            confidence = 'High'
        
        # Calculate percentiles using numpy
        p25 = float(np.percentile(working_rates, 25))
        median = float(np.percentile(working_rates, 50))
        p75 = float(np.percentile(working_rates, 75))
        
        return {
            'p25': round(p25, 2),
            'median': round(median, 2),
            'p75': round(p75, 2),
            'confidence': confidence,
            'data_points': data_points,
            'min': round(min(working_rates), 2),
            'max': round(max(working_rates), 2),
            'mean': round(float(np.mean(working_rates)), 2),
            'std_dev': round(float(np.std(working_rates)), 2),
            'outliers_removed': trim_stats['removed_count'],
            'original_count': trim_stats['before_count']
        }
    
    def generate_rate_bands(
        self,
        rates: List[float],
        currency: str,
        country: str,
        role: str,
        level: str
    ) -> Dict[str, Any]:
        """
        Generate complete rate band information.
        
        Args:
            rates: List of daily rates
            currency: Currency code
            country: Country name
            role: Job role
            level: Seniority level
            
        Returns:
            Complete rate band dictionary
        """
        stats = self.calculate_percentiles(rates)
        
        return {
            'country': country,
            'role': role,
            'level': level,
            'currency': currency,
            'p25_daily_rate': stats.get('p25'),
            'median_daily_rate': stats.get('median'),
            'p75_daily_rate': stats.get('p75'),
            'confidence': stats.get('confidence'),
            'data_points': stats.get('data_points'),
            'statistics': {
                'min': stats.get('min'),
                'max': stats.get('max'),
                'mean': stats.get('mean'),
                'std_dev': stats.get('std_dev')
            },
            'outliers_removed': stats.get('outliers_removed', 0),
            'original_count': stats.get('original_count', 0)
        }


def calculate_rate_bands(
    rates: List[float],
    currency: str,
    country: str,
    role: str,
    level: str,
    trim_percentage: float = 10.0,
    min_data_points: int = 10
) -> Dict[str, Any]:
    """
    Convenience function to calculate rate bands.
    
    Args:
        rates: List of daily rates
        currency: Currency code
        country: Country name
        role: Job role
        level: Seniority level
        trim_percentage: Percentage to trim for outlier removal
        min_data_points: Minimum data points for high confidence
        
    Returns:
        Rate band dictionary
    """
    calculator = RateBandCalculator(trim_percentage, min_data_points)
    return calculator.generate_rate_bands(rates, currency, country, role, level)
