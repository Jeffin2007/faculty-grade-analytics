"""
================================================================================
 FACULTY GRADE ANALYTICS PORTAL -- app.py (Production Ready)
================================================================================
 Single-file application: FastHTML + pandas + openpyxl + Plotly + xhtml2pdf
 + Ollama Cloud / Local API / Deterministic Insights Engine. Analytics and LLM
 advisory are strictly layered: the UI renders structured analytics and never
 computes academic statistics itself.

 Semester final result treated as the single source of truth. No internal /
 assessment / attendance / end-semester calculation is performed.
================================================================================
"""

from __future__ import annotations

import asyncio
import base64
import gc
import html
import io
import json
import math
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import quote, unquote

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

from fasthtml.common import (
    A,
    Aside,
    Body,
    Br,
    Button,
    Div,
    FastHTML,
    Footer,
    Form,
    H1,
    H2,
    H3,
    H4,
    H5,
    Header,
    Hr,
    Img,
    Input,
    Label,
    Link,
    Main,
    Meta,
    Nav,
    NotStr,
    Ol,
    Option,
    P,
    Script,
    Section,
    Select,
    Span,
    Strong,
    Style,
    Table,
    Tbody,
    Td,
    Th,
    Thead,
    Title,
    Tr,
    Ul,
    Response,
    RedirectResponse,
    HTMLResponse,
)

try:
    from xhtml2pdf import pisa

    _PISA_OK = True
except Exception:  # pragma: no cover
    pisa = None
    _PISA_OK = False

try:
    from langchain_community.llms import Ollama

    _LANGCHAIN_OK = True
except Exception:  # pragma: no cover
    Ollama = None
    _LANGCHAIN_OK = False

try:
    import kaleido  # noqa: F401

    _KALEIDO_OK = True
except Exception:
    _KALEIDO_OK = False

# =============================================================================
# 2) CONFIGURATION & AI PROVIDER DESIGN
# =============================================================================

# AI Provider Configuration
# Supported values for AI_PROVIDER:
#   1. ollama_cloud  - (Default) Uses Ollama Cloud API with OLLAMA_API_KEY
#   2. ollama_local  - Uses local Ollama server at OLLAMA_HOST / OLLAMA_BASE_URL
#   3. deterministic - Bypasses LLM API calls; uses deterministic Python insights

def _load_env_file() -> None:
    """Load environment variables from .env file if present in workspace."""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.isfile(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

_load_env_file()

AI_PROVIDER = os.environ.get("AI_PROVIDER", "ollama_cloud").strip().lower()

CFG = {
    "app_title": "Faculty Grade Analytics Portal",
    "app_version": "Version 1.0",
    "app_subtitle": "Saranathan College of Engineering · Regulations 2024 Compatible",
    "host": os.environ.get("HOST", "0.0.0.0"),
    "port": int(os.environ.get("PORT", 8000)),
    "max_upload_mb": int(os.environ.get("MAX_UPLOAD_MB", "20")),
    "ai_provider": AI_PROVIDER,
    "ollama_api_key": os.environ.get("OLLAMA_API_KEY", "").strip(),
    "ollama_model": os.environ.get("OLLAMA_MODEL", "llama3").strip(),
    "ollama_host": os.environ.get("OLLAMA_HOST", os.environ.get("OLLAMA_BASE_URL", "")).strip(),
    "ai_timeout_seconds": float(os.environ.get("AI_TIMEOUT_SECONDS", "90")),
    "ai_enabled": os.environ.get("AI_ENABLED", "1") not in ("0", "false", "no") and AI_PROVIDER != "deterministic",
}

CLASS_AI_INSTRUCTION = (
    "You are an expert AI Academic Advisor for teachers. Review the compiled class metrics. "
    "Write a practical analysis summarizing overall strengths, problem subjects, and "
    "targeted recommendations. Format with bold keywords and crisp bullet points."
)

# =============================================================================
# 3) CONSTANTS & RESULT STATUS CLASSIFICATION
# =============================================================================

GRADE_POINTS = {
    "O": 10, "A+": 9, "A": 8, "B+": 7, "B": 6, "C": 5,
    "U": 0, "RA": 0, "SA": 0, "WD": 0, "MM": 0, "WH2": 0,
}
PASSING_GRADES = {"O", "A+", "A", "B+", "B", "C"}
FAILING_GRADES = {"U", "RA", "SA", "WD", "MM", "WH2"}
ARREAR_GRADES = {"U", "RA"}
ATTENDANCE_GRADES = {"SA"}
WITHDRAWAL_GRADES = {"WD"}
MALPRACTICE_GRADES = {"MM", "WH2"}

GRADE_ORDER = ["O", "A+", "A", "B+", "B", "C", "U", "RA", "SA", "WD", "MM", "WH2"]
PASS_GRADE_ORDER = ["O", "A+", "A", "B+", "B", "C"]
FAIL_GRADE_ORDER = ["U", "RA", "SA", "WD", "MM", "WH2"]

RESULT_STATUS = {
    "U": {"type": "arrear", "description": "Reappearance required"},
    "RA": {"type": "arrear", "description": "Reappearance / Arrear"},
    "SA": {"type": "attendance_issue", "description": "Shortage of Attendance"},
    "WD": {"type": "withdrawal", "description": "Withdrawal"},
    "MM": {"type": "malpractice", "description": "Malpractice"},
    "WH2": {"type": "malpractice", "description": "Malpractice (Withheld)"},
}

GRADE_COLORS = {
    "O": "#16a34a",
    "A+": "#22c55e",
    "A": "#4ade80",
    "B+": "#86efac",
    "B": "#64748b",
    "C": "#94a3b8",
    "U": "#dc2626",
    "RA": "#ef4444",
    "SA": "#d97706",
    "WD": "#9333ea",
    "MM": "#7c3aed",
    "WH2": "#6b21a8",
}

C_NAVY = "#0f1b33"
C_NAVY_LIGHT = "#1e3a5f"
C_GREEN = "#16a34a"
C_AMBER = "#d97706"
C_RED = "#dc2626"
C_BLUE = "#2563eb"
C_SLATE = "#64748b"
C_PURPLE = "#9333ea"
C_INDIGO = "#7c3aed"
C_BG = "#f1f5f9"

COLORWAY = [C_NAVY, C_BLUE, C_GREEN, C_AMBER, C_RED, C_SLATE, "#0ea5e9", "#a855f7"]

GRADE_ALIAS = {
    "A+": ("A+", "APLUS", "A PLUS", "A_+", "A.", "A++"),
    "B+": ("B+", "BPLUS", "B PLUS", "B_+"),
    "C+": (),
}

GRADE_TOKEN_CLEAN = {
    "A+": "A+", "A PLUS": "A+", "AP": "A+", "A PLUS PLUS": "A+",
    "B+": "B+", "B PLUS": "B+", "BP": "B+",
    "A0": "A+", "A1": "O", "O": "O", "A": "A", "B": "B", "C": "C",
    "U": "U",
    "RA": "RA", "R.A": "RA", "R/A": "RA", "R A": "RA",
    "SA": "SA", "S A": "SA", "S.A": "SA",
    "WD": "WD", "W": "WD", "DW": "WD", "W.D": "WD",
    "MM": "MM", "M.M": "MM", "MALPRACTICE": "MM",
    "WH2": "WH2", "WH 2": "WH2", "WH-2": "WH2", "WH.2": "WH2", "WH02": "WH2",
}

HEADER_ALIASES: Dict[str, List[str]] = {
    "regno": [
        "register number", "student register number", "register no", "reg number",
        "reg no", "regno", "registration number", "registration no", "student number",
        "student no", "student id", "roll number", "roll no", "admission number",
        "student reg no", "register num", "regnum", "reg no.", "student. no",
    ],
    "name": [
        "student name", "name of the student", "candidate name", "student", "name",
        "full name", "student full name", "candidate", "student's name",
    ],
    "subject": [
        "subject name", "course name", "subject", "course", "paper", "course title",
        "subject title", "name of the subject", "course name subject",
    ],
    "course_code": [
        "course code", "subject code", "code", "course id", "subject no",
        "course number", "course id",
    ],
    "credits": [
        "credit", "credits", "credit point", "credit points", "credits earned", "credits sp",
    ],
    "grade": [
        "final grade", "letter grade", "final letter grade", "grade", "result grade",
        "result", "grade achieved", "final result", "grade secured", "overall grade",
    ],
    "dept": ["department", "department name", "branch", "discipline", "dept", "branch name"],
    "programme": ["programme", "program", "degree", "programme of study", "program name"],
    "batch": ["batch", "batch year", "batch no"],
    "year": ["year", "year of study", "study year"],
    "semester": ["semester", "sem", "current semester", "semester number"],
    "section": ["section", "sec", "class section"],
    "academic_year": ["academic year", "academic session", "ay", "acadyear", "aca year"],
    "instructor": ["instructor", "faculty", "faculty name", "staff", "staff name", "teacher"],
}

REQUIRED_FIELDS = ["regno", "name", "subject", "credits", "grade"]
OPTIONAL_FIELDS = ["course_code", "dept", "programme", "batch", "year", "semester", "section", "academic_year", "instructor"]

STATUS_CLEARED = "cleared"
STATUS_U = "u"
STATUS_MULTI_U = "multi-u"
STATUS_SA = "sa"
STATUS_WD = "wd"
STATUS_MALPRACTICE = "malpractice"

# =============================================================================
# 4) DATA MODELS
# =============================================================================


@dataclass
class ValidationIssue:
    severity: str  # "error" | "warning"
    row: str  # spreadsheet row label
    field: str
    value: str
    reason: str

    def to_dict(self) -> Dict[str, str]:
        return {"severity": self.severity, "row": self.row, "field": self.field,
                "value": self.value, "reason": self.reason}


@dataclass
class ValidationReport:
    sheet_name: str = ""
    header_row: int = 0
    total_input_rows: int = 0
    valid_records: int = 0
    dropped_rows: int = 0
    duplicates_removed: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)
    mapped_columns: Dict[str, str] = field(default_factory=dict)
    discovered_metadata: Dict[str, str] = field(default_factory=dict)
    fatal_error: str = ""

    def add(self, severity: str, row: str, field: str, value: str, reason: str) -> None:
        self.issues.append(ValidationIssue(severity, row, field, str(value), reason))

    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def has_fatal(self) -> bool:
        return bool(self.fatal_error)


@dataclass
class GradeRecord:
    regno: str
    name: str
    subject: str
    course_code: str
    credits: float
    grade: str
    points: float
    src_row: int
    meta: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = {"regno": self.regno, "name": self.name, "subject": self.subject,
             "course_code": self.course_code, "credits": self.credits,
             "grade": self.grade, "points": self.points, "src_row": self.src_row}
        d.update(self.meta)
        return d


@dataclass
class SubjectAnalysis:
    subject: str
    course_code: str
    credits: float
    student_count: int
    avg_gp: float
    median_gp: float
    pass_count: int
    pass_pct: float
    u_count: int
    ra_count: int
    sa_count: int
    wd_count: int
    mm_count: int
    wh2_count: int
    u_pct: float
    priority_level: str  # "High Attention" | "Moderate Attention" | "Normal"
    gp_diff_vs_class: float
    grade_counts: Dict[str, int]
    top_students: List[Dict[str, Any]] = field(default_factory=list)
    u_students: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def arrear_count(self) -> int:
        return self.u_count + self.ra_count

    @property
    def failure_concentration(self) -> int:
        return self.arrear_count

    def to_dict(self) -> Dict[str, Any]:
        return {"subject": self.subject, "course_code": self.course_code,
                "credits": self.credits, "student_count": self.student_count,
                "avg_gp": self.avg_gp, "median_gp": self.median_gp,
                "pass_count": self.pass_count, "pass_pct": self.pass_pct,
                "u_count": self.u_count, "ra_count": self.ra_count,
                "sa_count": self.sa_count, "wd_count": self.wd_count,
                "mm_count": self.mm_count, "wh2_count": self.wh2_count,
                "priority_level": self.priority_level,
                "gp_diff_vs_class": self.gp_diff_vs_class,
                "u_pct": self.u_pct, "grade_counts": self.grade_counts,
                "top_students": [(s["regno"], s["name"], s["grade"], s["points"]) for s in self.top_students],
                "u_students": [(s["regno"], s["name"]) for s in self.u_students]}


@dataclass
class StudentSubjectResult:
    subject: str
    course_code: str
    credits: float
    grade: str
    points: float


@dataclass
class StudentAnalysis:
    regno: str
    name: str
    courses: List[StudentSubjectResult] = field(default_factory=list)
    total_courses: int = 0
    credits_completed: float = 0.0
    credits_attempted: float = 0.0
    quality_points: float = 0.0
    gpa: Optional[float] = None
    rank: Optional[int] = None
    percentile: Optional[float] = None
    grade_counts: Dict[str, int] = field(default_factory=dict)
    passed_courses: int = 0
    u_count: int = 0
    ra_count: int = 0
    sa_count: int = 0
    wd_count: int = 0
    mm_count: int = 0
    wh2_count: int = 0
    attention: str = STATUS_CLEARED
    is_high_performer: bool = False
    strongest_subjects: List[str] = field(default_factory=list)
    attention_subjects: List[str] = field(default_factory=list)
    meta: Dict[str, str] = field(default_factory=dict)

    @property
    def arrear_count(self) -> int:
        return self.u_count + self.ra_count

    @property
    def malpractice_count(self) -> int:
        return self.mm_count + self.wh2_count

    def to_dict(self) -> Dict[str, Any]:
        d = {"regno": self.regno, "name": self.name, "total_courses": self.total_courses,
             "credits_completed": self.credits_completed,
             "credits_attempted": self.credits_attempted,
             "quality_points": self.quality_points, "gpa": self.gpa,
             "rank": self.rank, "percentile": self.percentile,
             "grade_counts": self.grade_counts, "passed_courses": self.passed_courses,
             "u_count": self.u_count, "ra_count": self.ra_count,
             "sa_count": self.sa_count, "wd_count": self.wd_count,
             "mm_count": self.mm_count, "wh2_count": self.wh2_count,
             "arrear_count": self.arrear_count, "malpractice_count": self.malpractice_count,
             "attention": self.attention, "is_high_performer": self.is_high_performer,
             "strongest_subjects": self.strongest_subjects,
             "attention_subjects": self.attention_subjects,
             "courses": [{"subject": c.subject, "course_code": c.course_code,
                          "credits": c.credits, "grade": c.grade, "points": c.points}
                         for c in self.courses]}
        d.update(self.meta)
        return d


@dataclass
class ClassAnalysis:
    file_name: str = ""
    generated_at: str = ""
    student_count: int = 0
    subject_count: int = 0
    record_count: int = 0
    class_gpa: Optional[float] = None
    highest_gpa: Optional[float] = None
    lowest_gpa: Optional[float] = None
    median_gpa: Optional[float] = None
    cleared_count: int = 0
    u_student_count: int = 0
    ra_student_count: int = 0
    arrear_student_count: int = 0
    multiple_u_count: int = 0
    sa_student_count: int = 0
    wd_student_count: int = 0
    malpractice_student_count: int = 0
    pass_rate: Optional[float] = None
    record_pass_rate: Optional[float] = None
    grade_distribution: Dict[str, int] = field(default_factory=dict)
    subject_distribution: Dict[str, int] = field(default_factory=dict)
    students: List[StudentAnalysis] = field(default_factory=list)
    subjects: List[SubjectAnalysis] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def attention_students(self) -> List[StudentAnalysis]:
        return [s for s in self.students if s.attention != STATUS_CLEARED]

    def to_dict(self) -> Dict[str, Any]:
        return {"file_name": self.file_name, "generated_at": self.generated_at,
                "student_count": self.student_count, "subject_count": self.subject_count,
                "record_count": self.record_count, "class_gpa": self.class_gpa,
                "highest_gpa": self.highest_gpa, "lowest_gpa": self.lowest_gpa,
                "median_gpa": self.median_gpa, "cleared_count": self.cleared_count,
                "u_student_count": self.u_student_count, "ra_student_count": self.ra_student_count,
                "arrear_student_count": self.arrear_student_count, "multiple_u_count": self.multiple_u_count,
                "sa_student_count": self.sa_student_count, "wd_student_count": self.wd_student_count,
                "malpractice_student_count": self.malpractice_student_count,
                "pass_rate": self.pass_rate, "record_pass_rate": self.record_pass_rate,
                "grade_distribution": self.grade_distribution,
                "subject_distribution": self.subject_distribution,
                "students": [s.to_dict() for s in self.students],
                "subjects": [s.to_dict() for s in self.subjects],
                "metadata": self.metadata}


@dataclass
class AnalyticsResult:
    ok: bool
    error: str = ""
    records: Optional[pd.DataFrame] = None
    report: ValidationReport = field(default_factory=ValidationReport)
    class_analysis: Optional[ClassAnalysis] = None


# =============================================================================
# 5) VALIDATION / EXCEL INGESTION
# =============================================================================


def _norm_key(s: Any) -> str:
    """Normalize an arbitrary spreadsheet value for comparison."""
    if s is None:
        return ""
    t = str(s).strip()
    t = re.sub(r"\s+", " ", t)
    return t


def _norm_header(s: Any) -> str:
    t = _norm_key(s)
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def _grade_normalize(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    val = _norm_key(raw).upper()
    val = re.sub(r"\s+", " ", val).strip()
    if val in GRADE_POINTS:
        return val
    key = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9+/.]", " ", val)).strip()
    if key in GRADE_TOKEN_CLEAN:
        return GRADE_TOKEN_CLEAN[key]
    compact = val.replace(" ", "").replace(".", "").replace("/", "").replace("-", "")
    if compact in GRADE_TOKEN_CLEAN:
        return GRADE_TOKEN_CLEAN[compact]
    return None


def _columns_to_targets(columns: List[str]) -> Dict[str, str]:
    """Map each canonical field to a matching spreadsheet column (or None)."""
    mapping: Dict[str, str] = {}

    taken: set = set()
    for target, aliases in HEADER_ALIASES.items():
        for a in aliases:
            want = _norm_header(a)
            for col in columns:
                if col in taken:
                    continue
                if _norm_header(col) == want:
                    mapping[target] = col
                    taken.add(col)
                    break
            if target in mapping:
                break

    key_rules = [
        ("academic_year", ["academic year", "academic session", "aca year", "acad", "session"]),
        ("regno", ["register number", "reg number", "register", "reg no", "regnum", "student number",
                   "student id", "student no", "roll", "admission", "matriculation"]),
        ("credits", ["credit"]),
        ("course_code", ["course code", "subject code", "sub code", "course id"]),
        ("subject", ["subject", "paper", "course", "title"]),
        ("grade", ["grade", "letter", "result", "secured", "achieved"]),
        ("semester", ["sem"]),
        ("programme", ["programme", "program", "degree"]),
        ("section", ["section", "sec"]),
        ("batch", ["batch"]),
        ("year", ["year"]),
        ("dept", ["dept", "department", "branch", "discipline"]),
        ("instructor", ["instructor", "faculty", "staff", "teacher"]),
        ("name", ["name"]),
    ]
    for col in columns:
        if col in taken:
            continue
        n = _norm_header(col)
        if not n:
            continue
        best = None
        best_len = -1
        for target, kws in key_rules:
            if target in mapping:
                continue
            for kw in kws:
                if kw in n and len(kw) > best_len:
                    best = target
                    best_len = len(kw)
        if best is not None:
            mapping[best] = col
            taken.add(col)

    if "course_code" not in mapping:
        for col in columns:
            if col in taken:
                continue
            n = _norm_header(col)
            if "code" in n and ("course" in n or "subject" in n):
                mapping["course_code"] = col
                taken.add(col)
                break

    return mapping


def _read_workbook(data: bytes) -> Tuple[Optional[pd.DataFrame], ValidationReport]:
    """Locate the most populated sheet and the best header row from an .xlsx."""
    report = ValidationReport()
    bio = io.BytesIO(data)
    try:
        import openpyxl

        wb = openpyxl.load_workbook(bio, read_only=True, data_only=True)
    except Exception as e:
        report.fatal_error = f"Corrupted or unreadable XLSX workbook: {e}"
        return None, report

    sheet_names = wb.sheetnames
    if not sheet_names:
        report.fatal_error = "Workbook contains no worksheets."
        return None, report

    chosen = max(
        sheet_names,
        key=lambda sn: _sheet_row_count(wb, sn),
    )
    report.sheet_name = chosen

    try:
        scan = pd.read_excel(io.BytesIO(data), sheet_name=chosen, header=None,
                             engine="openpyxl", dtype=str)
    except Exception as e:
        report.fatal_error = f"Could not read sheet '{chosen}': {e}"
        return None, report

    scan = scan.fillna("")
    best_row = 0
    best_score = 0
    limit = min(16, len(scan))
    for idx in range(limit):
        row = scan.iloc[idx].tolist()
        nonempty = sum(1 for c in row if str(c).strip())
        if nonempty == 0:
            continue
        mapped = _columns_to_targets(list(map(str, row)))
        score = nonempty + len(mapped) * 10
        if score > best_score:
            best_score = score
            best_row = idx
    report.header_row = best_row

    df = pd.read_excel(io.BytesIO(data), sheet_name=chosen, header=best_row,
                       engine="openpyxl", dtype=str)
    df = df.fillna("")
    return df, report


def _sheet_row_count(wb, sheet_name: str) -> int:
    try:
        ws = wb[sheet_name]
        ws.calculate_dimension()
        return ws.max_row or 0
    except Exception:
        return 0


def _clean_value(v: Any) -> str:
    s = _norm_key(v)
    return re.sub(r"\s+", " ", s).strip()


def _parse_credits(raw: Any) -> Optional[float]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = float(str(raw).strip())
        if 0.0 <= v <= 100.0 and math.isfinite(v):
            return v
    except Exception:
        pass
    return None


def _readable_required_columns() -> str:
    inner = []
    for f in REQUIRED_FIELDS:
        aliases = HEADER_ALIASES.get(f, [])
        inner.append(f"{f.replace('_', ' ')} (e.g. '{aliases[0] if aliases else f}')")
    return ", ".join(inner)


def validate_and_clean(data: bytes, file_name: str, custom_mapping: Optional[Dict[str, str]] = None) -> AnalyticsResult:
    """Validate + normalize the uploaded workbook into clean GradeRecords."""
    report = ValidationReport()

    df, report = _read_workbook(data)
    if report.has_fatal():
        return AnalyticsResult(ok=False, report=report)

    cols = [str(c) for c in df.columns.tolist()]
    mapping = custom_mapping or _columns_to_targets(cols)
    report.mapped_columns = mapping

    missing = [f for f in REQUIRED_FIELDS if f not in mapping or not mapping[f]]
    if missing:
        report.fatal_error = (
            "Could not locate required columns in the detected header row "
            f"(row {report.header_row + 1}). Missing: {', '.join(missing)}. "
            "Expected columns such as: " + _readable_required_columns() + "."
        )
        return AnalyticsResult(ok=False, report=report)

    report.total_input_rows = len(df)

    records: List[GradeRecord] = []
    seen: Dict[Tuple[str, str], GradeRecord] = {}
    dropped = 0
    dup = 0

    col_index = {t: (cols.index(v) if v and v in cols else None) for t, v in mapping.items()}
    for ridx in range(len(df)):
        row = df.iloc[ridx]
        rno = ridx + report.header_row + 2
        vals: Dict[str, str] = {}
        for target, ci in col_index.items():
            if ci is None:
                vals[target] = ""
            else:
                try:
                    vals[target] = _clean_value(row.iloc[ci])
                except Exception:
                    vals[target] = ""

        if not vals["regno"]:
            dropped += 1
            report.add("error", str(rno), "regno", "", "Missing student/register number.")
            continue
        if not vals["subject"]:
            dropped += 1
            report.add("error", str(rno), "subject", "", "Missing subject/course name.")
            continue
        grade = _grade_normalize(vals["grade"])
        if not grade:
            dropped += 1
            report.add("error", str(rno), "grade", vals["grade"], "Missing or blank final grade.")
            continue
        if grade not in GRADE_POINTS:
            dropped += 1
            report.add("error", str(rno), "grade", vals["grade"],
                       f"Unknown grade '{vals['grade']}' (expecting O, A+, A, B+, B, C, U, RA, SA, WD, MM, WH2).")
            continue

        credit = _parse_credits(vals["credits"])
        if credit is None:
            report.add("warning", str(rno), "credits", vals["credits"],
                       "Missing/invalid credits; treated as 0 (record still counted).")
            credit = 0.0

        norm_regno = vals["regno"].strip().upper()
        norm_subject = vals["subject"].strip().lower()
        key = (norm_regno, norm_subject)

        if key in seen:
            pre = seen[key]
            if pre.credits == credit and pre.grade == grade:
                dup += 1
                report.add("warning", str(rno), "duplicate", vals["regno"],
                           "Duplicate record (same student + subject exported twice) removed.")
                continue
            dropped += 1
            report.add("warning", str(rno), "conflict", vals["regno"],
                       f"Conflicting repeat grade (same student+subject seen at row {pre.src_row}). "
                       "Kept first occurrence only.")
            continue

        meta = {opt: vals[opt] for opt in OPTIONAL_FIELDS if vals.get(opt)}
        rec = GradeRecord(
            regno=vals["regno"],
            name=vals["name"] or "",
            subject=vals["subject"],
            course_code=vals["course_code"] or "",
            credits=credit,
            grade=grade,
            points=GRADE_POINTS[grade],
            src_row=rno,
            meta=meta,
        )
        seen[key] = rec
        records.append(rec)

    report.valid_records = len(records)
    report.dropped_rows = dropped
    report.duplicates_removed = dup

    if not records:
        report.fatal_error = (
            "No valid result records remain after validation (all rows were dropped). "
            "Please review the validation issues above."
        )
        if len(report.issues) <= 12:
            report.fatal_error += " Issues: " + "; ".join(i.reason for i in report.issues[:12])
        return AnalyticsResult(ok=False, report=report)

    out = pd.DataFrame([r.to_dict() for r in records])

    meta_disc: Dict[str, str] = {}
    for opt in OPTIONAL_FIELDS:
        series = out.get(opt)
        if series is not None:
            present = [str(v) for v in series.tolist() if str(v).strip()]
            if present:
                meta_disc[opt] = present[0]
    report.discovered_metadata = meta_disc

    return AnalyticsResult(ok=True, records=out, report=report)


# =============================================================================
# 6) ANALYTICS ENGINE & DETERMINISTIC INSIGHTS (UI-agnostic)
# =============================================================================


def _round(x: Optional[float], ndigits: int = 2) -> Optional[float]:
    if x is None:
        return None
    return round(float(x), ndigits)


def _pct(num: Union[int, float], den: Union[int, float]) -> Optional[float]:
    if not den:
        return None
    return round(100.0 * num / den, 1)


def compute_subject_analytics(records: pd.DataFrame, class_gpa_ref: Optional[float] = None) -> List[SubjectAnalysis]:
    """Subject-level metrics from the validated records dataframe."""
    subjects: List[SubjectAnalysis] = []
    for subject, grp in records.groupby("subject", sort=True):
        grp = grp.reset_index(drop=True)
        students = grp["regno"].astype(str).nunique()
        pts = grp["points"].astype(float)
        avg_gp = _round(float(pts.mean()), 2) if students else None
        median_gp = _round(float(pts.median()), 2) if students else None

        counts = {g: int((grp["grade"] == g).sum()) for g in GRADE_ORDER}
        pass_count = int(grp["grade"].isin(PASSING_GRADES).sum())
        u_count = int((grp["grade"] == "U").sum())
        ra_count = int((grp["grade"] == "RA").sum())
        sa_count = int((grp["grade"] == "SA").sum())
        wd_count = int((grp["grade"] == "WD").sum())
        mm_count = int((grp["grade"] == "MM").sum())
        wh2_count = int((grp["grade"] == "WH2").sum())

        arrear_total = u_count + ra_count
        pass_pct = _pct(pass_count, len(grp))
        u_pct = _pct(arrear_total, len(grp))

        gp_diff = (avg_gp - class_gpa_ref) if (avg_gp is not None and class_gpa_ref is not None) else 0.0

        if (pass_pct is not None and pass_pct < 75.0) or arrear_total >= 5 or gp_diff <= -1.0:
            priority = "High Attention"
        elif (pass_pct is not None and pass_pct < 85.0) or arrear_total >= 2:
            priority = "Moderate Attention"
        else:
            priority = "Normal"

        course_code = ""
        cc = grp["course_code"].dropna().astype(str)
        cc = cc[cc.str.strip() != ""]
        if len(cc):
            course_code = cc.mode().iloc[0]

        credits_series = grp["credits"].dropna().astype(float)
        credits = float(credits_series.mode().iloc[0]) if len(credits_series) else 0.0

        top = grp.sort_values(["points", "regno"], ascending=[False, True]).head(6)
        top_students = [
            {"regno": str(r["regno"]), "name": str(r["name"]),
             "grade": str(r["grade"]), "points": float(r["points"])}
            for _, r in top.iterrows()
        ]
        u_df = grp[grp["grade"].isin(ARREAR_GRADES)].sort_values("regno")
        u_students = [
            {"regno": str(r["regno"]), "name": str(r["name"]),
             "grade": str(r["grade"]), "points": float(r["points"])}
            for _, r in u_df.iterrows()
        ]

        subjects.append(SubjectAnalysis(
            subject=str(subject), course_code=course_code, credits=credits,
            student_count=int(students), avg_gp=avg_gp, median_gp=median_gp,
            pass_count=pass_count, pass_pct=pass_pct, u_count=u_count, ra_count=ra_count,
            sa_count=sa_count, wd_count=wd_count, mm_count=mm_count, wh2_count=wh2_count,
            u_pct=u_pct, priority_level=priority, gp_diff_vs_class=gp_diff,
            grade_counts=counts, top_students=top_students, u_students=u_students,
        ))
    return subjects


def compute_student_analytics(records: pd.DataFrame) -> List[StudentAnalysis]:
    """Student-level metrics with credit-weighted GPA (Regulations 2024)."""
    students: List[StudentAnalysis] = []
    for regno, grp in records.groupby("regno", sort=True):
        grp = grp.reset_index(drop=True)
        name = ""
        nm = grp["name"].dropna().astype(str)
        nm = nm[nm.str.strip() != ""]
        if len(nm):
            name = nm.mode().iloc[0]

        courses = []
        for _, r in grp.iterrows():
            courses.append(StudentSubjectResult(
                subject=str(r["subject"]), course_code=str(r["course_code"] or ""),
                credits=float(r["credits"] or 0.0), grade=str(r["grade"]),
                points=float(r["points"] or 0.0),
            ))
        courses.sort(key=lambda c: (c.subject.lower(), c.course_code))

        passing = [c for c in courses if c.grade in PASSING_GRADES]
        attempted_credits = sum(c.credits for c in courses)
        completed_credits = sum(c.credits for c in passing)
        quality_points = sum(c.credits * c.points for c in passing)
        gpa = (quality_points / completed_credits) if completed_credits > 0 else None

        counts = {g: sum(1 for c in courses if c.grade == g) for g in GRADE_ORDER}
        u_count = counts.get("U", 0)
        ra_count = counts.get("RA", 0)
        sa_count = counts.get("SA", 0)
        wd_count = counts.get("WD", 0)
        mm_count = counts.get("MM", 0)
        wh2_count = counts.get("WH2", 0)

        arrear_total = u_count + ra_count
        malpractice_total = mm_count + wh2_count

        if arrear_total >= 2:
            attention = STATUS_MULTI_U
        elif arrear_total == 1:
            attention = STATUS_U
        elif malpractice_total > 0:
            attention = STATUS_MALPRACTICE
        elif sa_count > 0:
            attention = STATUS_SA
        elif wd_count > 0:
            attention = STATUS_WD
        else:
            attention = STATUS_CLEARED

        is_high = (
            gpa is not None and gpa >= 8.5 and attention == STATUS_CLEARED
        )

        strongest = [c.subject for c in sorted(
            (c for c in passing), key=lambda c: (-c.points, c.subject.lower()))]
        attention_subjects = [c.subject for c in courses if c.grade in FAILING_GRADES]

        meta = {}
        for opt in OPTIONAL_FIELDS:
            s = grp.get(opt)
            if s is not None:
                present = [str(v) for v in s.tolist() if str(v).strip()]
                if present:
                    meta[opt] = present[0]

        students.append(StudentAnalysis(
            regno=str(regno), name=name, courses=courses,
            total_courses=len(courses),
            credits_completed=completed_credits, credits_attempted=attempted_credits,
            quality_points=quality_points, gpa=gpa,
            grade_counts=counts, passed_courses=len(passing),
            u_count=u_count, ra_count=ra_count, sa_count=sa_count, wd_count=wd_count,
            mm_count=mm_count, wh2_count=wh2_count,
            attention=attention, is_high_performer=is_high,
            strongest_subjects=strongest, attention_subjects=attention_subjects,
            meta=meta,
        ))
    return students


def _rank_students(students: List[StudentAnalysis]) -> None:
    """Competition-style ranking: ties share the best rank; assign percentiles."""
    n = len(students)
    if n == 0:
        return
    order = sorted(
        students,
        key=lambda s: (0 if s.gpa is not None else 1, -(_round(s.gpa, 4) or 0.0), s.regno.lower()),
    )
    prev_key = None
    prev_rank = 1
    for i, s in enumerate(order):
        key = (s.gpa is not None, _round(s.gpa, 4))
        if key == prev_key:
            s.rank = prev_rank
        else:
            s.rank = i + 1
            prev_rank = s.rank
            prev_key = key
        if s.gpa is None:
            s.percentile = None
        else:
            s.percentile = _round((n - s.rank + 1) / n * 100.0, 1)


def generate_deterministic_insights(ca: ClassAnalysis) -> Dict[str, Any]:
    """Compute rich, deterministic academic insights from the ClassAnalysis object."""
    insights = []
    
    if ca.pass_rate is not None:
        if ca.pass_rate >= 85.0:
            health_status = "Excellent"
            health_color = "text-green-700"
            health_bg = "bg-green-100 border-green-300"
        elif ca.pass_rate >= 70.0:
            health_status = "Good"
            health_color = "text-blue-700"
            health_bg = "bg-blue-100 border-blue-300"
        else:
            health_status = "Needs Attention"
            health_color = "text-amber-700"
            health_bg = "bg-amber-100 border-amber-300"
    else:
        health_status = "N/A"
        health_color = "text-slate-700"
        health_bg = "bg-slate-100 border-slate-300"

    sorted_by_pass = sorted(ca.subjects, key=lambda s: (s.pass_pct or 0, s.avg_gp or 0), reverse=True)
    best_subject = sorted_by_pass[0] if sorted_by_pass else None
    
    sorted_by_u = sorted(ca.subjects, key=lambda s: (s.arrear_count, -(s.pass_pct or 100)), reverse=True)
    weakest_subject = sorted_by_u[0] if sorted_by_u and sorted_by_u[0].arrear_count > 0 else None

    if ca.arrear_student_count > 0:
        insights.append(f"{ca.arrear_student_count} student(s) hold active arrears (U / RA grades).")
    else:
        insights.append("100% of students cleared all registered subjects with zero arrears.")

    if ca.multiple_u_count > 0:
        insights.append(f"{ca.multiple_u_count} student(s) hold multiple arrears requiring immediate intervention.")

    if ca.malpractice_student_count > 0:
        insights.append(f"🚨 {ca.malpractice_student_count} student(s) have recorded malpractice status (MM / WH2).")

    if best_subject and best_subject.pass_pct is not None:
        insights.append(f"'{best_subject.subject}' achieved highest pass percentage at {best_subject.pass_pct:.1f}%.")

    if weakest_subject and weakest_subject.arrear_count > 0:
        diff_str = f"{abs(weakest_subject.gp_diff_vs_class):.1f} lower average GP" if weakest_subject.gp_diff_vs_class < 0 else "comparable GP"
        insights.append(f"'{weakest_subject.subject}' has highest concentration of arrears ({weakest_subject.arrear_count} students, {diff_str} than class average).")

    top_distinction = ca.grade_distribution.get("O", 0) + ca.grade_distribution.get("A+", 0)
    if top_distinction > 0:
        insights.append(f"{top_distinction} result entries achieved top distinction (O or A+).")

    if ca.sa_student_count > 0:
        insights.append(f"{ca.sa_student_count} student(s) carry Shortage of Attendance (SA) status.")

    if ca.wd_student_count > 0:
        insights.append(f"{ca.wd_student_count} student(s) carry Withdrawal (WD) status.")

    return {
        "health_status": health_status,
        "health_color": health_color,
        "health_bg": health_bg,
        "best_subject": best_subject,
        "weakest_subject": weakest_subject,
        "bullet_insights": insights,
    }


def compute_class_analysis(records: pd.DataFrame, file_name: str) -> ClassAnalysis:
    """Compute the full deterministic class analysis."""
    ca = ClassAnalysis(file_name=file_name,
                       generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ca.student_count = int(records["regno"].nunique())
    ca.subject_count = int(records["subject"].nunique())
    ca.record_count = int(len(records))
    ca.metadata["semester_records"] = ca.record_count

    ca.students = compute_student_analytics(records)
    _rank_students(ca.students)

    gpas = [s.gpa for s in ca.students if s.gpa is not None]
    if gpas:
        ca.class_gpa = _round(float(np.mean(gpas)), 2)
        ca.highest_gpa = _round(float(np.max(gpas)), 2)
        ca.lowest_gpa = _round(float(np.min(gpas)), 2)
        ca.median_gpa = _round(float(np.median(gpas)), 2)

    ca.subjects = compute_subject_analytics(records, ca.class_gpa)

    ca.cleared_count = sum(1 for s in ca.students if s.attention == STATUS_CLEARED)
    ca.u_student_count = sum(1 for s in ca.students if s.u_count > 0)
    ca.ra_student_count = sum(1 for s in ca.students if s.ra_count > 0)
    ca.arrear_student_count = sum(1 for s in ca.students if s.arrear_count > 0)
    ca.multiple_u_count = sum(1 for s in ca.students if s.arrear_count >= 2)
    ca.sa_student_count = sum(1 for s in ca.students if s.sa_count > 0)
    ca.wd_student_count = sum(1 for s in ca.students if s.wd_count > 0)
    ca.malpractice_student_count = sum(1 for s in ca.students if s.malpractice_count > 0)

    ca.pass_rate = _pct(ca.cleared_count, ca.student_count)
    ca.record_pass_rate = _pct(
        int((records["grade"].isin(PASSING_GRADES)).sum()), len(records))

    ca.grade_distribution = {g: int((records["grade"] == g).sum()) for g in GRADE_ORDER}
    ca.subject_distribution = {
        s.subject: s.student_count for s in ca.subjects
    }
    return ca


def get_student(ca: ClassAnalysis, regno: str) -> Optional[StudentAnalysis]:
    regno_clean = unquote(str(regno)).strip().upper()
    for s in ca.students:
        if s.regno.strip().upper() == regno_clean:
            return s
    return None


def get_subject(ca: ClassAnalysis, subject: str) -> Optional[SubjectAnalysis]:
    subj_clean = unquote(str(subject)).strip().lower()
    for s in ca.subjects:
        if s.subject.strip().lower() == subj_clean:
            return s
    return None


# =============================================================================
# 7) CHART GENERATION (Plotly Express + Heatmap + Performance Distribution)
# =============================================================================

_PLOTLY_INJECTED = {"flag": False}


def reset_plotly_flag() -> None:
    _PLOTLY_INJECTED["flag"] = False


def _default_layout(fig: go.Figure, height: Optional[int] = None) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        font=dict(family="Inter, ui-sans-serif, system-ui, sans-serif", size=12, color="#1e293b"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=20, t=48, b=40),
        height=height or 360,
        title_font_size=15,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        hoverlabel=dict(bgcolor="#0f1b33", font_color="white", font_size=12),
        xaxis=dict(gridcolor="#eef2f7", zeroline=False),
        yaxis=dict(gridcolor="#eef2f7", zeroline=False),
    )
    return fig


def fig_grade_distribution(ca: ClassAnalysis) -> go.Figure:
    vals = [ca.grade_distribution.get(g, 0) for g in GRADE_ORDER]
    fig = px.bar(x=GRADE_ORDER, y=vals, color=GRADE_ORDER, color_discrete_map=GRADE_COLORS)
    fig.update_traces(marker_line_color="#0f1b33", marker_line_width=0.6, showlegend=False)
    fig.update_xaxes(categoryorder="array", categoryarray=GRADE_ORDER)
    fig.update_layout(title="Grade distribution (all result records)", yaxis_title="Records")
    return _default_layout(fig, 340)


def fig_subject_avg_gp(ca: ClassAnalysis) -> go.Figure:
    rows = [s for s in ca.subjects if s.avg_gp is not None]
    labels = [s.subject for s in rows]
    vals = [s.avg_gp or 0.0 for s in rows]
    fig = px.bar(x=labels, y=vals, color=vals, color_continuous_scale=["#dc2626", "#fbbf24", "#16a34a"],
                 range_color=[0, 10])
    fig.update_layout(title="Average grade point by subject", yaxis_title="Avg grade point")
    fig.update_yaxes(range=[0, 10])
    return _default_layout(fig, 360)


def fig_subject_pass_pct(ca: ClassAnalysis) -> go.Figure:
    labels = [s.subject for s in ca.subjects]
    vals = [s.pass_pct if s.pass_pct is not None else 0.0 for s in ca.subjects]
    fig = px.bar(x=labels, y=vals, color=vals, color_continuous_scale=["#dc2626", "#f59e0b", "#16a34a"],
                 range_color=[0, 100])
    fig.update_layout(title="Pass percentage by subject", yaxis_title="Pass %")
    fig.update_yaxes(range=[0, 100])
    return _default_layout(fig, 330)


def fig_failure_concentration(ca: ClassAnalysis, top: int = 8) -> go.Figure:
    subj = sorted(ca.subjects, key=lambda s: s.arrear_count, reverse=True)[:top]
    labels = [s.subject for s in subj]
    vals = [s.arrear_count for s in subj]
    colors = [C_RED if v > 0 else C_SLATE for v in vals]
    fig = px.bar(x=labels, y=vals, color=labels, color_discrete_map={
        l: c for l, c in zip(labels, colors)})
    fig.update_layout(title="Arrear concentration (U / RA grades by subject)",
                      yaxis_title="Arrear count", showlegend=False)
    return _default_layout(fig, 320)


def fig_student_performance_distribution(ca: ClassAnalysis) -> go.Figure:
    """Requirement 7: Student Performance Distribution bar chart."""
    high = sum(1 for s in ca.students if s.gpa is not None and s.gpa >= 8.5 and s.arrear_count == 0)
    avg = sum(1 for s in ca.students if s.gpa is not None and 7.0 <= s.gpa < 8.5 and s.arrear_count == 0)
    moderate = sum(1 for s in ca.students if s.gpa is not None and 5.0 <= s.gpa < 7.0 and s.arrear_count == 0)
    attention = sum(1 for s in ca.students if s.attention != STATUS_CLEARED)
    
    categories = ["High Performers (GPA ≥8.5)", "Solid Performers (7.0-8.4)", "Average (5.0-6.9)", "Needs Attention (Arrears/SA)"]
    counts = [high, avg, moderate, attention]
    colors = [C_GREEN, C_BLUE, C_AMBER, C_RED]
    
    fig = px.bar(x=counts, y=categories, orientation="h", color=categories,
                 color_discrete_map={cat: col for cat, col in zip(categories, colors)})
    fig.update_traces(showlegend=False)
    fig.update_layout(title="Student Cohort Performance Distribution", xaxis_title="Students")
    return _default_layout(fig, 320)


def fig_grade_heatmap(ca: ClassAnalysis) -> go.Figure:
    """Requirement 7: Grade Heatmap across subjects."""
    subj_list = ca.subjects[:8]
    subjects = [s.subject for s in subj_list]
    grades = ["O", "A+", "A", "B+", "B", "C", "U", "RA", "SA", "WD"]
    
    z = []
    for g in grades:
        row = [s.grade_counts.get(g, 0) for s in subj_list]
        z.append(row)
        
    fig = go.Figure(data=go.Heatmap(
        z=z, x=subjects, y=grades,
        colorscale="Viridis",
        reversescale=True,
        hovertemplate="Subject: %{x}<br>Grade: %{y}<br>Count: %{z}<extra></extra>"
    ))
    fig.update_layout(title="Grade Matrix Heatmap (Subjects vs Grade Tiers)", height=350)
    return _default_layout(fig, 350)


def fig_student_subjects(student: StudentAnalysis) -> go.Figure:
    labels = [c.subject for c in student.courses]
    pts = [c.points for c in student.courses]
    grades = [c.grade for c in student.courses]
    colors = [GRADE_COLORS.get(g, C_SLATE) for g in grades]
    fig = px.bar(x=labels, y=pts, color=labels, color_discrete_map={l: c for l, c in zip(labels, colors)})
    fig.update_layout(title="Subject-wise grade points", yaxis_title="Grade point")
    fig.update_yaxes(range=[0, 10])
    return _default_layout(fig, 320)


def fig_student_vs_class(student: StudentAnalysis, ca: ClassAnalysis) -> go.Figure:
    labels = [c.subject for c in student.courses]
    s_pts = [c.points for c in student.courses]
    subj_by = {s.subject: s for s in ca.subjects}
    class_pts = [subj_by.get(l).avg_gp if subj_by.get(l) else 0.0 for l in labels]
    x = labels + labels
    y = s_pts + class_pts
    series = ["Student"] * len(labels) + ["Class average"] * len(labels)
    fig = px.bar(x=x, y=y, color=series, color_discrete_map={"Student": C_NAVY, "Class average": C_AMBER},
                 barmode="group")
    fig.update_layout(title="Student vs class average (by subject)", yaxis_title="Grade point")
    fig.update_yaxes(range=[0, 10])
    return _default_layout(fig, 340)


def chart_html(fig: go.Figure) -> str:
    """Render a figure as an inline HTML fragment; inline plotly.js once per page."""
    include = not _PLOTLY_INJECTED["flag"]
    _PLOTLY_INJECTED["flag"] = True
    return fig.to_html(
        full_html=False,
        include_plotlyjs=include,
        config={"displayModeBar": False, "responsive": True, "locale": "en"},
    )


def chart_card(fig: go.Figure, note: Optional[str] = None) -> Div:
    body = [Div(NotStr(chart_html(fig)), cls="w-full overflow-hidden")]
    if note:
        body.append(P(note, cls="mt-1 text-xs text-slate-500"))
    return Div(*body, cls="card p-4 sm:p-5")


def fig_to_png(fig: go.Figure, width: int = 900) -> Optional[bytes]:
    """Static PNG via Kaleido; returns None when kaleido is unavailable."""
    if not _KALEIDO_OK:
        return None
    try:
        return fig.to_image(format="png", width=width, height=420, scale=1.5)
    except Exception:
        return None


def png_data_url(png: Optional[bytes]) -> str:
    if not png:
        return ""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


# =============================================================================
# 8) AI FUNCTIONS & OLLAMA CLOUD / LOCAL / DETERMINISTIC PROVIDER ENGINE
# =============================================================================

_AI_CACHE: Dict[str, Dict[str, Any]] = {}

AI_GUARDRAILS = (
    "CRITICAL CONSTRAINTS: Base every statement exclusively on the metrics "
    "provided. Result status meanings: U / RA indicate academic arrear or reappearance requirement; "
    "SA indicates shortage of attendance; WD indicates withdrawal; MM / WH2 indicate malpractice-related result status. "
    "Do not speculate about reasons or circumstances. Only report the status provided. "
    "Never infer details or accuse students of cheating. "
    "Never invent: attendance figures, internal or assessment marks, medical reasons, "
    "personal problems, or faculty misconduct."
)

PROHIBITIONS = (
    "Do not invent attendance figures, internal marks, assessment marks, "
    "reasons for failure, medical information, historical performance, or "
    "teacher misconduct. "
)


def _http_post_json(url: str, payload: dict, headers: dict, timeout: float) -> Optional[dict]:
    """Helper: execute JSON HTTP POST request with timeout and error handling."""
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                raw_body = resp.read().decode("utf-8")
                return json.loads(raw_body)
    except Exception:
        return None
    return None


def _ai_invoke(system: str, user: str) -> Optional[str]:
    """Execute LLM prompt against configured AI provider (ollama_cloud, ollama_local, or deterministic)."""
    provider = CFG.get("ai_provider", "ollama_cloud")
    if provider == "deterministic" or not CFG.get("ai_enabled", True):
        return None

    if not (system and user):
        return None

    timeout = CFG.get("ai_timeout_seconds", 90.0)
    model = CFG.get("ollama_model") or "llama3"

    if provider == "ollama_cloud":
        api_key = CFG.get("ollama_api_key", "")
        if not api_key:
            # Missing API key safely triggers deterministic fallback
            return None

        host = (CFG.get("ollama_host") or "https://api.ollama.com").rstrip("/")

        def _call_cloud() -> Optional[str]:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.1,
            }
            # Primary: OpenAI-compatible /v1/chat/completions endpoint
            res = _http_post_json(f"{host}/v1/chat/completions", payload, headers, timeout)
            if res and "choices" in res and res["choices"]:
                msg = res["choices"][0].get("message", {}).get("content", "")
                if msg and msg.strip():
                    return msg.strip()

            # Secondary: Native /api/chat endpoint
            chat_payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
            }
            res_chat = _http_post_json(f"{host}/api/chat", chat_payload, headers, timeout)
            if res_chat:
                if "message" in res_chat and isinstance(res_chat["message"], dict):
                    msg = res_chat["message"].get("content", "")
                    if msg and msg.strip():
                        return msg.strip()
                elif "response" in res_chat and str(res_chat["response"]).strip():
                    return str(res_chat["response"]).strip()

            return None

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call_cloud)
                return fut.result(timeout=timeout)
        except Exception:
            return None

    elif provider == "ollama_local":
        host = (CFG.get("ollama_host") or "http://localhost:11434").rstrip("/")

        def _call_local() -> Optional[str]:
            if _LANGCHAIN_OK and Ollama is not None:
                try:
                    llm = Ollama(model=model, base_url=host, temperature=0.1, top_p=0.9, verbose=False)
                    res = str(llm.invoke(f"{system}\n\n{user}")).strip()
                    if res:
                        return res
                except Exception:
                    pass

            headers = {"Content-Type": "application/json"}
            payload = {
                "model": model,
                "prompt": f"{system}\n\n{user}",
                "stream": False,
            }
            res = _http_post_json(f"{host}/api/generate", payload, headers, timeout)
            if res and "response" in res and str(res["response"]).strip():
                return str(res["response"]).strip()
            return None

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call_local)
                return fut.result(timeout=timeout)
        except Exception:
            return None

    return None


def _cache_get(key: str) -> Optional[str]:
    entry = _AI_CACHE.get(key)
    return entry["text"] if entry else None


def _cache_set(key: str, text: str, live: bool) -> None:
    _AI_CACHE[key] = {"text": text, "live": "live" if live else "fallback"}


def _ai_hash(*parts: Any) -> str:
    blob = "|".join(str(p) for p in parts)
    return str(abs(hash(blob)))


def _metrics_json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str, indent=2)


def generate_class_ai_insight(ca: ClassAnalysis) -> Dict[str, str]:
    """Class-level AI insight. Returns {'text', 'live'} (live in {'live','fallback'})."""
    key = "class:" + _ai_hash(ca.file_name, ca.record_count, ca.class_gpa,
                               sorted(ca.grade_distribution.items()))
    cached = _cache_get(key)
    if cached is not None:
        return {"text": cached, "live": _AI_CACHE[key]["live"]}

    payload = {
        "class_average_gpa": ca.class_gpa,
        "pass_percentage": ca.pass_rate,
        "best_subject": ca.subjects[0].subject if ca.subjects else "None",
        "weakest_subject": ca.subjects[-1].subject if ca.subjects else "None",
        "arrear_students": ca.arrear_student_count,
        "multiple_u_students": ca.multiple_u_count,
        "malpractice_students": ca.malpractice_student_count,
        "subject_failures": {s.subject: s.arrear_count for s in ca.subjects if s.arrear_count > 0},
    }
    system = (PROHIBITIONS + CLASS_AI_INSTRUCTION
              + "\n\n" + AI_GUARDRAILS)
    user = ("Here are the structured class metrics for a single semester of declared final "
            "grades. Write the class analysis.\n\n" + _metrics_json(payload))
    text = _ai_invoke(system, user)
    if not text:
        return {"text": fallback_class_insight(ca), "live": "fallback"}
    _cache_set(key, text, True)
    return {"text": text, "live": "live"}


def clarified_top_subjects(ca: ClassAnalysis) -> List[Dict[str, Any]]:
    top = sorted(ca.subjects, key=lambda s: (s.arrear_count, -(s.avg_gp or 0)), reverse=True)[:6]
    return [{"subject": s.subject, "avg_gp": s.avg_gp, "pass_pct": s.pass_pct, "u_count": s.u_count, "ra_count": s.ra_count}
            for s in top]


def generate_subject_ai_insight(subj: SubjectAnalysis, ca: ClassAnalysis) -> Dict[str, str]:
    key = "subject:" + _ai_hash(subj.subject, subj.avg_gp, subj.arrear_count)
    cached = _cache_get(key)
    if cached is not None:
        return {"text": cached, "live": _AI_CACHE[key]["live"]}

    payload = {
        "subject": subj.subject,
        "course_code": subj.course_code,
        "credits": subj.credits,
        "students_enrolled": subj.student_count,
        "average_grade_point": subj.avg_gp,
        "median_grade_point": subj.median_gp,
        "pass_percentage": subj.pass_pct,
        "u_count": subj.u_count,
        "ra_count": subj.ra_count,
        "sa_count": subj.sa_count,
        "wd_count": subj.wd_count,
        "mm_count": subj.mm_count,
        "wh2_count": subj.wh2_count,
        "u_percentage": subj.u_pct,
        "grade_distribution": subj.grade_counts,
        "class_overall": {
            "class_gpa": ca.class_gpa,
            "class_pass_percent": ca.pass_rate,
        },
    }
    system = (
        "You are an expert AI Academic Advisor for teachers. Review the subject "
        "metrics. Write a practical analysis summarizing overall strengths, problem "
        "subjects, and targeted recommendations. Format with bold keywords and crisp bullet points.\n"
        + PROHIBITIONS + AI_GUARDRAILS
    )
    user = ("Here are single-semester subject metrics. Produce the subject analysis.\n\n"
            + _metrics_json(payload))
    text = _ai_invoke(system, user)
    if not text:
        return {"text": fallback_subject_insight(subj, ca), "live": "fallback"}
    _cache_set(key, text, True)
    return {"text": text, "live": "live"}


def generate_student_brief(student: StudentAnalysis, ca: ClassAnalysis) -> Dict[str, str]:
    """Concise per-student AI academic brief."""
    key = "student:" + _ai_hash(student.regno, student.gpa, sorted(student.grade_counts.items()))
    cached = _cache_get(key)
    if cached is not None:
        return {"text": cached, "live": _AI_CACHE[key]["live"]}

    payload = {
        "gpa": student.gpa,
        "rank": student.rank,
        "percentile": student.percentile,
        "arrears": {"u": student.u_count, "ra": student.ra_count},
        "attendance_shortage": student.sa_count,
        "withdrawal": student.wd_count,
        "malpractice": {"mm": student.mm_count, "wh2": student.wh2_count},
        "courses": [
            {"subject": c.subject, "grade": c.grade, "points": c.points}
            for c in student.courses
        ],
    }
    system = (
        "You are an expert AI Academic Advisor for teachers. Write a concise "
        "academic briefing using bold keywords and crisp bullet points.\n"
        "Use only the provided metrics. " + PROHIBITIONS + AI_GUARDRAILS
    )
    user = "Provide the student academic brief.\n\n" + _metrics_json(payload)
    text = _ai_invoke(system, user)
    if not text:
        return {"text": fallback_student_brief(student, ca), "live": "fallback"}
    _cache_set(key, text, True)
    return {"text": text, "live": "live"}


def generate_ptm_brief(student: StudentAnalysis, ca: ClassAnalysis) -> Dict[str, str]:
    """Parent–Teacher Meeting brief for one student."""
    key = "ptm:" + _ai_hash(student.regno, student.gpa, tuple(sorted(student.grade_counts.items())))
    cached = _cache_get(key)
    if cached is not None:
        return {"text": cached, "live": _AI_CACHE[key]["live"]}

    payload = {
        "gpa": student.gpa,
        "rank": student.rank,
        "percentile": student.percentile,
        "total_courses": student.total_courses,
        "passed": student.passed_courses,
        "arrears": {"u": student.u_count, "ra": student.ra_count},
        "sa": student.sa_count,
        "wd": student.wd_count,
        "malpractice": {"mm": student.mm_count, "wh2": student.wh2_count},
        "courses": [
            {"subject": c.subject, "grade": c.grade, "points": c.points}
            for c in student.courses
        ],
        "class_gpa": ca.class_gpa,
    }
    system = (
        "You are an expert AI Academic Advisor helping a teacher prepare a "
        "Parent-Teacher Meeting brief. Write structured discussion points using bold keywords.\n"
        "Use only provided metrics. Do not invent causes, attendance, internal marks, "
        "or medical information. " + AI_GUARDRAILS
    )
    user = "Prepare the PTM brief for this student.\n\n" + _metrics_json(payload)
    text = _ai_invoke(system, user)
    if not text:
        return {"text": fallback_ptm_brief(student, ca), "live": "fallback"}
    _cache_set(key, text, True)
    return {"text": text, "live": "live"}


def ai_source_banner(live: str) -> str:
    if live == "live":
        provider = CFG.get("ai_provider", "ollama_cloud")
        model = CFG.get("ollama_model", "llama3")
        label = "Ollama Cloud" if provider == "ollama_cloud" else "local Ollama"
        return f"AI advisory generated by {label} ({model}) · treat as advisory, verify against official records."
    return "AI insights are currently unavailable. Analytics calculations are still available."


def fallback_class_insight(ca: ClassAnalysis) -> str:
    worst = [s for s in ca.subjects if s.arrear_count > 0]
    worst.sort(key=lambda s: (s.arrear_count, -(s.avg_gp or 0)), reverse=True)
    lines = []
    lines.append("## Overall Performance")
    if ca.pass_rate is not None and ca.pass_rate >= 75:
        lines.append(f"- Pass rate is **{ca.pass_rate:.1f}%** across {ca.student_count} students — solid cohort performance.")
    else:
        lines.append(f"- Pass rate is **{ca.pass_rate:.1f}%** — significant scope for academic recovery.")
    lines.append(f"- Class GPA average is **{fmt_gpa(ca.class_gpa)}** (median: **{fmt_gpa(ca.median_gpa)}**).")
    
    lines.append("\n## Strengths")
    if ca.cleared_count > 0:
        lines.append(f"- **{ca.cleared_count} student(s)** cleared all declared subjects without any arrears.")
    top_dist = ca.grade_distribution.get("O", 0) + ca.grade_distribution.get("A+", 0)
    if top_dist > 0:
        lines.append(f"- **{top_dist} result entries** achieved top distinction grades (O or A+).")

    lines.append("\n## Areas Requiring Attention")
    if worst:
        for s in worst[:3]:
            lines.append(f"- **{s.subject}**: {s.arrear_count} arrear(s) ({fmt_pct(s.u_pct)} of cohort).")
    else:
        lines.append("- No subjects show arrear grades in this semester evaluation.")
    if ca.multiple_u_count:
        lines.append(f"- **{ca.multiple_u_count} student(s)** hold multiple arrears requiring immediate intervention.")
    if ca.malpractice_student_count:
        lines.append(f"- 🚨 **{ca.malpractice_student_count} student(s)** carry malpractice status entries (MM/WH2).")

    lines.append("\n## Recommended Faculty Actions")
    lines.append(f"- Organize targeted remedial sessions for the {ca.arrear_student_count} student(s) with active arrears.")
    lines.append("- Review subject delivery for subjects with elevated failure concentrations.")

    lines.append("\n## PTM Discussion Points")
    lines.append("- Share student rank and credit completion metrics with parents.")
    lines.append("- Discuss academic support plans for attention subjects.")
    return "\n".join(lines)


def primary_grade(dist: Dict[str, int]) -> str:
    return max(dist.items(), key=lambda kv: kv[1])[0] if dist else ""


def fmt_pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}%"


def fmt_none_pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}%"


def summary_pct(counts: Dict[str, int]) -> Dict[str, float]:
    total = sum(counts.values())
    if not total:
        return {}
    return {g: round(100.0 * c / total, 1) for g, c in counts.items() if c and c > 0}


def grade_mix(pcts: Dict[str, float]) -> str:
    parts = [f"{g} {round(p)}%" for g, p in pcts.items() if p]
    return ", ".join(parts[:6]) if parts else "no records"


def fallback_subject_insight(subj: SubjectAnalysis, ca: ClassAnalysis) -> str:
    lines = []
    lines.append("## Overall Performance")
    lines.append(f"- **{subj.subject}** average grade point: **{fmt_gp(subj.avg_gp)}**, pass rate: **{fmt_none_pct(subj.pass_pct)}**.")
    lines.append(f"- Total enrolled students: **{subj.student_count}**.")
    
    lines.append("\n## Strengths")
    lines.append(f"- **{subj.pass_count} student(s)** successfully passed this course.")
    lines.append(f"- Grade mix distribution: {grade_mix(summary_pct(subj.grade_counts))}.")

    lines.append("\n## Areas Requiring Attention")
    if subj.arrear_count:
        lines.append(f"- **{subj.arrear_count} student(s)** hold active arrears (U: {subj.u_count}, RA: {subj.ra_count}).")
    else:
        lines.append("- Zero arrears recorded for this subject.")
    if subj.mm_count or subj.wh2_count:
        lines.append(f"- 🚨 **{subj.mm_count + subj.wh2_count} student(s)** have recorded malpractice status (MM: {subj.mm_count}, WH2: {subj.wh2_count}).")

    lines.append("\n## Recommended Faculty Actions")
    lines.append("- Plan targeted revision and tutorial sessions for students holding arrear grades.")
    lines.append("- Compare topic difficulty against class performance average.")

    lines.append("\n## PTM Discussion Points")
    lines.append(f"- Review student's grade achieved in {subj.subject} relative to class median ({fmt_gp(subj.median_gp)}).")
    return "\n".join(lines)


def fallback_student_brief(student: StudentAnalysis, ca: ClassAnalysis) -> str:
    lines = []
    lines.append("## Overall Performance")
    lines.append(f"- Student **{student.name} ({student.regno})** achieved GPA **{fmt_gpa(student.gpa)}** (Class Avg: **{fmt_gpa(ca.class_gpa)}**).")
    lines.append(f"- Rank: **{rank_text(student, ca.student_count)}** (Percentile: **{fmt_np_pct(student.percentile)}**).")

    lines.append("\n## Strengths")
    if student.strongest_subjects:
        lines.append("- Strongest performance in: **" + ", ".join(student.strongest_subjects[:3]) + "**.")
    else:
        lines.append("- Maintained passing grade standards across courses.")

    lines.append("\n## Areas Requiring Attention")
    if student.attention_subjects:
        lines.append("- Courses requiring immediate attention: **" + ", ".join(student.attention_subjects) + "**.")
    else:
        lines.append("- Cleared all registered semester subjects.")

    lines.append("\n## Recommended Faculty Actions")
    lines.append("- Monitor academic progress in re-assessment cycles.")
    lines.append("- Provide structured study guidance for arrear courses.")

    lines.append("\n## PTM Discussion Points")
    lines.append("- Present academic summary and credit completion status to parent.")
    lines.append("- Align on targeted home study schedule.")
    return "\n".join(lines)


def fallback_ptm_brief(student: StudentAnalysis, ca: ClassAnalysis) -> str:
    lines = []
    lines.append("## Overall Performance")
    lines.append(f"- **{student.name} ({student.regno})** holds GPA **{fmt_gpa(student.gpa)}** with rank **{rank_text(student, ca.student_count)}**.")
    lines.append(f"- Credits Completed: **{student.credits_completed:.1f} / {student.credits_attempted:.1f}**.")

    lines.append("\n## Strengths")
    lines.append("- " + (", ".join(f"**{s}**" for s in student.strongest_subjects[:3]) if student.strongest_subjects
                         else "Cleared declared result papers."))

    lines.append("\n## Areas Requiring Attention")
    if student.attention_subjects:
        for c in student.courses:
            if c.grade in FAILING_GRADES:
                lines.append(f"- **{c.subject}** (Grade: {c.grade})")
    else:
        lines.append("- No active arrears or failure statuses.")

    lines.append("\n## Recommended Faculty Actions")
    lines.append("- Provide remedial material for subjects needing attention.")
    lines.append("- Schedule follow-up assessment before next term.")

    lines.append("\n## PTM Discussion Points")
    lines.append("- Review student effort alignment with declared course credits.")
    lines.append("- Discuss academic support plan and progress tracking.")
    return "\n".join(lines)


def fmt_gpa(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def fmt_gp(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.2f}"


def fmt_np_pct(v: Optional[float]) -> str:
    return "—" if v is None else f"{v:.1f}%"


def rank_text(s: StudentAnalysis, total_students: int = 0) -> str:
    if s.rank is None:
        return "—"
    return f"{s.rank} of {total_students}" if total_students else f"{s.rank}"


# =============================================================================
# 9) PDF GENERATION (xhtml2pdf.pisa -- Professional University Grade Level)
# =============================================================================

PDF_CSS = """
<style>
@page { size: A4; margin: 18mm 14mm 16mm 14mm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10px; color: #1e293b; line-height: 1.45; }
h1 { font-size: 18px; color: #0f1b33; margin: 0 0 4px 0; font-weight: bold; }
h2 { font-size: 13px; color: #0f1b33; margin: 14px 0 6px 0; border-bottom: 1.5px solid #cbd5e1; padding-bottom: 3px; font-weight: bold; }
h3 { font-size: 11px; color: #1e3a5f; margin: 10px 0 4px 0; font-weight: bold; }
.header-box { background: #0f1b33; color: #ffffff; padding: 14px; border-radius: 6px; margin-bottom: 16px; text-align: center; }
.header-box h1 { color: #ffffff; margin: 0; font-size: 18px; letter-spacing: 0.5px; text-transform: uppercase; }
.header-box p { color: #cbd5e1; margin: 3px 0 0 0; font-size: 10px; }
.meta-box { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px; margin-bottom: 14px; font-size: 9px; }
table { width: 100%; border-collapse: collapse; margin: 6px 0 10px 0; }
th { background: #0f1b33; color: #fff; font-size: 9px; text-align: left; padding: 5px 6px; font-weight: bold; }
td { font-size: 9px; padding: 4px 6px; border-bottom: 1px solid #e2e8f0; }
tr:nth-child(even) td { background: #f8fafc; }
.card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; margin: 8px 0; background: #ffffff; }
.badge-pass { color: #16a34a; font-weight: bold; }
.badge-fail { color: #dc2626; font-weight: bold; }
.grade-o { background: #16a34a; } .grade-aplus { background: #22c55e; }
.grade-a { background: #4ade80; } .grade-bplus { background: #86efac; }
.grade-b { background: #64748b; } .grade-c { background: #94a3b8; }
.grade-u { background: #dc2626; } .grade-ra { background: #ef4444; }
.grade-sa { background: #d97706; } .grade-wd { background: #9333ea; }
.grade-mm { background: #7c3aed; } .grade-wh2 { background: #6b21a8; }
.alert-red { color: #dc2626; font-weight: bold; }
.note { font-size: 8px; color: #94a3b8; margin-top: 16px; border-top: 1px solid #e2e8f0; padding-top: 6px; text-align: center; }
</style>
"""


def _css_bar(label: str, value: int, max_val: int, color_cls: str) -> str:
    if not max_val:
        return ""
    pct = min(100.0 * value / max_val, 100)
    label_esc = html.escape(str(label))
    return (f'<div class="bar-row">'
            f'<span class="bar-label">{label_esc}</span>'
            f'<span class="bar-track"><span class="bar-fill {color_cls}" '
            f'style="width:{pct:.1f}%"></span></span>'
            f'<span class="bar-val">{value}</span></div>')


def _css_bars(title: str, items: List[Tuple[str, int, str]]) -> str:
    if not items:
        return ""
    max_val = max(v for _, v, _ in items if v > 0) or 1
    rows = "".join(_css_bar(l, v, max_val, c) for l, v, c in items if v > 0)
    title_esc = html.escape(title)
    return f"<h3>{title_esc}</h3>{rows}" if rows else ""


def _grade_color_cls(grade: str) -> str:
    mapping = {"O": "grade-o", "A+": "grade-aplus", "A": "grade-a",
               "B+": "grade-bplus", "B": "grade-b", "C": "grade-c",
               "U": "grade-u", "RA": "grade-ra", "SA": "grade-sa",
               "WD": "grade-wd", "MM": "grade-mm", "WH2": "grade-wh2"}
    return mapping.get(grade, "")


def _md_to_pdf_html(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    out = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("<br/>")
            continue
        if stripped.startswith("## "):
            inner = html.escape(stripped[3:])
            out.append(f"<h2>{inner}</h2>")
        elif stripped.startswith("- "):
            inner = html.escape(stripped[2:])
            inner = re.sub(r"&lt;strong&gt;(.+?)&lt;/strong&gt;", r"<b>\1</b>", inner)
            inner = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", inner)
            out.append(f"<li>{inner}</li>")
        elif stripped.startswith("**") and stripped.endswith("**"):
            inner = html.escape(stripped.strip("*"))
            out.append(f"<h3>{inner}</h3>")
        else:
            inner = html.escape(stripped)
            inner = re.sub(r"&lt;strong&gt;(.+?)&lt;/strong&gt;", r"<b>\1</b>", inner)
            inner = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", inner)
            out.append(f"<p>{inner}</p>")
    return "\n".join(out)


def _pdf_wrap(title: str, body_html: str) -> str:
    ts = datetime.now().strftime("%d %B %Y, %H:%M")
    title_esc = html.escape(title)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>{PDF_CSS}
<title>{title_esc}</title></head>
<body>
<div class="header-box">
<h1>SARANATHAN COLLEGE OF ENGINEERING</h1>
<p>FACULTY GRADE ANALYTICS PORTAL · REGULATIONS 2024 · OFFICIAL ACADEMIC REPORT</p>
</div>
<div class="meta-box">
<b>Report Title:</b> {title_esc} &nbsp;|&nbsp; <b>Generated Date:</b> {ts} &nbsp;|&nbsp; <b>Status:</b> Official Declared Results
</div>
{body_html}
<p class="note">Official University Executive Grade Analytics Report generated under Regulations 2024.<br/>
AI Advisory components are derived from declared metrics; verify against official registrar records.</p>
</body></html>"""


def pdf_from_html(html_str: str, title: str) -> Optional[bytes]:
    if not _PISA_OK:
        return None
    bio = io.BytesIO()
    try:
        status = pisa.CreatePDF(
            src=html_str,
            dest=bio,
            encoding="utf-8",
        )
        if status.err:
            return None
        return bio.getvalue()
    except Exception:
        return None


def build_class_pdf(ca: ClassAnalysis, ai_text: str) -> Optional[bytes]:
    parts = []

    # Requirement 5: Cover / Executive Summary Section
    parts.append("<h2>Executive Summary & Cohort Overview</h2>")
    parts.append("<table><tr><th>Metric</th><th>Value</th><th>Metric</th><th>Value</th></tr>")
    parts.append(
        f"<tr><td>Total Students</td><td><b>{ca.student_count}</b></td>"
        f"<td>Class GPA Average</td><td><b>{fmt_gpa(ca.class_gpa)}</b></td></tr>"
        f"<tr><td>Total Evaluated Subjects</td><td><b>{ca.subject_count}</b></td>"
        f"<td>Cleared Pass Rate</td><td><b>{fmt_np_pct(ca.pass_rate)}</b></td></tr>"
        f"<tr><td>Students Cleared</td><td><b>{ca.cleared_count}</b></td>"
        f"<td>Students with Arrears (U/RA)</td><td><b class='alert-red'>{ca.arrear_student_count}</b></td></tr>"
        f"<tr><td>Multiple Arrears</td><td><b class='alert-red'>{ca.multiple_u_count}</b></td>"
        f"<td>Malpractice Records (MM/WH2)</td><td><b>{ca.malpractice_student_count}</b></td></tr>"
    )
    parts.append("</table>")

    # Static PNG chart via Kaleido if available, otherwise pure CSS bar fallback
    gd_png = fig_to_png(fig_grade_distribution(ca))
    if gd_png:
        parts.append(f"<h3>Grade Distribution Chart</h3><p><img src='{png_data_url(gd_png)}' style='width:100%; max-height:240px;' /></p>")
    else:
        gd_items = [(g, ca.grade_distribution.get(g, 0), _grade_color_cls(g))
                    for g in GRADE_ORDER]
        parts.append(_css_bars("Grade Distribution Summary", gd_items))

    # Subject Performance Ranking Section
    parts.append("<h2>Subject Performance Ranking</h2><table>"
                 "<tr><th>Rank</th><th>Subject</th><th>Code</th><th>Credits</th>"
                 "<th>Students</th><th>Avg GP</th><th>Pass %</th><th>Priority Rating</th></tr>")
    ranked_subjects = sorted(ca.subjects, key=lambda s: (s.pass_pct or 0, s.avg_gp or 0), reverse=True)
    for idx, s in enumerate(ranked_subjects, start=1):
        p_cls = "alert-red" if s.priority_level == "High Attention" else ""
        parts.append(
            f"<tr><td>{idx}</td><td>{html.escape(s.subject)}</td><td>{html.escape(s.course_code or '—')}</td>"
            f"<td>{s.credits}</td><td>{s.student_count}</td>"
            f"<td>{fmt_gp(s.avg_gp)}</td><td>{fmt_np_pct(s.pass_pct)}</td>"
            f"<td><span class='{p_cls}'>{s.priority_level}</span></td></tr>"
        )
    parts.append("</table>")

    # High Priority Student Support Section
    attn = [s for s in ca.students if s.attention != STATUS_CLEARED]
    if attn:
        parts.append("<h2>High Priority Student Support List</h2><table>"
                     "<tr><th>Reg No</th><th>Name</th><th>Academic Status</th><th>GPA</th><th>Arrears</th></tr>")
        for s in attn[:25]:
            parts.append(
                f"<tr><td>{html.escape(s.regno)}</td><td>{html.escape(s.name)}</td>"
                f"<td>{html.escape(s.attention.upper())}</td><td>{fmt_gpa(s.gpa)}</td>"
                f"<td>{s.arrear_count}</td></tr>"
            )
        parts.append("</table>")

    # Top Rankings
    ranked = [s for s in ca.students if s.gpa is not None]
    ranked.sort(key=lambda s: (s.rank or 9999, s.regno))
    if ranked:
        parts.append("<h2>Class Rankings (Top 25)</h2><table>"
                     "<tr><th>Rank</th><th>Reg No</th><th>Name</th><th>GPA</th><th>Percentile</th></tr>")
        for s in ranked[:25]:
            parts.append(
                f"<tr><td>{s.rank}</td><td>{html.escape(s.regno)}</td><td>{html.escape(s.name)}</td>"
                f"<td>{fmt_gpa(s.gpa)}</td><td>{fmt_np_pct(s.percentile)}</td></tr>"
            )
        parts.append("</table>")

    if ai_text:
        parts.append("<h2>AI Academic Advisory Insight</h2>")
        parts.append(f"<div class='card'>{_md_to_pdf_html(ai_text)}</div>")

    body = "\n".join(parts)
    return pdf_from_html(_pdf_wrap("Executive Class Analytics Report", body), "Executive Class Analytics Report")


def build_subject_pdf(subj: SubjectAnalysis, ca: ClassAnalysis, ai_text: str) -> Optional[bytes]:
    parts = []

    parts.append(f"<h2>Subject Performance Analysis: {html.escape(subj.subject)}</h2>")
    if subj.course_code:
        parts.append(f"<p><b>Course Code:</b> {html.escape(subj.course_code)}</p>")
    parts.append("<table><tr><th>Metric</th><th>Value</th></tr>")
    for label, val in [
        ("Course Credits", subj.credits),
        ("Students Enrolled", subj.student_count),
        ("Average Grade Point", fmt_gp(subj.avg_gp)),
        ("Median Grade Point", fmt_gp(subj.median_gp)),
        ("Pass Count", f"{subj.pass_count} ({fmt_np_pct(subj.pass_pct)})"),
        ("U Count (Arrear)", subj.u_count),
        ("RA Count (Arrear)", subj.ra_count),
        ("SA Count (Attendance)", subj.sa_count),
        ("WD Count (Withdrawal)", subj.wd_count),
        ("MM / WH2 (Malpractice)", subj.mm_count + subj.wh2_count),
        ("Priority Rating", subj.priority_level),
    ]:
        parts.append(f"<tr><td>{html.escape(str(label))}</td><td>{html.escape(str(val))}</td></tr>")
    parts.append("</table>")

    gd_items = [(g, subj.grade_counts.get(g, 0), _grade_color_cls(g))
                for g in GRADE_ORDER if subj.grade_counts.get(g, 0) > 0]
    parts.append(_css_bars("Subject Grade Distribution", gd_items))

    if subj.top_students:
        parts.append("<h3>Top Performers</h3><table>"
                     "<tr><th>Reg No</th><th>Name</th><th>Grade</th><th>Points</th></tr>")
        for st in subj.top_students[:10]:
            parts.append(
                f"<tr><td>{html.escape(st['regno'])}</td><td>{html.escape(st['name'])}</td>"
                f"<td>{html.escape(st['grade'])}</td><td>{st['points']}</td></tr>"
            )
        parts.append("</table>")

    if subj.u_students:
        parts.append("<h3 class='alert-red'>Students with Arrear Grade (U / RA)</h3><table>"
                     "<tr><th>Reg No</th><th>Name</th><th>Grade</th></tr>")
        for st in subj.u_students:
            parts.append(f"<tr><td>{html.escape(st['regno'])}</td><td>{html.escape(st['name'])}</td><td>{html.escape(st['grade'])}</td></tr>")
        parts.append("</table>")

    parts.append("<h3>Subject vs Class Benchmark</h3><table>"
                 "<tr><th>Metric</th><th>This Subject</th><th>Class Overall Average</th></tr>")
    parts.append(
        f"<tr><td>Average GP</td><td>{fmt_gp(subj.avg_gp)}</td>"
        f"<td>{fmt_gp(ca.class_gpa)}</td></tr>"
    )
    parts.append(
        f"<tr><td>Pass Rate</td><td>{fmt_np_pct(subj.pass_pct)}</td>"
        f"<td>{fmt_np_pct(ca.pass_rate)}</td></tr>"
    )
    parts.append("</table>")

    if ai_text:
        parts.append("<h2>AI Subject Advisory</h2>")
        parts.append(f"<div class='card'>{_md_to_pdf_html(ai_text)}</div>")

    body = "\n".join(parts)
    return pdf_from_html(_pdf_wrap(f"Subject Report – {subj.subject}", body),
                         f"Subject Report – {subj.subject}")


def build_student_pdf(student: StudentAnalysis, ca: ClassAnalysis, ai_text: str) -> Optional[bytes]:
    parts = []

    parts.append(f"<h2>Student Academic Profile: {html.escape(student.name)}</h2>")
    parts.append(f"<p><b>Register Number:</b> {html.escape(student.regno)}</p>")
    if student.meta.get("dept"):
        parts.append(f"<p><b>Department:</b> {html.escape(student.meta['dept'])}</p>")

    parts.append("<h3>Academic Snapshot</h3><table><tr><th>Metric</th><th>Value</th></tr>")
    for label, val in [
        ("Semester GPA", fmt_gpa(student.gpa)),
        ("Class GPA Average", fmt_gpa(ca.class_gpa)),
        ("Class Rank", rank_text(student, ca.student_count)),
        ("Percentile Position", fmt_np_pct(student.percentile)),
        ("Total Registered Courses", student.total_courses),
        ("Credits Completed", f"{student.credits_completed:.1f}"),
        ("Credits Attempted", f"{student.credits_attempted:.1f}"),
        ("Quality Points Earned", f"{student.quality_points:.1f}"),
        ("Courses Passed", student.passed_courses),
        ("Arrears (U / RA)", f"{student.arrear_count} (U:{student.u_count}, RA:{student.ra_count})"),
        ("SA (Attendance Shortage)", student.sa_count),
        ("WD (Withdrawn)", student.wd_count),
        ("Malpractice (MM / WH2)", f"{student.malpractice_count} (MM:{student.mm_count}, WH2:{student.wh2_count})"),
        ("Academic Status", student.attention.upper()),
    ]:
        parts.append(f"<tr><td>{html.escape(str(label))}</td><td>{html.escape(str(val))}</td></tr>")
    parts.append("</table>")

    s_png = fig_to_png(fig_student_subjects(student))
    if s_png:
        parts.append(f"<h3>Subject-wise Grade Points Chart</h3><p><img src='{png_data_url(s_png)}' style='width:100%; max-height:240px;' /></p>")
    else:
        gp_items = [(g, student.grade_counts.get(g, 0), _grade_color_cls(g))
                    for g in GRADE_ORDER if student.grade_counts.get(g, 0) > 0]
        parts.append(_css_bars("Student Grade Profile", gp_items))

    if student.courses:
        parts.append("<h3>Semester Course Results & Quality Points</h3><table>"
                     "<tr><th>Subject</th><th>Credits</th><th>Grade</th>"
                     "<th>Points</th><th>Quality Points</th></tr>")
        for c in student.courses:
            status = "✓" if c.grade in PASSING_GRADES else "✗"
            parts.append(
                f"<tr><td>{html.escape(c.subject)}</td><td>{c.credits}</td>"
                f"<td>{html.escape(c.grade)}</td><td>{c.points}</td>"
                f"<td>{c.credits * c.points:.1f} {status}</td></tr>"
            )
        if student.credits_completed > 0:
            parts.append(
                f"<tr><td><b>Total (passing)</b></td>"
                f"<td>{student.credits_completed:.1f}</td>"
                f"<td>—</td><td>—</td>"
                f"<td>{student.quality_points:.1f}</td></tr>"
            )
            parts.append(
                f"<tr><td><b>Semester GPA</b></td><td colspan='3'>({student.quality_points:.1f} / "
                f"{student.credits_completed:.1f})</td>"
                f"<td><b>{fmt_gpa(student.gpa)}</b></td></tr>"
            )
        parts.append("</table>")

    if student.strongest_subjects:
        strong_esc = html.escape(", ".join(student.strongest_subjects[:6]))
        parts.append(f"<h3>Strongest Performance Subjects</h3><p>{strong_esc}</p>")
    if student.attention_subjects:
        attn_esc = html.escape(", ".join(student.attention_subjects))
        parts.append(f"<h3 class='alert-red'>Subjects Requiring Attention</h3><p>{attn_esc}</p>")

    if ai_text:
        parts.append("<h2>AI Academic Brief & PTM Discussion Points</h2>")
        parts.append(f"<div class='card'>{_md_to_pdf_html(ai_text)}</div>")

    body = "\n".join(parts)
    return pdf_from_html(
        _pdf_wrap(f"Student Report – {student.name} ({student.regno})", body),
        f"Student Report – {student.name}"
    )


# =============================================================================
# 10) REPORT CACHE & UUID VALIDATION
# =============================================================================

REPORT_CACHE: Dict[str, Dict[str, Any]] = {}


def is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def create_report_id(kind: str, payload: Dict[str, Any]) -> str:
    rid = str(uuid.uuid4())
    REPORT_CACHE[rid] = {
        "kind": kind,
        "payload": payload,
        "created": datetime.now().isoformat(),
    }
    return rid


def get_report(rid: str) -> Optional[Dict[str, Any]]:
    if not is_valid_uuid(rid):
        return None
    return REPORT_CACHE.get(rid)


def generate_report_pdf(rid: str) -> Optional[bytes]:
    entry = get_report(rid)
    if not entry:
        return None
    kind = entry["kind"]
    pl = entry["payload"]
    ca = pl.get("class_analysis")
    if ca is None:
        return None

    if kind == "class":
        ai = generate_class_ai_insight(ca)
        return build_class_pdf(ca, ai["text"])
    elif kind == "subject":
        subj = get_subject(ca, pl.get("subject", ""))
        if not subj:
            return None
        ai = generate_subject_ai_insight(subj, ca)
        return build_subject_pdf(subj, ca, ai["text"])
    elif kind == "student":
        student = get_student(ca, pl.get("regno", ""))
        if not student:
            return None
        ai = generate_student_brief(student, ca)
        return build_student_pdf(student, ca, ai["text"])
    return None


# =============================================================================
# 11) REUSABLE FASTHTML COMPONENTS + SESSION STATE
# =============================================================================

SESSION: Dict[str, Any] = {
    "records": None,
    "analytics": None,
    "file_name": "",
    "validation": None,
    "preview_raw_bytes": None,
    "preview_filename": "",
    "preview_cols": [],
    "preview_report": None,
    "ptm_briefs": {},
}

_ALERTS: List[Tuple[str, str]] = []


def push_alert(message: str, kind: str = "blue") -> None:
    _ALERTS.append((kind, message))


def pop_alerts() -> List[Tuple[str, str]]:
    out = list(_ALERTS)
    _ALERTS.clear()
    return out


def session_ready() -> bool:
    return SESSION["analytics"] is not None


COLORS = {
    "blue": "bg-blue-50 border-blue-300 text-blue-800",
    "green": "bg-green-50 border-green-300 text-green-800",
    "red": "bg-red-50 border-red-300 text-red-800",
    "amber": "bg-amber-50 border-amber-300 text-amber-800",
    "slate": "bg-slate-50 border-slate-300 text-slate-700",
}


def md_to_html(text: str) -> str:
    if not text:
        return ""
    lines = text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append("<br/>")
            continue
        if s.startswith("## "):
            inner = html.escape(s[3:])
            out.append(f"<h3 class='text-base font-bold text-slate-800 mt-4 mb-2 border-b pb-1'>{inner}</h3>")
        elif s.startswith("- "):
            inner = html.escape(s[2:])
            inner = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", inner)
            out.append(f"<li class='my-1 ml-4 list-disc'>{inner}</li>")
        elif s.startswith("**") and s.endswith("**"):
            inner = html.escape(s.strip("*"))
            out.append(f"<h4 class='mt-3 mb-1 font-semibold text-slate-700'>{inner}</h4>")
        else:
            inner = html.escape(s)
            inner = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", inner)
            out.append(f"<p class='my-1'>{inner}</p>")
    return "".join(out)


def grade_badge(grade: str) -> Span:
    css_class = grade.replace("+", "PLUS").replace(" ", "")
    return Span(grade, cls=f"grade-badge grade-{css_class}")


def status_badge(status: str) -> Span:
    m = {
        STATUS_CLEARED: ("Cleared", "badge-green"),
        STATUS_U: ("Arrear (1)", "badge-red"),
        STATUS_MULTI_U: ("Multi-Arrear", "badge-red"),
        STATUS_SA: ("SA (Attendance)", "badge-amber"),
        STATUS_WD: ("WD (Withdrawn)", "badge-purple"),
        STATUS_MALPRACTICE: ("🚨 Malpractice", "badge-indigo"),
    }
    label, cls = m.get(status, ("—", "badge-slate"))
    return Span(label, cls=f"badge {cls}")


def gpa_cell(gpa: Optional[float]) -> Span:
    if gpa is None:
        return Span("—", cls="text-slate-300")
    if gpa >= 8.5:
        color = "text-green-600"
    elif gpa >= 7.0:
        color = "text-blue-600"
    elif gpa >= 5.0:
        color = "text-amber-600"
    else:
        color = "text-red-600"
    return Span(f"{gpa:.2f}", cls=f"font-semibold {color}")


def alert_bar(kind: str, message: str) -> Div:
    icon_map = {"blue": "ℹ", "green": "✓", "red": "✕", "amber": "⚠"}
    icon = icon_map.get(kind, "ℹ")
    return Div(
        Span(icon, cls="text-lg"),
        Span(message, cls="text-sm font-medium"),
        cls=f"alert alert-{kind}",
    )


def card(*children, cls: str = "") -> Div:
    return Div(*children, cls=f"card {cls}")


def stat_card(label: str, value: str, accent: str = C_BLUE, sub: str = "") -> Div:
    inner = [
        P(label, cls="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1"),
        P(value, cls="text-3xl font-bold text-slate-800 tracking-tight"),
    ]
    if sub:
        inner.append(P(sub, cls="text-xs text-slate-500 mt-1"))
    return Div(*inner, cls="stat-card", style=f"--accent-color: {accent};")


def chart_container(fig, height: str = "h-80") -> Div:
    return Div(NotStr(chart_html(fig)), cls=f"chart-container {height} overflow-hidden")


def md_block(text: str, live: str = "fallback") -> Div:
    if live == "live":
        provider_name = "Ollama Cloud" if CFG.get("ai_provider") == "ollama_cloud" else "Local Ollama"
        banner_text = f"AI advisory generated by {provider_name} ({CFG.get('ollama_model', 'llama3')})."
        banner_cls = "bg-blue-50 text-blue-700 border-blue-200"
    else:
        banner_text = "AI insights are currently unavailable. Analytics calculations are still available."
        banner_cls = "bg-amber-50 text-amber-800 border-amber-200"

    return Div(
        Div(
            Span(banner_text, cls="text-xs font-medium"),
            cls=f"px-3 py-2 border-b {banner_cls}"
        ),
        Div(NotStr(md_to_html(text)), cls="prose p-4 sm:p-5"),
        cls="card overflow-hidden"
    )


def data_table(headers: List[str], rows: List, sortable: bool = False, table_id: str = "") -> Div:
    ths = [Th(h, scope="col") for h in headers]
    tbody_rows = []
    for row in rows:
        if hasattr(row, "tag") and getattr(row, "tag", "") == "tr":
            tbody_rows.append(row)
        elif isinstance(row, (list, tuple)):
            tds = []
            for cell in row:
                if hasattr(cell, "tag") and getattr(cell, "tag", "") == "td":
                    tds.append(cell)
                else:
                    tds.append(Td(cell if cell is not None else "—"))
            tbody_rows.append(Tr(*tds))
    tbody_id = f"{table_id}-tbody" if table_id else ""
    return Div(
        Table(
            Thead(Tr(*ths)),
            Tbody(*tbody_rows, id=tbody_id),
            id=table_id,
            cls="w-full"
        ),
        cls="overflow-x-auto"
    )


def sidebar(active: str, ca: Optional[ClassAnalysis] = None) -> Div:
    items = [
        ("/upload", "Upload", "upload"),
        ("/dashboard", "Dashboard", "dashboard"),
        ("/students", "Students", "students"),
        ("/subjects", "Subjects", "subjects"),
        ("/attention", "Attention", "attention"),
        ("/rankings", "Rankings", "rankings"),
        ("/ai-insights", "AI Insights", "ai-insights"),
        ("/reports", "Reports", "reports"),
    ]
    nav_items = []
    for href, label, key in items:
        is_active = active == key
        active_cls = "active" if is_active else ""
        nav_items.append(
            A(
                Span(label, cls="sidebar-text"),
                href=href,
                cls=f"sidebar-link {active_cls}",
                aria_label=f"Navigate to {label}"
            )
        )

    return Div(
        Div(
            Div(
                H3(CFG["app_title"], cls="text-white font-bold text-sm tracking-wide"),
                Span(CFG["app_version"], cls="inline-block px-2 py-0.5 mt-1 bg-blue-500/20 text-blue-300 text-[10px] font-semibold rounded-full border border-blue-400/30"),
                P(CFG["app_subtitle"], cls="text-slate-400 text-[10px] mt-1"),
                cls="px-5 pt-6 pb-4 border-b border-white/10 mb-2"
            ),
            *nav_items,
            cls="sidebar hidden lg:flex flex-col w-64 min-h-screen fixed left-0 top-0"
        ),
    )


def mobile_header(active: str) -> Div:
    items = [
        ("/upload", "Upload", "upload"),
        ("/dashboard", "Dashboard", "dashboard"),
        ("/students", "Students", "students"),
        ("/subjects", "Subjects", "subjects"),
        ("/attention", "Attention", "attention"),
        ("/rankings", "Rankings", "rankings"),
        ("/ai-insights", "AI Insights", "ai-insights"),
        ("/reports", "Reports", "reports"),
    ]
    links = []
    for href, label, key in items:
        is_active = active == key
        active_cls = "bg-white/10 text-white" if is_active else "text-slate-300"
        links.append(A(label, href=href, cls=f"block px-4 py-2.5 text-sm font-medium {active_cls} hover:bg-white/5 hover:text-white"))
    return Div(
        Div(
            Button("☰", onclick="document.getElementById('mobnav').classList.toggle('hidden')",
                   cls="text-white text-lg p-2 hover:bg-white/10 rounded-lg",
                   aria_label="Toggle Navigation"),
            Div(
                Span(CFG["app_title"], cls="text-sm font-bold text-white block"),
                Span(f"{CFG['app_version']} · Regulations 2024 Compatible", cls="text-[10px] text-slate-300 block"),
                cls="flex-1"
            ),
            cls="flex items-center gap-3 px-4 py-3 mobile-nav"
        ),
        Div(*links, id="mobnav", cls="hidden bg-navy-800 pb-2 lg:hidden"),
        cls="lg:hidden"
    )


def layout(title: str, active: str, content, ca: Optional[ClassAnalysis] = None) -> Tuple:
    reset_plotly_flag()
    alerts = pop_alerts()
    alert_divs = [alert_bar(k, m) for k, m in alerts]

    main_content = Div(*alert_divs, content,
                       cls="flex-1 max-w-full p-4 sm:p-6 lg:p-8 ml-0 lg:ml-64 min-h-screen bg-slate-50 main-content")

    return (
        Title(title + " – " + CFG["app_title"]),
        mobile_header(active),
        sidebar(active, ca),
        main_content,
        Script("""
        document.addEventListener('DOMContentLoaded', function() {
            document.querySelectorAll('[data-filter]').forEach(function(btn) {
                btn.addEventListener('click', function() {
                    var target = this.getAttribute('data-filter-target') || 'student-row';
                    var val = this.getAttribute('data-filter');
                    document.querySelectorAll('tr[data-row-type="' + target + '"]').forEach(function(tr) {
                        if (val === 'all') {
                            tr.style.display = '';
                        } else if (val === 'high') {
                            tr.style.display = (tr.getAttribute('data-high') === 'true') ? '' : 'none';
                        } else {
                            tr.style.display = (tr.getAttribute('data-status') === val) ? '' : 'none';
                        }
                    });
                    this.closest('.filter-group').querySelectorAll('.filter-btn').forEach(function(b) {
                        b.classList.remove('active');
                    });
                    this.classList.add('active');
                });
            });
            var mobToggle = document.getElementById('mobnav');
            if (mobToggle) {
                document.addEventListener('click', function(e) {
                    if (!e.target.closest('.mobile-nav') && !mobToggle.contains(e.target)) {
                        mobToggle.classList.add('hidden');
                    }
                });
            }
        });
        """),
    )


# =============================================================================
# 12) PAGE FUNCTIONS
# =============================================================================

def page_upload() -> Tuple:
    return layout("Upload", "upload", Div(
        H1("Upload Semester Result", cls="text-2xl font-bold text-slate-800 mb-2"),
        P("Upload an official .xlsx spreadsheet containing declared final result grades.",
          cls="text-slate-500 mb-8"),
        Form(
            Div(
                Div(
                    Div(
                        Span("📄", cls="text-4xl mb-3 block", id="upload-icon"),
                        P("Drag & drop your .xlsx file here", cls="text-slate-600 font-medium mb-1", id="upload-text"),
                        P("or click to browse from system", cls="text-slate-400 text-sm", id="upload-subtext"),
                        cls="text-center py-8"
                    ),
                    Input(type="file", name="file", accept=".xlsx", aria_label="Upload Excel spreadsheet file",
                          id="file-input",
                          cls="absolute inset-0 w-full h-full opacity-0 cursor-pointer"),
                    id="drop-zone",
                    cls="relative border-2 border-dashed border-slate-300 rounded-xl hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
                ),
                P(f"Accepted format: .xlsx only. Maximum size limit: {CFG['max_upload_mb']} MB.",
                  cls="mt-3 text-xs text-slate-400 text-center"),
                cls="mb-6"
            ),
            # Progress overlay (hidden by default)
            Div(
                Div(
                    Div(cls="upload-spinner"),
                    P("Uploading & analyzing…", cls="text-slate-600 font-medium mt-3", id="progress-text"),
                    P("Please wait while we process your spreadsheet.", cls="text-slate-400 text-sm mt-1"),
                    cls="text-center"
                ),
                id="upload-progress",
                cls="hidden rounded-xl bg-white/90 backdrop-blur-sm border border-slate-200 p-8 mb-6"
            ),
            Button("Analyze Spreadsheet & Preview Mapping →", type="submit", id="upload-btn",
                   cls="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold "
                       "py-3.5 px-6 rounded-lg transition-all hover:shadow-lg active:scale-[0.98]"),
            action="/upload-preview", method="POST", enctype="multipart/form-data",
            cls="card p-6"
        ),
        Style("""
            .upload-spinner {
                width: 40px; height: 40px; margin: 0 auto;
                border: 4px solid #e2e8f0; border-top-color: #3b82f6;
                border-radius: 50%; animation: spin 0.8s linear infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
            #drop-zone.drag-over {
                border-color: #3b82f6 !important;
                background-color: rgba(59, 130, 246, 0.08) !important;
                transform: scale(1.01);
            }
            #drop-zone.file-selected {
                border-color: #16a34a !important;
                background-color: rgba(22, 163, 74, 0.05) !important;
            }
        """),
        Script("""
        (function() {
            var dropZone = document.getElementById('drop-zone');
            var fileInput = document.getElementById('file-input');
            var uploadIcon = document.getElementById('upload-icon');
            var uploadText = document.getElementById('upload-text');
            var uploadSubtext = document.getElementById('upload-subtext');
            var uploadBtn = document.getElementById('upload-btn');
            var progressDiv = document.getElementById('upload-progress');
            var form = dropZone ? dropZone.closest('form') : null;

            if (!dropZone || !fileInput || !form) return;

            function showFileSelected(name) {
                dropZone.classList.remove('drag-over');
                dropZone.classList.add('file-selected');
                uploadIcon.textContent = '✅';
                uploadText.textContent = name;
                uploadSubtext.textContent = 'File ready. Click the button below to analyze.';
            }

            // Drag & drop events
            ['dragenter', 'dragover'].forEach(function(evt) {
                dropZone.addEventListener(evt, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    dropZone.classList.add('drag-over');
                });
            });
            ['dragleave', 'drop'].forEach(function(evt) {
                dropZone.addEventListener(evt, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    dropZone.classList.remove('drag-over');
                });
            });

            dropZone.addEventListener('drop', function(e) {
                var files = e.dataTransfer.files;
                if (files.length > 0) {
                    var file = files[0];
                    if (file.name.toLowerCase().endsWith('.xlsx')) {
                        fileInput.files = files;
                        showFileSelected(file.name);
                    } else {
                        uploadText.textContent = 'Only .xlsx files are accepted!';
                        uploadText.style.color = '#dc2626';
                        setTimeout(function() {
                            uploadText.textContent = 'Drag & drop your .xlsx file here';
                            uploadText.style.color = '';
                        }, 2500);
                    }
                }
            });

            // File input change (click-to-browse)
            fileInput.addEventListener('change', function() {
                if (fileInput.files.length > 0) {
                    showFileSelected(fileInput.files[0].name);
                }
            });

            // Show progress on form submit
            form.addEventListener('submit', function() {
                if (!fileInput.files || fileInput.files.length === 0) return;
                if (progressDiv) {
                    progressDiv.classList.remove('hidden');
                }
                uploadBtn.disabled = true;
                uploadBtn.textContent = 'Uploading…';
                uploadBtn.classList.add('opacity-60', 'cursor-not-allowed');
            });
        })();
        """),
        cls="max-w-xl mx-auto"
    ))


def page_upload_mapping() -> Tuple:
    """Requirements 1, 2, 3: Structure Preview, Column Mapping & Data Quality Check."""
    cols = SESSION.get("preview_cols", [])
    report: ValidationReport = SESSION.get("preview_report") or ValidationReport()
    filename = SESSION.get("preview_filename", "")
    mapping = report.mapped_columns or {}

    def col_select(target: str, label: str) -> Div:
        options = [Option("-- Unmapped --", value="")]
        selected = mapping.get(target, "")
        for c in cols:
            is_sel = (c == selected)
            options.append(Option(f"{c} {'✓' if is_sel else ''}", value=c, selected=is_sel))
        return Div(
            Label(f"{label}:", cls="block text-xs font-semibold text-slate-600 mb-1"),
            Select(*options, name=f"map_{target}", cls="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white focus:ring-2 focus:ring-blue-500"),
            cls="mb-3"
        )

    return layout("Excel Structure & Column Mapping", "upload", Div(
        H1("Excel File Analysis & Mapping", cls="text-2xl font-bold text-slate-800 mb-2"),
        P(f"File: {html.escape(filename)} · Review structure preview, column mapping, and data quality check.", cls="text-slate-500 mb-6"),

        # Requirement 1: Structure Preview Cards
        Div(
            stat_card("Detected Rows", str(report.total_input_rows), "#3b82f6"),
            stat_card("Valid Records", str(report.valid_records), "#16a34a"),
            stat_card("Sheet Name", report.sheet_name or "Sheet1", "#64748b"),
            stat_card("Quality Status", "Clean" if not report.issues else f"{len(report.issues)} Issues", "#16a34a" if not report.issues else "#d97706"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        ),

        # Requirement 3: Data Quality Check Report
        Div(
            H3("Excel Data Quality Check", cls="text-sm font-bold text-slate-800 mb-3"),
            Div(
                Div(Span("✓", cls="text-green-600 font-bold mr-2"), Span(f"{report.valid_records} valid result records detected.", cls="text-sm text-slate-700"), cls="py-1 flex items-center"),
                Div(Span("✓", cls="text-green-600 font-bold mr-2"), Span(f"Header row located automatically at row {report.header_row + 1}.", cls="text-sm text-slate-700"), cls="py-1 flex items-center"),
                Div(Span("⚠", cls="text-amber-600 font-bold mr-2"), Span(f"{report.duplicates_removed} duplicate row(s) removed during validation.", cls="text-sm text-slate-700"), cls="py-1 flex items-center") if report.duplicates_removed else None,
                Div(Span("⚠", cls="text-amber-600 font-bold mr-2"), Span(f"{report.dropped_rows} row(s) dropped due to missing mandatory fields.", cls="text-sm text-slate-700"), cls="py-1 flex items-center") if report.dropped_rows else None,
            ),
            cls="card p-5 mb-6"
        ),

        # Requirement 2: Column Mapping Form
        Form(
            H3("Detected Column Mapping", cls="text-sm font-bold text-slate-800 mb-3"),
            P("Confirm or adjust spreadsheet column assignments:", cls="text-xs text-slate-500 mb-4"),
            Div(
                col_select("regno", "Register Number"),
                col_select("name", "Student Name"),
                col_select("subject", "Subject Name"),
                col_select("credits", "Course Credits"),
                col_select("grade", "Final Result Grade"),
                col_select("course_code", "Course Code (Optional)"),
                cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6"
            ),
            Div(
                A("← Upload Different File", href="/upload", cls="px-4 py-2.5 text-sm font-medium text-slate-600 hover:text-slate-800"),
                Button("Confirm & Process Full Analytics →", type="submit",
                       cls="px-6 py-2.5 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors shadow-sm"),
                cls="flex items-center justify-between border-t pt-4"
            ),
            action="/upload-confirm", method="POST",
            cls="card p-6 mb-8"
        ),

        cls="max-w-4xl mx-auto"
    ))


def page_dashboard(ca: ClassAnalysis) -> Tuple:
    insights_data = generate_deterministic_insights(ca)
    ai = generate_class_ai_insight(ca)
    grade_dist_fig = fig_grade_distribution(ca)
    subj_avg_fig = fig_subject_avg_gp(ca)
    fail_fig = fig_failure_concentration(ca)
    dist_fig = fig_student_performance_distribution(ca)
    heatmap_fig = fig_grade_heatmap(ca)

    attn = sorted(ca.attention_students, key=lambda s: (s.arrear_count, s.malpractice_count, s.sa_count, s.wd_count), reverse=True)[:6]

    best_subj = insights_data["best_subject"]
    weakest_subj = insights_data["weakest_subject"]

    return layout("Dashboard", "dashboard", Div(
        # Page Title & Interactive Report Shortcut (Requirement 6)
        Div(
            Div(
                H1("Executive Dashboard", cls="text-2xl font-bold text-slate-800"),
                P(f"Semester results summary · {ca.student_count} students · {ca.subject_count} subjects evaluated",
                  cls="text-slate-500 text-sm mt-1"),
                cls="flex-1"
            ),
            Div(
                A("🌐 Open Interactive Web Report", href="/reports/interactive",
                  cls="px-4 py-2 text-sm font-semibold bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg shadow-sm transition-colors mr-2"),
                Form(Button("📄 Download PDF", type="submit",
                            cls="px-4 py-2 text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors"),
                     action="/report/class", method="POST", cls="inline-block"),
                cls="flex items-center gap-2"
            ),
            cls="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6"
        ),

        # 1. Executive Summary Card
        Div(
            Div(
                Div(
                    Span("Academic Health:", cls="text-xs font-semibold uppercase tracking-wider text-slate-400"),
                    Span(insights_data["health_status"],
                         cls=f"ml-2 px-2.5 py-0.5 rounded-full text-xs font-bold border {insights_data['health_bg']} {insights_data['health_color']}"),
                    cls="flex items-center mb-3"
                ),
                Div(
                    Div(
                        P("Class GPA Average", cls="text-xs text-slate-500"),
                        P(fmt_gpa(ca.class_gpa), cls="text-2xl font-bold text-slate-800"),
                        cls="border-r border-slate-100 pr-4"
                    ),
                    Div(
                        P("Pass Rate", cls="text-xs text-slate-500"),
                        P(fmt_np_pct(ca.pass_rate), cls="text-2xl font-bold text-green-600" if (ca.pass_rate or 0) >= 75 else "text-2xl font-bold text-amber-600"),
                        cls="border-r border-slate-100 pr-4 pl-2"
                    ),
                    Div(
                        P("Need Attention", cls="text-xs text-slate-500"),
                        P(str(len(ca.attention_students)), cls="text-2xl font-bold text-red-600"),
                        cls="border-r border-slate-100 pr-4 pl-2"
                    ),
                    Div(
                        P("Multiple Arrears", cls="text-xs text-slate-500"),
                        P(str(ca.multiple_u_count), cls="text-2xl font-bold text-red-700"),
                        cls="pl-2"
                    ),
                    cls="grid grid-cols-2 md:grid-cols-4 gap-2 mb-4 py-2 bg-slate-50 rounded-lg px-4"
                ),
                Div(
                    Div(
                        Span("Best Subject: ", cls="font-semibold text-slate-700"),
                        A(best_subj.subject, href=f"/subjects/{quote(best_subj.subject, safe='')}", cls="text-blue-600 hover:underline font-medium") if best_subj else Span("—"),
                        Span(f" ({best_subj.pass_pct:.1f}% pass rate)" if best_subj and best_subj.pass_pct is not None else "", cls="text-slate-500 text-xs"),
                        cls="text-sm border-r border-slate-200 pr-4"
                    ),
                    Div(
                        Span("Subject Needing Attention: ", cls="font-semibold text-slate-700"),
                        A(weakest_subj.subject, href=f"/subjects/{quote(weakest_subj.subject, safe='')}", cls="text-red-600 hover:underline font-medium") if weakest_subj else Span("None"),
                        Span(f" ({weakest_subj.arrear_count} arrears)" if weakest_subj else "", cls="text-slate-500 text-xs"),
                        cls="text-sm pl-4"
                    ),
                    cls="flex flex-col sm:flex-row sm:items-center gap-2 pt-2 border-t border-slate-100"
                ),
                cls="card p-5"
            ),
            cls="mb-6"
        ),

        # 2. Academic Attention Summary Grid
        Div(
            stat_card("🔴 Arrears (U/RA)", str(ca.arrear_student_count), "#dc2626"),
            stat_card("🟠 Attendance (SA)", str(ca.sa_student_count), "#d97706"),
            stat_card("🟣 Withdrawal (WD)", str(ca.wd_student_count), "#9333ea"),
            stat_card("🔮 Malpractice (MM/WH2)", str(ca.malpractice_student_count), "#7c3aed"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        ),

        # 3. Deterministic Important Insights Section
        Div(
            Div(
                H3("Important Calculated Insights", cls="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2"),
                Div(*[
                    Div(
                        Span("•", cls="text-blue-600 font-bold mr-2 text-lg"),
                        Span(item, cls="text-sm text-slate-700"),
                        cls="flex items-start py-1"
                    ) for item in insights_data["bullet_insights"]
                ]),
                cls="card p-5"
            ),
            cls="mb-6"
        ),

        # Requirement 7: Advanced Charts (Performance Distribution & Heatmap)
        Div(
            Div(
                H3("Cohort Performance Distribution", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(dist_fig, "h-72"),
                cls="card p-5"
            ),
            Div(
                H3("Grade Heatmap Matrix", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(heatmap_fig, "h-72"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # Interactive Standard Charts
        Div(
            Div(
                H3("Grade Distribution", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(grade_dist_fig, "h-72"),
                cls="card p-5"
            ),
            Div(
                H3("Average Grade Point by Subject", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(subj_avg_fig, "h-72"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # 5. Attention & Failure
        Div(
            Div(
                Div(
                    H3("Students Requiring Attention", cls="text-sm font-semibold text-slate-700"),
                    A("View All →", href="/attention", cls="text-xs text-blue-600 hover:underline font-medium"),
                    cls="flex items-center justify-between mb-4"
                ),
                *[Div(
                    Div(
                        A(s.name or "—", href=f"/students/{quote(s.regno, safe='')}",
                          cls="text-sm font-medium text-slate-800 hover:text-blue-600"),
                        P(s.regno, cls="text-xs text-slate-400 font-mono"),
                        cls="flex-1 min-w-0"
                    ),
                    Div(
                        status_badge(s.attention),
                        gpa_cell(s.gpa),
                        Span(f"{s.arrear_count} Arrear", cls="text-xs text-red-600 font-semibold") if s.arrear_count else Span("", cls="text-xs text-slate-300"),
                        cls="flex items-center gap-2"
                    ),
                    cls="flex items-center justify-between py-3 border-b border-slate-100 last:border-0"
                ) for s in attn] or [
                    Div(P("All students cleared.", cls="text-sm text-green-600"), cls="py-4 text-center")
                ],
                cls="card p-5"
            ),
            Div(
                H3("Failure / Arrear Concentration", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(fail_fig, "h-64"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # 6. Subject Performance Table
        Div(
            Div(
                H3("Subject Performance Overview", cls="text-sm font-semibold text-slate-700"),
                A("Subject Details →", href="/subjects", cls="text-xs text-blue-600 hover:underline font-medium"),
                cls="flex items-center justify-between mb-4"
            ),
            data_table(
                ["Subject", "Credits", "Students", "Avg GP", "Pass %", "Arrears (U/RA)", "Priority Rating", "Action"],
                [[
                    A(s.subject, href=f"/subjects/{quote(s.subject, safe='')}", cls="text-blue-600 hover:text-blue-700 font-medium"),
                    s.credits,
                    s.student_count,
                    fmt_gp(s.avg_gp),
                    fmt_np_pct(s.pass_pct),
                    Span(str(s.arrear_count), cls="text-red-600 font-semibold") if s.arrear_count else "0",
                    Span(s.priority_level, cls="text-xs font-bold text-red-600") if s.priority_level == "High Attention" else Span(s.priority_level, cls="text-xs font-medium text-slate-500"),
                    A("View →", href=f"/subjects/{quote(s.subject, safe='')}", cls="text-xs text-slate-500 hover:text-blue-600 font-medium"),
                ] for s in ca.subjects],
                table_id="subject-summary"
            ),
            cls="card p-5 mb-6"
        ),

        # 7. AI Advisory Section
        Div(
            H3("AI Academic Advisory Insight", cls="text-sm font-semibold text-slate-700 mb-3"),
            md_block(ai["text"], ai["live"]),
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_students(ca: ClassAnalysis) -> Tuple:
    students = ca.students
    rows = []
    for s in students:
        rows.append(Tr(
            Td(str(s.rank or "—"), cls="font-medium text-slate-600"),
            Td(s.regno, cls="font-mono text-xs text-slate-500"),
            Td(A(s.name or "—", href=f"/students/{quote(s.regno, safe='')}",
                 cls="text-blue-600 hover:text-blue-700 font-medium")),
            Td(gpa_cell(s.gpa)),
            Td(str(s.arrear_count), cls="text-red-600 font-semibold") if s.arrear_count else Td("0"),
            Td(status_badge(s.attention)),
            Td(f"{s.percentile:.1f}%" if s.percentile else "—", cls="text-slate-500"),
            data_row_type="student-row",
            data_status=s.attention,
            data_high=str(s.is_high_performer).lower(),
        ))

    return layout("Students", "students", Div(
        Div(
            Div(
                H1("Students", cls="text-2xl font-bold text-slate-800"),
                P(f"{len(students)} students · sorted by class rank",
                  cls="text-slate-500 text-sm mt-1"),
                cls="flex-1"
            ),
            Div(
                Input(type="text", placeholder="Search by name or register number...",
                      hx_get="/students/search", hx_trigger="keyup changed delay:300ms",
                      hx_target="#student-table-tbody",
                      cls="w-full sm:w-72 px-4 py-2 text-sm border border-slate-200 rounded-lg "
                          "focus:ring-2 focus:ring-blue-500 focus:border-blue-500 bg-white",
                      aria_label="Search students by name or register number"),
                cls="flex-shrink-0"
            ),
            cls="flex flex-col sm:flex-row sm:items-center gap-4 mb-6"
        ),

        Div(
            Button("All", data_filter="all", data_filter_target="student-row",
                   cls="filter-btn active", aria_label="Filter all students"),
            Button("Cleared", data_filter="cleared", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter cleared students"),
            Button("Arrear (1)", data_filter="u", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter single arrear students"),
            Button("Multi-Arrear", data_filter="multi-u", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter multiple arrear students"),
            Button("SA", data_filter="sa", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter SA students"),
            Button("WD", data_filter="wd", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter WD students"),
            Button("Malpractice", data_filter="malpractice", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter Malpractice students"),
            Button("High Performers", data_filter="high", data_filter_target="student-row",
                   cls="filter-btn", aria_label="Filter high performing students"),
            cls="flex flex-wrap gap-2 mb-6 filter-group"
        ),

        data_table(
            ["Rank", "Reg No", "Name", "GPA", "Arrear Count", "Status", "%ile"],
            rows,
            table_id="student-table"
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_student_detail(ca: ClassAnalysis, regno: str) -> Tuple:
    s = get_student(ca, regno)
    if s is None:
        return layout("Student Not Found", "", Div(
            Div(
                Span("🔍", cls="text-4xl mb-3 block"),
                H1("Student Not Found", cls="text-xl font-bold text-slate-800 mb-2"),
                P(f"No student with register number '{html.escape(regno)}' was found.", cls="text-slate-500 mb-4"),
                A("← Back to Students", href="/students",
                  cls="inline-flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium"),
                cls="text-center py-16"
            ),
            cls="max-w-lg mx-auto"
        ))

    subj_fig = fig_student_subjects(s)
    vs_fig = fig_student_vs_class(s, ca)
    ai = generate_student_brief(s, ca)
    ptm = SESSION.get("ptm_briefs", {}).get(s.regno)

    return layout(f"Student – {s.name}", "students", Div(
        # Navigation bar & Student Header with Prominent Download Button
        Div(
            A("← Back to Students List", href="/students", cls="text-xs text-blue-600 hover:underline font-medium mb-3 inline-block"),
            Div(
                Div(
                    H1(s.name or "—", cls="text-2xl font-bold text-slate-800"),
                    Div(
                        Span(s.regno, cls="text-sm text-slate-500 font-mono"),
                        Span("·", cls="text-slate-300"),
                        status_badge(s.attention),
                        cls="flex items-center gap-2 mt-1"
                    ),
                    cls="flex-1"
                ),
                Div(
                    Form(Button("📥 Download Student PDF Report", type="submit",
                                cls="px-4 py-2.5 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors shadow-sm"),
                         action="/report/student/" + s.regno, method="POST"),
                    cls="flex-shrink-0"
                ),
                cls="flex flex-col sm:flex-row sm:items-center gap-4 mb-6"
            ),
        ),

        # Academic Status Classification Tree Breakdown
        Div(
            H3("Academic Status Breakdown", cls="text-sm font-bold text-slate-800 mb-3"),
            Div(
                Div(
                    Span("🔴 Arrears", cls="font-semibold text-red-700 text-xs block mb-1"),
                    Div(
                        P(f"├── U (Reappearance Required): {s.u_count}", cls="text-xs text-slate-700 font-mono"),
                        P(f"└── RA (Reappearance / Arrear): {s.ra_count}", cls="text-xs text-slate-700 font-mono"),
                        cls="pl-2 border-l-2 border-red-300"
                    ),
                    cls="bg-red-50 p-3.5 rounded-lg border border-red-200"
                ),
                Div(
                    Span("🟠 Attendance Issues", cls="font-semibold text-amber-700 text-xs block mb-1"),
                    Div(
                        P(f"└── SA (Shortage of Attendance): {s.sa_count}", cls="text-xs text-slate-700 font-mono"),
                        cls="pl-2 border-l-2 border-amber-300"
                    ),
                    cls="bg-amber-50 p-3.5 rounded-lg border border-amber-200"
                ),
                Div(
                    Span("🔵 Withdrawal", cls="font-semibold text-purple-700 text-xs block mb-1"),
                    Div(
                        P(f"└── WD (Withdrawal): {s.wd_count}", cls="text-xs text-slate-700 font-mono"),
                        cls="pl-2 border-l-2 border-purple-300"
                    ),
                    cls="bg-purple-50 p-3.5 rounded-lg border border-purple-200"
                ),
                Div(
                    Span("🟣 Malpractice Record", cls="font-semibold text-indigo-700 text-xs block mb-1"),
                    Div(
                        P(f"├── MM (Malpractice): {s.mm_count}", cls="text-xs text-slate-700 font-mono"),
                        P(f"└── WH2 (Malpractice Withheld): {s.wh2_count}", cls="text-xs text-slate-700 font-mono"),
                        cls="pl-2 border-l-2 border-indigo-300"
                    ),
                    cls="bg-indigo-50 p-3.5 rounded-lg border border-indigo-200"
                ),
                cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
            ),
            cls="card p-5 mb-6"
        ),

        # Academic Snapshot Grid
        Div(
            H3("Academic Snapshot", cls="text-sm font-bold text-slate-800 mb-3"),
            Div(
                stat_card("Semester GPA", fmt_gpa(s.gpa), "#16a34a" if (s.gpa or 0) >= 7 else "#d97706"),
                stat_card("Class Rank", rank_text(s, ca.student_count), "#3b82f6"),
                stat_card("Percentile", f"{s.percentile:.1f}%" if s.percentile else "—", "#16a34a"),
                stat_card("Cleared Courses", f"{s.passed_courses}/{s.total_courses}", "#16a34a"),
                stat_card("Arrear Count", str(s.arrear_count), "#dc2626" if s.arrear_count else "#16a34a"),
                stat_card("SA Count", str(s.sa_count), "#d97706"),
                stat_card("WD Count", str(s.wd_count), "#9333ea"),
                stat_card("Malpractice", str(s.malpractice_count), "#7c3aed" if s.malpractice_count else "#64748b"),
                cls="grid grid-cols-2 md:grid-cols-4 gap-4"
            ),
            cls="mb-6"
        ),

        # Course Performance Table
        Div(
            H3("Semester Course Results", cls="text-sm font-semibold text-slate-700 mb-3"),
            data_table(
                ["Subject", "Code", "Credits", "Grade", "Points", "Subject Page"],
                [[
                    c.subject, c.course_code or "—", c.credits,
                    grade_badge(c.grade), f"{c.points}",
                    A("View Subject →", href=f"/subjects/{quote(c.subject, safe='')}", cls="text-xs text-blue-600 hover:underline font-medium")
                ] for c in s.courses],
                table_id="student-result"
            ),
            cls="card p-5 mb-6"
        ),

        # GPA Calculation Breakdown
        Div(
            H3("GPA Calculation Breakdown", cls="text-sm font-semibold text-slate-700 mb-3"),
            Div(
                Div(
                    P("Credits Completed (passed)", cls="text-xs text-slate-500 mb-1"),
                    P(f"{s.credits_completed:.1f}", cls="text-lg font-bold text-slate-800"),
                    cls="flex-1"
                ),
                Div(
                    P("Quality Points Earned", cls="text-xs text-slate-500 mb-1"),
                    P(f"{s.quality_points:.1f}", cls="text-lg font-bold text-slate-800"),
                    cls="flex-1"
                ),
                Div(
                    P("Semester GPA", cls="text-xs text-slate-500 mb-1"),
                    P(fmt_gpa(s.gpa), cls="text-2xl font-bold text-green-600"),
                    cls="flex-1"
                ),
                cls="flex gap-6 p-4 bg-slate-50 rounded-lg"
            ),
            P("Per Regulation 2024: GPA = Total Quality Points / Credits Completed (U, RA, SA, WD, MM, and WH2 excluded).", cls="text-xs text-slate-400 mt-3"),
            cls="card p-5 mb-6"
        ),

        # Student vs Class Visualizations
        Div(
            Div(
                H3("Subject-wise Grade Points", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(subj_fig, "h-64"),
                cls="card p-5"
            ),
            Div(
                H3("Student vs Class Average", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(vs_fig, "h-64"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # Performance Story: Strengths & Attention Areas
        Div(
            Div(
                H3("Strengths", cls="text-sm font-bold text-slate-800 mb-3"),
                Div(*[
                    Span(g, cls="inline-flex items-center px-3 py-1.5 bg-green-50 text-green-700 text-sm font-medium rounded-lg mr-2 mb-2")
                    for g in s.strongest_subjects[:5]
                ] or [P("Maintained declared passing standards across subjects.", cls="text-slate-500 text-sm")]),
                cls="card p-5"
            ),
            Div(
                H3("Attention Areas", cls="text-sm font-bold text-slate-800 mb-3"),
                *[Div(
                    Span(c.subject, cls="text-sm font-medium text-slate-700 flex-1"),
                    grade_badge(c.grade),
                    A("View Subject →", href=f"/subjects/{quote(c.subject, safe='')}", cls="text-xs text-blue-600 hover:underline font-medium ml-3"),
                    cls="flex items-center gap-2 py-1.5 border-b border-slate-100 last:border-0"
                ) for c in s.courses if c.grade in FAILING_GRADES] or [
                    P("Cleared all subjects cleanly with no U, RA, SA, WD, or Malpractice status.", cls="text-sm text-green-600 font-medium")
                ],
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # AI Academic Brief
        Div(
            H3("AI Academic Brief", cls="text-sm font-semibold text-slate-700 mb-3"),
            md_block(ai["text"], ai["live"]),
        ),

        # PTM Brief Action Section
        Div(
            H3("Parent-Teacher Meeting (PTM) Brief", cls="text-sm font-semibold text-slate-700 mb-3"),
            Form(
                Button("Generate / Refresh PTM Brief", type="submit",
                       hx_post=f"/student/{s.regno}/ptm",
                       hx_target="#ptm-result",
                       hx_swap="innerHTML",
                       cls="px-4 py-2 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors mb-4"),
            ),
            Div(
                NotStr(md_to_html(ptm["text"])) if ptm else
                P("Click the button above to generate structured PTM discussion points.",
                  cls="text-sm text-slate-400"),
                id="ptm-result",
                cls="mt-2"
            ),
            cls="card p-5 mb-6"
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_subjects(ca: ClassAnalysis) -> Tuple:
    sorted_by_pass = sorted(ca.subjects, key=lambda s: (s.pass_pct or 0, s.avg_gp or 0), reverse=True)
    sorted_by_u = sorted(ca.subjects, key=lambda s: (s.arrear_count, -(s.pass_pct or 100)), reverse=True)

    best_subj = sorted_by_pass[0] if sorted_by_pass else None
    weakest_subj = sorted_by_u[0] if sorted_by_u and sorted_by_u[0].arrear_count > 0 else None

    fail_fig = fig_failure_concentration(ca)
    avg_fig = fig_subject_avg_gp(ca)
    pass_fig = fig_subject_pass_pct(ca)

    return layout("Subject Analysis", "subjects", Div(
        Div(
            H1("Subject Analysis", cls="text-2xl font-bold text-slate-800"),
            P(f"{len(ca.subjects)} subjects evaluated · comprehensive cohort comparison",
              cls="text-slate-500 text-sm mt-1"),
            cls="mb-6"
        ),

        # Subject Ranking Cards (Dashboard Analytics)
        Div(
            Div(
                Div(
                    Span("🏆 Best Performing Subject", cls="text-sm font-bold text-green-700 mb-1 block"),
                    P(best_subj.subject if best_subj else "—", cls="text-lg font-bold text-slate-800"),
                    P(f"Pass Rate: {fmt_np_pct(best_subj.pass_pct)} · Avg GP: {fmt_gp(best_subj.avg_gp)}" if best_subj else "", cls="text-xs text-slate-500 mt-1"),
                    A("View Subject Details →", href=f"/subjects/{quote(best_subj.subject, safe='')}", cls="text-xs text-blue-600 hover:underline mt-2 inline-block font-medium") if best_subj else None,
                    cls="card p-5 border-l-4 border-l-green-500"
                ),
                Div(
                    Span("⚠️ Weakest Subject (Highest Arrear Count)", cls="text-sm font-bold text-red-700 mb-1 block"),
                    P(weakest_subj.subject if weakest_subj else "None", cls="text-lg font-bold text-slate-800"),
                    P(f"{weakest_subj.arrear_count} arrears · Pass Rate: {fmt_np_pct(weakest_subj.pass_pct)}" if weakest_subj else "All subjects cleared cleanly", cls="text-xs text-slate-500 mt-1"),
                    A("View Subject Details →", href=f"/subjects/{quote(weakest_subj.subject, safe='')}", cls="text-xs text-blue-600 hover:underline mt-2 inline-block font-medium") if weakest_subj else None,
                    cls="card p-5 border-l-4 border-l-red-500"
                ),
                cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6"
            ),
            P("Subject rankings are generated directly from calculated cohort metrics.", cls="text-xs text-slate-400 mb-6 italic"),
        ),

        # Key Metrics Grid
        Div(
            stat_card("Total Subjects", str(len(ca.subjects)), "#3b82f6"),
            stat_card("Total Arrears (U/RA)", str(sum(s.arrear_count for s in ca.subjects)), "#dc2626"),
            stat_card("Average GP Range", f"{min(s.avg_gp or 0 for s in ca.subjects):.1f} – {max(s.avg_gp or 0 for s in ca.subjects):.1f}" if ca.subjects else "—", "#64748b"),
            stat_card("Record Pass Rate", fmt_np_pct(ca.record_pass_rate), "#16a34a"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8"
        ),

        # Visual Charts
        Div(
            Div(
                H3("Average Grade Point by Subject", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(avg_fig, "h-72"),
                cls="card p-5"
            ),
            Div(
                H3("Pass Percentage by Subject", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(pass_fig, "h-72"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        Div(
            H3("Failure / Arrear Concentration across Subjects", cls="text-sm font-semibold text-slate-700 mb-3"),
            chart_container(fail_fig, "h-64"),
            cls="card p-5 mb-6"
        ),

        # All Subjects Health Table with Smarter Priority Rating (Requirement 4)
        Div(
            H3("All Subjects Health Table", cls="text-sm font-semibold text-slate-700 mb-4"),
            data_table(
                ["Subject", "Code", "Credits", "Students", "Avg GP", "Pass %", "Arrears", "Priority Rating", "Action"],
                [[
                    A(s.subject, href=f"/subjects/{quote(s.subject, safe='')}", cls="text-blue-600 hover:text-blue-700 font-medium"),
                    s.course_code or "—",
                    s.credits,
                    s.student_count,
                    fmt_gp(s.avg_gp),
                    fmt_np_pct(s.pass_pct),
                    Span(str(s.arrear_count), cls="text-red-600 font-semibold") if s.arrear_count else "0",
                    Span(s.priority_level, cls="text-xs font-bold text-red-600") if s.priority_level == "High Attention" else Span(s.priority_level, cls="text-xs font-medium text-slate-500"),
                    A("Details →", href=f"/subjects/{quote(s.subject, safe='')}", cls="text-xs text-blue-600 hover:underline font-medium"),
                ] for s in ca.subjects],
                table_id="subject-table"
            ),
            cls="card p-5"
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_subject_detail(ca: ClassAnalysis, subject: str) -> Tuple:
    subj = get_subject(ca, subject)
    if subj is None:
        return layout("Subject Not Found", "", Div(
            Div(
                Span("📚", cls="text-4xl mb-3 block"),
                H1("Subject Not Found", cls="text-xl font-bold text-slate-800 mb-2"),
                P(f"No subject '{html.escape(subject)}' found.", cls="text-slate-500 mb-4"),
                A("← Back to Subjects", href="/subjects",
                  cls="inline-flex items-center gap-2 text-blue-600 hover:text-blue-700 font-medium"),
                cls="text-center py-16"
            ),
            cls="max-w-lg mx-auto"
        ))

    ai = generate_subject_ai_insight(subj, ca)

    diff_str = f"{abs(subj.gp_diff_vs_class):.2f} lower than class avg" if subj.gp_diff_vs_class < 0 else f"+{subj.gp_diff_vs_class:.2f} above class avg"

    return layout(f"Subject – {subj.subject}", "subjects", Div(
        A("← Back to All Subjects", href="/subjects", cls="text-xs text-blue-600 hover:underline font-medium mb-3 inline-block"),
        Div(
            Div(
                H1(subj.subject, cls="text-2xl font-bold text-slate-800"),
                Div(
                    Span(subj.course_code or "—", cls="text-sm text-slate-500 font-mono") if subj.course_code else None,
                    Span(f"Credits: {subj.credits}", cls="text-sm text-slate-500"),
                    Span(f"Priority: {subj.priority_level}", cls="text-xs font-bold text-red-600" if subj.priority_level == "High Attention" else "text-xs font-medium text-slate-500"),
                    cls="flex items-center gap-3 mt-1"
                ),
                cls="flex-1"
            ),
            Div(
                Form(Button("Download Report", type="submit",
                            cls="px-4 py-2 text-sm font-medium bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg transition-colors"),
                     action="/report/subject/" + subj.subject, method="POST"),
                cls="flex-shrink-0"
            ),
            cls="flex flex-col sm:flex-row sm:items-center gap-4 mb-6"
        ),

        # Requirement 4: Smarter Deterministic Subject Analysis Card
        Div(
            H3(f"{subj.subject} Academic Priority & Comparison", cls="text-sm font-bold text-slate-800 mb-3"),
            Div(
                Div(
                    P("Arrear Count", cls="text-xs text-slate-500"),
                    P(f"{subj.arrear_count}", cls="text-xl font-bold text-red-600"),
                    P(f"{fmt_np_pct(subj.u_pct)} failure rate", cls="text-xs text-slate-400 mt-1"),
                    cls="bg-slate-50 p-4 rounded-lg"
                ),
                Div(
                    P("Pass Percentage", cls="text-xs text-slate-500"),
                    P(fmt_np_pct(subj.pass_pct), cls="text-xl font-bold text-slate-800"),
                    P(f"{subj.pass_count} passed", cls="text-xs text-slate-400 mt-1"),
                    cls="bg-slate-50 p-4 rounded-lg"
                ),
                Div(
                    P("Average GP Difference", cls="text-xs text-slate-500"),
                    P(f"{subj.avg_gp:.2f}" if subj.avg_gp else "—", cls="text-xl font-bold text-slate-800"),
                    P(diff_str, cls="text-xs font-medium text-amber-600" if subj.gp_diff_vs_class < 0 else "text-xs font-medium text-green-600"),
                    cls="bg-slate-50 p-4 rounded-lg"
                ),
                Div(
                    P("Attention Priority", cls="text-xs text-slate-500"),
                    P(subj.priority_level, cls="text-xl font-bold text-red-600" if subj.priority_level == "High Attention" else "text-xl font-bold text-slate-800"),
                    P("Deterministic Rating", cls="text-xs text-slate-400 mt-1"),
                    cls="bg-slate-50 p-4 rounded-lg"
                ),
                cls="grid grid-cols-2 md:grid-cols-4 gap-4"
            ),
            cls="card p-5 mb-6"
        ),

        # Subject Result Status Classification Table Breakdown
        Div(
            H3("Result Status Breakdown", cls="text-sm font-semibold text-slate-700 mb-3"),
            Div(
                data_table(
                    ["Passed", "U (Arrear)", "RA (Arrear)", "SA (Attendance)", "WD (Withdrawal)", "MM (Malpractice)", "WH2 (Withheld)"],
                    [[
                        Span(str(subj.pass_count), cls="font-bold text-green-600"),
                        Span(str(subj.u_count), cls="font-bold text-red-600") if subj.u_count else "0",
                        Span(str(subj.ra_count), cls="font-bold text-red-600") if subj.ra_count else "0",
                        Span(str(subj.sa_count), cls="font-bold text-amber-600") if subj.sa_count else "0",
                        Span(str(subj.wd_count), cls="font-bold text-purple-600") if subj.wd_count else "0",
                        Span(str(subj.mm_count), cls="font-bold text-indigo-600") if subj.mm_count else "0",
                        Span(str(subj.wh2_count), cls="font-bold text-indigo-600") if subj.wh2_count else "0",
                    ]]
                ),
                cls="card p-4 mb-6"
            ),
        ),

        # Grade Distribution Breakdown Bars
        Div(
            H3("Detailed Grade Distribution", cls="text-sm font-semibold text-slate-700 mb-4"),
            *[Div(
                Span(g, cls="w-12 text-xs font-bold text-slate-600"),
                Div(
                    Div(style=f"width:{round(100*subj.grade_counts.get(g, 0)/max(subj.student_count,1))}%; background:{GRADE_COLORS.get(g,'#999')};",
                        cls="h-6 rounded-md transition-all"),
                    cls="flex-1 bg-slate-100 rounded-md h-6 overflow-hidden"
                ),
                Span(str(subj.grade_counts.get(g, 0)), cls="w-10 text-xs text-right font-medium text-slate-600"),
                cls="flex items-center gap-3 mb-2"
            ) for g in GRADE_ORDER if subj.grade_counts.get(g, 0) > 0],
            cls="card p-5 mb-6"
        ),

        # Subject vs Class Comparison Table
        Div(
            H3("Subject vs Class Overall Benchmark", cls="text-sm font-semibold text-slate-700 mb-3"),
            data_table(
                ["Metric", "This Subject", "Class Overall Average", "Difference"],
                [
                    ["Avg GP", fmt_gp(subj.avg_gp), fmt_gp(ca.class_gpa),
                     f"+{(subj.avg_gp or 0) - (ca.class_gpa or 0):.2f}" if subj.avg_gp and ca.class_gpa else "—"],
                    ["Pass Rate", fmt_np_pct(subj.pass_pct), fmt_np_pct(ca.pass_rate),
                     f"+{(subj.pass_pct or 0) - (ca.pass_rate or 0):.1f}%" if subj.pass_pct and ca.pass_rate else "—"],
                    ["Arrears", str(subj.arrear_count), str(ca.arrear_student_count),
                     f"+{subj.arrear_count - ca.arrear_student_count}" if subj.arrear_count else "—"],
                ],
            ),
            cls="card p-5 mb-6"
        ),

        # Top Performers Section (UI Visible)
        Div(
            H3("Subject Top Performers", cls="text-sm font-semibold text-slate-700 mb-3"),
            data_table(
                ["Reg No", "Name", "Grade", "Points", "Profile Action"],
                [[st["regno"], st["name"], grade_badge(st["grade"]), st["points"],
                  A("View Student →", href=f"/students/{quote(st['regno'], safe='')}", cls="text-xs text-blue-600 hover:underline font-medium")]
                 for st in subj.top_students[:8]],
            ),
            cls="card p-5 mb-6"
        ),

        # Affected Students (Students with Arrear Grade U / RA)
        Div(
            H3("Students with Arrear Grade (U / RA)", cls="text-sm font-semibold text-red-700 mb-3"),
            *[Div(
                A(st["regno"], href=f"/students/{quote(st['regno'], safe='')}", cls="font-mono text-blue-600 hover:text-blue-700 text-sm font-medium"),
                Span(" — ", cls="text-slate-400"),
                Span(st["name"], cls="text-sm text-slate-700 flex-1"),
                grade_badge(st["grade"]),
                A("View Student Profile →", href=f"/students/{quote(st['regno'], safe='')}", cls="text-xs text-blue-600 hover:underline font-medium ml-3"),
                cls="flex items-center gap-2 py-2 border-b border-slate-100 last:border-0"
            ) for st in subj.u_students] or [
                P("No students with U / RA grade for this subject.", cls="text-sm text-green-600 py-2")
            ],
            cls="card p-5 mb-6"
        ),

        # AI Insight
        Div(
            H3("AI Subject Insight", cls="text-sm font-semibold text-slate-700 mb-3"),
            md_block(ai["text"], ai["live"]),
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_interactive_report(ca: ClassAnalysis) -> Tuple:
    """Requirement 6: Interactive Web Report Mode."""
    ai = generate_class_ai_insight(ca)
    grade_dist_fig = fig_grade_distribution(ca)
    dist_fig = fig_student_performance_distribution(ca)
    heatmap_fig = fig_grade_heatmap(ca)

    return layout("Interactive Web Report", "reports", Div(
        # University Report Header Banner
        Div(
            Div(
                H1("SARANATHAN COLLEGE OF ENGINEERING", cls="text-xl font-extrabold text-white tracking-wide text-center"),
                P("FACULTY GRADE ANALYTICS EXECUTIVE WEB REPORT · REGULATIONS 2024", cls="text-slate-300 text-xs text-center mt-1"),
                Div(
                    Span(f"Generated: {datetime.now().strftime('%d %B %Y')}", cls="text-xs text-slate-400"),
                    Span("·", cls="text-slate-500"),
                    Span(f"Students: {ca.student_count}", cls="text-xs text-slate-400"),
                    Span("·", cls="text-slate-500"),
                    Span(f"Class GPA: {fmt_gpa(ca.class_gpa)}", cls="text-xs text-slate-400"),
                    cls="flex items-center justify-center gap-3 mt-3 border-t border-white/10 pt-2"
                ),
                cls="bg-navy-800 p-6 rounded-xl text-white shadow-lg mb-6"
            ),
        ),

        # Quick Action Buttons
        Div(
            A("📄 Download PDF Report", href="/reports",
              cls="px-4 py-2 text-sm font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm transition-colors"),
            A("← Back to Dashboard", href="/dashboard",
              cls="px-4 py-2 text-sm font-medium bg-slate-200 hover:bg-slate-300 text-slate-700 rounded-lg transition-colors"),
            cls="flex items-center gap-3 mb-6"
        ),

        # Executive Metrics Cards
        Div(
            stat_card("Total Enrolled", str(ca.student_count), "#3b82f6"),
            stat_card("Class GPA Average", fmt_gpa(ca.class_gpa), "#16a34a"),
            stat_card("Cleared Pass Rate", fmt_np_pct(ca.pass_rate), "#16a34a" if (ca.pass_rate or 0) >= 75 else "#d97706"),
            stat_card("Active Arrears (U/RA)", str(ca.arrear_student_count), "#dc2626"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        ),

        # Interactive Visual Analytics Grid
        Div(
            Div(
                H3("Cohort Performance Distribution", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(dist_fig, "h-72"),
                cls="card p-5"
            ),
            Div(
                H3("Grade Heatmap Matrix", cls="text-sm font-semibold text-slate-700 mb-3"),
                chart_container(heatmap_fig, "h-72"),
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        # Subject Performance Ranking Table
        Div(
            H3("Subject Performance Ranking", cls="text-sm font-bold text-slate-800 mb-3"),
            data_table(
                ["Rank", "Subject", "Course Code", "Credits", "Students", "Avg GP", "Pass %", "Priority Rating"],
                [[
                    idx,
                    A(s.subject, href=f"/subjects/{quote(s.subject, safe='')}", cls="text-blue-600 hover:underline font-medium"),
                    s.course_code or "—",
                    s.credits,
                    s.student_count,
                    fmt_gp(s.avg_gp),
                    fmt_np_pct(s.pass_pct),
                    Span(s.priority_level, cls="text-xs font-bold text-red-600") if s.priority_level == "High Attention" else Span(s.priority_level, cls="text-xs font-medium text-slate-500"),
                ] for idx, s in enumerate(sorted(ca.subjects, key=lambda x: (x.pass_pct or 0, x.avg_gp or 0), reverse=True), start=1)],
            ),
            cls="card p-5 mb-6"
        ),

        # AI Advisory Summary
        Div(
            H3("AI Advisory Executive Summary", cls="text-sm font-bold text-slate-800 mb-3"),
            md_block(ai["text"], ai["live"]),
            cls="mb-6"
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_attention(ca: ClassAnalysis) -> Tuple:
    multi_u = [s for s in ca.students if s.attention == STATUS_MULTI_U]
    u_only = [s for s in ca.students if s.attention == STATUS_U]
    sa = [s for s in ca.students if s.attention == STATUS_SA]
    wd = [s for s in ca.students if s.attention == STATUS_WD]
    malpractice = [s for s in ca.students if s.attention == STATUS_MALPRACTICE]

    def attn_section(title, students, badge_cls, empty_msg) -> Div:
        if not students:
            return Div(
                Div(
                    Span("✓", cls="text-2xl mb-2 block text-green-400"),
                    P(empty_msg, cls="text-sm text-slate-500"),
                    cls="text-center py-8"
                ),
                cls="card"
            )
        return Div(
            Div(
                Span(title, cls="text-sm font-semibold text-slate-700"),
                Span(f"{len(students)}", cls="ml-2 badge badge-slate"),
                cls="flex items-center mb-4"
            ),
            *[Div(
                Div(
                    A(s.name or "—", href=f"/students/{quote(s.regno, safe='')}",
                      cls="text-sm font-medium text-slate-800 hover:text-blue-600"),
                    P(s.regno, cls="text-xs text-slate-400 font-mono mt-0.5"),
                    cls="flex-1 min-w-0"
                ),
                Div(
                    gpa_cell(s.gpa),
                    Span(f"{s.arrear_count} Arrear", cls="text-xs text-red-600 font-semibold") if s.arrear_count else None,
                    A("Profile & PTM →", href=f"/students/{quote(s.regno, safe='')}", cls="text-xs text-blue-600 hover:underline font-medium ml-2"),
                    cls="flex items-center gap-3"
                ),
                cls="flex items-center justify-between py-3 border-b border-slate-100 last:border-0"
            ) for s in students],
            cls="card p-5"
        )

    return layout("Attention", "attention", Div(
        Div(
            H1("Students Requiring Attention", cls="text-2xl font-bold text-slate-800"),
            P(f"{len(multi_u) + len(u_only) + len(sa) + len(wd) + len(malpractice)} students need attention across categories",
              cls="text-slate-500 text-sm mt-1"),
            cls="mb-6"
        ),

        Div(
            stat_card("Multiple Arrears", str(len(multi_u)), "#dc2626"),
            stat_card("Single Arrear", str(len(u_only)), "#dc2626"),
            stat_card("SA (Attendance)", str(len(sa)), "#d97706"),
            stat_card("Malpractice (MM/WH2)", str(len(malpractice)), "#7c3aed"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8"
        ),

        Div(
            attn_section("Multiple Arrear Students (U/RA)", multi_u, "badge-red", "No students with multiple arrears."),
            attn_section("Single Arrear Students (U/RA)", u_only, "badge-red", "No students with single arrear."),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),
        Div(
            attn_section("SA – Attendance Shortage", sa, "badge-amber", "No students with SA status."),
            attn_section("WD – Withdrawal Status", wd, "badge-purple", "No students with WD status."),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),
        Div(
            attn_section("🚨 Malpractice Record (MM / WH2)", malpractice, "badge-indigo", "No students with malpractice record."),
            cls="mb-6"
        ),

        cls="max-w-7xl mx-auto"
    ), ca=ca)


def page_rankings(ca: ClassAnalysis) -> Tuple:
    ranked = [s for s in ca.students if s.gpa is not None]
    ranked.sort(key=lambda s: (s.rank or 9999, s.regno))

    rows = []
    for s in ranked:
        medal = ""
        if s.rank == 1:
            medal = "🥇"
        elif s.rank == 2:
            medal = "🥈"
        elif s.rank == 3:
            medal = "🥉"
        rows.append(Tr(
            Td(f"{medal} {s.rank}" if medal else str(s.rank), cls="font-medium text-slate-600"),
            Td(s.regno, cls="font-mono text-xs text-slate-500"),
            Td(A(s.name or "—", href=f"/students/{quote(s.regno, safe='')}",
                 cls="text-blue-600 hover:text-blue-700 font-medium")),
            Td(gpa_cell(s.gpa)),
            Td(f"{s.percentile:.1f}%" if s.percentile else "—", cls="text-slate-500"),
            Td(str(s.arrear_count), cls="text-red-600 font-semibold") if s.arrear_count else Td("0"),
            Td(A("Profile →", href=f"/students/{quote(s.regno, safe='')}", cls="text-xs text-blue-600 hover:underline font-medium")),
        ))

    return layout("Rankings", "rankings", Div(
        Div(
            H1("Class Rankings", cls="text-2xl font-bold text-slate-800"),
            P(f"Based on credit-weighted GPA under Regulations 2024 · {len(ranked)} students ranked",
              cls="text-slate-500 text-sm mt-1"),
            cls="mb-6"
        ),

        Div(
            stat_card("Total Ranked", str(len(ranked)), "#3b82f6"),
            stat_card("Top GPA", fmt_gpa(ranked[0].gpa) if ranked else "—", "#16a34a"),
            stat_card("Median GPA", fmt_gpa(ca.median_gpa), "#64748b"),
            stat_card("Lowest GPA", fmt_gpa(ranked[-1].gpa) if ranked else "—", "#dc2626"),
            cls="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6"
        ),

        data_table(
            ["Rank", "Reg No", "Name", "GPA", "Percentile", "Arrears", "Action"],
            rows,
            table_id="rankings-table"
        ),

        cls="max-w-5xl mx-auto"
    ), ca=ca)


def page_ai_insights(ca: ClassAnalysis) -> Tuple:
    ai = generate_class_ai_insight(ca)

    problems = [s for s in ca.subjects if s.arrear_count > 0]
    problems.sort(key=lambda s: s.arrear_count, reverse=True)

    return layout("AI Insights", "ai-insights", Div(
        Div(
            H1("AI Class Analysis", cls="text-2xl font-bold text-slate-800"),
            P("Advisory output from local analysis and LLM review. Verify against official records.",
              cls="text-slate-500 text-sm mt-1"),
            cls="mb-6"
        ),

        md_block(ai["text"], ai["live"]),

        Div(
            Div(
                Div(
                    Span("✓", cls="text-green-500 text-lg mr-2"),
                    Span("Strengths Summary", cls="text-sm font-semibold text-slate-700"),
                    cls="flex items-center mb-3"
                ),
                P(f"Pass rate: {fmt_np_pct(ca.pass_rate)}", cls="text-sm text-slate-600 mb-1"),
                P(f"Class GPA Average: {fmt_gpa(ca.class_gpa)}", cls="text-sm text-slate-600 mb-1"),
                P(f"Cleared students: {ca.cleared_count} of {ca.student_count}", cls="text-sm text-slate-600"),
                cls="card p-5"
            ),
            Div(
                Div(
                    Span("⚠", cls="text-red-500 text-lg mr-2"),
                    Span("Problem Subjects (Arrears)", cls="text-sm font-semibold text-slate-700"),
                    cls="flex items-center mb-3"
                ),
                *[Div(
                    A(s.subject, href=f"/subjects/{quote(s.subject, safe='')}", cls="font-medium text-slate-700 hover:text-blue-600"),
                    Span(f"{s.arrear_count} Arrear", cls="text-red-600 font-semibold text-sm ml-2"),
                    Span(f"({fmt_np_pct(s.u_pct)})", cls="text-slate-400 text-sm ml-1"),
                    cls="flex items-center py-1.5"
                ) for s in problems[:5]] or [
                    P("No subjects with arrears recorded.", cls="text-sm text-green-600")
                ],
                cls="card p-5"
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6"
        ),

        Div(
            Div(
                Span("→", cls="text-blue-500 text-lg mr-2"),
                Span("Recommended Actions", cls="text-sm font-semibold text-slate-700"),
                cls="flex items-center mb-3"
            ),
            P(f"1. Give targeted support to {ca.multiple_u_count} student(s) with multiple arrears.",
              cls="text-sm text-slate-600 mb-1"),
            P("2. Schedule remedial tutorial sessions for high failure concentration subjects.",
              cls="text-sm text-slate-600 mb-1"),
            P(f"3. Engage {ca.sa_student_count} SA, {ca.wd_student_count} WD, and {ca.malpractice_student_count} Malpractice students "
              "through the appropriate academic office.", cls="text-sm text-slate-600"),
            cls="card p-5"
        ),

        cls="max-w-4xl mx-auto"
    ), ca=ca)


def page_reports(ca: ClassAnalysis) -> Tuple:
    return layout("Reports", "reports", Div(
        Div(
            H1("Generate Academic Reports", cls="text-2xl font-bold text-slate-800"),
            P("Download official PDF reports or open interactive web presentation reports.",
              cls="text-slate-500 text-sm mt-1"),
            cls="mb-8"
        ),

        Div(
            Div(
                Div(
                    Span("📊", cls="text-3xl mb-3 block"),
                    H3("Class Executive Report", cls="text-base font-semibold text-slate-800 mb-2"),
                    P("Comprehensive class overview including executive cover page, grade distribution, "
                      "subject rankings, risk list, and AI advisory.",
                      cls="text-sm text-slate-500 mb-4 leading-relaxed"),
                    Div(
                        Form(Button("📄 Download Class PDF", type="submit",
                                    cls="w-full px-4 py-2.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors mb-2"),
                             action="/report/class", method="POST"),
                        A("🌐 Open Interactive Web Report", href="/reports/interactive",
                          cls="block w-full text-center px-4 py-2.5 text-sm font-semibold bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg transition-colors"),
                    ),
                ),
                cls="card p-6"
            ),

            Div(
                Div(
                    Span("📚", cls="text-3xl mb-3 block"),
                    H3("Subject Report", cls="text-base font-semibold text-slate-800 mb-2"),
                    P("Detailed subject metrics including grade distribution, top students, "
                      "arrear list, subject vs class comparison, and AI insight.",
                      cls="text-sm text-slate-500 mb-4 leading-relaxed"),
                    Form(
                        Select(*[Option(s.subject, value=s.subject) for s in ca.subjects],
                               name="subject", aria_label="Select Subject for Report",
                               cls="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg mb-3 "
                                   "focus:ring-2 focus:ring-blue-500 focus:border-blue-500"),
                        Button("Generate Subject PDF", type="submit",
                               cls="w-full px-4 py-2.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"),
                        action="/report/subject-select", method="POST",
                    ),
                ),
                cls="card p-6"
            ),

            Div(
                Div(
                    Span("👤", cls="text-3xl mb-3 block"),
                    H3("Student Report", cls="text-base font-semibold text-slate-800 mb-2"),
                    P("Individual student profile including semester result, GPA calculation, "
                      "rank, strengths, attention areas, and AI brief.",
                      cls="text-sm text-slate-500 mb-4 leading-relaxed"),
                    Form(
                        Input(type="text", name="regno", placeholder="Enter register number", aria_label="Student Register Number for Report",
                              cls="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg mb-3 "
                                  "focus:ring-2 focus:ring-blue-500 focus:border-blue-500"),
                        Button("Generate Student PDF", type="submit",
                               cls="w-full px-4 py-2.5 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"),
                        action="/report/student-select", method="POST",
                    ),
                ),
                cls="card p-6"
            ),

            cls="grid grid-cols-1 md:grid-cols-3 gap-6"
        ),

        cls="max-w-6xl mx-auto"
    ), ca=ca)


# =============================================================================
# 13) ROUTES & FASTHTML APPLICATION SETUP
# =============================================================================

app = FastHTML(
    hdrs=(
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Link(rel="stylesheet", href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css"),
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(rel="stylesheet", href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"),
        Style("""
            :root {
                --navy-900: #0c1929;
                --navy-800: #0f1b33;
                --navy-700: #1e3a5f;
                --slate-50: #f8fafc;
                --slate-100: #f1f5f9;
                --slate-200: #e2e8f0;
                --slate-300: #cbd5e1;
                --slate-400: #94a3b8;
                --slate-500: #64748b;
                --slate-600: #475569;
                --slate-700: #334155;
                --slate-800: #1e293b;
                --slate-900: #0f172a;
                --green-500: #22c55e;
                --green-600: #16a34a;
                --green-700: #15803d;
                --amber-500: #f59e0b;
                --amber-600: #d97706;
                --red-500: #ef4444;
                --red-600: #dc2626;
                --blue-500: #3b82f6;
                --blue-600: #2563eb;
                --purple-500: #a855f7;
                --purple-600: #9333ea;
                --indigo-600: #7c3aed;
            }

            * { box-sizing: border-box; }
            body {
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: var(--slate-50);
                color: var(--slate-800);
                line-height: 1.6;
                -webkit-font-smoothing: antialiased;
                -moz-osx-font-smoothing: grayscale;
            }

            /* Typography */
            h1 { font-size: 1.75rem; font-weight: 700; color: var(--slate-900); line-height: 1.2; letter-spacing: -0.025em; }
            h2 { font-size: 1.25rem; font-weight: 600; color: var(--slate-800); line-height: 1.3; }
            h3 { font-size: 1rem; font-weight: 600; color: var(--slate-700); line-height: 1.4; }
            h4 { font-size: 0.875rem; font-weight: 600; color: var(--slate-600); line-height: 1.5; }

            /* Cards */
            .card {
                background: #fff;
                border: 1px solid var(--slate-200);
                border-radius: 0.75rem;
                box-shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
                transition: box-shadow 0.2s ease, border-color 0.2s ease;
            }
            .card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06), 0 2px 4px rgba(0,0,0,0.03); }

            /* Stat Cards */
            .stat-card {
                background: #fff;
                border: 1px solid var(--slate-200);
                border-radius: 0.75rem;
                padding: 1.25rem 1.5rem;
                transition: all 0.2s ease;
                position: relative;
                overflow: hidden;
            }
            .stat-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: var(--accent-color, var(--blue-500));
                opacity: 0;
                transition: opacity 0.2s ease;
            }
            .stat-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
            .stat-card:hover::before { opacity: 1; }

            /* Tables */
            table { border-collapse: collapse; width: 100%; }
            thead th {
                background: var(--slate-50);
                border-bottom: 2px solid var(--slate-200);
                font-weight: 600;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--slate-500);
                padding: 0.75rem 1rem;
                text-align: left;
                white-space: nowrap;
            }
            tbody td {
                padding: 0.75rem 1rem;
                border-bottom: 1px solid var(--slate-100);
                font-size: 0.875rem;
                color: var(--slate-700);
                transition: background-color 0.15s ease;
            }
            tbody tr:hover td { background-color: var(--slate-50); }
            tbody tr:last-child td { border-bottom: none; }

            /* Filter Buttons */
            .filter-btn {
                padding: 0.375rem 0.75rem;
                font-size: 0.75rem;
                font-weight: 500;
                border-radius: 9999px;
                transition: all 0.2s ease;
                border: 1px solid transparent;
                cursor: pointer;
            }
            .filter-btn:hover { transform: translateY(-1px); box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .filter-btn.active { background: var(--navy-800); color: #fff; border-color: var(--navy-700); }
            .filter-btn:not(.active) { background: #fff; border-color: var(--slate-200); color: var(--slate-600); }
            .filter-btn:not(.active):hover { background: var(--slate-50); border-color: var(--slate-300); }

            /* Links */
            a { color: inherit; text-decoration: none; transition: color 0.15s ease; }
            a.text-blue { color: var(--blue-600); }
            a.text-blue:hover { color: var(--blue-700); text-decoration: underline; }

            /* Focus States */
            *:focus-visible {
                outline: 2px solid var(--blue-500);
                outline-offset: 2px;
                border-radius: 4px;
            }
            input:focus-visible, select:focus-visible, button:focus-visible {
                outline: 2px solid var(--blue-500);
                outline-offset: 2px;
            }

            /* Badges */
            .badge {
                display: inline-flex;
                align-items: center;
                padding: 0.25rem 0.625rem;
                font-size: 0.75rem;
                font-weight: 600;
                border-radius: 9999px;
                line-height: 1;
            }
            .badge-green { background: #dcfce7; color: var(--green-700); }
            .badge-red { background: #fee2e2; color: var(--red-600); }
            .badge-amber { background: #fef3c7; color: var(--amber-600); }
            .badge-purple { background: #f3e8ff; color: var(--purple-600); }
            .badge-indigo { background: #ede9fe; color: var(--indigo-600); }
            .badge-slate { background: var(--slate-100); color: var(--slate-600); }

            /* Grade Badges */
            .grade-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 2rem;
                padding: 0.25rem 0.5rem;
                font-size: 0.75rem;
                font-weight: 700;
                border-radius: 0.375rem;
                color: #fff;
            }
            .grade-O { background: var(--green-600); }
            .grade-APLUS { background: #22c55e; }
            .grade-A { background: #4ade80; color: var(--slate-900); }
            .grade-BPLUS { background: #86efac; color: var(--slate-900); }
            .grade-B { background: var(--slate-400); }
            .grade-C { background: var(--slate-300); color: var(--slate-700); }
            .grade-U { background: var(--red-500); }
            .grade-RA { background: #ef4444; }
            .grade-SA { background: var(--amber-500); }
            .grade-WD { background: var(--purple-500); }
            .grade-MM { background: #7c3aed; }
            .grade-WH2 { background: #6b21a8; }

            /* Alerts */
            .alert {
                padding: 0.75rem 1rem;
                border-radius: 0.5rem;
                font-size: 0.875rem;
                font-weight: 500;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin-bottom: 1rem;
            }
            .alert-blue { background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe; }
            .alert-green { background: #f0fdf4; color: var(--green-700); border: 1px solid #bbf7d0; }
            .alert-red { background: #fef2f2; color: var(--red-600); border: 1px solid #fecaca; }
            .alert-amber { background: #fffbeb; color: #92400e; border: 1px solid #fde68a; }

            /* Prose (AI content) */
            .prose { font-size: 0.875rem; line-height: 1.7; color: var(--slate-700); }
            .prose li { margin: 0.375rem 0; list-style: disc; padding-left: 1.25rem; }
            .prose p { margin: 0.5rem 0; }
            .prose h4 { margin: 1rem 0 0.375rem 0; font-weight: 600; color: var(--slate-800); }
            .prose strong { font-weight: 600; color: var(--slate-900); }

            /* Sidebar */
            .sidebar {
                background: linear-gradient(180deg, var(--navy-900) 0%, var(--navy-800) 100%);
                border-right: 1px solid rgba(255,255,255,0.05);
            }
            .sidebar-link {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.625rem 1rem;
                font-size: 0.875rem;
                font-weight: 500;
                color: rgba(255,255,255,0.6);
                border-radius: 0.5rem;
                transition: all 0.2s ease;
                margin: 0.125rem 0.5rem;
            }
            .sidebar-link:hover {
                background: rgba(255,255,255,0.08);
                color: rgba(255,255,255,0.9);
            }
            .sidebar-link.active {
                background: rgba(255,255,255,0.12);
                color: #fff;
                font-weight: 600;
            }

            /* Empty State */
            .empty-state {
                text-align: center;
                padding: 3rem 1.5rem;
                color: var(--slate-400);
            }

            /* Loading */
            .loading { display: flex; align-items: center; justify-content: center; padding: 3rem; }
            .spinner {
                width: 2rem;
                height: 2rem;
                border: 3px solid var(--slate-200);
                border-top-color: var(--blue-500);
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
            }
            @keyframes spin { to { transform: rotate(360deg); } }

            /* Chart Container */
            .chart-container {
                background: #fff;
                border: 1px solid var(--slate-200);
                border-radius: 0.75rem;
                padding: 1.25rem;
                min-height: 20rem;
            }
            .chart-container .js-plotly-plot { width: 100% !important; }

            /* Mobile */
            @media (max-width: 1023px) {
                .mobile-nav {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    z-index: 50;
                    background: var(--navy-900);
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                }
            }
            @media (min-width: 1024px) {
                .mobile-nav { display: none; }
                .main-content { margin-left: 16rem; }
            }

            /* Scrollbar */
            ::-webkit-scrollbar { width: 6px; height: 6px; }
            ::-webkit-scrollbar-track { background: var(--slate-100); }
            ::-webkit-scrollbar-thumb { background: var(--slate-300); border-radius: 3px; }
            ::-webkit-scrollbar-thumb:hover { background: var(--slate-400); }
        """),
    ),
    exception_handlers={404: lambda req, exc: page_upload()},
)


@app.get("/favicon.ico")
def route_favicon():
    return Response(status_code=204)


@app.get("/")
def route_root():
    return page_upload()


@app.get("/upload")
def route_upload_get():
    return page_upload()


@app.post("/upload-preview")
async def route_upload_preview(request):
    try:
        form = await request.form()
        file = form.get("file")
        if file is None:
            push_alert("No file selected.", "red")
            return RedirectResponse("/upload", status_code=303)

        raw_filename = getattr(file, "filename", "") or ""
        filename = os.path.basename(raw_filename)
        filename = re.sub(r"[^\w\.\-]", "_", filename)

        if not filename.lower().endswith(".xlsx"):
            push_alert("Only .xlsx files are accepted.", "red")
            return RedirectResponse("/upload", status_code=303)

        max_bytes = CFG["max_upload_mb"] * 1024 * 1024
        chunks = []
        total_size = 0
        while True:
            chunk = await file.read(64 * 1024)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_bytes:
                push_alert(f"File exceeds maximum allowed size of {CFG['max_upload_mb']} MB.", "red")
                return RedirectResponse("/upload", status_code=303)
            chunks.append(chunk)

        data = b"".join(chunks)
        if not data:
            push_alert("Uploaded file is empty.", "red")
            return RedirectResponse("/upload", status_code=303)

        df, report = _read_workbook(data)
        if report.has_fatal():
            push_alert(report.fatal_error, "red")
            return RedirectResponse("/upload", status_code=303)

        cols = [str(c) for c in df.columns.tolist()]
        mapping = _columns_to_targets(cols)
        report.mapped_columns = mapping

        full_res = validate_and_clean(data, filename, mapping)

        SESSION["preview_raw_bytes"] = data
        SESSION["preview_filename"] = filename
        SESSION["preview_cols"] = cols
        SESSION["preview_report"] = full_res.report

        return page_upload_mapping()
    except Exception as e:
        push_alert(f"File analysis error: {e}", "red")
        return RedirectResponse("/upload", status_code=303)


@app.post("/upload-confirm")
async def route_upload_confirm(request):
    try:
        data = SESSION.get("preview_raw_bytes")
        filename = SESSION.get("preview_filename", "result.xlsx")
        if not data:
            push_alert("Upload session expired. Please re-upload your file.", "amber")
            return RedirectResponse("/upload", status_code=303)

        form = await request.form()
        custom_mapping = {}
        for f in REQUIRED_FIELDS + OPTIONAL_FIELDS:
            val = form.get(f"map_{f}", "").strip()
            if val:
                custom_mapping[f] = val

        result = validate_and_clean(data, filename, custom_mapping)

        if not result.ok:
            SESSION["records"] = None
            SESSION["analytics"] = None
            SESSION["validation"] = result.report
            push_alert(f"Validation error: {result.report.fatal_error}", "red")
            return RedirectResponse("/upload", status_code=303)

        ca = compute_class_analysis(result.records, filename)

        SESSION["records"] = result.records
        SESSION["analytics"] = ca
        SESSION["file_name"] = filename
        SESSION["validation"] = result.report
        SESSION["ptm_briefs"] = {}

        push_alert(
            f"Successfully processed {result.report.valid_records} records for {ca.student_count} "
            f"students across {ca.subject_count} subjects.",
            "green"
        )
        return RedirectResponse("/dashboard", status_code=303)
    except Exception as e:
        push_alert(f"Processing error: {e}", "red")
        return RedirectResponse("/upload", status_code=303)


@app.post("/reset")
def route_reset():
    SESSION["records"] = None
    SESSION["analytics"] = None
    SESSION["validation"] = None
    SESSION["preview_raw_bytes"] = None
    SESSION["ptm_briefs"] = {}
    push_alert("Session cleared. Upload a new file to begin.", "blue")
    return RedirectResponse("/", status_code=303)


@app.get("/dashboard")
def route_dashboard():
    if not session_ready():
        push_alert("No data loaded. Please upload a semester result first.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_dashboard(SESSION["analytics"])


@app.get("/students")
def route_students():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_students(SESSION["analytics"])


@app.get("/students/search")
def route_students_search(q: str = ""):
    if not session_ready():
        return NotStr("")
    ca = SESSION["analytics"]
    q_lower = unquote(q).lower().strip()
    results = []
    for s in ca.students:
        if q_lower and q_lower not in s.regno.lower() and q_lower not in (s.name or "").lower():
            continue
        results.append(Tr(
            Td(str(s.rank or "—"), cls="font-medium text-slate-600"),
            Td(s.regno, cls="font-mono text-xs text-slate-500"),
            Td(A(s.name or "—", href=f"/students/{quote(s.regno, safe='')}",
                 cls="text-blue-600 hover:text-blue-700 font-medium")),
            Td(gpa_cell(s.gpa)),
            Td(str(s.arrear_count), cls="text-red-600 font-semibold") if s.arrear_count else Td("0"),
            Td(status_badge(s.attention)),
            Td(f"{s.percentile:.1f}%" if s.percentile else "—", cls="text-slate-500"),
            data_row_type="student-row",
            data_status=s.attention,
            data_high=str(s.is_high_performer).lower(),
        ))
    if not results:
        return NotStr(f"<tr><td colspan='7' class='text-center py-6 text-slate-400'>No student matching '{html.escape(q)}' found.</td></tr>")
    return NotStr("".join(str(r) for r in results))


@app.get("/students/{regno}")
def route_student_detail(regno: str):
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_student_detail(SESSION["analytics"], regno)


@app.post("/student/{regno}/ptm")
def route_ptm(regno: str):
    if not session_ready():
        return NotStr("<p class='text-red-600 text-sm'>No data loaded.</p>")
    ca = SESSION["analytics"]
    s = get_student(ca, regno)
    if s is None:
        return NotStr(f"<p class='text-red-600 text-sm'>Student {html.escape(regno)} not found.</p>")
    ptm = generate_ptm_brief(s, ca)
    SESSION.setdefault("ptm_briefs", {})[s.regno] = ptm
    return Div(
        P(ai_source_banner(ptm["live"]), cls="text-xs text-slate-400 italic mb-2"),
        NotStr(md_to_html(ptm["text"])),
        cls="prose prose-sm max-w-none"
    )


@app.get("/subjects")
def route_subjects():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_subjects(SESSION["analytics"])


@app.get("/subjects/{subject}")
def route_subject_detail(subject: str):
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_subject_detail(SESSION["analytics"], subject)


@app.get("/attention")
def route_attention():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_attention(SESSION["analytics"])


@app.get("/rankings")
def route_rankings():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_rankings(SESSION["analytics"])


@app.get("/ai-insights")
def route_ai_insights():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_ai_insights(SESSION["analytics"])


@app.get("/reports")
def route_reports():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_reports(SESSION["analytics"])


@app.get("/reports/interactive")
def route_reports_interactive():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    return page_interactive_report(SESSION["analytics"])


@app.post("/report/class")
def route_report_class():
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    rid = create_report_id("class", {"class_analysis": SESSION["analytics"]})
    return RedirectResponse(f"/download-pdf?report_id={rid}", status_code=303)


@app.post("/report/subject/{subject}")
def route_report_subject(subject: str):
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    rid = create_report_id("subject", {"class_analysis": SESSION["analytics"], "subject": subject})
    return RedirectResponse(f"/download-pdf?report_id={rid}", status_code=303)


@app.post("/report/subject-select")
async def route_report_subject_select(request):
    form = await request.form()
    subject = form.get("subject", "")
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    rid = create_report_id("subject", {"class_analysis": SESSION["analytics"], "subject": subject})
    return RedirectResponse(f"/download-pdf?report_id={rid}", status_code=303)


@app.post("/report/student/{regno}")
def route_report_student(regno: str):
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    rid = create_report_id("student", {"class_analysis": SESSION["analytics"], "regno": regno})
    return RedirectResponse(f"/download-pdf?report_id={rid}", status_code=303)


@app.post("/report/student-select")
async def route_report_student_select(request):
    form = await request.form()
    regno = form.get("regno", "").strip()
    if not regno:
        push_alert("Please enter a register number.", "amber")
        return RedirectResponse("/reports", status_code=303)
    if not session_ready():
        push_alert("No data loaded.", "amber")
        return RedirectResponse("/", status_code=303)
    ca = SESSION["analytics"]
    s = get_student(ca, regno)
    if not s:
        push_alert(f"Student '{html.escape(regno)}' not found in the dataset.", "red")
        return RedirectResponse("/reports", status_code=303)
    rid = create_report_id("student", {"class_analysis": ca, "regno": s.regno})
    return RedirectResponse(f"/download-pdf?report_id={rid}", status_code=303)


@app.get("/download-pdf")
def route_download_pdf(report_id: str = ""):
    if not report_id or not is_valid_uuid(report_id):
        push_alert("Invalid report link.", "red")
        return RedirectResponse("/reports", status_code=303)

    entry = get_report(report_id)
    if not entry:
        push_alert("Report expired or not found. Please regenerate.", "red")
        return RedirectResponse("/reports", status_code=303)

    pdf_bytes = generate_report_pdf(report_id)
    if not pdf_bytes:
        push_alert("PDF generation failed. Ensure report data is valid.", "red")
        return RedirectResponse("/reports", status_code=303)

    kind = entry["kind"]
    ca = entry["payload"].get("class_analysis")
    if kind == "class":
        fname = f"class_report_{ca.file_name if ca else 'report'}.pdf"
    elif kind == "subject":
        subj = entry["payload"].get("subject", "subject")
        fname = f"subject_report_{subj}.pdf"
    else:
        regno = entry["payload"].get("regno", "student")
        fname = f"student_report_{regno}.pdf"

    safe_fname = re.sub(r"[^\w\.\-]", "_", fname)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_fname}"'},
    )


# =============================================================================
# 14) APPLICATION STARTUP
# =============================================================================

if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8000))

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port
    )