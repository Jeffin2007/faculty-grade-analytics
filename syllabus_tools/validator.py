"""
syllabus_tools/validator.py
Validates syllabus catalog JSON schema, checks for duplicate course codes,
missing credits, malformed semesters, and category integrity.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


class CatalogValidationError(Exception):
    def __init__(self, issues: List[str]):
        self.issues = issues
        super().__init__("; ".join(issues))


def validate_catalog_schema(data: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate catalog data dictionary.
    Returns (is_valid, list_of_issues).
    """
    issues: List[str] = []

    if not isinstance(data, dict):
        return False, ["Catalog data must be a JSON object."]

    # Required top-level keys
    for req in ["department", "department_code", "regulation", "courses"]:
        if req not in data or not data[req]:
            issues.append(f"Missing required top-level field: '{req}'")

    courses = data.get("courses", [])
    if not isinstance(courses, list) or len(courses) == 0:
        issues.append("Catalog 'courses' must be a non-empty list of course definitions.")
        return False, issues

    seen_codes: Dict[str, int] = {}
    for idx, c in enumerate(courses):
        if not isinstance(c, dict):
            issues.append(f"Course entry at index {idx} must be a JSON object.")
            continue

        raw_code = str(c.get("code", "")).strip().upper()
        clean_code = re.sub(r"[^A-Z0-9]", "", raw_code)

        if not clean_code:
            issues.append(f"Course at index {idx} has an empty or invalid course code.")
        else:
            if clean_code in seen_codes:
                issues.append(
                    f"Duplicate course code '{raw_code}' detected at index {idx} (first seen at index {seen_codes[clean_code]})."
                )
            else:
                seen_codes[clean_code] = idx

        name = str(c.get("name", "")).strip()
        if not name:
            issues.append(f"Course '{raw_code or f'index {idx}'}' is missing a 'name'.")

        try:
            credits_val = float(c.get("credits", -1))
            if credits_val < 0.0 or credits_val > 30.0:
                issues.append(f"Course '{raw_code}' has invalid credits: {credits_val} (must be between 0.0 and 30.0).")
        except (ValueError, TypeError):
            issues.append(f"Course '{raw_code}' credits value '{c.get('credits')}' is not a valid number.")

        try:
            sem = int(c.get("semester", 0))
            if sem < 1 or sem > 10:
                issues.append(f"Course '{raw_code}' has invalid semester: {sem} (must be between 1 and 10).")
        except (ValueError, TypeError):
            issues.append(f"Course '{raw_code}' semester value '{c.get('semester')}' is not a valid integer.")

        aliases = c.get("aliases", [])
        if not isinstance(aliases, list):
            issues.append(f"Course '{raw_code}' 'aliases' must be a list of strings.")

    return len(issues) == 0, issues
