import unittest
import pandas as pd
import os
import sys
sys.path.insert(0, os.path.abspath("."))
import app
from app import (
    compute_student_analytics,
    compute_class_analysis,
    generate_student_brief,
    generate_ptm_brief,
    fallback_student_brief,
    fallback_ptm_brief,
    StudentSubjectResult,
    STATUS_CLEARED,
    STATUS_MULTI_U,
    STATUS_U,
    STATUS_BACKLOG,
)

class TestCarriedArrearsIntelligence(unittest.TestCase):
    def test_current_arrear_student_with_carried_previous_arrears(self):
        # Current semester records: Student has 1 current arrear (24AD201 - RA) and 1 pass (24AD202 - A)
        records_data = [
            {"regno": "813824243001", "name": "ALICE", "subject": "Data Structures", "course_code": "24AD201", "credits": 4.0, "grade": "RA", "points": 0.0},
            {"regno": "813824243001", "name": "ALICE", "subject": "Digital Principles", "course_code": "24AD202", "credits": 3.0, "grade": "A", "points": 8.0},
            {"regno": "813824243002", "name": "BOB", "subject": "Data Structures", "course_code": "24AD201", "credits": 4.0, "grade": "B+", "points": 7.0},
            {"regno": "813824243002", "name": "BOB", "subject": "Digital Principles", "course_code": "24AD202", "credits": 3.0, "grade": "A", "points": 8.0},
        ]
        df = pd.DataFrame(records_data)

        # Previous semester results:
        # ALICE has an uncleared previous arrear (24MA101 - U) and a cleared previous arrear (24PH101 - B)
        # BOB has a cleared previous arrear (24MA101 - B)
        prev_records = [
            {"regno": "813824243001", "subject": "Matrices and Calculus", "course_code": "24MA101", "credits": 4.0, "grade": "U", "points": 0.0},
            {"regno": "813824243001", "subject": "Engineering Physics", "course_code": "24PH101", "credits": 3.0, "grade": "B", "points": 6.0},
            {"regno": "813824243002", "subject": "Matrices and Calculus", "course_code": "24MA101", "credits": 4.0, "grade": "B", "points": 6.0},
        ]

        students = compute_student_analytics(df, prev_records=prev_records)
        alice = next(s for s in students if s.regno == "813824243001")
        bob = next(s for s in students if s.regno == "813824243002")

        # Verify ALICE (Current Arrear Student with Carried Previous Arrear)
        self.assertEqual(alice.arrear_count, 1)
        self.assertIn("24MA101", alice.carried_previous_arrears)
        self.assertEqual(alice.carried_previous_arrear_count, 1)
        self.assertIn("24PH101", alice.cleared_previous_subjects)
        self.assertEqual(alice.total_active_arrear_count, 2)  # 1 current + 1 carried
        self.assertEqual(alice.attention, STATUS_MULTI_U)
        self.assertEqual(alice.risk_level, "High Risk")

        # Verify BOB (Cleared Student who resolved earlier arrears)
        self.assertEqual(bob.arrear_count, 0)
        self.assertEqual(bob.carried_previous_arrear_count, 0)
        self.assertIn("24MA101", bob.cleared_previous_subjects)
        self.assertEqual(bob.total_active_arrear_count, 0)
        self.assertEqual(bob.attention, STATUS_CLEARED)
        self.assertEqual(bob.risk_level, "Low Risk / Cleared")

    def test_ai_and_fallback_briefs_carried_arrears_content(self):
        ca = compute_class_analysis(pd.DataFrame([
            {"regno": "813824243001", "name": "ALICE", "subject": "Data Structures", "course_code": "24AD201", "credits": 4.0, "grade": "RA", "points": 0.0},
            {"regno": "813824243001", "name": "ALICE", "subject": "Digital Principles", "course_code": "24AD202", "credits": 3.0, "grade": "A", "points": 8.0},
        ]), "result.pdf", prev_records=[
            {"regno": "813824243001", "subject": "Matrices and Calculus", "course_code": "24MA101", "credits": 4.0, "grade": "U", "points": 0.0},
        ])

        alice = ca.students[0]
        self.assertEqual(alice.total_active_arrear_count, 2)

        # Verify fallback student brief contains both current and carried arrears
        brief_txt = fallback_student_brief(alice, ca)
        self.assertIn("Current Semester Arrears", brief_txt)
        self.assertIn("Carried Previous Semester Arrears", brief_txt)
        self.assertIn("24MA101", brief_txt)
        self.assertIn("Total Active Arrear Load", brief_txt)

        # Verify fallback PTM brief contains both current and carried arrears
        ptm_txt = fallback_ptm_brief(alice, ca)
        self.assertIn("Current Semester Arrears", ptm_txt)
        self.assertIn("Carried Previous Semester Arrears", ptm_txt)
        self.assertIn("24MA101", ptm_txt)
        self.assertIn("Total Active Arrear Burden", ptm_txt)


if __name__ == "__main__":
    unittest.main()
