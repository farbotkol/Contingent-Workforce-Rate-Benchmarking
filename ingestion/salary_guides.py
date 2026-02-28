"""
Salary Guide Extraction Module

Handles extraction of salary data from public salary guides (PDF format).
EPIC 2 - Data Ingestion (Public Sources Only)
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logger.warning("pdfplumber not available. PDF extraction will not work.")


class SalaryGuideExtractor:
    """Extract salary data from public salary guides in PDF format."""
    
    def __init__(self):
        """Initialize the salary guide extractor."""
        if not PDF_SUPPORT:
            logger.warning("PDF support not available. Install pdfplumber to enable.")
    
    def extract_from_pdf(
        self,
        pdf_path: str,
        source_name: str,
        country: str
    ) -> List[Dict[str, Any]]:
        """
        Extract salary data from a PDF salary guide.
        
        Args:
            pdf_path: Path to PDF file
            source_name: Name of the salary guide source
            country: Country the guide covers
            
        Returns:
            List of extracted salary records
        """
        if not PDF_SUPPORT:
            logger.error("PDF extraction not available. Install pdfplumber.")
            return []
        
        extracted_data = []
        timestamp = datetime.utcnow().isoformat()
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                logger.info(f"Processing PDF: {pdf_path} ({len(pdf.pages)} pages)")
                
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract tables from the page
                    tables = page.extract_tables()
                    
                    if not tables:
                        # Try text extraction if no tables found
                        text = page.extract_text()
                        if text:
                            logger.debug(f"Page {page_num}: No tables, found text")
                    
                    for table_num, table in enumerate(tables):
                        if not table:
                            continue
                        
                        # Process table data
                        # This is a generic implementation - specific guides may need custom parsing
                        logger.debug(f"Page {page_num}, Table {table_num}: {len(table)} rows")
                        
                        # Skip if table is too small
                        if len(table) < 2:
                            continue
                        
                        # Assume first row is header
                        headers = [str(h).lower().strip() if h else '' for h in table[0]]
                        
                        for row in table[1:]:
                            if not row or all(not cell for cell in row):
                                continue
                            
                            # Try to extract role and salary information
                            record = self._parse_table_row(
                                headers,
                                row,
                                source_name,
                                country,
                                timestamp
                            )
                            
                            if record:
                                extracted_data.append(record)
                
                logger.info(f"Extracted {len(extracted_data)} records from {pdf_path}")
                
        except Exception as e:
            logger.error(f"Error extracting from PDF {pdf_path}: {str(e)}")
            # Don't crash - just log the error
        
        return extracted_data
    
    def _parse_table_row(
        self,
        headers: List[str],
        row: List[Any],
        source_name: str,
        country: str,
        timestamp: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parse a single table row to extract salary information.
        
        Args:
            headers: Table column headers
            row: Table row data
            source_name: Source name
            country: Country
            timestamp: Extraction timestamp
            
        Returns:
            Extracted record or None if parsing fails
        """
        # Find role/title column
        role_col_idx = None
        for idx, header in enumerate(headers):
            if any(keyword in header for keyword in ['role', 'title', 'position', 'job']):
                role_col_idx = idx
                break
        
        # Find salary columns
        min_salary_idx = None
        max_salary_idx = None
        
        for idx, header in enumerate(headers):
            if 'min' in header or 'low' in header or 'from' in header:
                min_salary_idx = idx
            elif 'max' in header or 'high' in header or 'to' in header:
                max_salary_idx = idx
            elif 'salary' in header and not min_salary_idx:
                # Single salary column
                min_salary_idx = idx
                max_salary_idx = idx
        
        # Extract data
        if role_col_idx is None or min_salary_idx is None:
            return None
        
        try:
            role = str(row[role_col_idx]).strip() if row[role_col_idx] else None
            if not role or role.lower() in ['none', '']:
                return None
            
            # Extract salary values
            min_salary_str = str(row[min_salary_idx]) if row[min_salary_idx] else None
            max_salary_str = str(row[max_salary_idx]) if max_salary_idx and row[max_salary_idx] else min_salary_str
            
            # Clean and parse salary values (remove currency symbols, commas)
            min_salary = self._parse_salary(min_salary_str)
            max_salary = self._parse_salary(max_salary_str)
            
            if min_salary is None:
                return None
            
            # Calculate average if we have a range
            if max_salary and max_salary > min_salary:
                avg_salary = (min_salary + max_salary) / 2
            else:
                avg_salary = min_salary
            
            return {
                'job_title': role,
                'min_salary': min_salary,
                'max_salary': max_salary,
                'avg_salary': avg_salary,
                'country': country,
                'source_name': source_name,
                'source_type': 'salary_guide',
                'extraction_timestamp': timestamp
            }
            
        except Exception as e:
            logger.debug(f"Error parsing row: {str(e)}")
            return None
    
    def _parse_salary(self, salary_str: Optional[str]) -> Optional[float]:
        """
        Parse salary string to float value.
        
        Args:
            salary_str: Salary string (e.g., "$80,000", "80000", "80K")
            
        Returns:
            Parsed salary value or None
        """
        if not salary_str:
            return None
        
        try:
            # Remove common currency symbols and characters
            cleaned = salary_str.replace('$', '').replace('€', '').replace('£', '')
            cleaned = cleaned.replace(',', '').replace(' ', '').strip()
            
            # Handle K (thousands) and M (millions)
            multiplier = 1
            if cleaned.endswith('K') or cleaned.endswith('k'):
                multiplier = 1000
                cleaned = cleaned[:-1]
            elif cleaned.endswith('M') or cleaned.endswith('m'):
                multiplier = 1000000
                cleaned = cleaned[:-1]
            
            value = float(cleaned) * multiplier
            return value
            
        except (ValueError, AttributeError):
            return None


def extract_salary_guide(
    pdf_path: str,
    source_name: str,
    country: str
) -> List[Dict[str, Any]]:
    """
    Convenience function to extract data from a salary guide PDF.
    
    Args:
        pdf_path: Path to PDF file
        source_name: Name of the source
        country: Country
        
    Returns:
        List of extracted records
    """
    extractor = SalaryGuideExtractor()
    return extractor.extract_from_pdf(pdf_path, source_name, country)
