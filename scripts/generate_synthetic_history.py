#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import os
import random
import sys
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage.database import BenchmarkDatabase


LEVELS = ["Junior", "Mid", "Senior", "Lead", "Architect"]
MAJOR_CITIES_BY_COUNTRY: Dict[str, List[str]] = {
    "Australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"],
    "Singapore": ["Singapore"],
    "India": ["Bengaluru", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai"],
    "Philippines": ["Metro Manila", "Cebu", "Davao", "Clark", "Iloilo"],
}


def subtract_months(d: date, months: int) -> date:
    year = d.year
    month = d.month - months
    while month <= 0:
        month += 12
        year -= 1
    return date(year, month, 1)


def month_starts(month_count: int) -> List[date]:
    current_month_start = date.today().replace(day=1)
    return [subtract_months(current_month_start, i) for i in reversed(range(month_count))]


def month_key(d: date) -> str:
    return d.isoformat()


def combo_key(role: str, level: str, country: str, city: str) -> str:
    return f"{role}|{level}|{country}|{city}"


def confidence_from_points(data_points: int) -> str:
    if data_points >= 30:
        return "High"
    if data_points >= 10:
        return "Medium"
    return "Low"


def classify_role_seek(raw_role: str) -> Tuple[str, str]:
    role = (raw_role or "").lower()
    if any(token in role for token in ["data", "ai", "ml", "analytics", "bi", "scientist"]):
        return "Information & Communication Technology", "Data & AI"
    if any(token in role for token in ["devops", "platform", "cloud", "infrastructure", "sre"]):
        return "Information & Communication Technology", "DevOps & Infrastructure"
    if any(token in role for token in ["security", "cyber", "infosec", "iam"]):
        return "Information & Communication Technology", "Security"
    if any(token in role for token in ["architect", "principal engineer", "engineering manager", "head of engineering"]):
        return "Information & Communication Technology", "Architecture & Leadership"
    if any(token in role for token in ["developer", "engineer", "programmer", "full stack", "backend", "frontend", "software"]):
        return "Information & Communication Technology", "Software Engineering"
    if any(token in role for token in ["salesforce", "crm", "mulesoft", "certinia"]):
        return "Information & Communication Technology", "Enterprise Applications"
    if any(token in role for token in ["payroll", "workforce", "hris", "hcm"]):
        return "Human Resources & Recruitment", "Payroll & Workforce Operations"
    if any(token in role for token in ["project", "program", "scrum", "delivery"]):
        return "Information & Communication Technology", "Project Management"
    if any(token in role for token in ["support", "service desk", "helpdesk", "desktop"]):
        return "Information & Communication Technology", "Help Desk & IT Support"
    if any(token in role for token in ["qa", "test", "automation tester"]):
        return "Information & Communication Technology", "Testing & QA"
    return "Information & Communication Technology", "Other"


def load_canonical_roles() -> List[str]:
    mapping_path = os.path.join(PROJECT_ROOT, "config", "role_mapping.yaml")
    if not os.path.exists(mapping_path):
        return []

    with open(mapping_path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    roles = payload.get("canonical_roles") or []
    return [str(role).strip() for role in roles if str(role).strip()]


def load_country_currency_map() -> Dict[str, str]:
    multipliers_path = os.path.join(PROJECT_ROOT, "config", "multipliers.yaml")
    if not os.path.exists(multipliers_path):
        return {}

    with open(multipliers_path, "r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    currencies = payload.get("currencies") or {}
    return {str(country): str(currency) for country, currency in currencies.items()}


def fetch_seed_rows(db: BenchmarkDatabase) -> List[dict]:
    cursor = db.conn.cursor()
    cursor.execute(
        '''
        WITH ranked AS (
            SELECT
                id,
                role,
                level,
                country,
                IFNULL(city, '') AS city,
                currency,
                median_daily_rate,
                p25_daily_rate,
                p75_daily_rate,
                data_points,
                timestamp,
                ROW_NUMBER() OVER (
                    PARTITION BY role, level, country, IFNULL(city, '')
                    ORDER BY timestamp DESC, id DESC
                ) AS rn
            FROM benchmark_results
            WHERE median_daily_rate IS NOT NULL
        )
        SELECT
            id,
            role,
            level,
            country,
            city,
            currency,
            median_daily_rate,
            p25_daily_rate,
            p75_daily_rate,
            data_points,
            timestamp
        FROM ranked
        WHERE rn = 1
        '''
    )
    return [dict(row) for row in cursor.fetchall()]


def fetch_observed_history(db: BenchmarkDatabase) -> Dict[str, Dict[str, dict]]:
    cursor = db.conn.cursor()
    cursor.execute(
        '''
        SELECT
            role,
            level,
            country,
            IFNULL(city, '') AS city,
            substr(timestamp, 1, 7) || '-01' AS month_start,
            AVG(median_daily_rate) AS median_daily_rate,
            AVG(data_points) AS data_points
        FROM benchmark_results
        WHERE median_daily_rate IS NOT NULL
          AND source <> 'Synthetic'
          AND timestamp IS NOT NULL
        GROUP BY role, level, country, IFNULL(city, ''), month_start
        '''
    )

    history: Dict[str, Dict[str, dict]] = {}
    for row in cursor.fetchall():
        item = dict(row)
        key = combo_key(item["role"], item["level"], item["country"], item["city"])
        history.setdefault(key, {})[item["month_start"]] = {
            "median": float(item["median_daily_rate"]),
            "data_points": int(round(item.get("data_points") or 0)),
        }
    return history


def fetch_existing_months(
    db: BenchmarkDatabase,
    start_month: str,
    end_month: str,
) -> Dict[str, Set[str]]:
    cursor = db.conn.cursor()
    cursor.execute(
        '''
        SELECT
            role,
            level,
            country,
            IFNULL(city, '') AS city,
            substr(timestamp, 1, 7) || '-01' AS month_start
        FROM benchmark_results
        WHERE timestamp >= ?
          AND timestamp <= ?
          AND median_daily_rate IS NOT NULL
        GROUP BY role, level, country, IFNULL(city, ''), month_start
        ''',
        (start_month, end_month),
    )

    existing: Dict[str, Set[str]] = {}
    for row in cursor.fetchall():
        item = dict(row)
        key = combo_key(item["role"], item["level"], item["country"], item["city"])
        existing.setdefault(key, set()).add(item["month_start"])
    return existing


def inferred_monthly_growth(observed_values: List[float], months_span: int) -> Optional[float]:
    if len(observed_values) < 2 or months_span <= 0:
        return None

    start = observed_values[0]
    end = observed_values[-1]
    if start <= 0 or end <= 0:
        return None

    return (end / start) ** (1 / months_span) - 1


def macro_monthly_growth(target_month: date) -> float:
    year = target_month.year

    if year <= 2018:
        return 0.0020
    if year == 2019:
        return 0.0028
    if year == 2020:
        return -0.0015
    if year == 2021:
        return 0.0075
    if year == 2022:
        return 0.0060
    if year == 2023:
        return 0.0035
    if year == 2024:
        return 0.0028
    return 0.0025


def synthesize_seed(role: str, level: str, country: str, city: str, currency: str) -> dict:
    family, function = classify_role_seek(role)
    role_seed = f"{role}|{level}|{country}|{city}"
    rng = random.Random(int(hashlib.sha256(role_seed.encode("utf-8")).hexdigest()[:16], 16))

    country_base = {
        "Australia": 860.0,
        "Singapore": 700.0,
        "India": 360.0,
        "Philippines": 300.0,
    }
    level_factor = {
        "Junior": 0.72,
        "Mid": 1.00,
        "Senior": 1.28,
        "Lead": 1.48,
        "Architect": 1.68,
    }
    function_factor = {
        "Data & AI": 1.10,
        "DevOps & Infrastructure": 1.08,
        "Security": 1.12,
        "Architecture & Leadership": 1.15,
        "Software Engineering": 1.00,
        "Enterprise Applications": 1.05,
        "Payroll & Workforce Operations": 0.97,
        "Project Management": 0.96,
        "Help Desk & IT Support": 0.82,
        "Testing & QA": 0.90,
        "Other": 0.95,
    }
    city_factor = {
        "Sydney": 1.06,
        "Melbourne": 1.04,
        "Singapore": 1.00,
        "Bengaluru": 1.03,
        "Mumbai": 1.02,
        "Metro Manila": 1.02,
    }

    baseline = country_base.get(country, 650.0)
    baseline *= level_factor.get(level, 1.0)
    baseline *= function_factor.get(function, 1.0)
    baseline *= city_factor.get(city, 1.0)
    baseline *= (1 + rng.uniform(-0.06, 0.06))

    return {
        "id": -1,
        "role": role,
        "level": level,
        "country": country,
        "city": city,
        "currency": currency,
        "median_daily_rate": round(max(50.0, baseline), 2),
        "p25_daily_rate": round(max(40.0, baseline * 0.88), 2),
        "p75_daily_rate": round(max(55.0, baseline * 1.15), 2),
        "data_points": rng.randint(10, 24),
    }


def build_complete_seeds(db: BenchmarkDatabase) -> List[dict]:
    existing_seeds = fetch_seed_rows(db)
    currencies = load_country_currency_map()
    roles = load_canonical_roles()

    existing_by_key = {
        combo_key(seed["role"], seed["level"], seed["country"], seed.get("city") or ""): seed
        for seed in existing_seeds
    }

    countries = list(currencies.keys()) if currencies else sorted({seed["country"] for seed in existing_seeds})
    if not countries:
        countries = ["Australia", "Singapore", "India", "Philippines"]

    if not roles:
        roles = sorted({seed["role"] for seed in existing_seeds})

    completed = list(existing_seeds)

    for country in countries:
        country_currency = currencies.get(country, next(iter(currencies.values()), "AUD"))
        cities = MAJOR_CITIES_BY_COUNTRY.get(country, [""])
        for city in cities:
            for role in roles:
                for level in LEVELS:
                    key = combo_key(role, level, country, city)
                    if key in existing_by_key:
                        continue
                    synthetic_seed = synthesize_seed(role, level, country, city, country_currency)
                    completed.append(synthetic_seed)
                    existing_by_key[key] = synthetic_seed

    return completed


def generate_for_seed(
    seed: dict,
    months: List[date],
    observed_history: Optional[Dict[str, dict]] = None,
    existing_months: Optional[Set[str]] = None,
) -> List[Tuple]:
    role = seed["role"]
    level = seed["level"]
    country = seed["country"]
    city = (seed.get("city") or "").strip()
    currency = seed["currency"]
    base_median = float(seed["median_daily_rate"])
    base_points = int(seed.get("data_points") or 12)

    family, function = classify_role_seek(role)

    seed_key = combo_key(role, level, country, city)
    seed_int = int(hashlib.sha256(seed_key.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(seed_int)

    annual_trend = rng.uniform(-0.01, 0.07)
    season_phase = rng.uniform(0, math.pi * 2)

    observed_history = observed_history or {}
    existing_months = existing_months or set()
    month_index = {month_key(m): i for i, m in enumerate(months)}

    observed_points: List[Tuple[int, float]] = []
    for month_str, values in observed_history.items():
        idx = month_index.get(month_str)
        if idx is None:
            continue
        observed_points.append((idx, float(values["median"])))

    observed_points.sort(key=lambda x: x[0])
    observed_values = [value for _, value in observed_points]
    observed_span = observed_points[-1][0] - observed_points[0][0] if len(observed_points) >= 2 else 0

    inferred_growth = inferred_monthly_growth(observed_values, observed_span)
    role_monthly_growth = inferred_growth if inferred_growth is not None else (annual_trend / 12.0)

    medians: List[Optional[float]] = [None] * len(months)
    medians[-1] = max(50.0, base_median)

    for idx in reversed(range(len(months) - 1)):
        month = months[idx]
        m_key = month_key(month)

        if m_key in observed_history:
            medians[idx] = max(50.0, float(observed_history[m_key]["median"]))
            continue

        next_median = medians[idx + 1]
        if next_median is None:
            next_median = medians[-1]

        seasonal_now = 0.012 * math.sin((2 * math.pi * ((idx % 12) / 12.0)) + season_phase)
        seasonal_next = 0.012 * math.sin((2 * math.pi * (((idx + 1) % 12) / 12.0)) + season_phase)
        seasonal_delta = seasonal_next - seasonal_now

        growth = macro_monthly_growth(month) + role_monthly_growth + seasonal_delta + rng.gauss(0, 0.004)
        growth = min(0.05, max(-0.05, growth))

        denominator = 1 + growth
        if denominator <= 0.2:
            denominator = 0.2

        medians[idx] = max(50.0, next_median / denominator)

    rows: List[Tuple] = []
    previous_median = None

    for index, month in enumerate(months):
        m_key = month_key(month)
        if m_key in existing_months:
            observed = observed_history.get(m_key)
            previous_median = float(observed["median"]) if observed else previous_median
            continue

        median = float(medians[index] if medians[index] is not None else base_median)
        median *= (1 + rng.gauss(0, 0.002))
        median = max(50.0, median)

        if previous_median is None:
            growth_pct = 0.0
        else:
            growth_pct = ((median - previous_median) / previous_median) * 100 if previous_median > 0 else 0

        if growth_pct > 0.9:
            market_mode = "Inflationary"
        elif growth_pct < -0.9:
            market_mode = "Contraction"
        else:
            market_mode = "Stable"

        spread_bias = 0.0 if market_mode == "Stable" else 0.01
        lower_spread = rng.uniform(0.09, 0.14) + spread_bias
        upper_spread = rng.uniform(0.10, 0.17) + spread_bias
        p25 = max(40.0, median * (1 - lower_spread))
        p75 = max(median + 1, median * (1 + upper_spread))

        observed = observed_history.get(m_key)
        if observed and observed.get("data_points", 0) > 0:
            points = int(observed["data_points"])
        else:
            year_factor = 0.90 if month.year == 2020 else (1.10 if month.year in (2021, 2022) else 1.0)
            season_points = 1 + 0.08 * math.sin((2 * math.pi * (index % 12) / 12.0) + season_phase)
            points = max(6, int(round(base_points * year_factor * season_points * rng.uniform(0.88, 1.15))))

        confidence = confidence_from_points(points)
        timestamp = month.isoformat()

        query_payload = {
            "generator": "synthetic_history_v3_backfill",
            "seed_record_id": seed.get("id"),
            "seek_family": family,
            "seek_function": function,
            "seek_role": role,
        }
        statistics_payload = {
            "synthetic": True,
            "month_index": index,
            "observed_blend": bool(observed),
            "seek": {
                "family": family,
                "function": function,
                "role": role,
            },
        }

        rows.append(
            (
                role,
                level,
                country,
                city or None,
                "Synthetic",
                currency,
                round(p25, 2),
                round(median, 2),
                round(p75, 2),
                market_mode,
                confidence,
                1,
                points,
                timestamp,
                json.dumps(query_payload),
                json.dumps(statistics_payload),
            )
        )

        previous_median = median

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate and backfill realistic monthly synthetic benchmark history across SEEK family/function/role."
    )
    parser.add_argument("--months", type=int, default=60, help="Number of months to backfill (default: 60)")
    parser.add_argument("--db-path", type=str, default=None, help="Optional custom SQLite database path")
    args = parser.parse_args()

    db = BenchmarkDatabase(args.db_path)
    try:
        seeds = build_complete_seeds(db)
        if not seeds:
            raise SystemExit("No benchmark seeds available and no canonical roles loaded.")

        months = month_starts(args.months)
        start_month = months[0].isoformat()
        end_month = months[-1].isoformat()

        observed_history_by_key = fetch_observed_history(db)
        existing_months_by_key = fetch_existing_months(db, start_month, end_month)

        all_rows: List[Tuple] = []
        for seed in seeds:
            key = combo_key(seed["role"], seed["level"], seed["country"], (seed.get("city") or "").strip())
            all_rows.extend(
                generate_for_seed(
                    seed,
                    months,
                    observed_history_by_key.get(key),
                    existing_months_by_key.get(key),
                )
            )

        if all_rows:
            cursor = db.conn.cursor()
            cursor.executemany(
                '''
                INSERT INTO benchmark_results (
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                all_rows,
            )
            db.conn.commit()

        families = set()
        functions = set()
        roles = set()
        for seed in seeds:
            family, function = classify_role_seek(seed["role"])
            families.add(family)
            functions.add(function)
            roles.add(seed["role"])

        print(f"Seed combinations considered: {len(seeds)}")
        print(f"SEEK families covered: {len(families)}")
        print(f"SEEK functions covered: {len(functions)}")
        print(f"Roles covered: {len(roles)}")
        print(f"Months in window: {len(months)}")
        print(f"Synthetic rows backfilled: {len(all_rows)}")
        print(f"Range: {start_month} to {end_month}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
