"""
syllabus_tools package
Admin tools for extracting, validating, and publishing syllabus catalogs.
"""

from syllabus_tools.validator import validate_catalog_schema, CatalogValidationError
from syllabus_tools.extractor import extract_syllabus_pdf
from syllabus_tools.publisher import publish_syllabus_draft

__all__ = [
    "validate_catalog_schema",
    "CatalogValidationError",
    "extract_syllabus_pdf",
    "publish_syllabus_draft",
]
