"""
Market Mode Detection Module

Detects market momentum: Inflationary, Contraction, or Stable.
EPIC 5 - Market Mode Detection
"""

from typing import Dict, Optional, List, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MarketModeDetector:
    """Detect market mode based on rate and job posting trends."""
    
    def __init__(
        self,
        job_growth_threshold: float = 15.0,
        rate_growth_threshold: float = 5.0,
        job_decline_threshold: float = 15.0
    ):
        """
        Initialize market mode detector.
        
        Args:
            job_growth_threshold: Job posting growth % for inflationary signal
            rate_growth_threshold: Rate growth % for inflationary signal
            job_decline_threshold: Job posting decline % for contraction signal
        """
        self.job_growth_threshold = job_growth_threshold
        self.rate_growth_threshold = rate_growth_threshold
        self.job_decline_threshold = job_decline_threshold
    
    def calculate_growth_rate(
        self,
        current: float,
        historical: float
    ) -> Optional[float]:
        """
        Calculate percentage growth rate.
        
        Args:
            current: Current value
            historical: Historical value
            
        Returns:
            Growth rate as percentage, or None if historical is 0
        """
        if historical == 0 or historical is None:
            return None
        
        growth = ((current - historical) / historical) * 100
        return round(growth, 2)
    
    def detect_mode(
        self,
        current_median_rate: float,
        historical_median_rate: Optional[float],
        current_posting_count: int,
        historical_posting_count: Optional[int],
        data_points: int
    ) -> Dict[str, Any]:
        """
        Detect market mode based on trends.
        
        Logic:
        - Inflationary: ≥15% job growth AND >5% rate growth
        - Contraction: ≥15% job decline
        - Stable: Otherwise
        
        Args:
            current_median_rate: Current median daily rate
            historical_median_rate: Historical median rate (from previous period)
            current_posting_count: Current number of job postings
            historical_posting_count: Historical job posting count
            data_points: Number of data points in current analysis
            
        Returns:
            Dictionary with market_mode, confidence, and supporting metrics
        """
        # Calculate growth rates
        rate_growth = self.calculate_growth_rate(
            current_median_rate,
            historical_median_rate
        ) if historical_median_rate else None
        
        posting_growth = self.calculate_growth_rate(
            current_posting_count,
            historical_posting_count
        ) if historical_posting_count else None
        
        # Determine confidence based on data availability
        confidence = self._calculate_confidence(
            data_points,
            has_historical_rate=historical_median_rate is not None,
            has_historical_postings=historical_posting_count is not None
        )
        
        # Detect mode
        mode = "Stable"  # Default
        
        if rate_growth is not None and posting_growth is not None:
            # Both metrics available
            if (posting_growth >= self.job_growth_threshold and 
                rate_growth > self.rate_growth_threshold):
                mode = "Inflationary"
            elif posting_growth <= -self.job_decline_threshold:
                mode = "Contraction"
        elif posting_growth is not None:
            # Only posting data available
            if posting_growth >= self.job_growth_threshold:
                mode = "Inflationary"
            elif posting_growth <= -self.job_decline_threshold:
                mode = "Contraction"
        elif rate_growth is not None:
            # Only rate data available
            if rate_growth > self.rate_growth_threshold:
                mode = "Inflationary"
        
        logger.info(
            f"Market mode detected: {mode} "
            f"(rate_growth={rate_growth}%, posting_growth={posting_growth}%)"
        )
        
        return {
            'market_mode': mode,
            'confidence': confidence,
            'rate_growth_pct': rate_growth,
            'posting_growth_pct': posting_growth,
            'current_median_rate': current_median_rate,
            'historical_median_rate': historical_median_rate,
            'current_posting_count': current_posting_count,
            'historical_posting_count': historical_posting_count,
            'data_points': data_points
        }
    
    def _calculate_confidence(
        self,
        data_points: int,
        has_historical_rate: bool,
        has_historical_postings: bool
    ) -> str:
        """
        Calculate confidence level for market mode detection.
        
        Args:
            data_points: Number of current data points
            has_historical_rate: Whether historical rate data exists
            has_historical_postings: Whether historical posting data exists
            
        Returns:
            Confidence level: 'High', 'Medium', or 'Low'
        """
        # Base confidence on data points
        if data_points < 10:
            base_confidence = 'Low'
        elif data_points < 30:
            base_confidence = 'Medium'
        else:
            base_confidence = 'High'
        
        # Reduce confidence if missing historical data
        if not has_historical_rate and not has_historical_postings:
            return 'Low'  # No historical data
        elif not has_historical_rate or not has_historical_postings:
            # Only one type of historical data
            if base_confidence == 'High':
                return 'Medium'
            else:
                return 'Low'
        
        return base_confidence


def detect_market_mode(
    current_median_rate: float,
    historical_median_rate: Optional[float],
    current_posting_count: int,
    historical_posting_count: Optional[int],
    data_points: int,
    job_growth_threshold: float = 15.0,
    rate_growth_threshold: float = 5.0,
    job_decline_threshold: float = 15.0
) -> Dict[str, Any]:
    """
    Convenience function to detect market mode.
    
    Args:
        current_median_rate: Current median daily rate
        historical_median_rate: Historical median rate
        current_posting_count: Current job posting count
        historical_posting_count: Historical job posting count
        data_points: Number of data points
        job_growth_threshold: Job growth threshold %
        rate_growth_threshold: Rate growth threshold %
        job_decline_threshold: Job decline threshold %
        
    Returns:
        Market mode detection result
    """
    detector = MarketModeDetector(
        job_growth_threshold,
        rate_growth_threshold,
        job_decline_threshold
    )
    return detector.detect_mode(
        current_median_rate,
        historical_median_rate,
        current_posting_count,
        historical_posting_count,
        data_points
    )
