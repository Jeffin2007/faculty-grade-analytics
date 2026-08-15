"""
syllabus/loader.py
================================================================================
Dynamic Syllabus Catalog Loader and Resolution Engine
================================================================================
Independent module (Zero dependencies on app.py).
Responsibilities:
1. Load registry.json to discover available departments and regulations.
2. Load, validate, and index department regulation JSON catalogs.
3. Build O(1) in-memory lookup indexes (Course Code, Subject Name, Alias, Semester).
4. Perform strict, context-aware course resolution with priority:
   - Overrides -> Exact Normalized Code -> Code Alias -> Exact Subject Name -> Subject Alias -> Fuzzy -> Unresolved.
5. Invalidate caches dynamically without requiring server restart.
"""

from __future__ import annotations

import difflib
import functools
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

SYLLABUS_DIR = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(SYLLABUS_DIR, "registry.json")

_CACHE_LOCK = threading.Lock()
_CATALOG_CACHE: Dict[Tuple[str, str], CatalogIndex] = {}


@dataclass
class CatalogMetadata:
    department_code: str
    department_name: str
    programme: str
    regulation: str
    catalog_version: str
    sha256_hash: str
    status: str
    course_count: int
    filepath: str


@dataclass
class CatalogIndex:
    metadata: CatalogMetadata
    raw_data: Dict[str, Any]
    courses: List[Dict[str, Any]]
    course_code_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    subject_name_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    subject_name_multi_index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    alias_index: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    alias_multi_index: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    semester_index: Dict[int, List[Dict[str, Any]]] = field(default_factory=dict)


def normalize_course_code(code: Any) -> str:
    """
    Normalize course code tokens into canonical uppercase alphanumeric format.
    Example: '24-AD-401' -> '24AD401', '24 AD 401' -> '24AD401'.
    Never reorders characters.
    """
    if not code:
        return ""
    token = str(code).strip().upper()
    return re.sub(r"[^A-Z0-9]", "", token)


def normalize_text(text: Any) -> str:
    """Normalize text with single whitespace and uppercase."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip()).upper()


def normalize_alphanumeric(text: Any) -> str:
    """Strip all non-alphanumeric characters and uppercase."""
    if not text:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(text).strip().upper())


def load_registry(force_reload: bool = False) -> Dict[str, Any]:
    """Load the central registry.json file."""
    if not os.path.isfile(REGISTRY_PATH):
        return {"version": "1.0", "departments": []}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_registered_departments() -> List[Dict[str, Any]]:
    """Return a list of all registered departments from registry.json."""
    data = load_registry()
    depts = data.get("departments", [])
    # Format available regulations for easy UI consumption
    for d in depts:
        catalogs = d.get("catalogs", {})
        d["catalog_available"] = bool(catalogs and any(c.get("status") == "ACTIVE" for c in catalogs.values()))
        d["available_regulations"] = list(catalogs.keys())
        d["active_regulation"] = next((r for r, c in catalogs.items() if c.get("status") == "ACTIVE"), None)
    return depts


def invalidate_catalog_cache(department_code: Optional[str] = None, regulation: Optional[str] = None) -> None:
    """
    Invalidate in-memory catalog and resolution caches.
    If department_code and regulation are provided, evicts that entry.
    Otherwise, evicts all cached catalogs.
    """
    with _CACHE_LOCK:
        if department_code and regulation:
            key = (department_code.strip().upper(), regulation.strip().upper())
            _CATALOG_CACHE.pop(key, None)
        else:
            _CATALOG_CACHE.clear()
    _memoized_resolve_course.cache_clear()


def get_catalog(
    department_code: str = "AI_DS",
    regulation: str = "R2024",
    force_reload: bool = False
) -> Optional[CatalogIndex]:
    """
    Load, validate, index, and cache a department regulation syllabus catalog.
    Thread-safe and fast O(1) indexed access.
    """
    dept_clean = department_code.strip().upper()
    reg_clean = regulation.strip().upper()
    cache_key = (dept_clean, reg_clean)

    with _CACHE_LOCK:
        if not force_reload and cache_key in _CATALOG_CACHE:
            return _CATALOG_CACHE[cache_key]

    dept_folder = dept_clean.lower()
    reg_filename = f"{reg_clean.lower()}.json"
    catalog_path = os.path.join(SYLLABUS_DIR, dept_folder, reg_filename)

    if not os.path.isfile(catalog_path):
        alt_folder = re.sub(r"[^a-z0-9]", "_", dept_folder)
        catalog_path_alt = os.path.join(SYLLABUS_DIR, alt_folder, reg_filename)
        if os.path.isfile(catalog_path_alt):
            catalog_path = catalog_path_alt
        else:
            return None

    try:
        with open(catalog_path, "rb") as f:
            raw_bytes = f.read()

        data = json.loads(raw_bytes.decode("utf-8"))
        sha256_hash = data.get("catalog_hash") or hashlib.sha256(raw_bytes).hexdigest()
    except Exception as e:
        raise RuntimeError(f"Failed to read syllabus catalog at {catalog_path}: {e}")

    courses = data.get("courses", [])
    dept_name = data.get("department", dept_clean)
    programme = data.get("programme", dept_name)
    version = data.get("catalog_version", "1.0")
    status = data.get("status", "ACTIVE")

    metadata = CatalogMetadata(
        department_code=dept_clean,
        department_name=dept_name,
        programme=programme,
        regulation=reg_clean,
        catalog_version=version,
        sha256_hash=sha256_hash,
        status=status,
        course_count=len(courses),
        filepath=catalog_path
    )

    catalog_index = CatalogIndex(
        metadata=metadata,
        raw_data=data,
        courses=courses
    )

    # Build O(1) lookup tables
    for item in courses:
        code_raw = str(item.get("code", "")).strip().upper()
        code_clean = normalize_course_code(code_raw)
        if code_raw:
            catalog_index.course_code_index[code_raw] = item
        if code_clean:
            catalog_index.course_code_index[code_clean] = item

        name_upper = normalize_text(item.get("name", ""))
        name_clean = normalize_alphanumeric(name_upper)
        if name_upper:
            catalog_index.subject_name_index[name_upper] = item
            catalog_index.subject_name_multi_index.setdefault(name_upper, []).append(item)
        if name_clean:
            catalog_index.subject_name_index[name_clean] = item
            catalog_index.subject_name_multi_index.setdefault(name_clean, []).append(item)

        for alias in item.get("aliases", []):
            alias_upper = normalize_text(alias)
            alias_clean = normalize_alphanumeric(alias_upper)
            if alias_upper:
                catalog_index.alias_index[alias_upper] = item
                catalog_index.alias_multi_index.setdefault(alias_upper, []).append(item)
            if alias_clean:
                catalog_index.alias_index[alias_clean] = item
                catalog_index.alias_multi_index.setdefault(alias_clean, []).append(item)

        sem = int(item.get("semester", 1))
        catalog_index.semester_index.setdefault(sem, []).append(item)

    with _CACHE_LOCK:
        _CATALOG_CACHE[cache_key] = catalog_index

    return catalog_index


@functools.lru_cache(maxsize=4096)
def _memoized_resolve_course(
    norm: str,
    clean_code: str,
    catalog_hash: str,
    dept_code: str,
    target_sem: int,
    reg_code: str
) -> Tuple[str, str, float, int, str, float, bool]:
    """
    Internal LRU-memoized resolver keyed by catalog SHA256 hash.
    """
    key = (dept_code, reg_code)
    catalog = _CATALOG_CACHE.get(key)
    if not catalog:
        catalog = get_catalog(dept_code, reg_code)
        if not catalog:
            return (norm, clean_code or norm, 3.0, target_sem or 1, "Uncategorized", 0.0, True)

    def _select_best_semester(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not items:
            return {}
        if len(items) == 1:
            return items[0]
        if target_sem:
            # 1. Prioritize current target semester
            for it in items:
                if it.get("semester") == target_sem:
                    return it
            # 2. Prioritize previous semesters (arrear courses) in descending order
            for sem in range(target_sem - 1, 0, -1):
                for it in items:
                    if it.get("semester") == sem:
                        return it
            # 3. Otherwise subsequent semesters
            for sem in range(target_sem + 1, 9):
                for it in items:
                    if it.get("semester") == sem:
                        return it
        return items[0]

    # 1. Exact / Normalized Course Code (O(1))
    if norm in catalog.course_code_index:
        item = catalog.course_code_index[norm]
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    if clean_code in catalog.course_code_index:
        item = catalog.course_code_index[clean_code]
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    # 1b. R24 <-> R26 Course Code Variant (trailing 'A' equivalence e.g. 24CH402 <-> 24CH402A)
    if clean_code.endswith("A") and len(clean_code) > 4 and clean_code[-2].isdigit():
        base_c = clean_code[:-1]
        if base_c in catalog.course_code_index:
            item = catalog.course_code_index[base_c]
            return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)
        if base_c in catalog.alias_index:
            item = catalog.alias_index[base_c]
            return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)
    else:
        var_a = f"{clean_code}A"
        if var_a in catalog.course_code_index:
            item = catalog.course_code_index[var_a]
            return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)
        if var_a in catalog.alias_index:
            item = catalog.alias_index[var_a]
            return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)


    # 2. Exact / Normalized Subject Name (O(1)) with semester awareness
    if norm in catalog.subject_name_multi_index:
        item = _select_best_semester(catalog.subject_name_multi_index[norm])
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    if clean_code in catalog.subject_name_multi_index:
        item = _select_best_semester(catalog.subject_name_multi_index[clean_code])
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    # 3. Exact / Normalized Alias (O(1)) with semester awareness
    if norm in catalog.alias_multi_index:
        item = _select_best_semester(catalog.alias_multi_index[norm])
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    if clean_code in catalog.alias_multi_index:
        item = _select_best_semester(catalog.alias_multi_index[clean_code])
        return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Sem 1-4 Foundation"), 1.0, False)

    # 4. Fuzzy Match Fallback (only if exact lookups failed)
    best_item = None
    best_score = 0.0

    for item in catalog.courses:
        s_name = difflib.SequenceMatcher(None, norm, item.get("name", "").upper()).ratio()
        if s_name > best_score:
            best_score = s_name
            best_item = item
        for alias in item.get("aliases", []):
            s_alias = difflib.SequenceMatcher(None, norm, alias.upper()).ratio()
            if s_alias > best_score:
                best_score = s_alias
                best_item = item

    if best_item and best_score >= 0.80:
        return (best_item["name"], best_item["code"], float(best_item.get("credits", 3.0)), int(best_item.get("semester", target_sem or 1)), best_item.get("category", "Sem 1-4 Foundation"), round(best_score, 2), False)
    elif best_item and best_score >= 0.60:
        return (best_item["name"], best_item["code"], float(best_item.get("credits", 3.0)), int(best_item.get("semester", target_sem or 1)), best_item.get("category", "Sem 1-4 Foundation"), round(best_score, 2), True)

    return (norm, clean_code or norm, 3.0, target_sem or 1, "Sem 1-4 Foundation", round(best_score, 2), True)


def resolve_course(
    value: Any,
    catalog: Union[CatalogIndex, str, None] = None,
    context: Optional[Dict[str, Any]] = None,
    custom_overrides: Optional[Dict[str, str]] = None
) -> Tuple[str, str, float, int, str, float, bool]:
    """
    Context-aware course resolver accepting AnalysisContext.
    """
    if not value:
        return ("Unknown Subject", "", 0.0, 0, "Uncategorized", 0.0, True)

    clean_raw = str(value).strip()
    norm = normalize_text(clean_raw)
    clean_code = normalize_alphanumeric(clean_raw)

    ctx = context or {}
    dept = ctx.get("department", "AI_DS")
    reg = ctx.get("regulation", "R2024")
    target_sem = int(ctx.get("semester", 0))

    if isinstance(catalog, str):
        dept = catalog
        active_cat = get_catalog(dept, reg)
    elif isinstance(catalog, CatalogIndex):
        active_cat = catalog
        dept = active_cat.metadata.department_code
        reg = active_cat.metadata.regulation
    else:
        active_cat = get_catalog(dept, reg)

    if not active_cat:
        return (clean_raw, clean_code or clean_raw, 3.0, target_sem or 1, "Uncategorized", 0.0, True)

    # 0. Custom manual overrides
    if custom_overrides and norm in custom_overrides:
        target_name = custom_overrides[norm]
        target_upper = normalize_text(target_name)
        if target_upper in active_cat.subject_name_index:
            item = active_cat.subject_name_index[target_upper]
            return (item["name"], item["code"], float(item.get("credits", 3.0)), int(item.get("semester", target_sem or 1)), item.get("category", "Custom Subject"), 1.0, False)
        return (target_name, "", 3.0, target_sem or 1, "Custom Subject", 1.0, False)

    res = _memoized_resolve_course(
        norm,
        clean_code,
        active_cat.metadata.sha256_hash,
        dept,
        target_sem,
        reg
    )

    if res[0] == norm and not active_cat.course_code_index.get(norm):
        return (clean_raw, clean_code or clean_raw, res[2], res[3], res[4], res[5], res[6])
    return res


def get_expected_subjects(
    department_code: str = "AI_DS",
    regulation: str = "R2024",
    semester: int = 1
) -> Dict[str, Any]:
    """
    Get full subject manifest for a department/regulation and semester:
    - Current semester courses (semester == target_sem)
    - Loaded arrear courses (1 <= semester < target_sem)
    - Electives and advanced courses (semester > target_sem)
    """
    catalog = get_catalog(department_code, regulation)
    if not catalog:
        return {
            "ok": False,
            "department": department_code,
            "regulation": regulation,
            "semester": semester,
            "current_semester_courses": [],
            "arrear_courses": [],
            "other_courses": [],
            "total_courses": 0,
            "message": f"Catalog not found for {department_code} {regulation}"
        }

    sem_int = int(semester) if semester else 1
    current = []
    arrears = []
    others = []

    for c in catalog.courses:
        c_sem = int(c.get("semester", 1))
        c_summary = {
            "id": c.get("id", ""),
            "code": c.get("code", ""),
            "name": c.get("name", ""),
            "semester": c_sem,
            "credits": float(c.get("credits", 3.0)),
            "type": c.get("type", "THEORY"),
            "category": c.get("category", ""),
            "aliases": c.get("aliases", [])
        }
        if c_sem == sem_int:
            current.append(c_summary)
        elif 1 <= c_sem < sem_int:
            arrears.append(c_summary)
        else:
            others.append(c_summary)

    return {
        "ok": True,
        "department": catalog.metadata.department_code,
        "department_name": catalog.metadata.department_name,
        "programme": catalog.metadata.programme,
        "regulation": catalog.metadata.regulation,
        "catalog_version": catalog.metadata.catalog_version,
        "catalog_hash": catalog.metadata.sha256_hash,
        "semester": sem_int,
        "current_semester_courses": current,
        "arrear_courses": arrears,
        "other_courses": others,
        "total_courses": len(catalog.courses),
        "arrear_semesters_loaded": list(range(1, sem_int)) if sem_int > 1 else []
    }

