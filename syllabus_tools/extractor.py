"""
syllabus_tools/extractor.py
Deterministic extractor for curriculum & syllabus PDFs.
Extracts Department, Programme, Regulation, Semesters, Course Codes, Course Titles,
Credits, Categories, and Types with confidence scoring and status tracking.
Workflow states: EXTRACTED -> REVIEW_REQUIRED -> APPROVED -> PUBLISHED -> ACTIVE
"""

from __future__ import annotations

import io
import json
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz  # PyMuPDF

ROMAN_TO_INT = {
    "I": 1, "II": 2, "III": 3, "IV": 4,
    "V": 5, "VI": 6, "VII": 7, "VIII": 8,
    "IX": 9, "X": 10,
    "1": 1, "2": 2, "3": 3, "4": 4,
    "5": 5, "6": 6, "7": 7, "8": 8
}

COURSE_CODE_PATTERN = re.compile(r"\b(\d{2}[A-Z]{2,4}\d{3,4})\b")


def extract_syllabus_pdf(
    pdf_source: Union[bytes, str],
    department_code_hint: Optional[str] = None,
    regulation_hint: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extracts course data from a syllabus PDF and writes a draft JSON.
    Returns draft dictionary and file path.
    """
    if isinstance(pdf_source, bytes):
        doc = fitz.open(stream=pdf_source, filetype="pdf")
    else:
        doc = fitz.open(pdf_source)

    if len(doc) == 0:
        raise ValueError("PDF document has 0 pages.")

    # 1. Document metadata extraction from initial pages
    header_text = ""
    for p in range(min(5, len(doc))):
        header_text += doc[p].get_text() + "\n"

    header_upper = header_text.upper()

    # Department detection
    dept_code = department_code_hint or "CUSTOM"
    dept_name = "Department"
    programme = "Undergraduate Programme"

    if "ARTIFICIAL INTELLIGENCE" in header_upper and "DATA SCIENCE" in header_upper:
        dept_code = "AI_DS"
        dept_name = "Artificial Intelligence and Data Science"
        programme = "B.Tech. - Artificial Intelligence and Data Science"
    elif "MACHINE LEARNING" in header_upper or "AIML" in header_upper:
        dept_code = "AIML"
        dept_name = "CSE (Artificial Intelligence and Machine Learning)"
        programme = "B.E - CSE (Artificial Intelligence and Machine Learning)"
    elif "BUSINESS SYSTEM" in header_upper or "CSBS" in header_upper:
        dept_code = "CSBS"
        dept_name = "Computer Science & Business System"
        programme = "B.Tech. - Computer Science & Business System"
    elif "COMPUTER SCIENCE" in header_upper and "ENGINEERING" in header_upper:
        dept_code = "CSE"
        dept_name = "Computer Science and Engineering"
        programme = "B.E. - Computer Science and Engineering"
    elif "ELECTRONICS AND COMMUNICATION" in header_upper or "ECE" in header_upper:
        dept_code = "ECE"
        dept_name = "Electronics and Communication Engineering"
        programme = "B.E. - Electronics and Communication Engineering"
    elif "ELECTRICAL AND ELECTRONICS" in header_upper or "EEE" in header_upper:
        dept_code = "EEE"
        dept_name = "Electrical and Electronics Engineering"
        programme = "B.E. - Electrical and Electronics Engineering"
    elif "INSTRUMENTATION" in header_upper or "ICE" in header_upper:
        dept_code = "ICE"
        dept_name = "Instrumentation and Control Engineering"
        programme = "B.E. - Instrumentation and Control Engineering"
    elif "INFORMATION TECHNOLOGY" in header_upper or "IT" in header_upper:
        dept_code = "IT"
        dept_name = "Information Technology"
        programme = "B.Tech. - Information Technology"
    elif "MECHANICAL" in header_upper or "MECH" in header_upper:
        dept_code = "MECH"
        dept_name = "Mechanical Engineering"
        programme = "B.E. - Mechanical Engineering"
    elif "CIVIL" in header_upper:
        dept_code = "CIVIL"
        dept_name = "Civil Engineering"
        programme = "B.E. - Civil Engineering"

    # Regulation detection
    regulation = regulation_hint or "R2024"
    reg_match = re.search(r"REGULATION[S]?\s*(20\d{2}|R\d{4})", header_upper)
    if reg_match:
        val = reg_match.group(1)
        regulation = f"R{val}" if not val.startswith("R") else val

    # 2. Extract courses semester by semester
    courses: List[Dict[str, Any]] = []
    seen_codes = set()
    current_semester = 1
    current_category = "Sem 1-4 Foundation"
    needs_review_count = 0

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        for line_idx, line in enumerate(lines):
            line_upper = line.upper()

            # Check for semester headings
            sem_m = re.search(r"\bSEMESTER\s+([I|V|X|0-9]+)\b", line_upper)
            if sem_m:
                sem_str = sem_m.group(1)
                if sem_str in ROMAN_TO_INT:
                    current_semester = ROMAN_TO_INT[sem_str]
                    current_category = "Sem 1-4 Foundation" if current_semester <= 4 else "Sem 5-8 Advanced"

            # Check for Course Code pattern
            code_matches = COURSE_CODE_PATTERN.findall(line_upper)
            for raw_code in code_matches:
                clean_code = re.sub(r"[^A-Z0-9]", "", raw_code)
                if clean_code in seen_codes:
                    continue

                title_candidates = []
                credits_val = 3.0
                course_type = "THEORY"
                confidence = 0.95
                status = "VERIFIED"

                after_code = line[line.find(raw_code) + len(raw_code):].strip()
                if after_code and len(after_code) > 2 and not after_code.isdigit():
                    title_candidates.append(after_code)

                for offset in [1, 2]:
                    if line_idx + offset < len(lines):
                        nxt = lines[line_idx + offset]
                        if not COURSE_CODE_PATTERN.search(nxt) and not nxt.startswith("SEMESTER") and len(nxt) > 2:
                            if re.match(r"^[\d\.\s]+$", nxt):
                                num_parts = nxt.split()
                                if num_parts:
                                    try:
                                        c_cand = float(num_parts[-1])
                                        if 0.0 <= c_cand <= 20.0:
                                            credits_val = c_cand
                                    except ValueError:
                                        pass
                            elif len(nxt) > 3 and not any(k in nxt.upper() for k in ["TOTAL", "CONTACT", "PERIOD"]):
                                title_candidates.append(nxt)

                if title_candidates:
                    raw_title = " ".join(title_candidates[:2])
                    clean_title = re.sub(r"\b(BSC|ESC|PCC|PEC|OEC|MC|EEC|HSMC|THEORY|PRACTICAL)\b", "", raw_title, flags=re.IGNORECASE).strip()
                    clean_title = re.sub(r"\s+", " ", clean_title)
                    course_name = clean_title or raw_title
                    confidence = 0.95
                else:
                    course_name = f"Course {clean_code}"
                    status = "REVIEW_REQUIRED"
                    confidence = 0.50
                    needs_review_count += 1

                if any(w in course_name.upper() for w in ["LAB", "LABORATORY", "PRACTICAL"]):
                    course_type = "LAB"
                    if credits_val == 3.0:
                        credits_val = 1.5
                elif "PROJECT" in course_name.upper() or "INTERNSHIP" in course_name.upper():
                    course_type = "PROJECT"

                aliases = [clean_code]
                words = course_name.split()
                if len(words) > 1:
                    abbrev = "".join(w[0] for w in words if w[0].isalnum()).upper()
                    if len(abbrev) >= 2 and len(abbrev) <= 6:
                        aliases.append(abbrev)
                aliases.append(course_name)

                course_id = f"{dept_code}_{regulation}_{clean_code}"

                course_entry = {
                    "id": course_id,
                    "code": clean_code,
                    "name": course_name,
                    "short_name": "",
                    "credits": credits_val,
                    "semester": current_semester,
                    "type": course_type,
                    "category": current_category,
                    "confidence": round(confidence, 2),
                    "status": status,
                    "aliases": list(dict.fromkeys(aliases))
                }

                courses.append(course_entry)
                seen_codes.add(clean_code)

    draft_id = f"{dept_code.lower()}_{regulation.lower()}_{uuid.uuid4().hex[:6]}"
    overall_status = "REVIEW_REQUIRED" if needs_review_count > 0 else "EXTRACTED"

    draft_data = {
        "draft_id": draft_id,
        "catalog_version": "1.0-draft",
        "status": overall_status,
        "department": dept_name,
        "department_code": dept_code,
        "programme": programme,
        "regulation": regulation,
        "academic_structure": {
            "semesters": 8
        },
        "courses": courses,
        "total_courses_extracted": len(courses),
        "needs_review_count": needs_review_count
    }

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = output_dir or os.path.join(base_dir, "syllabus_drafts")
    os.makedirs(target_dir, exist_ok=True)

    draft_filename = f"{dept_code.lower()}_{regulation.lower()}_draft.json"
    draft_filepath = os.path.join(target_dir, draft_filename)

    with open(draft_filepath, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, indent=2, ensure_ascii=False)

    return {
        "draft_id": draft_id,
        "draft_file": draft_filepath,
        "draft_data": draft_data
    }
