"""
CSV Export Module

Handles export of benchmark results to Rate Card Matrix compatible CSV format.
EPIC 7 - Rate Card Matrix Export
"""

import csv
import os
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CSVExporter:
    """Export benchmark results to CSV format compatible with Rate Card Matrix."""
    
    # Required CSV headers per specification
    HEADERS = [
        'Country',
        'Role',
        'Level',
        'Currency',
        'P25_Daily_Rate',
        'Median_Daily_Rate',
        'P75_Daily_Rate',
        'Market_Mode',
        'Source_Count',
        'Timestamp'
    ]
    
    def __init__(self, export_dir: Optional[str] = None):
        """
        Initialize CSV exporter.
        
        Args:
            export_dir: Directory for exports. If None, uses default 'exports' directory.
        """
        if export_dir is None:
            export_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'exports'
            )
        
        self.export_dir = export_dir
        
        # Create export directory if it doesn't exist
        os.makedirs(self.export_dir, exist_ok=True)
        logger.info(f"CSV exporter initialized with export_dir: {self.export_dir}")
    
    def generate_filename(
        self,
        role: str,
        country: str,
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Generate filename following the convention: role_country_YYYYMMDD.csv
        
        Args:
            role: Job role
            country: Country name
            timestamp: Optional timestamp (defaults to now)
            
        Returns:
            Filename string
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Clean role and country names for filename
        clean_role = role.replace(' ', '_').replace('/', '_')
        clean_country = country.replace(' ', '_')
        date_str = timestamp.strftime('%Y%m%d')
        
        return f"{clean_role}_{clean_country}_{date_str}.csv"
    
    def export_single(
        self,
        benchmark_data: Dict[str, Any],
        filename: Optional[str] = None
    ) -> str:
        """
        Export a single benchmark result to CSV.
        
        Args:
            benchmark_data: Benchmark result dictionary
            filename: Optional custom filename
            
        Returns:
            Path to the exported file
        """
        if filename is None:
            filename = self.generate_filename(
                benchmark_data.get('role', 'Unknown'),
                benchmark_data.get('country', 'Unknown')
            )
        
        filepath = os.path.join(self.export_dir, filename)
        
        # Convert benchmark data to CSV row format
        row = self._benchmark_to_row(benchmark_data)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS)
            writer.writeheader()
            writer.writerow(row)
        
        logger.info(f"Exported benchmark to {filepath}")
        return filepath
    
    def export_multiple(
        self,
        benchmark_data_list: List[Dict[str, Any]],
        filename: Optional[str] = None
    ) -> str:
        """
        Export multiple benchmark results to a single CSV file.
        
        Args:
            benchmark_data_list: List of benchmark result dictionaries
            filename: Optional custom filename
            
        Returns:
            Path to the exported file
        """
        if not benchmark_data_list:
            raise ValueError("No benchmark data to export")
        
        if filename is None:
            # Use first record for filename generation
            first_record = benchmark_data_list[0]
            filename = self.generate_filename(
                first_record.get('role', 'Multiple'),
                first_record.get('country', 'Multiple')
            )
        
        filepath = os.path.join(self.export_dir, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=self.HEADERS)
            writer.writeheader()
            
            for benchmark_data in benchmark_data_list:
                row = self._benchmark_to_row(benchmark_data)
                writer.writerow(row)
        
        logger.info(f"Exported {len(benchmark_data_list)} benchmarks to {filepath}")
        return filepath
    
    def _benchmark_to_row(self, benchmark_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert benchmark data dictionary to CSV row format.
        
        Args:
            benchmark_data: Benchmark result dictionary
            
        Returns:
            Dictionary matching CSV headers
        """
        # Handle both snake_case and direct field names
        return {
            'Country': benchmark_data.get('country', ''),
            'Role': benchmark_data.get('role', ''),
            'Level': benchmark_data.get('level', ''),
            'Currency': benchmark_data.get('currency', ''),
            'P25_Daily_Rate': self._format_rate(
                benchmark_data.get('p25_daily_rate') or benchmark_data.get('p25')
            ),
            'Median_Daily_Rate': self._format_rate(
                benchmark_data.get('median_daily_rate') or benchmark_data.get('median')
            ),
            'P75_Daily_Rate': self._format_rate(
                benchmark_data.get('p75_daily_rate') or benchmark_data.get('p75')
            ),
            'Market_Mode': benchmark_data.get('market_mode', ''),
            'Source_Count': benchmark_data.get('source_count', ''),
            'Timestamp': self._format_timestamp(
                benchmark_data.get('timestamp')
            )
        }
    
    def _format_rate(self, rate: Optional[float]) -> str:
        """
        Format a rate value for CSV output.
        
        Args:
            rate: Rate value
            
        Returns:
            Formatted rate string
        """
        if rate is None:
            return ''
        
        # Format to 2 decimal places
        return f"{rate:.2f}"
    
    def _format_timestamp(self, timestamp: Optional[str]) -> str:
        """
        Format timestamp for CSV output.
        
        Args:
            timestamp: Timestamp string or None
            
        Returns:
            Formatted timestamp
        """
        if not timestamp:
            return datetime.utcnow().isoformat()
        
        return timestamp
    
    def export_from_database_records(
        self,
        db_records: List[Dict[str, Any]],
        filename: Optional[str] = None
    ) -> str:
        """
        Export database records directly to CSV.
        
        Args:
            db_records: List of database record dictionaries
            filename: Optional custom filename
            
        Returns:
            Path to exported file
        """
        return self.export_multiple(db_records, filename)


def export_benchmark(
    benchmark_data: Dict[str, Any],
    export_dir: Optional[str] = None,
    filename: Optional[str] = None
) -> str:
    """
    Convenience function to export a single benchmark.
    
    Args:
        benchmark_data: Benchmark result dictionary
        export_dir: Optional export directory
        filename: Optional filename
        
    Returns:
        Path to exported file
    """
    exporter = CSVExporter(export_dir)
    return exporter.export_single(benchmark_data, filename)


def export_benchmarks(
    benchmark_data_list: List[Dict[str, Any]],
    export_dir: Optional[str] = None,
    filename: Optional[str] = None
) -> str:
    """
    Convenience function to export multiple benchmarks.
    
    Args:
        benchmark_data_list: List of benchmark dictionaries
        export_dir: Optional export directory
        filename: Optional filename
        
    Returns:
        Path to exported file
    """
    exporter = CSVExporter(export_dir)
    return exporter.export_multiple(benchmark_data_list, filename)
