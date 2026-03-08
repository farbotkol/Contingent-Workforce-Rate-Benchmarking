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
            env_path = os.getenv("DATABASE_PATH")
            if env_path:
                db_path = env_path
            else:
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
                city TEXT,
                source TEXT NOT NULL DEFAULT 'unknown',
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
                statistics TEXT
            )
        ''')

        if self._benchmark_table_requires_rebuild(cursor):
            self._rebuild_benchmark_results_table(cursor)
        
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

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_city
            ON benchmark_results(city)
        ''')

        # Normalize legacy values to current conventions
        cursor.execute("UPDATE benchmark_results SET source = 'unknown' WHERE source IS NULL OR TRIM(source) = ''")
        cursor.execute("UPDATE benchmark_results SET timestamp = substr(timestamp, 1, 10) WHERE length(timestamp) > 10")

        # Enforce one benchmark per role/level/country/source per calendar date
        try:
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_daily_benchmark
                ON benchmark_results(role, level, country, IFNULL(city, ''), source, substr(timestamp, 1, 10))
            ''')
        except sqlite3.IntegrityError:
            self._delete_duplicate_daily_benchmarks(cursor)
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_daily_benchmark
                ON benchmark_results(role, level, country, IFNULL(city, ''), source, substr(timestamp, 1, 10))
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

        # Application settings table (e.g., active branding theme)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')

        current_ts = datetime.utcnow().isoformat()
        cursor.execute('''
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', ('branding', 'cxc', current_ts))
        
        self.conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    def _benchmark_table_requires_rebuild(self, cursor: sqlite3.Cursor) -> bool:
        """Return True if benchmark_results table needs schema migration/rebuild."""
        cursor.execute("PRAGMA table_info(benchmark_results)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'source' not in columns:
            return True
        if 'city' not in columns:
            return True

        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='benchmark_results'")
        row = cursor.fetchone()
        create_sql = (row[0] or "") if row else ""
        legacy_unique_clause = "UNIQUE(role, level, country, timestamp)"
        if legacy_unique_clause in create_sql:
            return True

        return False

    def _rebuild_benchmark_results_table(self, cursor: sqlite3.Cursor) -> None:
        """Rebuild benchmark_results table to include source and remove legacy unique constraint."""
        logger.info("Rebuilding benchmark_results table to apply source-aware daily uniqueness")

        cursor.execute("DROP TABLE IF EXISTS benchmark_results_legacy")
        cursor.execute("ALTER TABLE benchmark_results RENAME TO benchmark_results_legacy")

        cursor.execute('''
            CREATE TABLE benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                level TEXT NOT NULL,
                country TEXT NOT NULL,
                city TEXT,
                source TEXT NOT NULL DEFAULT 'unknown',
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
                statistics TEXT
            )
        ''')

        cursor.execute("PRAGMA table_info(benchmark_results_legacy)")
        legacy_columns = {row[1] for row in cursor.fetchall()}
        has_legacy_source = 'source' in legacy_columns
        has_legacy_city = 'city' in legacy_columns

        cursor.execute("SELECT * FROM benchmark_results_legacy ORDER BY id DESC")
        rows = cursor.fetchall()

        kept_rows = []
        seen_keys = set()
        duplicate_to_keep = {}

        for row in rows:
            row_dict = dict(row)
            source = row_dict.get('source') if has_legacy_source else None
            source = source.strip() if isinstance(source, str) else source
            if not source:
                source = 'unknown'

            timestamp = row_dict.get('timestamp')
            timestamp = str(timestamp) if timestamp is not None else ''
            date_key = timestamp[:10]

            dedupe_key = (
                row_dict.get('role'),
                row_dict.get('level'),
                row_dict.get('country'),
                (row_dict.get('city') or '').strip() if has_legacy_city and isinstance(row_dict.get('city'), str) else (row_dict.get('city') or ''),
                source,
                date_key,
            )

            if dedupe_key in seen_keys:
                existing_keep_id = duplicate_to_keep.get(dedupe_key)
                if existing_keep_id is not None:
                    duplicate_to_keep[row_dict['id']] = existing_keep_id
                continue

            seen_keys.add(dedupe_key)
            duplicate_to_keep[dedupe_key] = row_dict['id']

            row_dict['source'] = source
            if has_legacy_city:
                city = row_dict.get('city')
                row_dict['city'] = city.strip() if isinstance(city, str) else city
            else:
                row_dict['city'] = None
            row_dict['timestamp'] = date_key
            kept_rows.append(row_dict)

        for row_dict in kept_rows:
            cursor.execute('''
                INSERT INTO benchmark_results (
                    id,
                    role,
                    level,
                    country,
                    city,
                    source,
                    currency,
                    p25_daily_rate,
                    median_daily_rate,
                    p75_daily_rate,
                    market_mode,
                    confidence,
                    source_count,
                    data_points,
                    timestamp,
                    query_params,
                    statistics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                row_dict.get('id'),
                row_dict.get('role'),
                row_dict.get('level'),
                row_dict.get('country'),
                row_dict.get('city'),
                row_dict.get('source'),
                row_dict.get('currency'),
                row_dict.get('p25_daily_rate'),
                row_dict.get('median_daily_rate'),
                row_dict.get('p75_daily_rate'),
                row_dict.get('market_mode'),
                row_dict.get('confidence'),
                row_dict.get('source_count'),
                row_dict.get('data_points'),
                row_dict.get('timestamp'),
                row_dict.get('query_params'),
                row_dict.get('statistics'),
            ))

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_data_sources'")
        has_raw_sources_table = cursor.fetchone() is not None
        if has_raw_sources_table:
            for duplicate_id, keep_id in duplicate_to_keep.items():
                if isinstance(duplicate_id, int):
                    cursor.execute(
                        "UPDATE raw_data_sources SET benchmark_id = ? WHERE benchmark_id = ?",
                        (keep_id, duplicate_id),
                    )

        cursor.execute("DROP TABLE benchmark_results_legacy")
        logger.info(f"Benchmark table rebuild complete. Retained {len(kept_rows)} de-duplicated records.")

    def _delete_duplicate_daily_benchmarks(self, cursor: sqlite3.Cursor) -> None:
        """Delete duplicate benchmark rows for the same date/role/level/country/source, keeping newest."""
        cursor.execute("SELECT * FROM benchmark_results ORDER BY id DESC")
        rows = cursor.fetchall()

        seen_keys = set()
        duplicate_to_keep = {}

        for row in rows:
            row_dict = dict(row)
            source = row_dict.get('source')
            source = source.strip() if isinstance(source, str) else source
            if not source:
                source = 'unknown'

            timestamp = row_dict.get('timestamp')
            timestamp = str(timestamp) if timestamp is not None else ''
            date_key = timestamp[:10]

            dedupe_key = (
                row_dict.get('role'),
                row_dict.get('level'),
                row_dict.get('country'),
                (row_dict.get('city') or '').strip() if isinstance(row_dict.get('city'), str) else (row_dict.get('city') or ''),
                source,
                date_key,
            )

            if dedupe_key in seen_keys:
                duplicate_to_keep[row_dict['id']] = duplicate_to_keep[dedupe_key]
                continue

            seen_keys.add(dedupe_key)
            duplicate_to_keep[dedupe_key] = row_dict['id']

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_data_sources'")
        has_raw_sources_table = cursor.fetchone() is not None

        for duplicate_id, keep_id in duplicate_to_keep.items():
            if not isinstance(duplicate_id, int):
                continue
            if has_raw_sources_table:
                cursor.execute(
                    "UPDATE raw_data_sources SET benchmark_id = ? WHERE benchmark_id = ?",
                    (keep_id, duplicate_id),
                )
            cursor.execute("DELETE FROM benchmark_results WHERE id = ?", (duplicate_id,))

        duplicate_count = len([key for key in duplicate_to_keep.keys() if isinstance(key, int)])
        if duplicate_count:
            logger.info(f"Deleted {duplicate_count} duplicate benchmark rows during startup cleanup")
    
    def store_benchmark(
        self,
        role: str,
        level: str,
        country: str,
        city: Optional[str],
        source: str,
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
            city: City name (optional)
            source: Benchmark source label (e.g., cli, web_single, web_bulk, web_upload)
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
        timestamp = datetime.utcnow().date().isoformat()
        normalized_city = (city or '').strip()
        
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT id FROM benchmark_results
                                                WHERE role = ? AND level = ? AND country = ?
                            AND IFNULL(city, '') = ?
                            AND source = ?
              AND substr(timestamp, 1, 10) = ?
            ORDER BY id DESC
            LIMIT 1
                                ''', (role, level, country, normalized_city, source, timestamp))

        existing_row = cursor.fetchone()
        serialized_query_params = json.dumps(query_params) if query_params else None
        serialized_statistics = json.dumps(statistics) if statistics else None

        if existing_row:
            record_id = existing_row['id']
            cursor.execute('''
                UPDATE benchmark_results
                SET source = ?,
                    city = ?,
                    currency = ?,
                    p25_daily_rate = ?,
                    median_daily_rate = ?,
                    p75_daily_rate = ?,
                    market_mode = ?,
                    confidence = ?,
                    source_count = ?,
                    data_points = ?,
                    timestamp = ?,
                    query_params = ?,
                    statistics = ?
                WHERE id = ?
            ''', (
                source,
                normalized_city or None,
                currency,
                p25, median, p75,
                market_mode, confidence, source_count, data_points,
                timestamp,
                serialized_query_params,
                serialized_statistics,
                record_id
            ))
            self.conn.commit()
            logger.info(f"Updated existing daily benchmark with ID {record_id}")
            return record_id

        cursor.execute('''
            INSERT INTO benchmark_results (
                role, level, country, city, source, currency,
                p25_daily_rate, median_daily_rate, p75_daily_rate,
                market_mode, confidence, source_count, data_points,
                timestamp, query_params, statistics
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            role, level, country, normalized_city or None, source, currency,
            p25, median, p75,
            market_mode, confidence, source_count, data_points,
            timestamp,
            serialized_query_params,
            serialized_statistics
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

    def get_all_benchmarks(
        self,
        page: int = 1,
        page_size: int = 25,
        role_query: Optional[str] = None,
        level: Optional[str] = None,
        country: Optional[str] = None,
        city: Optional[str] = None,
        source: Optional[str] = None,
        sort_by: str = "timestamp",
        sort_dir: str = "desc",
    ) -> Dict[str, Any]:
        """
        Get paginated benchmark results with optional filters.

        Args:
            page: 1-based page index
            page_size: Number of rows per page
            role_query: Optional case-insensitive role contains filter
            level: Optional exact seniority level filter
            country: Optional exact country filter
            city: Optional exact city filter
            source: Optional exact source filter
            sort_by: Sort column key
            sort_dir: Sort direction (asc|desc)

        Returns:
            Dictionary with pagination metadata and records
        """
        safe_page = max(1, int(page))
        safe_page_size = max(1, min(200, int(page_size)))

        where_clauses = []
        params: List[Any] = []

        if role_query:
            where_clauses.append("LOWER(role) LIKE ?")
            params.append(f"%{role_query.lower()}%")
        if level:
            where_clauses.append("level = ?")
            params.append(level)
        if country:
            where_clauses.append("country = ?")
            params.append(country)
        if city:
            where_clauses.append("city = ?")
            params.append(city)
        if source:
            where_clauses.append("source = ?")
            params.append(source)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        offset = (safe_page - 1) * safe_page_size

        sortable_columns = {
            "timestamp": "timestamp",
            "role": "role",
            "level": "level",
            "country": "country",
            "city": "city",
            "source": "source",
            "currency": "currency",
            "median": "median_daily_rate",
            "market_mode": "market_mode",
            "data_points": "data_points",
        }
        order_column = sortable_columns.get((sort_by or "").strip().lower(), "timestamp")
        order_direction = "ASC" if (sort_dir or "").strip().lower() == "asc" else "DESC"

        cursor = self.conn.cursor()
        cursor.execute(
            f'''
            SELECT COUNT(*) AS total_count
            FROM benchmark_results
            {where_sql}
            ''',
            params,
        )
        total_count = int(cursor.fetchone()["total_count"])

        cursor.execute(
            f'''
            SELECT *
            FROM benchmark_results
            {where_sql}
            ORDER BY {order_column} {order_direction}, id DESC
            LIMIT ? OFFSET ?
            ''',
            [*params, safe_page_size, offset],
        )
        records = [dict(row) for row in cursor.fetchall()]

        total_pages = max(1, (total_count + safe_page_size - 1) // safe_page_size)

        return {
            "records": records,
            "total_count": total_count,
            "page": min(safe_page, total_pages),
            "page_size": safe_page_size,
            "total_pages": total_pages,
        }

    def get_benchmark_filter_options(self) -> Dict[str, List[str]]:
        """Get distinct values for benchmark filters."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT DISTINCT level FROM benchmark_results WHERE level IS NOT NULL AND TRIM(level) <> '' ORDER BY level")
        levels = [row["level"] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT country FROM benchmark_results WHERE country IS NOT NULL AND TRIM(country) <> '' ORDER BY country")
        countries = [row["country"] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT source FROM benchmark_results WHERE source IS NOT NULL AND TRIM(source) <> '' ORDER BY source")
        sources = [row["source"] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT city FROM benchmark_results WHERE city IS NOT NULL AND TRIM(city) <> '' ORDER BY city")
        cities = [row["city"] for row in cursor.fetchall()]

        return {
            "levels": levels,
            "countries": countries,
            "cities": cities,
            "sources": sources,
        }

    def get_all_benchmark_records(self) -> List[Dict[str, Any]]:
        """
        Get all benchmark rows for analytics/reporting use cases.

        Returns:
            List of benchmark result dictionaries ordered by latest first
        """
        cursor = self.conn.cursor()
        cursor.execute(
            '''
            SELECT *
            FROM benchmark_results
            ORDER BY timestamp DESC, id DESC
            '''
        )
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

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get application setting value by key."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT value FROM app_settings WHERE key = ?', (key,))
        row = cursor.fetchone()
        if row:
            return row['value']
        return default

    def set_setting(self, key: str, value: str) -> None:
        """Set application setting value by key."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        ''', (key, value, datetime.utcnow().isoformat()))
        self.conn.commit()
    
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
