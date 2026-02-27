"""
Database Storage Module

Handles SQLite storage for benchmark results and historical tracking.
EPIC 6 - Historical Storage & Trend Tracking
"""

import sqlite3
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class BenchmarkDatabase:
    """SQLite database for storing benchmark results and historical trends."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'benchmark_data.db'
            )
        
        self.db_path = db_path
        self.conn = None
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # Enable column access by name
        
        cursor = self.conn.cursor()
        
        # Main benchmark results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                level TEXT NOT NULL,
                country TEXT NOT NULL,
                currency TEXT NOT NULL,
                p25_daily_rate REAL,
                median_daily_rate REAL,
                p75_daily_rate REAL,
                market_mode TEXT,
                confidence TEXT,
                source_count INTEGER,
                data_points INTEGER,
                timestamp TEXT NOT NULL,
                query_params TEXT,
                statistics TEXT,
                UNIQUE(role, level, country, timestamp)
            )
        ''')
        
        # Create indexes for efficient querying
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_role_country_level 
            ON benchmark_results(role, country, level)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON benchmark_results(timestamp)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_country 
            ON benchmark_results(country)
        ''')
        
        # Raw data sources table (for tracking individual data points)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_data_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                benchmark_id INTEGER,
                source_name TEXT,
                source_type TEXT,
                daily_rate REAL,
                rate_type TEXT,
                job_title TEXT,
                extraction_timestamp TEXT,
                metadata TEXT,
                FOREIGN KEY (benchmark_id) REFERENCES benchmark_results(id)
            )
        ''')
        
        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")
    
    def store_benchmark(
        self,
        role: str,
        level: str,
        country: str,
        currency: str,
        p25: Optional[float],
        median: Optional[float],
        p75: Optional[float],
        market_mode: str,
        confidence: str,
        source_count: int,
        data_points: int,
        query_params: Optional[Dict] = None,
        statistics: Optional[Dict] = None
    ) -> int:
        """
        Store a benchmark result in the database.
        
        Args:
            role: Canonical role name
            level: Seniority level
            country: Country name
            currency: Currency code
            p25: 25th percentile daily rate
            median: Median daily rate
            p75: 75th percentile daily rate
            market_mode: Market mode (Inflationary/Stable/Contraction)
            confidence: Confidence level (High/Medium/Low)
            source_count: Number of sources used
            data_points: Number of data points
            query_params: Optional query parameters
            statistics: Optional additional statistics
            
        Returns:
            ID of the inserted record
        """
        timestamp = datetime.utcnow().isoformat()
        
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO benchmark_results (
                role, level, country, currency,
                p25_daily_rate, median_daily_rate, p75_daily_rate,
                market_mode, confidence, source_count, data_points,
                timestamp, query_params, statistics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            role, level, country, currency,
            p25, median, p75,
            market_mode, confidence, source_count, data_points,
            timestamp,
            json.dumps(query_params) if query_params else None,
            json.dumps(statistics) if statistics else None
        ))
        
        self.conn.commit()
        record_id = cursor.lastrowid
        logger.info(f"Stored benchmark result with ID {record_id}")
        return record_id
    
    def get_latest_benchmark(
        self,
        role: str,
        country: str,
        level: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent benchmark for a role/country/level.
        
        Args:
            role: Canonical role name
            country: Country name
            level: Seniority level
            
        Returns:
            Benchmark result dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM benchmark_results
            WHERE role = ? AND country = ? AND level = ?
            ORDER BY timestamp DESC
            LIMIT 1
        ''', (role, country, level))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def get_historical_benchmarks(
        self,
        role: str,
        country: str,
        level: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get historical benchmarks for trend analysis.
        
        Args:
            role: Canonical role name
            country: Country name
            level: Seniority level
            limit: Maximum number of records to return
            
        Returns:
            List of benchmark result dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM benchmark_results
            WHERE role = ? AND country = ? AND level = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (role, country, level, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_benchmark_by_country(
        self,
        country: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get all recent benchmarks for a country.
        
        Args:
            country: Country name
            limit: Maximum number of records
            
        Returns:
            List of benchmark results
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM benchmark_results
            WHERE country = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (country, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def compare_with_historical(
        self,
        role: str,
        country: str,
        level: str
    ) -> Optional[Dict[str, Any]]:
        """
        Compare latest benchmark with previous period.
        
        Args:
            role: Canonical role name
            country: Country name
            level: Seniority level
            
        Returns:
            Comparison dictionary with current and previous values
        """
        benchmarks = self.get_historical_benchmarks(role, country, level, limit=2)
        
        if len(benchmarks) < 2:
            return None
        
        current = benchmarks[0]
        previous = benchmarks[1]
        
        return {
            'current': current,
            'previous': previous,
            'median_change': current['median_daily_rate'] - previous['median_daily_rate'],
            'median_change_pct': (
                ((current['median_daily_rate'] - previous['median_daily_rate']) / 
                 previous['median_daily_rate'] * 100)
                if previous['median_daily_rate'] > 0 else None
            ),
            'data_points_change': current['data_points'] - previous['data_points']
        }
    
    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def get_database(db_path: Optional[str] = None) -> BenchmarkDatabase:
    """
    Factory function to get a database instance.
    
    Args:
        db_path: Optional path to database file
        
    Returns:
        BenchmarkDatabase instance
    """
    return BenchmarkDatabase(db_path)
