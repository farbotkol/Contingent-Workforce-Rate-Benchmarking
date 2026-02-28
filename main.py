#!/usr/bin/env python3
"""
Main CLI Interface for Contingent Workforce Rate Benchmarking Agent

EPIC 9 - CLI Interface
"""

import click
import logging
import sys
from typing import Optional
from datetime import datetime

from processing.normalization import RoleNormalizer
from processing.conversion import SalaryConverter
from processing.statistics import RateBandCalculator
from processing.market_mode import MarketModeDetector
from storage.database import BenchmarkDatabase
from export.csv_export import CSVExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.group()
@click.version_option(version='1.0.0')
def cli():
    """Contingent Workforce Rate Benchmarking Agent
    
    Benchmark technology contractor daily rates across multiple markets.
    """
    pass


@cli.command()
@click.option('--role', required=True, help='Job role/title (e.g., "Senior Software Engineer")')
@click.option('--level', help='Seniority level override (Junior/Mid/Senior/Lead/Architect)')
@click.option('--country', required=True, help='Country (Australia/Singapore/India/Philippines)')
@click.option('--rates', multiple=True, type=float, help='Daily rates to analyze (can be specified multiple times)')
@click.option('--salaries', multiple=True, type=float, help='Annual salaries to convert (can be specified multiple times)')
@click.option('--output', help='Custom output filename for CSV export')
@click.option('--no-export', is_flag=True, help='Skip CSV export')
@click.option('--db-path', help='Custom database path')
def benchmark(
    role: str,
    level: Optional[str],
    country: str,
    rates: tuple,
    salaries: tuple,
    output: Optional[str],
    no_export: bool,
    db_path: Optional[str]
):
    """Run a benchmark analysis for a specific role and country.
    
    Example:
        python main.py benchmark --role "Senior Software Engineer" --country Australia \\
            --rates 800 --rates 850 --rates 900 --salaries 120000 --salaries 130000
    """
    logger.info("=" * 60)
    logger.info("Starting Benchmark Analysis")
    logger.info("=" * 60)
    
    try:
        # Initialize components
        normalizer = RoleNormalizer()
        converter = SalaryConverter()
        calculator = RateBandCalculator()
        detector = MarketModeDetector()
        db = BenchmarkDatabase(db_path)
        
        # Normalize role
        normalized = normalizer.normalize(role, level)
        canonical_role = normalized['canonical_role']
        seniority_level = normalized['seniority_level']
        
        if canonical_role == "Unmapped Role":
            logger.warning(f"Could not map role '{role}' to internal taxonomy")
            click.echo(f"⚠️  Warning: Unmapped role '{role}'", err=True)
        
        logger.info(f"Normalized: '{role}' → '{canonical_role}' ({seniority_level})")
        
        # Collect all daily rates
        daily_rates = list(rates)
        
        # Convert salaries to daily rates
        if salaries:
            logger.info(f"Converting {len(salaries)} salaries to daily rates...")
            for salary in salaries:
                result = converter.annual_to_daily(salary, country)
                daily_rates.append(result['daily_rate'])
                logger.info(f"  {salary:,.0f} → {result['daily_rate']:.2f} {result['currency']}/day")
        
        if not daily_rates:
            click.echo("❌ Error: No rates or salaries provided. Use --rates or --salaries.", err=True)
            sys.exit(1)
        
        logger.info(f"Total data points: {len(daily_rates)}")
        
        # Calculate rate bands
        currency = converter.get_currency(country)
        rate_bands = calculator.generate_rate_bands(
            daily_rates,
            currency,
            country,
            canonical_role,
            seniority_level
        )
        
        # Get historical data for market mode detection
        historical = db.get_latest_benchmark(canonical_role, country, seniority_level)
        
        historical_median = historical['median_daily_rate'] if historical else None
        historical_count = historical['data_points'] if historical else None
        
        # Detect market mode
        market_result = detector.detect_mode(
            rate_bands['median_daily_rate'],
            historical_median,
            len(daily_rates),
            historical_count,
            len(daily_rates)
        )
        
        # Display results
        click.echo("\n" + "=" * 60)
        click.echo("📊 BENCHMARK RESULTS")
        click.echo("=" * 60)
        click.echo(f"Role:     {canonical_role}")
        click.echo(f"Level:    {seniority_level}")
        click.echo(f"Country:  {country}")
        click.echo(f"Currency: {currency}")
        click.echo(f"\n💰 Daily Rate Bands:")
        click.echo(f"  P25:    {rate_bands['p25_daily_rate']:>10.2f} {currency}")
        click.echo(f"  Median: {rate_bands['median_daily_rate']:>10.2f} {currency}")
        click.echo(f"  P75:    {rate_bands['p75_daily_rate']:>10.2f} {currency}")
        click.echo(f"\n📈 Market Mode: {market_result['market_mode']}")
        click.echo(f"   Confidence:  {rate_bands['confidence']}")
        click.echo(f"   Data Points: {rate_bands['data_points']}")
        
        if market_result['rate_growth_pct'] is not None:
            click.echo(f"   Rate Growth: {market_result['rate_growth_pct']:+.1f}%")
        
        click.echo("=" * 60 + "\n")
        
        # Store in database
        benchmark_id = db.store_benchmark(
            role=canonical_role,
            level=seniority_level,
            country=country,
            source='AI',
            currency=currency,
            p25=rate_bands['p25_daily_rate'],
            median=rate_bands['median_daily_rate'],
            p75=rate_bands['p75_daily_rate'],
            market_mode=market_result['market_mode'],
            confidence=rate_bands['confidence'],
            source_count=1,  # CLI input
            data_points=len(daily_rates),
            statistics=rate_bands.get('statistics')
        )
        
        logger.info(f"Stored benchmark in database (ID: {benchmark_id})")
        
        # Export to CSV
        if not no_export:
            exporter = CSVExporter()
            export_data = {
                'role': canonical_role,
                'level': seniority_level,
                'country': country,
                'currency': currency,
                'p25_daily_rate': rate_bands['p25_daily_rate'],
                'median_daily_rate': rate_bands['median_daily_rate'],
                'p75_daily_rate': rate_bands['p75_daily_rate'],
                'market_mode': market_result['market_mode'],
                'source_count': 1,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            filepath = exporter.export_single(export_data, output)
            click.echo(f"✅ Exported to: {filepath}\n")
        
        db.close()
        
    except Exception as e:
        logger.error(f"Benchmark failed: {str(e)}", exc_info=True)
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--role', required=True, help='Job role')
@click.option('--level', required=True, help='Seniority level')
@click.option('--country', required=True, help='Country')
@click.option('--limit', default=10, help='Number of historical records to show')
@click.option('--db-path', help='Custom database path')
def history(role: str, level: str, country: str, limit: int, db_path: Optional[str]):
    """View historical benchmark data for a role/country/level."""
    try:
        db = BenchmarkDatabase(db_path)
        normalizer = RoleNormalizer()
        
        # Normalize role
        normalized = normalizer.map_title(role)
        
        records = db.get_historical_benchmarks(normalized, country, level, limit)
        
        if not records:
            click.echo(f"No historical data found for {normalized}/{level}/{country}")
            return
        
        click.echo("\n" + "=" * 80)
        click.echo(f"📜 HISTORICAL BENCHMARKS: {normalized} ({level}) in {country}")
        click.echo("=" * 80)
        
        for i, record in enumerate(records, 1):
            click.echo(f"\n{i}. {record['timestamp'][:10]}")
            click.echo(f"   Median: {record['median_daily_rate']:.2f} {record['currency']}")
            click.echo(f"   Range:  {record['p25_daily_rate']:.2f} - {record['p75_daily_rate']:.2f}")
            click.echo(f"   Market: {record['market_mode']} (Confidence: {record['confidence']})")
            click.echo(f"   Data:   {record['data_points']} points")
        
        click.echo("\n" + "=" * 80 + "\n")
        
        db.close()
        
    except Exception as e:
        logger.error(f"History lookup failed: {str(e)}")
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('title')
def normalize(title: str):
    """Normalize a job title to canonical role and seniority level.
    
    Example:
        python main.py normalize "Senior Full Stack Developer"
    """
    try:
        normalizer = RoleNormalizer()
        result = normalizer.normalize(title)
        
        click.echo("\n" + "=" * 60)
        click.echo("🏷️  ROLE NORMALIZATION")
        click.echo("=" * 60)
        click.echo(f"Input:      {title}")
        click.echo(f"Role:       {result['canonical_role']}")
        click.echo(f"Level:      {result['seniority_level']}")
        click.echo(f"Confidence: {result['confidence']:.1%}")
        click.echo("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"Normalization failed: {str(e)}")
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.option('--salary', required=True, type=float, help='Annual salary')
@click.option('--country', required=True, help='Country')
def convert(salary: float, country: str):
    """Convert annual salary to daily contractor rate.
    
    Example:
        python main.py convert --salary 120000 --country Australia
    """
    try:
        converter = SalaryConverter()
        result = converter.annual_to_daily(salary, country)
        
        click.echo("\n" + "=" * 60)
        click.echo("💱 SALARY CONVERSION")
        click.echo("=" * 60)
        click.echo(f"Annual Salary: {salary:>15,.2f}")
        click.echo(f"Country:       {country:>15}")
        click.echo(f"Multiplier:    {result['multiplier_used']:>15.2f}")
        click.echo(f"Working Days:  {result['working_days']:>15}")
        click.echo(f"\nDaily Rate:    {result['daily_rate']:>15.2f} {result['currency']}")
        click.echo(f"Rate Type:     {result['rate_type']:>15}")
        
        if result.get('superannuation_excluded'):
            click.echo(f"\n⚠️  Note: Australian superannuation excluded")
        
        click.echo("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"Conversion failed: {str(e)}")
        click.echo(f"❌ Error: {str(e)}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()
