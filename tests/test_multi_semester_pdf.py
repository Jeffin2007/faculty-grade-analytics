import unittest
import os
import app


class TestMultiSemesterPDFExtraction(unittest.TestCase):
    def setUp(self):
        self.pdf_path = os.path.join(os.path.dirname(__file__), "..", "AID (3).pdf")

    def test_multi_semester_extraction_and_segregation(self):
        if not os.path.exists(self.pdf_path):
            self.skipTest("AID (3).pdf not found in root")

        with open(self.pdf_path, "rb") as f:
            pdf_bytes = f.read()

        report = app.extract_coe_pdf(pdf_bytes, "AID (3).pdf")

        self.assertTrue(report.ok)
        self.assertEqual(report.primary_semester, 2)
        self.assertEqual(report.student_count, 126)
        self.assertEqual(report.subject_count, 8)
        self.assertEqual(len(report.records), 1008)  # 126 * 8 = 1008
        self.assertEqual(len(report.prev_records), 34)
        self.assertEqual(len(report.all_records), 1042)
        self.assertEqual(len(report.detected_semesters), 2)

        # Verify Student 813825243108 has all 8 records and correct name
        s108_recs = [r for r in report.records if r.register_number == "813825243108"]
        self.assertEqual(len(s108_recs), 8)
        self.assertEqual(s108_recs[0].student_name, "SUYAMBUSREE RAMATHITCHANA S")
        s108_grades = {r.subject_code: r.result_status for r in s108_recs}
        self.assertEqual(s108_grades.get("24CS201"), "A")
        self.assertEqual(s108_grades.get("24EN201"), "A")
        self.assertEqual(s108_grades.get("24MA201"), "A")
        self.assertEqual(s108_grades.get("24PH201"), "A")
        self.assertEqual(s108_grades.get("24TA201"), "B")
        self.assertEqual(s108_grades.get("24CS211"), "S")
        self.assertEqual(s108_grades.get("24EM211"), "S")
        self.assertEqual(s108_grades.get("24ES201"), "A")

        # Verify Sem 1 (arrear reappearance) is segregated into prev_records
        self.assertTrue(len(report.prev_records) > 0)
        prev_sem_info = next((s for s in report.detected_semesters if s["semester"] == 1), None)
        self.assertIsNotNone(prev_sem_info)
        self.assertEqual(prev_sem_info["student_count"], 13)
        self.assertTrue(prev_sem_info["is_arrear"])
        self.assertFalse(prev_sem_info["is_primary"])

        # Verify Sem 2 is active primary cohort
        primary_sem_info = next((s for s in report.detected_semesters if s["semester"] == 2), None)
        self.assertIsNotNone(primary_sem_info)
        self.assertEqual(primary_sem_info["student_count"], 126)
        self.assertEqual(primary_sem_info["subject_count"], 8)
        self.assertTrue(primary_sem_info["is_primary"])

        # Test class analysis computation with segregated prev_records
        df = app.pdf_records_to_dataframe(report.records)
        ca = app.compute_class_analysis(df, "AID (3).pdf", prev_records=report.prev_records)
        ca.quarantined_tokens = report.quarantined_tokens
        ca.subject_mappings = app.build_subject_mapping_log(report.records)

        self.assertEqual(ca.student_count, 126)
        self.assertEqual(ca.subject_count, 8)
        self.assertEqual(len(ca.subjects), 8)

        # Verify subject mappings have valid official subject names
        for sm in ca.subject_mappings:
            self.assertTrue(bool(sm.get("official_subject_name")))
            self.assertNotEqual(sm.get("official_subject_name"), sm.get("course_code"))

        # Verify Student 813825243108 in ClassAnalysis
        s108_obj = app.get_student(ca, "813825243108")
        self.assertIsNotNone(s108_obj)
        self.assertEqual(s108_obj.name, "SUYAMBUSREE RAMATHITCHANA S")
        self.assertEqual(len(s108_obj.courses), 8)

        # Verify student with previous semester reappearance (e.g. Ajay M)
        ajay = app.get_student(ca, "813825243005")
        self.assertIsNotNone(ajay)
        self.assertEqual(len(ajay.courses), 8)
        self.assertTrue(len(ajay.previous_semester_results) > 0)
        self.assertIsNotNone(ajay.gpa)

    def test_empty_or_corrupt_pdf_handling(self):
        # Empty bytes
        report_empty = app.extract_coe_pdf(b"", "empty.pdf")
        self.assertFalse(report_empty.ok)
        self.assertIn("empty", report_empty.fatal_error.lower())

        # Invalid corrupt bytes
        report_corrupt = app.extract_coe_pdf(b"Not a valid PDF header content", "corrupt.pdf")
        self.assertFalse(report_corrupt.ok)
        self.assertEqual(report_corrupt.doc_metadata.document_type, "EMPTY_OR_CORRUPT_PDF")
        self.assertTrue(len(report_corrupt.fatal_error) > 0)

    def test_semester_parsing_variations(self):
        # Test various semester textual patterns
        test_cases = [
            ("SEMESTER : II", 2),
            ("SEMESTER: 03", 3),
            ("SEM : IV", 4),
            ("1ST SEMESTER", 1),
            ("2ND SEM", 2),
            ("3RD SEMESTER", 3),
            ("4TH SEM", 4),
            ("FIFTH SEMESTER", 5),
            ("SIXTH SEM", 6),
            ("SEVENTH SEMESTER", 7),
            ("EIGHTH SEM", 8),
            ("RESULTS FOR SEMESTER - 1", 1),
        ]
        for text, expected_sem in test_cases:
            parsed = app._parse_page_semester(text)
            self.assertEqual(parsed, expected_sem, f"Failed for text: '{text}'")

    def test_grade_normalization_edge_cases(self):
        # Test all passing and special failing grades
        cases = {
            "O": "O", "S": "S", "A+": "A+", "A PLUS": "A+", "A": "A",
            "B+": "B+", "B PLUS": "B+", "B": "B", "C+": "C+", "C PLUS": "C+", "C": "C",
            "U": "U", "RA": "RA", "R.A": "RA", "UA": "UA", "ABS": "UA", "ABSENT": "UA",
            "SA": "SA", "S.A": "SA", "WD": "WD", "W.D": "WD", "WITHDRAWN": "WD",
            "MM": "MM", "MALPRACTICE": "MM", "WH2": "WH2", "WH-2": "WH2", "WITHHELD": "WH2"
        }
        for raw, expected in cases.items():
            norm = app._grade_normalize(raw)
            self.assertEqual(norm, expected, f"Failed normalizing grade: {raw}")

    def test_all_126_students_extracted_without_loss(self):
        if not os.path.exists(self.pdf_path):
            self.skipTest("AID (3).pdf not found in root")

        with open(self.pdf_path, "rb") as f:
            pdf_bytes = f.read()

        report = app.extract_coe_pdf(pdf_bytes, "AID (3).pdf")
        df = app.pdf_records_to_dataframe(report.records)
        ca = app.compute_class_analysis(df, "AID (3).pdf", prev_records=report.prev_records)

        # Ensure all 126 students exist and have valid names and 8 courses
        self.assertEqual(len(ca.students), 126)
        for s in ca.students:
            self.assertTrue(len(s.regno) >= 10)
            self.assertTrue(bool(s.name.strip()))
            self.assertNotEqual(s.name.strip(), "—")
            self.assertEqual(s.total_courses, 8)
            self.assertIsNotNone(s.gpa)


if __name__ == "__main__":
    unittest.main()
