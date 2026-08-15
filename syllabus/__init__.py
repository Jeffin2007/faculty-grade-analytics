"""
Syllabus package for Faculty Grade Analytics Portal.
"""

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

__all__ = [
    "get_catalog",
    "get_registered_departments",
    "load_registry",
    "normalize_course_code",
    "resolve_course",
    "invalidate_catalog_cache",
    "CatalogIndex",
    "CatalogMetadata",
]
