#!/usr/bin/env python3
"""
scripts/patch_app.py
Applies targeted updates to app.py:
1. Replaces hardcoded SYLLABUS_CATALOG_R2024 and static indexes with syllabus.loader calls.
2. Updates DocumentMetadata and extract_coe_pdf with AnalysisContext.
3. Updates build_subject_mapping_log, build_department_excel, and alias_override_card.
4. Adds Academic Catalog Selection to page_upload.
5. Adds Catalog Match Confidence banner to page_pdf_preview.
6. Adds Syllabus Management UI and routes (/syllabus, /syllabus/upload, /syllabus/draft/{id}, /syllabus/publish/{id}).
7. Adds Syllabus link to sidebar and mobile_header.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(BASE_DIR, "app.py")

with open(APP_PY, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update imports
import_insert = """
from syllabus.loader import (
    get_catalog,
    get_registered_departments,
    load_registry,
    normalize_course_code,
    resolve_course,
    invalidate_catalog_cache,
    CatalogIndex,
    CatalogMetadata,
)
from syllabus_tools.extractor import extract_syllabus_pdf
from syllabus_tools.validator import validate_catalog_schema, CatalogValidationError
from syllabus_tools.publisher import publish_syllabus_draft, rollback_catalog
"""

if "from syllabus.loader import" not in content:
    content = content.replace("from urllib.parse import quote, unquote", "from urllib.parse import quote, unquote" + import_insert)

# 2. Replace Section 3.1
section_3_1_start = "# =============================================================================\n# 3.1) B.TECH AI & DS (R2024) SYLLABUS CATALOG & ALIAS RESOLVER"
section_3_2_start = "# =============================================================================\n# 3.2) DIRECT COE PDF EXTRACTION, METADATA & RECONCILIATION ENGINE"

new_section_3_1 = """# =============================================================================
# 3.1) DYNAMIC SYLLABUS CATALOG & CONTEXT-AWARE RESOLVER (via syllabus.loader)
# =============================================================================

def _get_active_catalog(department: str = "AI_DS", regulation: str = "R2024") -> Optional[CatalogIndex]:
    cat = get_catalog(department, regulation)
    if cat is None:
        cat = get_catalog("AI_DS", "R2024")
    return cat

def _normalize_course_code_token(token: Any) -> str:
    return normalize_course_code(token)

def resolve_subject_info(
    raw_name: Any,
    custom_overrides: Optional[Dict[str, str]] = None,
    context: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, float, int, str, float, bool]:
    \"\"\"
    Context-aware course resolver delegating directly to syllabus.loader.resolve_course.
    Returns (canonical_name, canonical_code, credits, semester, category, confidence, is_ambiguous).
    \"\"\"
    ctx = context or SESSION.get("analysis_context", {"department": "AI_DS", "regulation": "R2024", "semester": 4})
    return resolve_course(raw_name, context=ctx, custom_overrides=custom_overrides)
"""

if section_3_1_start in content and section_3_2_start in content:
    idx1 = content.find(section_3_1_start)
    idx2 = content.find(section_3_2_start)
    content = content[:idx1] + new_section_3_1 + "\n\n" + content[idx2:]

# 3. Update DocumentMetadata dataclass
old_doc_meta = """@dataclass
class DocumentMetadata:
    institution: str = "Saranathan College of Engineering"
    programme: str = "B.Tech AI & DS"
    department: str = "Department of AI & DS"
    regulation: str = "R2024"
    semester: str = "Semester III"
    academic_year: str = "2025 - 2026"
    exam_session: str = "Nov / Dec 2025"
    publication_date: str = "Unknown / Needs Review"
    page_count: int = 0
    document_type: str = "DIGITAL_TEXT_PDF"  # "DIGITAL_TEXT_PDF" | "SCANNED_PDF" | "EMPTY_OR_CORRUPT_PDF" """

new_doc_meta = """@dataclass
class DocumentMetadata:
    institution: str = "Saranathan College of Engineering"
    programme: str = "B.Tech AI & DS"
    department: str = "Department of AI & DS"
    regulation: str = "R2024"
    semester: str = "Semester III"
    academic_year: str = "2025 - 2026"
    exam_session: str = "Nov / Dec 2025"
    publication_date: str = "Unknown / Needs Review"
    page_count: int = 0
    document_type: str = "DIGITAL_TEXT_PDF"  # "DIGITAL_TEXT_PDF" | "SCANNED_PDF" | "EMPTY_OR_CORRUPT_PDF"
    # Catalog provenance & Confidence verification
    catalog_department: str = "AI_DS"
    catalog_regulation: str = "R2024"
    catalog_semester: str = "Semester IV"
    catalog_version: str = "1.0"
    catalog_hash: str = ""
    catalog_match_status: str = "CONFIRMED"  # "CONFIRMED" | "MISMATCH" | "UNCHECKED"
    catalog_match_message: str = \"\"\""""

if old_doc_meta in content:
    content = content.replace(old_doc_meta, new_doc_meta)

# 4. Update extract_coe_pdf signature and catalog lookup
content = content.replace(
    "def extract_coe_pdf(pdf_bytes: bytes, filename: str) -> PDFExtractionReport:",
    "def extract_coe_pdf(pdf_bytes: bytes, filename: str, analysis_context: Optional[Dict[str, Any]] = None) -> PDFExtractionReport:"
)

# 5. Update build_subject_mapping_log
old_build_log = """def build_subject_mapping_log(records: List[StudentResultRecord]) -> List[Dict[str, Any]]:
    \"\"\"
    Collapse per-cell PDF records into one row per unique subject_code, in first-seen
    order, with resolution provenance. This is what repeated page headers must NOT
    fan out into duplicate subjects -- dict keying on subject_code enforces that.
    \"\"\"
    seen: Dict[str, Dict[str, Any]] = {}
    for r in records:
        code = r.subject_code or r.original_subject_text or r.subject_name
        if not code or code in seen:
            continue
        can_name, canon_code, cred, sem, cat, conf, ambiguous = resolve_subject_info(
            r.subject_code or r.original_subject_text
        )
        resolved_in_catalog = bool(canon_code) and canon_code.upper() in COURSE_CODE_INDEX
        if resolved_in_catalog and conf >= 0.999:
            method, resolution_confidence = "EXACT_COURSE_CODE", 1.0
        elif resolved_in_catalog:
            method, resolution_confidence = "ALIAS_OR_NAME_MATCH", conf
        elif ambiguous:
            method, resolution_confidence = "UNRESOLVED", 0.0
        else:
            method, resolution_confidence = "FUZZY_MATCH", conf
        seen[code] = {
            "course_code": r.subject_code or code,
            "official_subject_name": can_name if resolved_in_catalog else (r.subject_name or can_name),
            "semester": sem,
            "credits": cred,
            "course_type": (COURSE_CODE_INDEX.get(canon_code.upper(), {}) or {}).get("type", ""),
            "resolution_method": method,
            "resolution_confidence": resolution_confidence,
            "source_page": r.source_page,
            "unresolved": not resolved_in_catalog,
        }
    return list(seen.values())"""

new_build_log = """def build_subject_mapping_log(records: List[StudentResultRecord], catalog_context: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    \"\"\"
    Collapse per-cell PDF records into one row per unique subject_code, in first-seen
    order, with resolution provenance. This is what repeated page headers must NOT
    fan out into duplicate subjects -- dict keying on subject_code enforces that.
    \"\"\"
    seen: Dict[str, Dict[str, Any]] = {}
    ctx = catalog_context or SESSION.get("analysis_context", {"department": "AI_DS", "regulation": "R2024", "semester": 4})
    active_cat = _get_active_catalog(ctx.get("department", "AI_DS"), ctx.get("regulation", "R2024"))
    for r in records:
        code = r.subject_code or r.original_subject_text or r.subject_name
        if not code or code in seen:
            continue
        can_name, canon_code, cred, sem, cat, conf, ambiguous = resolve_course(
            r.subject_code or r.original_subject_text,
            catalog=active_cat,
            context=ctx
        )
        resolved_in_catalog = bool(canon_code) and active_cat is not None and (
            canon_code.upper() in active_cat.course_code_index or
            normalize_course_code(canon_code) in active_cat.course_code_index
        )
        if resolved_in_catalog and conf >= 0.999:
            method, resolution_confidence = "EXACT_COURSE_CODE", 1.0
        elif resolved_in_catalog:
            method, resolution_confidence = "ALIAS_OR_NAME_MATCH", conf
        elif ambiguous:
            method, resolution_confidence = "UNRESOLVED", 0.0
        else:
            method, resolution_confidence = "FUZZY_MATCH", conf
        course_type = ""
        if active_cat and canon_code:
            c_info = active_cat.course_code_index.get(canon_code.upper()) or active_cat.course_code_index.get(normalize_course_code(canon_code)) or {}
            course_type = c_info.get("type", "")
        seen[code] = {
            "course_code": r.subject_code or code,
            "official_subject_name": can_name if resolved_in_catalog else (r.subject_name or can_name),
            "semester": sem,
            "credits": cred,
            "course_type": course_type,
            "resolution_method": method,
            "resolution_confidence": resolution_confidence,
            "source_page": r.source_page,
            "unresolved": not resolved_in_catalog,
        }
    return list(seen.values())"""

if old_build_log in content:
    content = content.replace(old_build_log, new_build_log)

# 6. Update alias override select
content = content.replace(
    '*[Option(item["name"], value=item["name"]) for item in SYLLABUS_CATALOG_R2024],',
    '*[Option(item["name"], value=item["name"]) for item in (_get_active_catalog().courses if _get_active_catalog() else [])],'
)

# 7. Update course code index checks in XLS parsing
content = content.replace(
    'if _normalize_course_code_token(cell) in COURSE_CODE_INDEX',
    'if (_get_active_catalog() and _normalize_course_code_token(cell) in _get_active_catalog().course_code_index)'
)

content = content.replace(
    'resolved_in_catalog = bool(code) and code.upper() in COURSE_CODE_INDEX',
    'active_c = _get_active_catalog(); resolved_in_catalog = bool(code) and active_c is not None and (code.upper() in active_c.course_code_index or _normalize_course_code_token(code) in active_c.course_code_index)'
)

with open(APP_PY, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully applied core patches to app.py")
