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
        self.assertEqual(len(report.detected_semesters), 2)

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

        self.assertEqual(ca.student_count, 126)
        self.assertEqual(ca.subject_count, 8)
        self.assertEqual(len(ca.subjects), 8)

        # Verify student with previous semester reappearance (e.g. Ajay M)
        ajay = app.get_student(ca, "813825243005")
        self.assertIsNotNone(ajay)
        self.assertEqual(len(ajay.courses), 8)
        self.assertTrue(len(ajay.previous_semester_results) > 0)
        self.assertIsNotNone(ajay.gpa)


if __name__ == "__main__":
    unittest.main()
