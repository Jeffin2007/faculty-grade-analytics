import unittest
import os
import sys
import pandas as pd
sys.path.insert(0, os.path.abspath("."))
import app
from app import (
    parse_combined_ia_marks_content,
    parse_ia_marks_content,
    clean_staff_name,
    build_department_excel,
    compute_class_analysis,
)

class TestCombinedIAMarksParsing(unittest.TestCase):
    def setUp(self):
        self.ia_a_path = "f:/mark_analysis/II A IA.html"
        self.ia_b_path = "f:/mark_analysis/II B.html"

    def test_clean_staff_name(self):
        self.assertEqual(clean_staff_name("gohila priyadharshini7130"), "Gohila Priyadharshini")
        self.assertEqual(clean_staff_name("suganyadevi-eee"), "Suganyadevi")
        self.assertEqual(clean_staff_name("subhashini-mat"), "Subhashini")
        self.assertEqual(clean_staff_name("murali-phy"), "Murali")
        self.assertEqual(clean_staff_name("thangam-tamil"), "Thangam")

    def test_parse_section_a_html(self):
        if not os.path.exists(self.ia_a_path):
            self.skipTest("II A IA.html not found")
        with open(self.ia_a_path, "rb") as f:
            multi_marks, titles, staff, meta = parse_combined_ia_marks_content(f.read(), "II A IA.html")

        self.assertEqual(len(multi_marks["ia1"]), 63)
        self.assertEqual(len(multi_marks["mut1"]), 63)
        self.assertEqual(len(multi_marks["ia2"]), 63)
        self.assertEqual(len(multi_marks["mut2"]), 63)

        # Verify staff names
        self.assertEqual(staff.get("24CS201A"), "Gohila Priyadharshini")
        self.assertEqual(staff.get("24EN201A"), "Vijayarenganayaki")
        self.assertEqual(staff.get("24ES201A"), "Suganyadevi")
        self.assertEqual(staff.get("24MA201A"), "Subhashini")
        self.assertEqual(staff.get("24PH201A"), "Murali")
        self.assertEqual(staff.get("24TA201A"), "Thangam")

        # Verify sample student marks (813825243001)
        s1 = multi_marks["ia1"].get("813825243001")
        self.assertIsNotNone(s1)
        self.assertEqual(s1["marks"].get("24CS201A"), "96")
        self.assertEqual(s1["marks"].get("24EN201A"), "68")
        self.assertEqual(s1["quota"], "GQ")

    def test_parse_section_b_html(self):
        if not os.path.exists(self.ia_b_path):
            self.skipTest("II B.html not found")
        with open(self.ia_b_path, "rb") as f:
            multi_marks, titles, staff, meta = parse_combined_ia_marks_content(f.read(), "II B.html")

        self.assertEqual(len(multi_marks["ia1"]), 41)
        self.assertEqual(len(multi_marks["mut1"]), 41)
        self.assertEqual(len(multi_marks["ia2"]), 41)
        self.assertEqual(len(multi_marks["mut2"]), 41)

        # Verify Section B staff names
        self.assertEqual(staff.get("24CS201A"), "Mangalambigai")
        self.assertEqual(staff.get("24EN201A"), "Lakshmi")
        self.assertEqual(staff.get("24ES201A"), "Vigneshwaran")
        self.assertEqual(staff.get("24MA201A"), "Arunkumar")
        self.assertEqual(staff.get("24PH201A"), "Senthilkumar")

        # Verify sample student marks (813825243065)
        s65 = multi_marks["ia1"].get("813825243065")
        self.assertIsNotNone(s65)
        self.assertEqual(s65["marks"].get("24CS201A"), "92")
        self.assertEqual(s65["quota"], "GQ")

    def test_multi_section_merge_and_excel_generation(self):
        if not os.path.exists(self.ia_a_path) or not os.path.exists(self.ia_b_path):
            self.skipTest("Section HTML files not found")

        ia_store = {"ia1": {}, "mut1": {}, "ia2": {}, "mut2": {}, "ia3": {}}
        staff_directory = {}

        for p in [self.ia_a_path, self.ia_b_path]:
            with open(p, "rb") as f:
                multi_marks, titles, staff, meta = parse_combined_ia_marks_content(f.read(), os.path.basename(p))
                for tk, tdata in multi_marks.items():
                    ia_store[tk].update(tdata)
                for code, sname in staff.items():
                    if code not in staff_directory:
                        staff_directory[code] = sname
                    else:
                        existing = [x.strip() for x in staff_directory[code].split("&")]
                        if sname not in existing:
                            staff_directory[code] = f"{staff_directory[code]} & {sname}"

        # Total students merged: 63 + 41 = 104
        self.assertEqual(len(ia_store["ia1"]), 104)
        self.assertEqual(staff_directory.get("24CS201A"), "Gohila Priyadharshini & Mangalambigai")

        # Build mock class analysis with failed student to verify Analysis 4
        records = [
            {"regno": "813825243001", "name": "ABINASH. S", "subject": "Data Structures", "course_code": "24CS201A", "credits": 4.0, "grade": "RA", "points": 0.0},
            {"regno": "813825243001", "name": "ABINASH. S", "subject": "English", "course_code": "24EN201A", "credits": 3.0, "grade": "A", "points": 8.0},
        ]
        df = pd.DataFrame(records)
        ca = compute_class_analysis(df, "mock.pdf")
        ca.subject_mappings = [
            {"course_code": "24CS201A", "official_subject_name": "Data Structures", "credits": 4.0},
            {"course_code": "24EN201A", "official_subject_name": "English", "credits": 3.0},
        ]

        from app import PDFExtractionReport, DocumentMetadata
        rep = PDFExtractionReport(doc_metadata=DocumentMetadata(
            institution="Saranathan College of Engineering",
            department="Artificial Intelligence and Data Science",
            programme="B.Tech. AI & DS",
            semester="II",
            academic_year="2025-2026",
            exam_session="April/May 2026"
        ))

        xlsx_bytes = build_department_excel(ca, rep, staff_directory, "mock.pdf", ia_marks_dir=ia_store)
        self.assertGreater(len(xlsx_bytes), 1000)

        # Inspect generated openpyxl sheet Analysis 4_New
        import openpyxl
        import io
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
        self.assertIn("Analysis 4_New", wb.sheetnames)
        ws4 = wb["Analysis 4_New"]
        
        # Check student row contains IAT 1 mark 96 and MUT 1 mark 86 for 24CS201A
        found = False
        for r in range(1, ws4.max_row + 1):
            if ws4.cell(row=r, column=6).value == "813825243001":
                found = True
                self.assertEqual(ws4.cell(row=r, column=8).value, "GQ") # Quota
                self.assertEqual(ws4.cell(row=r, column=9).value, "96") # IAT 1
                self.assertEqual(ws4.cell(row=r, column=10).value, "86") # MUT 1
                self.assertEqual(ws4.cell(row=r, column=11).value, "94") # IAT 2
                break
        self.assertTrue(found, "Student 813825243001 should be present in Analysis 4_New")


if __name__ == "__main__":
    unittest.main()
