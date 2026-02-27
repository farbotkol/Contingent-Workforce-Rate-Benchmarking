# Contingent Workforce Rate Benchmarking Agent

A Python-based system for benchmarking technology contractor daily rates across Australia, Singapore, India, and the Philippines. The system normalizes roles, converts salaries to daily contractor rates (in local currency), generates percentile bands, detects market trends, and stores results in SQLite for historical tracking.

## Features

- **Role Normalization**: Maps external job titles to internal taxonomy with seniority classification
- **Multi-Country Support**: Australia, Singapore, India, Philippines
- **Salary Conversion**: Convert annual salaries to daily contractor rates using country-specific multipliers
- **Statistical Analysis**: Generate P25, Median, P75 rate bands with outlier removal
- **Market Mode Detection**: Detect Inflationary, Stable, or Contraction market conditions
- **Historical Tracking**: SQLite database for trend analysis
- **CSV Export**: Rate Card Matrix compatible CSV output
- **Docker Support**: Containerized deployment
- **Extensible**: Modular architecture for future enhancements

## Requirements

- Python 3.11+
- Dependencies listed in `requirements.txt`

## Installation

### Local Installation

```bash
# Clone the repository
git clone https://github.com/farbotkol/Contingent-Workforce-Rate-Benchmarking.git
cd Contingent-Workforce-Rate-Benchmarking

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Docker Installation

```bash
# Build the Docker image
docker build -t rate-benchmark .

# Run with Docker
docker run -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports rate-benchmark --help
```

## Usage

### Command Line Interface

#### Run a Benchmark

```bash
python main.py benchmark \
  --role "Senior Software Engineer" \
  --country Australia \
  --rates 800 --rates 850 --rates 900 \
  --salaries 120000 --salaries 130000
```

#### Normalize a Job Title

```bash
python main.py normalize "Senior Full Stack Developer"
```

#### Convert Salary to Daily Rate

```bash
python main.py convert --salary 120000 --country Australia
```

#### View Historical Benchmarks

```bash
python main.py history \
  --role "Software Engineer" \
  --level Senior \
  --country Australia \
  --limit 10
```

### Docker Usage

```bash
# Run benchmark with Docker
docker run -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports \
  rate-benchmark benchmark \
  --role "Senior DevOps Engineer" \
  --country Singapore \
  --rates 1000 --rates 1100 --rates 1200

# Normalize a title
docker run rate-benchmark normalize "Lead Data Scientist"

# Convert salary
docker run rate-benchmark convert --salary 100000 --country Singapore
```

## Project Structure

```
rate_benchmark/
├── config/                    # Configuration files
│   ├── multipliers.yaml      # Country-specific conversion multipliers
│   └── role_mapping.yaml     # Job title to role mappings
├── processing/               # Core processing modules
│   ├── normalization.py     # Role and seniority normalization
│   ├── conversion.py        # Salary to daily rate conversion
│   ├── statistics.py        # Percentile and outlier logic
│   └── market_mode.py       # Market trend detection
├── storage/                 # Data persistence
│   └── database.py          # SQLite operations
├── ingestion/               # Data collection (framework)
│   ├── salary_guides.py     # PDF salary guide extraction
│   └── job_boards.py        # Job board scraping framework
├── export/                  # Export functionality
│   └── csv_export.py        # CSV export for Rate Card Matrix
├── tests/                   # Unit tests
│   ├── test_normalization.py
│   ├── test_conversion.py
│   ├── test_statistics.py
│   └── test_market_mode.py
├── exports/                 # CSV output directory
├── main.py                  # CLI entry point
├── requirements.txt         # Python dependencies
├── Dockerfile              # Docker configuration
└── README.md               # This file
```

## Configuration

### Multipliers (config/multipliers.yaml)

Country-specific multipliers for converting annual salary to daily contractor rates:

- **Australia**: 1.35 (excludes 11% superannuation)
- **Singapore**: 1.30
- **India**: 1.25
- **Philippines**: 1.28

Formula: `daily_rate = (annual_salary × multiplier) / 220`

### Role Mapping (config/role_mapping.yaml)

Maps external job titles to canonical internal roles. Supports:
- Multiple external titles per canonical role
- Seniority keyword detection (Junior, Mid, Senior, Lead, Architect)
- Case-insensitive matching
- Partial title matching

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=processing --cov=storage --cov=export

# Run specific test file
pytest tests/test_normalization.py
```

## Output Format

### CSV Export

CSV files follow the Rate Card Matrix format:

```csv
Country,Role,Level,Currency,P25_Daily_Rate,Median_Daily_Rate,P75_Daily_Rate,Market_Mode,Source_Count,Timestamp
Australia,Software Engineer,Senior,AUD,750.00,850.00,950.00,Stable,10,2024-01-15T10:30:00
```

### Database Schema

SQLite database stores:
- Role, level, country
- P25, Median, P75 daily rates
- Market mode and confidence
- Source count and data points
- Timestamp and query parameters

## Market Mode Detection

The system detects three market modes:

- **Inflationary**: ≥15% job growth AND >5% rate growth
- **Contraction**: ≥15% job posting decline
- **Stable**: Otherwise

Confidence levels: High (30+ data points), Medium (10-29), Low (<10)

## Important Notes

- **Australian Rates**: Exclude 11% superannuation by default
- **Data Sources**: Framework supports public salary guides and job boards
- **Scraping Ethics**: Always respect robots.txt and legal boundaries
- **Rate Limiting**: Default 1-second delay between requests
- **Local Currency**: All outputs in local currency (AUD, SGD, INR, PHP)

## Future Enhancements

- City-level benchmarking
- Margin modeling
- Additional countries
- Real-time job board integration
- API endpoint for programmatic access
- Advanced market trend analytics

## License

This project is open source. Please ensure compliance with all data source terms of service and applicable laws when using scraping functionality.

## Contributing

Contributions welcome! Please ensure:
- Code follows existing style
- Tests pass (`pytest`)
- New features include tests
- Configuration-driven (no hardcoded values)
- Documentation updated

## Support

For issues or questions, please open an issue on GitHub.
