#!/usr/bin/env python3

import csv
import io
import json
import base64
import os
import re
import hashlib
import yaml
import subprocess
import sys
from urllib.parse import urlparse, parse_qs, unquote
from typing import List, Optional, Dict, Any

from flask import Flask, render_template, request, redirect, url_for, send_from_directory, abort
import requests
from bs4 import BeautifulSoup

from processing.normalization import RoleNormalizer
from processing.conversion import SalaryConverter
from processing.statistics import RateBandCalculator
from processing.market_mode import MarketModeDetector
from storage.database import BenchmarkDatabase


app = Flask(__name__)


BRANDING_CONFIGS: Dict[str, Dict[str, Any]] = {
    "oncore": {
        "key": "oncore",
        "title": "Oncore Workforce Benchmarking",
        "colors": {
            "primary": "#23415A",
            "accent": "#ff825a",
            "bg": "#f3f3f5",
            "text": "#1f2f3f",
            "muted": "#5f6f7f",
            "card": "#ffffff",
            "border": "#d9dde2",
            "top_strip_text": "#ffffff",
            "button_text": "#ffffff",
        },
        "top_strip_text": "Self-Service for Contractors • Focus on your work, we'll handle the rest.",
        "top_strip_link_text": "Get Started Today",
        "brand_url": "https://www.oncoreservices.com/",
        "logo_url": "https://5059516.fs1.hubspotusercontent-na1.net/hubfs/5059516/Oncore%20Logo_Workwell%20Logo-1.png",
        "logo_alt": "Oncore",
        "brand_name": "Oncore",
        "tagline": "Contractor workforce benchmarking and rate insights.",
        "cta_text": "Contact Us",
        "footer_prefix": "Oncore workforce solutions",
        "footer_url_text": "www.oncoreservices.com",
    },
    "cxc": {
        "key": "cxc",
        "title": "CXC Global Workforce Benchmarking",
        "colors": {
            "primary": "#343a42",
            "accent": "#95d03a",
            "bg": "#f3f3f5",
            "text": "#2f343b",
            "muted": "#5f6670",
            "card": "#ffffff",
            "border": "#d9dde2",
            "top_strip_text": "#1f252b",
            "button_text": "#1f252b",
        },
        "top_strip_text": "Why Human+ works | Smarter tech. Real people. Better outcomes.",
        "top_strip_link_text": "See how",
        "brand_url": "https://www.cxcglobal.com/",
        "logo_url": "https://www.cxcglobal.com/wp-content/uploads/2023/05/cxc-logo-main.webp",
        "logo_alt": "CXC Global",
        "brand_name": "CXC Global",
        "tagline": "Predictable. Scalable. Reliable workforce benchmarking.",
        "cta_text": "Contact us",
        "footer_prefix": "CXC Global workforce solutions",
        "footer_url_text": "www.cxcglobal.com",
    },
}


SAMPLE_DOWNLOADS: Dict[str, str] = {
    "upload-normalize": "test_load_file.csv",
    "bulk-benchmark": "sample_bulk_100_roles.csv",
}


MAJOR_CITIES_BY_COUNTRY: Dict[str, List[str]] = {
    "Australia": ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide", "Canberra"],
    "Singapore": ["Singapore"],
    "India": ["Bengaluru", "Mumbai", "Delhi NCR", "Hyderabad", "Pune", "Chennai"],
    "Philippines": ["Metro Manila", "Cebu", "Davao", "Clark", "Iloilo"],
}


BASE_DIR = os.path.dirname(__file__)
ROLE_MAPPING_PATH = os.path.join(BASE_DIR, "config", "role_mapping.yaml")
TAXONOMY_RULES_PATH = os.path.join(BASE_DIR, "config", "taxonomy_rules.yaml")


def default_taxonomy_rules() -> Dict[str, Any]:
    return {
        "default": {
            "family": "Information & Communication Technology",
            "function": "Other",
        },
        "rules": [
            {
                "name": "Data & AI",
                "family": "Information & Communication Technology",
                "function": "Data & AI",
                "keywords": ["data", "ai", "ml", "analytics", "bi", "scientist"],
            },
            {
                "name": "DevOps & Infrastructure",
                "family": "Information & Communication Technology",
                "function": "DevOps & Infrastructure",
                "keywords": ["devops", "platform", "cloud", "infrastructure", "sre"],
            },
            {
                "name": "Security",
                "family": "Information & Communication Technology",
                "function": "Security",
                "keywords": ["security", "cyber", "infosec", "iam"],
            },
            {
                "name": "Architecture & Leadership",
                "family": "Information & Communication Technology",
                "function": "Architecture & Leadership",
                "keywords": ["architect", "principal engineer", "engineering manager", "head of engineering"],
            },
            {
                "name": "Software Engineering",
                "family": "Information & Communication Technology",
                "function": "Software Engineering",
                "keywords": ["developer", "engineer", "programmer", "full stack", "backend", "frontend", "software"],
            },
            {
                "name": "Enterprise Applications",
                "family": "Information & Communication Technology",
                "function": "Enterprise Applications",
                "keywords": ["salesforce", "crm", "mulesoft", "certinia"],
            },
            {
                "name": "Payroll & Workforce Operations",
                "family": "Human Resources & Recruitment",
                "function": "Payroll & Workforce Operations",
                "keywords": ["payroll", "workforce", "hris", "hcm"],
            },
            {
                "name": "Project Management",
                "family": "Information & Communication Technology",
                "function": "Project Management",
                "keywords": ["project", "program", "scrum", "delivery"],
            },
            {
                "name": "Help Desk & IT Support",
                "family": "Information & Communication Technology",
                "function": "Help Desk & IT Support",
                "keywords": ["support", "service desk", "helpdesk", "desktop"],
            },
            {
                "name": "Testing & QA",
                "family": "Information & Communication Technology",
                "function": "Testing & QA",
                "keywords": ["qa", "test", "automation tester"],
            },
        ],
    }


def load_taxonomy_rules() -> Dict[str, Any]:
    if not os.path.exists(TAXONOMY_RULES_PATH):
        defaults = default_taxonomy_rules()
        save_taxonomy_rules(defaults)
        return defaults

    with open(TAXONOMY_RULES_PATH, "r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    rules = loaded.get("rules")
    if not isinstance(rules, list):
        loaded["rules"] = []

    default_block = loaded.get("default")
    if not isinstance(default_block, dict):
        loaded["default"] = default_taxonomy_rules()["default"]

    return loaded


def save_taxonomy_rules(rules: Dict[str, Any]) -> None:
    with open(TAXONOMY_RULES_PATH, "w", encoding="utf-8") as file:
        yaml.safe_dump(rules, file, sort_keys=False, allow_unicode=True)


def load_role_mapping_config() -> Dict[str, Any]:
    with open(ROLE_MAPPING_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def save_role_mapping_config(config: Dict[str, Any]) -> None:
    with open(ROLE_MAPPING_PATH, "w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, sort_keys=False, allow_unicode=True)


def add_role_mapping_alias(canonical_role: str, alias: str) -> Dict[str, Any]:
    role_name = (canonical_role or "").strip()
    alias_value = (alias or "").strip()
    if not role_name:
        raise ValueError("Canonical role is required")
    if not alias_value:
        raise ValueError("Alias title is required")

    config = load_role_mapping_config()
    canonical_roles = config.get("canonical_roles") or []
    role_mappings = config.get("role_mappings") or {}

    if role_name not in canonical_roles:
        canonical_roles.append(role_name)
    aliases = role_mappings.get(role_name) or []

    alias_lower = alias_value.lower()
    existing = {str(item).lower() for item in aliases}
    if alias_lower not in existing:
        aliases.append(alias_value)

    role_mappings[role_name] = aliases
    config["canonical_roles"] = canonical_roles
    config["role_mappings"] = role_mappings
    save_role_mapping_config(config)
    return config


def classify_role_taxonomy_with_rules(role_name: str, rules_config: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    role = (role_name or "").lower().strip()
    rules_source = rules_config or load_taxonomy_rules()
    rules = rules_source.get("rules") or []

    for rule in rules:
        family = (rule.get("family") or "").strip()
        function = (rule.get("function") or "").strip()
        keywords = [str(item).strip().lower() for item in (rule.get("keywords") or []) if str(item).strip()]
        if not family or not function or not keywords:
            continue
        if any(keyword in role for keyword in keywords):
            return {"family": family, "function": function, "rule": (rule.get("name") or "")}

    default_block = rules_source.get("default") or {}
    return {
        "family": (default_block.get("family") or "Information & Communication Technology"),
        "function": (default_block.get("function") or "Other"),
        "rule": "default",
    }


def get_branding_config(branding_key: Optional[str]) -> Dict[str, Any]:
    key = (branding_key or "oncore").strip().lower()
    return BRANDING_CONFIGS.get(key, BRANDING_CONFIGS["oncore"])


@app.context_processor
def inject_branding() -> Dict[str, Any]:
    db: Optional[BenchmarkDatabase] = None
    try:
        db = BenchmarkDatabase()
        branding_key_env = os.getenv("BRANDING_KEY")
        if branding_key_env:
            branding_key = branding_key_env.strip().lower()
            if branding_key:
                db.set_setting("branding", branding_key)
        else:
            branding_key = db.get_setting("branding", "oncore")
        branding = get_branding_config(branding_key)
    except Exception:
        branding = get_branding_config("oncore")
    finally:
        if db:
            db.close()

    return {
        "branding": branding,
        "branding_key": branding.get("key", "oncore"),
    }


def parse_number_list(raw: str) -> List[float]:
    if not raw:
        return []

    values: List[float] = []
    for part in raw.replace("\n", ",").replace(";", ",").split(","):
        cleaned = part.strip()
        if not cleaned:
            continue
        values.append(float(cleaned))
    return values


def parse_number_inputs(raw_values: List[str]) -> List[float]:
    values: List[float] = []
    for raw in raw_values:
        cleaned = (raw or "").strip()
        if not cleaned:
            continue
        try:
            values.append(float(cleaned))
        except ValueError as exc:
            raise ValueError(f"Invalid numeric input: {cleaned}") from exc
    return values


def available_countries() -> List[str]:
    converter = SalaryConverter()
    return sorted(list(converter.multipliers.keys()))


def parse_csv_rows(text: str) -> List[dict]:
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("CSV headers are missing")

    headers = {header.strip().lower(): header for header in reader.fieldnames if header}
    if "title" not in headers or "description" not in headers:
        raise ValueError("CSV must include 'title' and 'description' columns")

    rows: List[dict] = []
    for index, record in enumerate(reader, start=2):
        title = (record.get(headers["title"]) or "").strip()
        description = (record.get(headers["description"]) or "").strip()
        if not title and not description:
            continue

        rows.append(
            {
                "line": index,
                "title": title,
                "description": description,
                "city": (record.get(headers.get("city", "")) or "").strip() if "city" in headers else "",
            }
        )

    if not rows:
        raise ValueError("No valid rows found in uploaded CSV")

    return rows


def parse_uploaded_rows(file_storage) -> List[dict]:
    if not file_storage or not file_storage.filename:
        raise ValueError("CSV file is required")

    raw_content = file_storage.read()
    if not raw_content:
        raise ValueError("Uploaded file is empty")

    text = raw_content.decode("utf-8-sig")
    return parse_csv_rows(text)


def parse_bulk_benchmark_rows(file_storage) -> List[dict]:
    if not file_storage or not file_storage.filename:
        raise ValueError("CSV file is required")

    raw_content = file_storage.read()
    if not raw_content:
        raise ValueError("Uploaded file is empty")

    text = raw_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV headers are missing")

    header_map = {header.strip().lower(): header for header in reader.fieldnames if header}
    if "role" not in header_map:
        raise ValueError("CSV must include 'role' column")

    rows: List[dict] = []
    for index, record in enumerate(reader, start=2):
        role = (record.get(header_map["role"]) or "").strip()
        if not role:
            continue

        def get_value(column_name: str) -> str:
            header = header_map.get(column_name)
            return (record.get(header) or "").strip() if header else ""

        rows.append(
            {
                "line": index,
                "role": role,
                "city": get_value("city"),
                "description": get_value("description"),
                "level": get_value("level"),
                "rate_low": get_value("rate_low"),
                "rate_medium": get_value("rate_medium"),
                "rate_high": get_value("rate_high"),
                "salary_low": get_value("salary_low"),
                "salary_medium": get_value("salary_medium"),
                "salary_high": get_value("salary_high"),
                "rates": get_value("rates"),
                "salaries": get_value("salaries"),
            }
        )

    if not rows:
        raise ValueError("No valid rows found in uploaded CSV")

    return rows


def parse_sample_rows() -> List[dict]:
    sample_path = os.path.join(os.path.dirname(__file__), "test_load_file.csv")
    with open(sample_path, "r", encoding="utf-8") as sample_file:
        return parse_csv_rows(sample_file.read())


def _parse_numeric_value(raw: str) -> Optional[float]:
    cleaned = raw.replace(",", "").replace("$", "").replace("A$", "").replace("S$", "")
    cleaned = cleaned.replace("₹", "").replace("₱", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_rates_from_text(text: str, country: str, converter: SalaryConverter) -> List[float]:
    rates: List[float] = []
    lowered = text.lower()

    range_daily_matches = re.finditer(
        r"(\d[\d,]{2,7}(?:\.\d+)?)\s*(?:-|–|to)\s*(\d[\d,]{2,7}(?:\.\d+)?)\s*(?:aud|sgd|inr|php|\$|₹|₱)?\s*(?:/\s*day|per\s*day|daily)",
        lowered,
    )
    for match in range_daily_matches:
        first = _parse_numeric_value(match.group(1))
        second = _parse_numeric_value(match.group(2))
        if first:
            rates.append(first)
        if second:
            rates.append(second)

    daily_matches = re.finditer(
        r"(?:aud|sgd|inr|php|\$|a\$|s\$|₹|₱)?\s*(\d[\d,]{2,7}(?:\.\d+)?)\s*(?:aud|sgd|inr|php|\$|₹|₱)?\s*(?:/\s*day|per\s*day|daily)",
        lowered,
    )
    for match in daily_matches:
        value = _parse_numeric_value(match.group(1))
        if value:
            rates.append(value)

    hourly_matches = re.finditer(
        r"(?:aud|sgd|inr|php|\$|a\$|s\$|₹|₱)?\s*(\d[\d,]{2,6}(?:\.\d+)?)\s*(?:aud|sgd|inr|php|\$|₹|₱)?\s*(?:/\s*hour|per\s*hour|hourly)",
        lowered,
    )
    for match in hourly_matches:
        value = _parse_numeric_value(match.group(1))
        if value:
            rates.append(value * 8)

    annual_matches = re.finditer(
        r"(?:aud|sgd|inr|php|\$|a\$|s\$|₹|₱)?\s*(\d[\d,]{4,9}(?:\.\d+)?)\s*(?:aud|sgd|inr|php|\$|₹|₱)?\s*(?:per\s*annum|/\s*year|yearly|annually|pa)",
        lowered,
    )
    for match in annual_matches:
        annual_value = _parse_numeric_value(match.group(1))
        if annual_value:
            converted = converter.annual_to_daily(annual_value, country)
            rates.append(converted["daily_rate"])

    annual_range_matches = re.finditer(
        r"(?:aud|sgd|inr|php|\$|a\$|s\$|₹|₱)?\s*(\d[\d,]{4,9}(?:\.\d+)?)\s*(?:-|–|to)\s*(\d[\d,]{4,9}(?:\.\d+)?)",
        lowered,
    )
    for match in annual_range_matches:
        first = _parse_numeric_value(match.group(1))
        second = _parse_numeric_value(match.group(2))
        if first and second and first >= 20000 and second >= 20000:
            rates.append(converter.annual_to_daily(first, country)["daily_rate"])
            rates.append(converter.annual_to_daily(second, country)["daily_rate"])

    generic_salary_matches = re.finditer(
        r"(?:salary|pay|compensation|earn|earning|package)[^\d]{0,24}(\d[\d,]{4,9}(?:\.\d+)?)",
        lowered,
    )
    for match in generic_salary_matches:
        value = _parse_numeric_value(match.group(1))
        if value and value >= 20000:
            rates.append(converter.annual_to_daily(value, country)["daily_rate"])

    filtered = [rate for rate in rates if 100 <= rate <= 5000]
    deduped: List[float] = []
    seen = set()
    for rate in filtered:
        rounded = round(rate, 2)
        if rounded not in seen:
            seen.add(rounded)
            deduped.append(rounded)
    return deduped


def _extract_search_result_urls(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: List[str] = []

    for anchor in soup.select("a.result__a"):
        href = anchor.get("href") or ""
        if not href:
            continue

        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            query = parse_qs(parsed.query)
            uddg = query.get("uddg", [""])[0]
            if uddg:
                href = unquote(uddg)

        if href.startswith("http"):
            urls.append(href)

    deduped: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def fetch_internet_benchmark_rates(role: str, description: str, country: str, converter: SalaryConverter) -> List[float]:
    query_variants = [
        f"{role} {description} contractor day rate {country}",
        f"{role} {country} salary range",
        f"{role} {country} daily rate",
    ]
    url = "https://duckduckgo.com/html/"
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Safari/537.36"}

    rates: List[float] = []
    urls_to_scan: List[str] = []

    for query in query_variants:
        try:
            response = requests.get(url, params={"q": query}, headers=headers, timeout=12)
            response.raise_for_status()
        except Exception:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        snippets = [node.get_text(" ", strip=True) for node in soup.select(".result, .result__snippet")]
        if not snippets:
            snippets = [soup.get_text(" ", strip=True)]

        for snippet in snippets[:20]:
            rates.extend(extract_rates_from_text(snippet, country, converter))

        urls_to_scan.extend(_extract_search_result_urls(response.text)[:8])

    scanned = 0
    for source_url in urls_to_scan:
        if scanned >= 12:
            break
        try:
            source_response = requests.get(source_url, headers=headers, timeout=10)
            if source_response.status_code >= 400:
                continue
            source_text = BeautifulSoup(source_response.text, "html.parser").get_text(" ", strip=True)
            if source_text:
                rates.extend(extract_rates_from_text(source_text[:300000], country, converter))
            scanned += 1
        except Exception:
            continue

    deduped: List[float] = []
    seen = set()
    for rate in rates:
        if rate not in seen:
            seen.add(rate)
            deduped.append(rate)
    return deduped[:20]


def generate_ai_estimated_rates(role: str, canonical_role: str, seniority_level: str, country: str) -> List[float]:
    country_mid_baseline = {
        "Australia": 850.0,
        "Singapore": 700.0,
        "India": 18000.0,
        "Philippines": 7000.0,
    }
    level_factor = {
        "Junior": 0.75,
        "Mid": 1.0,
        "Senior": 1.2,
        "Lead": 1.35,
        "Architect": 1.45,
    }

    role_key = (canonical_role or role or "").lower()
    role_factor = 1.0
    if "architect" in role_key:
        role_factor = 1.25
    elif "data" in role_key:
        role_factor = 1.12
    elif "devops" in role_key or "platform" in role_key or "cloud" in role_key:
        role_factor = 1.15
    elif "software" in role_key or "engineer" in role_key or "developer" in role_key:
        role_factor = 1.08
    elif "qa" in role_key or "test" in role_key:
        role_factor = 0.85

    base = country_mid_baseline.get(country, 800.0)
    level = seniority_level if seniority_level in level_factor else "Mid"
    median = base * level_factor[level] * role_factor

    seed_source = f"{role}|{canonical_role}|{seniority_level}|{country}".encode("utf-8")
    seed_hash = hashlib.sha256(seed_source).hexdigest()
    jitter = (int(seed_hash[:4], 16) % 9 - 4) / 100.0
    median *= (1 + jitter)

    p25 = median * 0.88
    p75 = median * 1.14

    return [
        round(p25, 2),
        round((p25 + median) / 2, 2),
        round(median, 2),
        round((median + p75) / 2, 2),
        round(p75, 2),
    ]


def base_context() -> dict:
    countries = available_countries()
    levels = ["", "Junior", "Mid", "Senior", "Lead", "Architect"]
    benchmark_sources = [
        "Manual Entry",
        "Client Provided",
        "Salary Guide",
        "Job Board",
        "Internal Data",
        "AI",
    ]
    major_cities_by_country = {
        country: MAJOR_CITIES_BY_COUNTRY.get(country, [])
        for country in countries
    }
    return {
        "countries": countries,
        "levels": levels,
        "benchmark_sources": benchmark_sources,
        "major_cities_by_country": major_cities_by_country,
    }


def default_country(countries: List[str]) -> str:
    return countries[0] if countries else ""


def default_city(country: str) -> str:
    cities = MAJOR_CITIES_BY_COUNTRY.get(country, [])
    return cities[0] if cities else ""


def classify_role_taxonomy(role_name: str) -> Dict[str, str]:
    result = classify_role_taxonomy_with_rules(role_name)
    return {
        "family": result.get("family") or "Information & Communication Technology",
        "function": result.get("function") or "Other",
    }


def _parse_float(raw_value: Any) -> Optional[float]:
    if raw_value is None:
        return None
    cleaned = str(raw_value).strip()
    if not cleaned:
        return None
    return float(cleaned)


def daily_rate_to_annual_salary(daily_rate: float, country: str, converter: SalaryConverter) -> float:
    multiplier = converter.get_multiplier(country)
    working_days = converter.get_working_days(country)
    return round((float(daily_rate) * float(working_days)) / float(multiplier), 2)


def build_salary_comparison(
    annual_salary: float,
    lower_bound: float,
    upper_bound: float,
) -> Dict[str, Any]:
    low = min(lower_bound, upper_bound)
    high = max(lower_bound, upper_bound)

    spread = max(high - low, 1.0)
    padding = max(spread * 0.3, 1.0)
    axis_min = max(0.0, min(low, annual_salary) - padding)
    axis_max = max(high, annual_salary) + padding
    axis_span = max(axis_max - axis_min, 1.0)

    def to_pct(value: float) -> float:
        pct = ((value - axis_min) / axis_span) * 100.0
        return max(0.0, min(100.0, round(pct, 2)))

    if annual_salary < low:
        status = "lower"
    elif annual_salary > high:
        status = "higher"
    else:
        status = "within"

    return {
        "status": status,
        "status_text": "lower than" if status == "lower" else "higher than" if status == "higher" else "within",
        "annual_salary": annual_salary,
        "lower_bound": low,
        "upper_bound": high,
        "axis_min": round(axis_min, 2),
        "axis_max": round(axis_max, 2),
        "salary_pct": to_pct(annual_salary),
        "range_start_pct": to_pct(low),
        "range_end_pct": to_pct(high),
        "range_width_pct": max(0.0, round(to_pct(high) - to_pct(low), 2)),
    }


def find_latest_benchmark_for_compare(
    db: BenchmarkDatabase,
    canonical_role: str,
    level: str,
    country: str,
    city: str,
) -> Optional[Dict[str, Any]]:
    city_name = (city or "").strip()
    if city_name:
        city_result = db.get_all_benchmarks(
            page=1,
            page_size=25,
            role_query=canonical_role,
            level=level,
            country=country,
            city=city_name,
            sort_by="timestamp",
            sort_dir="desc",
        )
        for row in city_result.get("records", []):
            if (row.get("role") or "").strip().lower() == canonical_role.lower():
                return row

    return db.get_latest_benchmark(canonical_role, country, level)


def process_single_benchmark(form: dict) -> dict:
    db: Optional[BenchmarkDatabase] = None
    try:
        if not form["role"]:
            raise ValueError("Role is required")
        if not form["country"]:
            raise ValueError("Country is required")

        normalizer = RoleNormalizer()
        converter = SalaryConverter()
        calculator = RateBandCalculator()
        detector = MarketModeDetector()
        db = BenchmarkDatabase()

        normalized = normalizer.normalize(form["role"], form["level"] or None)
        canonical_role = normalized["canonical_role"]
        seniority_level = normalized["seniority_level"]

        if any(key in form for key in ["rate_low", "rate_medium", "rate_high", "salary_low", "salary_medium", "salary_high"]):
            daily_rates = parse_number_inputs([
                form.get("rate_low", ""),
                form.get("rate_medium", ""),
                form.get("rate_high", ""),
            ])
            salaries = parse_number_inputs([
                form.get("salary_low", ""),
                form.get("salary_medium", ""),
                form.get("salary_high", ""),
            ])
        elif "rate_inputs" in form or "salary_inputs" in form:
            daily_rates = parse_number_inputs(form.get("rate_inputs", []))
            salaries = parse_number_inputs(form.get("salary_inputs", []))
        else:
            daily_rates = parse_number_list(form["rates"])
            salaries = parse_number_list(form["salaries"])

        for salary in salaries:
            converted = converter.annual_to_daily(salary, form["country"])
            daily_rates.append(converted["daily_rate"])

        if not daily_rates:
            raise ValueError("Provide at least one daily rate or salary")

        currency = converter.get_currency(form["country"])
        rate_bands = calculator.generate_rate_bands(
            daily_rates,
            currency,
            form["country"],
            canonical_role,
            seniority_level,
        )

        historical = db.get_latest_benchmark(canonical_role, form["country"], seniority_level)
        historical_median = historical["median_daily_rate"] if historical else None
        historical_count = historical["data_points"] if historical else None

        market_result = detector.detect_mode(
            rate_bands["median_daily_rate"],
            historical_median,
            len(daily_rates),
            historical_count,
            len(daily_rates),
        )

        benchmark_id = db.store_benchmark(
            role=canonical_role,
            level=seniority_level,
            country=form["country"],
            city=(form.get("city") or default_city(form["country"]) or None),
            source=(form.get("source", "AI").strip() or "AI"),
            currency=currency,
            p25=rate_bands["p25_daily_rate"],
            median=rate_bands["median_daily_rate"],
            p75=rate_bands["p75_daily_rate"],
            market_mode=market_result["market_mode"],
            confidence=rate_bands["confidence"],
            source_count=1,
            data_points=len(daily_rates),
            statistics=rate_bands.get("statistics"),
        )

        p25_annual = daily_rate_to_annual_salary(rate_bands["p25_daily_rate"], form["country"], converter)
        median_annual = daily_rate_to_annual_salary(rate_bands["median_daily_rate"], form["country"], converter)
        p75_annual = daily_rate_to_annual_salary(rate_bands["p75_daily_rate"], form["country"], converter)

        return {
            "role": canonical_role,
            "level": seniority_level,
            "country": form["country"],
            "city": (form.get("city") or default_city(form["country"])),
            "currency": currency,
            "p25": rate_bands["p25_daily_rate"],
            "median": rate_bands["median_daily_rate"],
            "p75": rate_bands["p75_daily_rate"],
            "p25_annual": p25_annual,
            "median_annual": median_annual,
            "p75_annual": p75_annual,
            "confidence": rate_bands["confidence"],
            "data_points": rate_bands["data_points"],
            "market_mode": market_result["market_mode"],
            "rate_growth": market_result["rate_growth_pct"],
            "benchmark_id": benchmark_id,
        }
    finally:
        if db:
            db.close()


def process_bulk_benchmark(form: dict) -> dict:
    db: Optional[BenchmarkDatabase] = None
    try:
        if not form["country"]:
            raise ValueError("Country is required")
        if not form["source"]:
            raise ValueError("Source is required")
        if not form["rows"]:
            raise ValueError("Provide at least one bulk row")

        normalizer = RoleNormalizer()
        converter = SalaryConverter()
        calculator = RateBandCalculator()
        detector = MarketModeDetector()
        db = BenchmarkDatabase()

        output_rows = []
        success_count = 0

        for row in form["rows"]:
            try:
                line_number = row.get("line", "-")
                role = (row.get("role") or "").strip()
                level = (row.get("level") or "").strip()
                if not role:
                    raise ValueError("Role is required")

                canonical_role = (row.get("canonical_role") or "").strip()
                seniority_level = (row.get("seniority_level") or "").strip()
                if not canonical_role or not seniority_level:
                    normalized = normalizer.normalize(role, level or None)
                    canonical_role = normalized["canonical_role"]
                    seniority_level = normalized["seniority_level"]

                structured_daily_rates = parse_number_inputs([
                    row.get("rate_low", ""),
                    row.get("rate_medium", ""),
                    row.get("rate_high", ""),
                ])
                structured_salaries = parse_number_inputs([
                    row.get("salary_low", ""),
                    row.get("salary_medium", ""),
                    row.get("salary_high", ""),
                ])

                daily_rates = structured_daily_rates if structured_daily_rates else parse_number_list(row.get("rates", ""))
                salaries = structured_salaries if structured_salaries else parse_number_list(row.get("salaries", ""))
                for salary in salaries:
                    converted = converter.annual_to_daily(salary, form["country"])
                    daily_rates.append(converted["daily_rate"])

                if not daily_rates:
                    raise ValueError("No rates or salaries provided")

                currency = converter.get_currency(form["country"])
                rate_bands = calculator.generate_rate_bands(daily_rates, currency, form["country"], canonical_role, seniority_level)

                historical = db.get_latest_benchmark(canonical_role, form["country"], seniority_level)
                historical_median = historical["median_daily_rate"] if historical else None
                historical_count = historical["data_points"] if historical else None

                market_result = detector.detect_mode(
                    rate_bands["median_daily_rate"],
                    historical_median,
                    len(daily_rates),
                    historical_count,
                    len(daily_rates),
                )

                benchmark_id = db.store_benchmark(
                    role=canonical_role,
                    level=seniority_level,
                    country=form["country"],
                    city=(row.get("city") or form.get("city") or default_city(form["country"]) or None),
                    source=form["source"],
                    currency=currency,
                    p25=rate_bands["p25_daily_rate"],
                    median=rate_bands["median_daily_rate"],
                    p75=rate_bands["p75_daily_rate"],
                    market_mode=market_result["market_mode"],
                    confidence=rate_bands["confidence"],
                    source_count=1,
                    data_points=len(daily_rates),
                    statistics=rate_bands.get("statistics"),
                )

                output_rows.append(
                    {
                        "line": line_number,
                        "status": "ok",
                        "input_role": role,
                        "role": canonical_role,
                        "level": seniority_level,
                        "country": form["country"],
                        "city": (row.get("city") or form.get("city") or default_city(form["country"])),
                        "source": form["source"],
                        "median": rate_bands["median_daily_rate"],
                        "p25": rate_bands["p25_daily_rate"],
                        "p75": rate_bands["p75_daily_rate"],
                        "currency": currency,
                        "market_mode": market_result["market_mode"],
                        "data_points": len(daily_rates),
                        "benchmark_id": benchmark_id,
                    }
                )
                success_count += 1
            except Exception as row_exc:
                output_rows.append(
                    {
                        "line": row.get("line", "-"),
                        "status": "error",
                        "input_role": row.get("role", ""),
                        "country": form["country"],
                        "city": (row.get("city") or form.get("city") or default_city(form["country"])),
                        "source": form["source"],
                        "message": str(row_exc),
                    }
                )

        if not output_rows:
            raise ValueError("No non-empty rows provided")

        return {
            "country": form["country"],
            "source": form["source"],
            "rows": output_rows,
            "success_count": success_count,
            "error_count": len(output_rows) - success_count,
        }
    finally:
        if db:
            db.close()


def process_bulk_normalize(parsed_rows: List[dict], country: str, source: str) -> dict:
    if not country:
        raise ValueError("Country is required")
    if not source:
        raise ValueError("Source is required")
    if not parsed_rows:
        raise ValueError("No rows to normalize")

    normalizer = RoleNormalizer()
    normalized_rows = []
    for row in parsed_rows:
        role = (row.get("role") or "").strip()
        description = (row.get("description") or "").strip()
        level = (row.get("level") or "").strip()
        normalize_input = f"{role} {description}".strip()
        normalized = normalizer.normalize(normalize_input, level or None)
        normalized_rows.append(
            {
                **row,
                "canonical_role": normalized["canonical_role"],
                "seniority_level": normalized["seniority_level"],
                "confidence": normalized["confidence"],
                "is_unmapped": normalized["canonical_role"] == "Unmapped Role",
            }
        )

    return {
        "rows": normalized_rows,
        "payload_b64": base64.b64encode(json.dumps(normalized_rows).encode("utf-8")).decode("utf-8"),
        "country": country,
        "source": source,
        "count": len(normalized_rows),
    }


def process_upload_normalize(form: dict, use_sample: bool) -> dict:
    if use_sample:
        parsed_rows = parse_sample_rows()
    else:
        file_storage = request.files.get("normalize_file")
        parsed_rows = parse_uploaded_rows(file_storage)

    normalizer = RoleNormalizer()
    normalized_rows = []
    for row in parsed_rows:
        normalize_input = f"{row['title']} {row['description']}".strip()
        normalized = normalizer.normalize(normalize_input)
        normalized_rows.append(
            {
                **row,
                "canonical_role": normalized["canonical_role"],
                "seniority_level": normalized["seniority_level"],
                "confidence": normalized["confidence"],
                "rates": "",
                "salaries": "",
            }
        )

    return {
        "rows": normalized_rows,
        "payload_b64": base64.b64encode(json.dumps(normalized_rows).encode("utf-8")).decode("utf-8"),
        "country": form["country"],
        "count": len(normalized_rows),
        "default_rates": form["default_rates"],
        "default_salaries": form["default_salaries"],
        "use_internet": form["use_internet"],
        "use_ai_estimate": form["use_ai_estimate"],
    }


def process_upload_benchmark(form: dict, countries: List[str]) -> dict:
    db: Optional[BenchmarkDatabase] = None
    try:
        payload_b64 = form["payload_b64"]
        accepted_lines = set(form["accepted_lines"])
        selected_country = form["country"]
        default_rates = form["default_rates"]
        default_salaries = form["default_salaries"]
        use_internet = form["use_internet"]
        use_ai_estimate = form["use_ai_estimate"]

        if not payload_b64:
            raise ValueError("Normalized payload is missing")
        payload_json = base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        normalized_rows = json.loads(payload_json)
        if not isinstance(normalized_rows, list):
            raise ValueError("Invalid normalized payload")
        if not accepted_lines:
            raise ValueError("Select at least one row to benchmark")

        converter = SalaryConverter()
        calculator = RateBandCalculator()
        detector = MarketModeDetector()
        db = BenchmarkDatabase()

        output_rows = []
        success_count = 0
        for row in normalized_rows:
            line_value = str(row.get("line", ""))
            if line_value not in accepted_lines:
                continue
            try:
                country = (row.get("country") or selected_country or default_country(countries)).strip()
                if not country:
                    raise ValueError("Country is required")
                city = (row.get("city") or form.get("city") or default_city(country)).strip()

                canonical_role = row.get("canonical_role", "").strip()
                seniority_level = row.get("seniority_level", "Mid").strip() or "Mid"
                rates_raw = row.get("rates", "") or default_rates
                salaries_raw = row.get("salaries", "") or default_salaries

                daily_rates = parse_number_list(rates_raw)
                salaries = parse_number_list(salaries_raw)

                internet_rates: List[float] = []
                ai_rates: List[float] = []
                search_context = f"role='{row.get('title', '')}' country='{country}'"
                if use_internet:
                    internet_rates = fetch_internet_benchmark_rates(
                        row.get("title", ""),
                        row.get("description", ""),
                        country,
                        converter,
                    )
                    daily_rates.extend(internet_rates)

                if not daily_rates and use_ai_estimate:
                    ai_rates = generate_ai_estimated_rates(
                        row.get("title", ""),
                        canonical_role,
                        seniority_level,
                        country,
                    )
                    daily_rates.extend(ai_rates)

                for salary in salaries:
                    converted = converter.annual_to_daily(salary, country)
                    daily_rates.append(converted["daily_rate"])

                if not daily_rates:
                    raise ValueError(
                        "No benchmark data found (defaults + internet search + AI estimate). "
                        f"Context: {search_context}."
                    )

                currency = converter.get_currency(country)
                rate_bands = calculator.generate_rate_bands(daily_rates, currency, country, canonical_role, seniority_level)

                historical = db.get_latest_benchmark(canonical_role, country, seniority_level)
                historical_median = historical["median_daily_rate"] if historical else None
                historical_count = historical["data_points"] if historical else None

                market_result = detector.detect_mode(
                    rate_bands["median_daily_rate"],
                    historical_median,
                    len(daily_rates),
                    historical_count,
                    len(daily_rates),
                )

                benchmark_id = db.store_benchmark(
                    role=canonical_role,
                    level=seniority_level,
                    country=country,
                    city=city or None,
                    source="AI",
                    currency=currency,
                    p25=rate_bands["p25_daily_rate"],
                    median=rate_bands["median_daily_rate"],
                    p75=rate_bands["p75_daily_rate"],
                    market_mode=market_result["market_mode"],
                    confidence=rate_bands["confidence"],
                    source_count=1,
                    data_points=len(daily_rates),
                    statistics=rate_bands.get("statistics"),
                )

                output_rows.append(
                    {
                        "line": row.get("line"),
                        "status": "ok",
                        "role": canonical_role,
                        "level": seniority_level,
                        "country": country,
                        "city": city,
                        "median": rate_bands["median_daily_rate"],
                        "p25": rate_bands["p25_daily_rate"],
                        "p75": rate_bands["p75_daily_rate"],
                        "currency": currency,
                        "market_mode": market_result["market_mode"],
                        "data_points": len(daily_rates),
                        "benchmark_id": benchmark_id,
                        "internet_points": len(internet_rates),
                        "ai_points": len(ai_rates),
                    }
                )
                success_count += 1
            except Exception as row_exc:
                output_rows.append(
                    {
                        "line": row.get("line"),
                        "status": "error",
                        "role": row.get("canonical_role", ""),
                        "country": row.get("country", "") or selected_country,
                        "city": row.get("city", "") or form.get("city", "") or default_city(selected_country),
                        "message": str(row_exc),
                    }
                )

        if not output_rows:
            raise ValueError("No accepted rows found in payload")

        return {
            "normalize": {
                "rows": normalized_rows,
                "payload_b64": payload_b64,
                "country": selected_country,
                "count": len(normalized_rows),
                "default_rates": default_rates,
                "default_salaries": default_salaries,
                "use_internet": use_internet,
                "use_ai_estimate": use_ai_estimate,
            },
            "benchmark": {
                "rows": output_rows,
                "success_count": success_count,
                "error_count": len(output_rows) - success_count,
            },
        }
    finally:
        if db:
            db.close()


@app.route("/")
def index():
    return redirect(url_for("analytics_page"))


@app.route("/download/sample/<sample_key>")
def download_sample(sample_key: str):
    filename = SAMPLE_DOWNLOADS.get(sample_key)
    if not filename:
        abort(404)

    base_dir = os.path.dirname(__file__)
    file_path = os.path.join(base_dir, filename)
    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(base_dir, filename, as_attachment=True)


@app.route("/admin/synthetic-backfill", methods=["POST"])
def synthetic_backfill_admin():
    admin_token = os.getenv("ADMIN_TOKEN")
    provided_token = (
        request.headers.get("X-Admin-Token")
        or request.args.get("token")
        or request.form.get("token")
    )

    if not admin_token or not provided_token or provided_token != admin_token:
        abort(403)

    try:
        months = int(request.args.get("months") or request.form.get("months") or 24)
    except (TypeError, ValueError):
        months = 24

    months = max(1, min(months, 120))
    db_path = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "benchmark_data.db"))
    script_path = os.path.join(BASE_DIR, "scripts", "generate_synthetic_history.py")

    if not os.path.exists(script_path):
        return {"status": "error", "message": "Synthetic generator script not found."}, 500

    try:
        result = subprocess.run(
            [
                sys.executable,
                script_path,
                "--months",
                str(months),
                "--db-path",
                db_path,
            ],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "Synthetic backfill timed out."}, 504

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    payload = {
        "status": "ok" if result.returncode == 0 else "error",
        "returncode": result.returncode,
        "months": months,
        "db_path": db_path,
        "stdout": stdout[-4000:] if stdout else "",
        "stderr": stderr[-4000:] if stderr else "",
    }
    return payload, (200 if result.returncode == 0 else 500)


@app.route("/benchmark", methods=["GET", "POST"])
def benchmark_page():
    ctx = base_context()
    countries = ctx["countries"]
    form = {
        "role": "",
        "level": "",
        "country": default_country(countries),
        "city": default_city(default_country(countries)),
        "source": "Manual Entry",
        "rate_low": "",
        "rate_medium": "",
        "rate_high": "",
        "salary_low": "",
        "salary_medium": "",
        "salary_high": "",
    }
    normalize_error = None
    benchmark_error = None
    normalize_result = None
    result = None

    if request.method == "POST":
        action = request.form.get("action", "benchmark_normalize").strip()
        form = {
            "role": request.form.get("benchmark_role", "").strip(),
            "level": request.form.get("benchmark_level", "").strip(),
            "country": request.form.get("benchmark_country", default_country(countries)).strip(),
            "city": request.form.get("benchmark_city", "").strip(),
            "source": request.form.get("benchmark_source", "Manual Entry").strip(),
            "rate_low": request.form.get("benchmark_rate_low", "").strip(),
            "rate_medium": request.form.get("benchmark_rate_medium", "").strip(),
            "rate_high": request.form.get("benchmark_rate_high", "").strip(),
            "salary_low": request.form.get("benchmark_salary_low", "").strip(),
            "salary_medium": request.form.get("benchmark_salary_medium", "").strip(),
            "salary_high": request.form.get("benchmark_salary_high", "").strip(),
        }

        if action == "benchmark_normalize":
            try:
                if not form["role"]:
                    raise ValueError("Role is required")
                if not form["country"]:
                    raise ValueError("Country is required")

                normalizer = RoleNormalizer()
                normalized = normalizer.normalize(form["role"], form["level"] or None)
                normalize_result = {
                    "original_role": form["role"],
                    "canonical_role": normalized["canonical_role"],
                    "seniority_level": normalized["seniority_level"],
                    "confidence": normalized["confidence"],
                    "is_unmapped": normalized["canonical_role"] == "Unmapped Role",
                }
            except Exception as exc:
                normalize_error = str(exc)

        if action == "benchmark_run":
            try:
                normalizer = RoleNormalizer()
                normalized = normalizer.normalize(form["role"], form["level"] or None)
                normalize_result = {
                    "original_role": form["role"],
                    "canonical_role": normalized["canonical_role"],
                    "seniority_level": normalized["seniority_level"],
                    "confidence": normalized["confidence"],
                    "is_unmapped": normalized["canonical_role"] == "Unmapped Role",
                }
                result = process_single_benchmark(form)
            except Exception as exc:
                benchmark_error = str(exc)

    return render_template(
        "benchmark.html",
        benchmark_form=form,
        normalize_result=normalize_result,
        normalize_error=normalize_error,
        benchmark_error=benchmark_error,
        result=result,
        **ctx,
    )


@app.route("/salary-compare", methods=["GET", "POST"])
def salary_compare_page():
    ctx = base_context()
    countries = ctx["countries"]
    form = {
        "role": "",
        "level": "",
        "country": default_country(countries),
        "city": default_city(default_country(countries)),
        "annual_salary": "",
    }
    error = None
    benchmark_result = None
    salary_compare_result = None

    if request.method == "POST":
        form = {
            "role": request.form.get("salary_compare_role", "").strip(),
            "level": request.form.get("salary_compare_level", "").strip(),
            "country": request.form.get("salary_compare_country", default_country(countries)).strip(),
            "city": request.form.get("salary_compare_city", "").strip(),
            "annual_salary": request.form.get("salary_compare_annual_salary", "").strip(),
        }

        db: Optional[BenchmarkDatabase] = None
        try:
            if not form["role"]:
                raise ValueError("Role is required")
            if not form["country"]:
                raise ValueError("Country is required")
            if not form["annual_salary"]:
                raise ValueError("Annual salary is required")

            annual_salary = float(form["annual_salary"].replace(",", ""))
            if annual_salary <= 0:
                raise ValueError("Annual salary must be positive")

            normalizer = RoleNormalizer()
            normalized = normalizer.normalize(form["role"], form["level"] or None)
            canonical_role = normalized["canonical_role"]
            seniority_level = normalized["seniority_level"]

            db = BenchmarkDatabase()
            benchmark_row = find_latest_benchmark_for_compare(
                db=db,
                canonical_role=canonical_role,
                level=seniority_level,
                country=form["country"],
                city=form["city"],
            )
            if not benchmark_row:
                raise ValueError("No benchmark data found for this role and location yet. Run a benchmark first.")

            converter = SalaryConverter()
            p25_daily = benchmark_row.get("p25_daily_rate")
            median_daily = benchmark_row.get("median_daily_rate")
            p75_daily = benchmark_row.get("p75_daily_rate")

            if p25_daily is None or p75_daily is None:
                raise ValueError("Benchmark range is incomplete for salary comparison")

            p25_annual = daily_rate_to_annual_salary(float(p25_daily), form["country"], converter)
            median_annual = daily_rate_to_annual_salary(float(median_daily), form["country"], converter) if median_daily is not None else None
            p75_annual = daily_rate_to_annual_salary(float(p75_daily), form["country"], converter)

            salary_compare_result = build_salary_comparison(annual_salary, p25_annual, p75_annual)
            benchmark_result = {
                "input_role": form["role"],
                "role": canonical_role,
                "level": seniority_level,
                "country": form["country"],
                "city": form["city"],
                "currency": benchmark_row.get("currency") or converter.get_currency(form["country"]),
                "p25_annual": p25_annual,
                "median_annual": median_annual,
                "p75_annual": p75_annual,
                "market_mode": benchmark_row.get("market_mode") or "Unknown",
                "timestamp": str(benchmark_row.get("timestamp") or "")[:10],
            }
        except Exception as exc:
            error = str(exc)
        finally:
            if db:
                db.close()

    return render_template(
        "salary_compare.html",
        compare_form=form,
        benchmark_result=benchmark_result,
        salary_compare_result=salary_compare_result,
        error=error,
        **ctx,
    )


@app.route("/bulk", methods=["GET", "POST"])
def bulk_page():
    ctx = base_context()
    countries = ctx["countries"]
    form = {
        "country": default_country(countries),
        "city": default_city(default_country(countries)),
        "source": "Manual Entry",
        "filename": "",
    }
    normalize_error = None
    benchmark_error = None
    normalize_result = None
    benchmark_result = None

    if request.method == "POST":
        action = request.form.get("action", "bulk_normalize").strip()

        if action == "bulk_normalize":
            file_storage = request.files.get("bulk_file")
            form = {
                "country": request.form.get("bulk_country", default_country(countries)).strip(),
                "city": request.form.get("bulk_city", "").strip(),
                "source": request.form.get("bulk_source", "Manual Entry").strip(),
                "filename": file_storage.filename if file_storage else "",
            }
            try:
                parsed_rows = parse_bulk_benchmark_rows(file_storage)
                normalize_result = process_bulk_normalize(parsed_rows, form["country"], form["source"])
            except Exception as exc:
                normalize_error = str(exc)

        if action == "bulk_benchmark_accepted":
            form = {
                "country": request.form.get("accepted_country", default_country(countries)).strip(),
                "city": request.form.get("accepted_city", "").strip(),
                "source": request.form.get("accepted_source", "Manual Entry").strip(),
                "filename": request.form.get("accepted_filename", "").strip(),
            }
            try:
                payload_b64 = request.form.get("normalized_payload_b64", "").strip()
                accepted_lines = set(request.form.getlist("accepted_lines"))
                if not payload_b64:
                    raise ValueError("Normalized payload is missing")
                if not accepted_lines:
                    raise ValueError("Select at least one row to benchmark")

                payload_json = base64.b64decode(payload_b64.encode("utf-8")).decode("utf-8")
                normalized_rows = json.loads(payload_json)
                if not isinstance(normalized_rows, list):
                    raise ValueError("Invalid normalized payload")

                accepted_rows = [row for row in normalized_rows if str(row.get("line", "")) in accepted_lines]
                if not accepted_rows:
                    raise ValueError("No accepted rows found in payload")

                normalize_result = {
                    "rows": normalized_rows,
                    "payload_b64": payload_b64,
                    "country": form["country"],
                    "source": form["source"],
                    "count": len(normalized_rows),
                }
                benchmark_result = process_bulk_benchmark(
                    {
                        "country": form["country"],
                        "city": form["city"],
                        "source": form["source"],
                        "rows": accepted_rows,
                    }
                )
            except Exception as exc:
                benchmark_error = str(exc)

    return render_template(
        "bulk.html",
        bulk_form=form,
        normalize_result=normalize_result,
        benchmark_result=benchmark_result,
        normalize_error=normalize_error,
        benchmark_error=benchmark_error,
        **ctx,
    )


@app.route("/upload", methods=["GET", "POST"])
def upload_page():
    ctx = base_context()
    countries = ctx["countries"]
    upload_form = {
        "country": default_country(countries),
        "city": default_city(default_country(countries)),
        "default_rates": "",
        "default_salaries": "",
        "use_internet": True,
        "use_ai_estimate": True,
    }
    normalize_result = None
    benchmark_result = None
    normalize_error = None
    benchmark_error = None

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        upload_form = {
            "country": request.form.get("upload_country", default_country(countries)).strip(),
            "city": request.form.get("upload_city", "").strip(),
            "default_rates": request.form.get("default_rates", "").strip(),
            "default_salaries": request.form.get("default_salaries", "").strip(),
            "use_internet": request.form.get("use_internet_benchmarks") == "on",
            "use_ai_estimate": request.form.get("use_ai_estimate") == "on",
        }

        if action in ["upload_normalize", "upload_normalize_sample"]:
            try:
                normalize_result = process_upload_normalize(upload_form, action == "upload_normalize_sample")
            except Exception as exc:
                normalize_error = str(exc)

        if action == "upload_benchmark_accepted":
            try:
                accepted_form = {
                    "payload_b64": request.form.get("normalized_payload_b64", "").strip(),
                    "accepted_lines": request.form.getlist("accepted_lines"),
                    "country": request.form.get("accepted_country", default_country(countries)).strip(),
                    "city": request.form.get("accepted_city", "").strip(),
                    "default_rates": request.form.get("accepted_default_rates", "").strip(),
                    "default_salaries": request.form.get("accepted_default_salaries", "").strip(),
                    "use_internet": request.form.get("accepted_use_internet") == "on",
                    "use_ai_estimate": request.form.get("accepted_use_ai_estimate") == "on",
                }
                processed = process_upload_benchmark(accepted_form, countries)
                normalize_result = processed["normalize"]
                benchmark_result = processed["benchmark"]
            except Exception as exc:
                benchmark_error = str(exc)

    return render_template(
        "upload.html",
        upload_form=upload_form,
        normalize_result=normalize_result,
        benchmark_result=benchmark_result,
        normalize_error=normalize_error,
        benchmark_error=benchmark_error,
        **ctx,
    )


@app.route("/normalize", methods=["GET", "POST"])
def normalize_page():
    form = {"title": ""}
    error = None
    result = None

    if request.method == "POST":
        form = {"title": request.form.get("normalize_title", "").strip()}
        try:
            if not form["title"]:
                raise ValueError("Job title is required")
            normalizer = RoleNormalizer()
            result = normalizer.normalize(form["title"])
        except Exception as exc:
            error = str(exc)

    return render_template("normalize.html", normalize_form=form, error=error, result=result, **base_context())


@app.route("/convert", methods=["GET", "POST"])
def convert_page():
    countries = available_countries()
    form = {"salary": "", "country": default_country(countries)}
    error = None
    result = None

    if request.method == "POST":
        form = {
            "salary": request.form.get("convert_salary", "").strip(),
            "country": request.form.get("convert_country", default_country(countries)).strip(),
        }
        try:
            if not form["salary"]:
                raise ValueError("Salary is required")
            salary_value = float(form["salary"])
            converter = SalaryConverter()
            result = converter.annual_to_daily(salary_value, form["country"])
        except Exception as exc:
            error = str(exc)

    return render_template("convert.html", convert_form=form, error=error, result=result, countries=countries)


@app.route("/history", methods=["GET", "POST"])
def history_page():
    countries = available_countries()
    form = {
        "role": "",
        "level": "Senior",
        "country": default_country(countries),
        "limit": "10",
    }
    error = None
    result = None

    if request.method == "POST":
        form = {
            "role": request.form.get("history_role", "").strip(),
            "level": request.form.get("history_level", "Senior").strip(),
            "country": request.form.get("history_country", default_country(countries)).strip(),
            "limit": request.form.get("history_limit", "10").strip(),
        }
        db: Optional[BenchmarkDatabase] = None
        try:
            if not form["role"]:
                raise ValueError("Role is required")
            limit = int(form["limit"])
            if limit <= 0:
                raise ValueError("Limit must be greater than 0")

            normalizer = RoleNormalizer()
            normalized_role = normalizer.map_title(form["role"])
            db = BenchmarkDatabase()
            records = db.get_historical_benchmarks(normalized_role, form["country"], form["level"], limit)
            result = {"normalized_role": normalized_role, "records": records}
        except Exception as exc:
            error = str(exc)
        finally:
            if db:
                db.close()

    return render_template("history.html", history_form=form, error=error, result=result, countries=countries)


@app.route("/taxonomy", methods=["GET", "POST"])
def taxonomy_page():
    error = None
    success = None
    test_result = None

    taxonomy_rules = load_taxonomy_rules()
    role_mapping_config = load_role_mapping_config()

    test_form = {
        "title": "",
        "level": "",
    }
    rule_form = {
        "name": "",
        "family": "",
        "function": "",
        "keywords": "",
    }
    mapping_form = {
        "canonical_role": "",
        "alias": "",
    }

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        test_form = {
            "title": request.form.get("test_title", "").strip(),
            "level": request.form.get("test_level", "").strip(),
        }
        rule_form = {
            "name": request.form.get("rule_name", "").strip(),
            "family": request.form.get("rule_family", "").strip(),
            "function": request.form.get("rule_function", "").strip(),
            "keywords": request.form.get("rule_keywords", "").strip(),
        }
        mapping_form = {
            "canonical_role": request.form.get("mapping_canonical_role", "").strip(),
            "alias": request.form.get("mapping_alias", "").strip(),
        }

        try:
            if action == "taxonomy_test":
                if not test_form["title"]:
                    raise ValueError("Role title is required")

                normalizer = RoleNormalizer()
                normalized = normalizer.normalize(test_form["title"], test_form["level"] or None)
                taxonomy = classify_role_taxonomy_with_rules(test_form["title"], taxonomy_rules)

                test_result = {
                    "original_title": test_form["title"],
                    "normalised_role": normalized["canonical_role"],
                    "seniority_level": normalized["seniority_level"],
                    "normalisation_confidence": normalized["confidence"],
                    "job_family": taxonomy["family"],
                    "job_function": taxonomy["function"],
                    "matched_rule": taxonomy.get("rule") or "default",
                }

            elif action == "taxonomy_add_rule":
                if not rule_form["family"]:
                    raise ValueError("Job family is required")
                if not rule_form["function"]:
                    raise ValueError("Job function is required")
                if not rule_form["keywords"]:
                    raise ValueError("At least one keyword is required")

                keywords = [
                    value.strip().lower()
                    for value in re.split(r"[,;\n]+", rule_form["keywords"])
                    if value.strip()
                ]
                if not keywords:
                    raise ValueError("At least one valid keyword is required")

                taxonomy_rules = load_taxonomy_rules()
                taxonomy_rules.setdefault("rules", []).append(
                    {
                        "name": rule_form["name"] or rule_form["function"],
                        "family": rule_form["family"],
                        "function": rule_form["function"],
                        "keywords": keywords,
                    }
                )
                save_taxonomy_rules(taxonomy_rules)
                success = "Taxonomy rule added"

            elif action == "taxonomy_add_mapping":
                add_role_mapping_alias(mapping_form["canonical_role"], mapping_form["alias"])
                success = "Role mapping alias added"

        except Exception as exc:
            error = str(exc)

    taxonomy_rules = load_taxonomy_rules()
    role_mapping_config = load_role_mapping_config()

    rule_rows = taxonomy_rules.get("rules") or []
    role_mappings = role_mapping_config.get("role_mappings") or {}
    canonical_roles = role_mapping_config.get("canonical_roles") or sorted(role_mappings.keys())

    mapping_rows: List[Dict[str, Any]] = []
    for canonical_role in sorted(canonical_roles):
        aliases = role_mappings.get(canonical_role) or []
        mapping_rows.append(
            {
                "canonical_role": canonical_role,
                "alias_count": len(aliases),
                "aliases": aliases,
            }
        )

    return render_template(
        "taxonomy.html",
        taxonomy_rules=taxonomy_rules,
        rule_rows=rule_rows,
        mapping_rows=mapping_rows,
        canonical_roles=sorted(canonical_roles),
        test_form=test_form,
        rule_form=rule_form,
        mapping_form=mapping_form,
        test_result=test_result,
        error=error,
        success=success,
        **base_context(),
    )


@app.route("/all-benchmarks")
def all_benchmarks_page():
    error = None
    records = []
    total_count = 0
    page = 1
    page_size = 25
    total_pages = 1
    filter_options = {
        "levels": [],
        "countries": [],
        "cities": [],
        "sources": [],
    }
    filters = {
        "role_query": request.args.get("role_query", "").strip(),
        "level": request.args.get("level", "").strip(),
        "country": request.args.get("country", "").strip(),
        "city": request.args.get("city", "").strip(),
        "source": request.args.get("source", "").strip(),
    }
    sort_by = request.args.get("sort_by", "timestamp").strip().lower()
    sort_dir = request.args.get("sort_dir", "desc").strip().lower()
    if sort_dir not in ["asc", "desc"]:
        sort_dir = "desc"

    valid_sort_fields = [
        "timestamp",
        "role",
        "level",
        "country",
        "city",
        "source",
        "currency",
        "median",
        "market_mode",
        "data_points",
    ]
    if sort_by not in valid_sort_fields:
        sort_by = "timestamp"
    view_mode = request.args.get("view", "rates").strip().lower()
    if view_mode not in ["rates", "salaries"]:
        view_mode = "rates"

    try:
        requested_page = int(request.args.get("page", "1"))
    except ValueError:
        requested_page = 1

    try:
        requested_page_size = int(request.args.get("page_size", "25"))
    except ValueError:
        requested_page_size = 25

    db: Optional[BenchmarkDatabase] = None
    try:
        db = BenchmarkDatabase()
        filter_options = db.get_benchmark_filter_options()

        result = db.get_all_benchmarks(
            page=requested_page,
            page_size=requested_page_size,
            role_query=filters["role_query"] or None,
            level=filters["level"] or None,
            country=filters["country"] or None,
            city=filters["city"] or None,
            source=filters["source"] or None,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        records = result["records"]
        total_count = result["total_count"]
        page = result["page"]
        page_size = result["page_size"]
        total_pages = result["total_pages"]

        converter = SalaryConverter()
        for row in records:
            p25_daily = row.get("p25_daily_rate")
            median_daily = row.get("median_daily_rate")
            p75_daily = row.get("p75_daily_rate")
            country = row.get("country")
            taxonomy = classify_role_taxonomy(row.get("role") or "")
            row["taxonomy_family"] = taxonomy["family"]
            row["taxonomy_function"] = taxonomy["function"]

            if view_mode == "salaries" and country in converter.multipliers:
                multiplier = converter.get_multiplier(country)
                working_days = converter.get_working_days(country)

                def to_annual(value):
                    if value is None:
                        return None
                    return round((float(value) * working_days) / multiplier, 2)

                row["display_p25"] = to_annual(p25_daily)
                row["display_median"] = to_annual(median_daily)
                row["display_p75"] = to_annual(p75_daily)
                row["display_metric_label"] = "Annual Salary Equivalent"
            else:
                row["display_p25"] = p25_daily
                row["display_median"] = median_daily
                row["display_p75"] = p75_daily
                row["display_metric_label"] = "Daily Rate"
    except Exception as exc:
        error = str(exc)
    finally:
        if db:
            db.close()

    return render_template(
        "all_benchmarks.html",
        records=records,
        error=error,
        filters=filters,
        filter_options=filter_options,
        total_count=total_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        view_mode=view_mode,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


@app.route("/analytics")
def analytics_page():
    error = None
    analytics_rows: List[Dict[str, Any]] = []

    db: Optional[BenchmarkDatabase] = None
    try:
        db = BenchmarkDatabase()
        records = db.get_all_benchmark_records()

        converter = SalaryConverter()
        multiplier_map = converter.multipliers

        for row in records:
            country = row.get("country")
            multiplier_config = multiplier_map.get(country, {})
            multiplier = multiplier_config.get("multiplier")
            working_days = multiplier_config.get("working_days_per_year", 220)

            median_daily = row.get("median_daily_rate")
            if median_daily is not None and multiplier:
                median_annual = round((float(median_daily) * float(working_days)) / float(multiplier), 2)
            else:
                median_annual = None

            analytics_rows.append(
                {
                    "id": row.get("id"),
                    "timestamp": str(row.get("timestamp") or ""),
                    "month": str(row.get("timestamp") or "")[:7],
                    "role": row.get("role") or "",
                    "level": row.get("level") or "",
                    "country": country or "",
                    "city": row.get("city") or "",
                    "source": row.get("source") or "",
                    "currency": row.get("currency") or "",
                    "market_mode": row.get("market_mode") or "Unknown",
                    "p25_daily_rate": row.get("p25_daily_rate"),
                    "median_daily_rate": median_daily,
                    "p75_daily_rate": row.get("p75_daily_rate"),
                    "median_annual_salary": median_annual,
                    "data_points": row.get("data_points") or 0,
                }
            )
    except Exception as exc:
        error = str(exc)
    finally:
        if db:
            db.close()

    return render_template(
        "analytics.html",
        analytics_rows=analytics_rows,
        analytics_count=len(analytics_rows),
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
