"""
syllabus_tools/publisher.py
Validates, archives prior versions into versions/, generates catalog SHA-256 hash,
publishes active JSON catalog, updates registry.json catalog map, and supports rollback.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple

from syllabus_tools.validator import validate_catalog_schema, CatalogValidationError
from syllabus.loader import invalidate_catalog_cache, REGISTRY_PATH, SYLLABUS_DIR


def publish_syllabus_draft(
    draft_data: Dict[str, Any],
    actor: str = "Faculty Academic Committee"
) -> Dict[str, Any]:
    """
    Validates, archives prior version, publishes new JSON catalog,
    updates registry.json, and invalidates cache.
    """
    # 1. Validation Gate
    is_valid, issues = validate_catalog_schema(draft_data)
    if not is_valid:
        raise CatalogValidationError(issues)

    dept_code = str(draft_data["department_code"]).strip().upper()
    dept_folder_name = dept_code.lower()
    reg = str(draft_data["regulation"]).strip().upper()
    reg_filename = f"{reg.lower()}.json"

    dept_dir = os.path.join(SYLLABUS_DIR, dept_folder_name)
    versions_dir = os.path.join(dept_dir, "versions")
    os.makedirs(dept_dir, exist_ok=True)
    os.makedirs(versions_dir, exist_ok=True)
    target_catalog_path = os.path.join(dept_dir, reg_filename)

    # 2. Version Preservation (Archive existing if present)
    prior_version_archived = None
    next_ver_num = 1
    if os.path.isfile(target_catalog_path):
        try:
            with open(target_catalog_path, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            old_ver = old_data.get("catalog_version", "1.0")
            existing_versions = [f for f in os.listdir(versions_dir) if f.startswith(f"{reg.lower()}_v")]
            next_ver_num = len(existing_versions) + 1
            archive_filename = f"{reg.lower()}_v{next_ver_num}.json"
            archive_path = os.path.join(versions_dir, archive_filename)
            shutil.copy2(target_catalog_path, archive_path)
            prior_version_archived = archive_filename
        except Exception:
            pass

    # 3. Clean and build final catalog data
    courses_cleaned = []
    for c in draft_data.get("courses", []):
        code = str(c.get("code", "")).strip().upper()
        course_id = c.get("id") or f"{dept_code}_{reg}_{code}"
        courses_cleaned.append({
            "id": course_id,
            "code": code,
            "name": str(c.get("name", "")).strip(),
            "short_name": c.get("short_name", ""),
            "semester": int(c.get("semester", 1)),
            "credits": float(c.get("credits", 3.0)),
            "type": c.get("type", "THEORY"),
            "category": c.get("category", "Sem 1-4 Foundation" if int(c.get("semester", 1)) <= 4 else "Sem 5-8 Advanced"),
            "aliases": c.get("aliases", [])
        })

    if prior_version_archived:
        pub_version = f"{next_ver_num + 1}.0"
    else:
        pub_version = draft_data.get("catalog_version", "1.0").replace("-draft", "")

    created_date = time.strftime("%Y-%m-%d")

    final_catalog = {
        "catalog_version": pub_version,
        "catalog_hash": "",
        "status": "ACTIVE",
        "department": draft_data.get("department", dept_code),
        "department_code": dept_code,
        "programme": draft_data.get("programme", draft_data.get("department", dept_code)),
        "regulation": reg,
        "source": draft_data.get("source", f"{draft_data.get('department', dept_code)} {reg} Curriculum"),
        "approved_by": actor,
        "created_date": created_date,
        "academic_structure": draft_data.get("academic_structure", {"semesters": 8}),
        "courses": courses_cleaned
    }

    # Generate SHA-256 hash
    content_for_hash = json.dumps({k: v for k, v in final_catalog.items() if k != "catalog_hash"}, sort_keys=True)
    catalog_hash = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()
    final_catalog["catalog_hash"] = catalog_hash

    # Write target catalog
    with open(target_catalog_path, "w", encoding="utf-8") as f:
        json.dump(final_catalog, f, indent=2, ensure_ascii=False)

    # 4. Update registry.json
    if os.path.isfile(REGISTRY_PATH):
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                registry = json.load(f)

            depts = registry.get("departments", [])
            dept_found = False
            for d in depts:
                if d.get("code", "").upper() == dept_code:
                    dept_found = True
                    catalogs = d.setdefault("catalogs", {})
                    catalogs[reg] = {
                        "status": "ACTIVE",
                        "file": f"{dept_folder_name}/{reg_filename}",
                        "version": pub_version,
                        "hash": catalog_hash,
                        "published_at": created_date
                    }
                    break

            if not dept_found:
                depts.append({
                    "code": dept_code,
                    "name": final_catalog["department"],
                    "programme": final_catalog["programme"],
                    "catalogs": {
                        reg: {
                            "status": "ACTIVE",
                            "file": f"{dept_folder_name}/{reg_filename}",
                            "version": pub_version,
                            "hash": catalog_hash,
                            "published_at": created_date
                        }
                    }
                })

            registry["departments"] = depts
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # 5. Dynamic Cache Invalidation
    invalidate_catalog_cache(dept_code, reg)

    return {
        "status": "PUBLISHED",
        "department_code": dept_code,
        "regulation": reg,
        "catalog_version": pub_version,
        "catalog_hash": catalog_hash,
        "catalog_path": target_catalog_path,
        "archived_prior": prior_version_archived,
        "course_count": len(final_catalog["courses"])
    }


def rollback_catalog(
    dept_code: str,
    regulation: str,
    version_filename: str
) -> Dict[str, Any]:
    """
    Rolls back the active catalog to a specified archived version.
    """
    dept_folder = dept_code.strip().lower()
    reg_clean = regulation.strip().upper()
    dept_dir = os.path.join(SYLLABUS_DIR, dept_folder)
    versions_dir = os.path.join(dept_dir, "versions")
    version_path = os.path.join(versions_dir, version_filename)
    active_path = os.path.join(dept_dir, f"{reg_clean.lower()}.json")

    if not os.path.isfile(version_path):
        raise FileNotFoundError(f"Version file {version_path} not found.")

    # Archive current before rollback
    ts = int(time.time())
    if os.path.isfile(active_path):
        shutil.copy2(active_path, os.path.join(versions_dir, f"{reg_clean.lower()}_prerollback_{ts}.json"))

    # Restore
    shutil.copy2(version_path, active_path)

    with open(active_path, "r", encoding="utf-8") as f:
        restored_data = json.load(f)

    # Invalidate cache
    invalidate_catalog_cache(dept_code, reg_clean)

    return {
        "status": "ROLLED_BACK",
        "department_code": dept_code,
        "regulation": reg_clean,
        "restored_version": restored_data.get("catalog_version"),
        "restored_hash": restored_data.get("catalog_hash")
    }
