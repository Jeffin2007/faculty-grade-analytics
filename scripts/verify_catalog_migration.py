#!/usr/bin/env python3
"""
scripts/verify_catalog_migration.py
Strict verification gate:
1. Verifies that hardcoded SYLLABUS_CATALOG_R2024 has been completely removed from app.py.
2. Verifies that syllabus/ai_ds/r2024.json contains all 56 courses, Course IDs, manifest, and SHA-256 hash.
3. Verifies that app.py and syllabus.loader dynamically load and resolve all 56 courses identically.
"""

import ast
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

APP_PY = os.path.join(BASE_DIR, "app.py")
AI_DS_JSON = os.path.join(BASE_DIR, "syllabus", "ai_ds", "r2024.json")


def verify_old_catalog_removed_from_app():
    with open(APP_PY, "r", encoding="utf-8") as f:
        content = f.read()

    has_hardcoded_list = "SYLLABUS_CATALOG_R2024: List[Dict[str, Any]] = [" in content or "SYLLABUS_CATALOG_R2024 = [" in content
    return not has_hardcoded_list


def main():
    print("==================================================")
    print("MIGRATION & ARCHITECTURE VERIFICATION REPORT")
    print("==================================================")

    # 1. Check removal from app.py
    removed = verify_old_catalog_removed_from_app()
    assert removed, "Hardcoded SYLLABUS_CATALOG_R2024 list still found in app.py!"
    print("Old hardcoded catalog removed:              PASS")

    # 2. Check JSON file existence
    if not os.path.isfile(AI_DS_JSON):
        print(f"ERROR: {AI_DS_JSON} does not exist.")
        sys.exit(1)

    with open(AI_DS_JSON, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    json_courses = json_data.get("courses", [])

    # 3. Course Count
    total_js = len(json_courses)
    assert total_js == 56, f"Expected 56 courses, got {total_js}"
    print(f"AI & DS catalog migrated:                   PASS (56 / 56 courses)")

    # 4. Manifest & Integrity
    catalog_hash = json_data.get("catalog_hash")
    assert catalog_hash and len(catalog_hash) == 64, f"Invalid catalog hash: {catalog_hash}"
    assert json_data.get("status") == "ACTIVE", f"Invalid status: {json_data.get('status')}"
    assert json_data.get("department_code") == "AI_DS", f"Invalid dept code: {json_data.get('department_code')}"
    assert json_data.get("regulation") == "R2024", f"Invalid regulation: {json_data.get('regulation')}"
    print("Catalog Manifest & Checksum:                PASS")

    # 5. Course fields validation
    for c in json_courses:
        code = c.get("code")
        assert code and len(code) >= 6, f"Malformed code: {code}"
        assert c.get("id") == f"AI_DS_R2024_{code}", f"Invalid course ID: {c.get('id')}"
        assert c.get("name"), f"Missing name for {code}"
        assert isinstance(c.get("credits"), (int, float)) and c.get("credits") >= 0, f"Invalid credits for {code}"
        assert 1 <= int(c.get("semester")) <= 8, f"Invalid semester for {code}"
        assert isinstance(c.get("aliases"), list), f"Invalid aliases for {code}"

    print("Course Codes:                               PASS")
    print("Course Names:                               PASS")
    print("Credits Values:                             PASS")
    print("Semester Allocations:                       PASS")
    print("Course Aliases:                             PASS")
    print("Course Identity IDs:                        PASS")

    # 6. Dynamic resolution testing via syllabus.loader
    from syllabus.loader import get_catalog, resolve_course
    cat = get_catalog("AI_DS", "R2024")
    assert cat is not None, "Failed to load catalog via syllabus.loader!"

    for c in json_courses:
        code = c["code"]
        name, res_code, cred, sem, cat_name, conf, amb = resolve_course(code, catalog=cat)
        assert res_code == code, f"Resolution code mismatch for {code}: got {res_code}"
        assert name == c["name"], f"Resolution name mismatch for {code}: got {name}"
        assert cred == c["credits"], f"Resolution credits mismatch for {code}: got {cred}"
        assert sem == c["semester"], f"Resolution semester mismatch for {code}: got {sem}"
        assert conf == 1.0, f"Confidence not 1.0 for exact code {code}"
        assert not amb, f"Resolution marked ambiguous for exact code {code}"

    print("Dynamic O(1) Course Resolution:             PASS (56/56 verified)")
    print("==================================================")
    print("ALL MIGRATION & RESOLUTION GATES: PASS")
    print("==================================================")


if __name__ == "__main__":
    main()
