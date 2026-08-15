#!/usr/bin/env python3
"""
scripts/migrate_catalog.py
Extracts the hardcoded SYLLABUS_CATALOG_R2024 from app.py and writes
syllabus/ai_ds/r2024.json (with course identity IDs and catalog manifest)
and syllabus/registry.json (with catalog map per department).
"""

import ast
import json
import os
import hashlib
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(BASE_DIR, "app.py")
SYLLABUS_DIR = os.path.join(BASE_DIR, "syllabus")
DRAFTS_DIR = os.path.join(BASE_DIR, "syllabus_drafts")


def extract_app_catalog():
    with open(APP_PY, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename="app.py")

    catalog = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "SYLLABUS_CATALOG_R2024":
            catalog = ast.literal_eval(node.value)
            break
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if getattr(target, "id", "") == "SYLLABUS_CATALOG_R2024":
                    catalog = ast.literal_eval(node.value)
                    break

    if catalog is None:
        raise RuntimeError("Could not locate SYLLABUS_CATALOG_R2024 in app.py")

    return catalog


def main():
    catalog_courses = extract_app_catalog()
    print(f"Extracted {len(catalog_courses)} courses from app.py")

    # Create department folders and versions subfolders
    depts = ["ai_ds", "cse", "aiml", "civil", "csbs", "ece", "eee", "ice", "it", "mech"]
    for d in depts:
        os.makedirs(os.path.join(SYLLABUS_DIR, d), exist_ok=True)
        os.makedirs(os.path.join(SYLLABUS_DIR, d, "versions"), exist_ok=True)
    os.makedirs(DRAFTS_DIR, exist_ok=True)

    # Add Course Identity ID: e.g. AI_DS_R2024_24AD401
    enriched_courses = []
    for c in catalog_courses:
        code = c["code"]
        course_id = f"AI_DS_R2024_{code}"
        entry = {
            "id": course_id,
            "code": code,
            "name": c["name"],
            "short_name": c.get("short_name", ""),
            "semester": c["semester"],
            "credits": float(c["credits"]),
            "type": c.get("type", "THEORY" if c["credits"] >= 2 else "LAB"),
            "category": c.get("category", "Sem 1-4 Foundation" if c["semester"] <= 4 else "Sem 5-8 Advanced"),
            "aliases": c.get("aliases", [])
        }
        enriched_courses.append(entry)

    # Initial data without hash
    ai_ds_data = {
        "catalog_version": "1.0",
        "catalog_hash": "",
        "status": "ACTIVE",
        "department": "Artificial Intelligence and Data Science",
        "department_code": "AI_DS",
        "programme": "B.Tech. - Artificial Intelligence and Data Science",
        "regulation": "R2024",
        "source": "B.Tech AI & DS R2024 Curriculum",
        "approved_by": "Faculty Academic Committee",
        "created_date": "2026-08-14",
        "academic_structure": {
            "semesters": 8
        },
        "courses": enriched_courses
    }

    # Compute deterministic SHA256 of content
    content_for_hash = json.dumps({k: v for k, v in ai_ds_data.items() if k != "catalog_hash"}, sort_keys=True)
    catalog_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
    ai_ds_data["catalog_hash"] = catalog_hash

    ai_ds_json_path = os.path.join(SYLLABUS_DIR, "ai_ds", "r2024.json")
    with open(ai_ds_json_path, "w", encoding="utf-8") as f:
        json.dump(ai_ds_data, f, indent=2, ensure_ascii=False)

    # Also archive v1
    v1_path = os.path.join(SYLLABUS_DIR, "ai_ds", "versions", "r2024_v1.json")
    with open(v1_path, "w", encoding="utf-8") as f:
        json.dump(ai_ds_data, f, indent=2, ensure_ascii=False)

    print(f"Wrote {ai_ds_json_path} (Hash: {catalog_hash[:12]}...)")

    # Build registry.json with structured catalogs map
    departments_meta = [
        {
            "code": "AI_DS",
            "name": "Artificial Intelligence and Data Science",
            "programme": "B.Tech. - Artificial Intelligence and Data Science",
            "catalogs": {
                "R2024": {
                    "status": "ACTIVE",
                    "file": "ai_ds/r2024.json",
                    "version": "1.0",
                    "hash": catalog_hash,
                    "published_at": "2026-08-14"
                }
            }
        },
        {
            "code": "AIML",
            "name": "CSE (Artificial Intelligence and Machine Learning)",
            "programme": "B.E - CSE (Artificial Intelligence and Machine Learning)",
            "catalogs": {}
        },
        {
            "code": "CIVIL",
            "name": "Civil Engineering",
            "programme": "B.E. - Civil Engineering",
            "catalogs": {}
        },
        {
            "code": "CSBS",
            "name": "Computer Science & Business System",
            "programme": "B.Tech. - Computer Science & Business System",
            "catalogs": {}
        },
        {
            "code": "CSE",
            "name": "Computer Science and Engineering",
            "programme": "B.E. - Computer Science and Engineering",
            "catalogs": {}
        },
        {
            "code": "ECE",
            "name": "Electronics and Communication Engineering",
            "programme": "B.E. - Electronics and Communication Engineering",
            "catalogs": {}
        },
        {
            "code": "EEE",
            "name": "Electrical and Electronics Engineering",
            "programme": "B.E. - Electrical and Electronics Engineering",
            "catalogs": {}
        },
        {
            "code": "ICE",
            "name": "Instrumentation and Control Engineering",
            "programme": "B.E. - Instrumentation and Control Engineering",
            "catalogs": {}
        },
        {
            "code": "IT",
            "name": "Information Technology",
            "programme": "B.Tech. - Information Technology",
            "catalogs": {}
        },
        {
            "code": "MECH",
            "name": "Mechanical Engineering",
            "programme": "B.E. - Mechanical Engineering",
            "catalogs": {}
        }
    ]

    registry_data = {
        "version": "1.0",
        "institution": "Saranathan College of Engineering",
        "departments": departments_meta
    }

    registry_path = os.path.join(SYLLABUS_DIR, "registry.json")
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry_data, f, indent=2, ensure_ascii=False)

    print(f"Wrote {registry_path}")


if __name__ == "__main__":
    main()
