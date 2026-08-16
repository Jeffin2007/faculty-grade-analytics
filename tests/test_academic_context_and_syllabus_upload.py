import unittest
import os
import json
import sys
sys.path.insert(0, os.path.abspath("."))
import app
from syllabus.loader import (
    get_registered_departments,
    get_catalog,
    save_and_register_syllabus,
    resolve_course,
    load_registry,
    REGISTRY_PATH,
)

class TestAcademicContextAndSyllabusUpload(unittest.TestCase):
    def setUp(self):
        self.pdf_path = os.path.join(os.path.dirname(__file__), "..", "AID (3).pdf")

    def test_registered_departments_exist(self):
        depts = get_registered_departments()
        self.assertGreaterEqual(len(depts), 10)
        dept_codes = [d["code"] for d in depts]
        self.assertIn("AI_DS", dept_codes)
        self.assertIn("AIML", dept_codes)
        self.assertIn("CSE", dept_codes)
        self.assertIn("ECE", dept_codes)
        self.assertIn("EEE", dept_codes)
        self.assertIn("IT", dept_codes)
        self.assertIn("MECH", dept_codes)

    def test_page_upload_rendering(self):
        # Ensure page_upload executes and contains selection controls
        page = app.page_upload()
        self.assertIsNotNone(page)

    def test_extract_coe_pdf_with_academic_context(self):
        if not os.path.exists(self.pdf_path):
            self.skipTest("AID (3).pdf not found in root")

        with open(self.pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Pass explicit Department and Semester context
        context = {
            "department": "AI_DS",
            "semester": 2,
            "regulation": "R2024"
        }
        report = app.extract_coe_pdf(pdf_bytes, "AID (3).pdf", analysis_context=context)

        self.assertTrue(report.ok)
        self.assertEqual(report.primary_semester, 2)
        self.assertEqual(report.student_count, 126)
        self.assertEqual(report.doc_metadata.department, "AI_DS")
        self.assertEqual(report.doc_metadata.regulation, "R2024")

    def test_save_and_register_new_regulation_syllabus(self):
        # Create a test syllabus for a new regulation (e.g. R2028_TEST)
        test_dept = "AI_DS"
        test_reg = "R2028_TEST"
        test_courses = [
            {
                "code": "28AD101",
                "name": "Advanced Neural Architectures",
                "semester": 1,
                "credits": 4.0,
                "type": "THEORY",
                "category": "Sem 1-4 Foundation"
            },
            {
                "code": "28AD111",
                "name": "Deep Learning Laboratory",
                "semester": 1,
                "credits": 2.0,
                "type": "LAB",
                "category": "Sem 1-4 Foundation"
            }
        ]

        res = save_and_register_syllabus(
            department_code=test_dept,
            regulation_code=test_reg,
            courses=test_courses,
            actor="Unit Test Runner"
        )

        self.assertTrue(res["ok"])
        self.assertEqual(res["course_count"], 2)

        # Verify catalog is retrievable
        cat = get_catalog(test_dept, test_reg, force_reload=True)
        self.assertIsNotNone(cat)
        self.assertEqual(len(cat.courses), 2)

        # Verify resolve_course works with new catalog
        course_name, code, cred, sem, cat_name, conf, amb = resolve_course(
            "28AD101",
            context={"department": test_dept, "regulation": test_reg, "semester": 1}
        )
        self.assertEqual(course_name, "Advanced Neural Architectures")
        self.assertEqual(cred, 4.0)
        self.assertFalse(amb)

        # Cleanup test catalog file and registry entry
        try:
            if os.path.isfile(res["filepath"]):
                os.remove(res["filepath"])
            reg_data = load_registry()
            for d in reg_data.get("departments", []):
                if d.get("code") == test_dept and "catalogs" in d:
                    d["catalogs"].pop(test_reg, None)
            with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(reg_data, f, indent=2)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()
