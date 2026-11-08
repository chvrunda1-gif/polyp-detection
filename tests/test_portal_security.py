import io
import os
import sys
import unittest
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from database.db import get_db, init_db

class PortalSecurityAndWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_polyscope.sqlite3"
        init_db(self.db_path)

        self.app = create_app({
            "TESTING": True,
            "DATABASE_PATH": str(self.db_path),
            "SECRET_KEY": "test-key-security-checks",
            "ORIGINALS_FOLDER": str(Path(self.temp_dir.name) / "originals"),
            "RESULTS_FOLDER": str(Path(self.temp_dir.name) / "results"),
            "MASKS_FOLDER": str(Path(self.temp_dir.name) / "masks"),
            "ALLOWED_EXTENSIONS": {"jpg", "jpeg", "png", "webp"}
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 1. NORMAL LOGIN TESTS (NAME, USERNAME, EMAIL + PASSWORD) ─────────────

    def test_normal_login_patient_by_email_and_name(self):
        """Test patient can log in with email or display name and password."""
        # By email
        res1 = self.client.post("/api/auth/login", json={
            "identifier": "patient@polyscope.ai",
            "password": "patient1234",
            "role": "patient"
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json["user"]["role"], "patient")
        self.assertIn("patient_portal.html", res1.json["portal_url"])

        # By full name
        res2 = self.client.post("/api/auth/login", json={
            "identifier": "John Doe",
            "password": "patient1234"
        })
        self.assertEqual(res2.status_code, 200)
        self.assertIn("John Doe", res2.json["user"]["name"])

        # By alias 'patient'
        res3 = self.client.post("/api/auth/login", json={
            "identifier": "patient",
            "password": "patient1234"
        })
        self.assertEqual(res3.status_code, 200)

    def test_normal_login_doctor_by_email_and_name(self):
        """Test doctor can log in with email or physician name and password."""
        # By email
        res1 = self.client.post("/api/auth/login", json={
            "identifier": "doctor@polyscope.ai",
            "password": "doctor1234",
            "role": "doctor"
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json["user"]["role"], "doctor")
        self.assertIn("doctor_portal.html", res1.json["portal_url"])

        # By physician name
        res2 = self.client.post("/api/auth/login", json={
            "identifier": "Dr. Rajesh Sharma",
            "password": "doctor1234"
        })
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json["user"]["role"], "doctor")

        # By short name 'Rajesh Sharma'
        res3 = self.client.post("/api/auth/login", json={
            "identifier": "Rajesh Sharma",
            "password": "doctor1234"
        })
        self.assertEqual(res3.status_code, 200)

        # By alias 'doctor'
        res4 = self.client.post("/api/auth/login", json={
            "identifier": "doctor",
            "password": "doctor1234"
        })
        self.assertEqual(res4.status_code, 200)

    def test_normal_login_admin_by_email_and_name(self):
        """Test admin can log in with email or admin name and password."""
        # By email
        res1 = self.client.post("/api/auth/login", json={
            "identifier": "admin@polyscope.ai",
            "password": "admin1234",
            "role": "admin"
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json["user"]["role"], "admin")
        self.assertIn("admin_portal.html", res1.json["portal_url"])

        # By admin name
        res2 = self.client.post("/api/auth/login", json={
            "identifier": "Dr. Sarah Lin",
            "password": "admin1234"
        })
        self.assertEqual(res2.status_code, 200)

        # By short name 'Sarah Lin'
        res3 = self.client.post("/api/auth/login", json={
            "identifier": "Sarah Lin",
            "password": "admin1234"
        })
        self.assertEqual(res3.status_code, 200)

    def test_new_user_registration_and_normal_login(self):
        """Test a newly registered patient can immediately log in by email, username, or name."""
        reg_res = self.client.post("/api/auth/register", json={
            "name": "Jane Clinical Patient",
            "email": "jane.patient@example.com",
            "password": "securepassword123",
            "age": 48,
            "gender": "Female",
            "phone": "+1 (555) 234-5678"
        })
        self.assertEqual(reg_res.status_code, 201)
        patient_code = reg_res.json["user"]["patient_code"]

        # Log in by email
        res1 = self.client.post("/api/auth/login", json={
            "identifier": "jane.patient@example.com",
            "password": "securepassword123"
        })
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json["user"]["name"], "Jane Clinical Patient")

        # Log in by display name
        res2 = self.client.post("/api/auth/login", json={
            "identifier": "Jane Clinical Patient",
            "password": "securepassword123"
        })
        self.assertEqual(res2.status_code, 200)

        # Log in by patient code
        res3 = self.client.post("/api/auth/login", json={
            "identifier": patient_code,
            "password": "securepassword123"
        })
        self.assertEqual(res3.status_code, 200)

        # Wrong password rejected
        res4 = self.client.post("/api/auth/login", json={
            "identifier": "jane.patient@example.com",
            "password": "wrongpassword"
        })
        self.assertEqual(res4.status_code, 401)

    def test_demo_logins_remain_operational(self):
        """Test optional 1-click demo logins continue to work smoothly."""
        for role in ["patient", "doctor", "admin"]:
            res = self.client.post(f"/api/auth/demo-login/{role}")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json["user"]["role"], role)
            self.assertTrue(len(res.json["csrf_token"]) > 10)

    # ── 2. DOCTOR PORTAL POLYP DETECTION & REVIEW WORKFLOW ────────────────────

    def test_doctor_polyp_detection_workflow(self):
        """Test complete polyp detection workflow exclusively inside Doctor Portal."""
        # 1. Log in as Doctor
        login_res = self.client.post("/api/auth/login", json={
            "identifier": "doctor@polyscope.ai",
            "password": "doctor1234",
            "role": "doctor"
        })
        self.assertEqual(login_res.status_code, 200)

        # 2. Doctor runs detection on patient case
        detect_res = self.client.post("/api/doctor/detect", data={
            "patient_id": "3",
            "case_id": "1",
            "sample_id": "sample_polyp_1"
        })
        self.assertEqual(detect_res.status_code, 200)
        data = detect_res.json
        self.assertIn("scan_id", data)
        self.assertTrue(data["detected"])
        self.assertGreater(data["confidence"], 50.0)
        self.assertIsNotNone(data["result_image_b64"])
        self.assertIsNotNone(data["mask_image_b64"])
        scan_id = data["scan_id"]

        # 3. Doctor reviews finding (confirms polyp and enters observations)
        review_res = self.client.post(f"/api/doctor/scans/{scan_id}/review", json={
            "doctor_confirmed": True,
            "doctor_notes": "Polyp located in cecum/ascending junction. Cold-snare resection recommended.",
            "recommendations": "Schedule colonoscopy surveillance in 12 months."
        })
        self.assertEqual(review_res.status_code, 200)
        self.assertEqual(review_res.json["doctor_confirmed"], 1)

        # 4. Doctor updates case status to Follow-up required
        status_res = self.client.post("/api/doctor/cases/1/status", json={
            "status": "Follow-up required",
            "is_resolved": "No",
            "doctor_conclusion": "Tubular adenoma excised with clear margins. Annual surveillance recommended.",
            "patient_instructions": "Maintain high fiber diet. Return in 12 months for follow-up exam.",
            "follow_up_date": "12 Months"
        })
        self.assertEqual(status_res.status_code, 200)

        # 5. Doctor generates verified clinical report
        report_res = self.client.post("/api/doctor/reports/generate", json={
            "case_id": 1,
            "patient_id": 3,
            "scan_id": scan_id,
            "report_title": "Endoscopic Polypectomy Verification Report",
            "doctor_conclusions": "Benign tubular adenoma successfully removed.",
            "recommendations": "Follow-up colonoscopy in 12 months.",
            "resolution_status": "Follow-up required",
            "follow_up_instructions": "12 Months"
        })
        self.assertEqual(report_res.status_code, 201)
        self.assertIn("report_id", report_res.json)

    def test_doctor_upload_new_image_workflow(self):
        """Doctor can upload new colonoscopy images for patients into their record."""
        # 1. Log in as Doctor
        self.client.post("/api/auth/login", json={
            "identifier": "doctor@polyscope.ai",
            "password": "doctor1234",
            "role": "doctor"
        })

        # 2. Upload image for patient #3
        with open("static/samples/sample_polyp_1.jpg", "rb") as f:
            img_data = f.read()

        upload_res = self.client.post("/api/doctor/upload", data={
            "patient_id": "3",
            "case_title": "Screening Colonoscopy - Ascending Colon Frame",
            "colonic_location": "Ascending Colon",
            "image": (io.BytesIO(img_data), "doctor_upload_test.jpg")
        }, content_type="multipart/form-data")

        self.assertEqual(upload_res.status_code, 201)
        self.assertIn("scan_id", upload_res.json)
        self.assertIn("case_id", upload_res.json)

    # ── 3. PATIENT ACCESS RESTRICTIONS & VIEWING APPROVALS ────────────────────

    def test_patient_strictly_blocked_from_ai_detection(self):
        """Patients must NEVER have access to run raw AI polyp detection."""
        # Log in as patient
        login_res = self.client.post("/api/auth/login", json={
            "identifier": "patient@polyscope.ai",
            "password": "patient1234",
            "role": "patient"
        })
        self.assertEqual(login_res.status_code, 200)

        # 1. Attempt to call doctor detection endpoint
        doc_detect_res = self.client.post("/api/doctor/detect", data={
            "sample_id": "sample_polyp_1"
        })
        self.assertEqual(doc_detect_res.status_code, 403)

        # 2. Attempt to call doctor scan review
        review_res = self.client.post("/api/doctor/scans/1/review", json={
            "doctor_confirmed": True
        })
        self.assertEqual(review_res.status_code, 403)

        # 3. Attempt to call admin dashboard
        admin_res = self.client.get("/api/admin/dashboard")
        self.assertEqual(admin_res.status_code, 403)

    def test_patient_can_view_approved_report_and_dashboard(self):
        """Patients can view their assigned case progress and doctor-approved reports."""
        # Log in as patient
        self.client.post("/api/auth/login", json={
            "identifier": "patient@polyscope.ai",
            "password": "patient1234",
            "role": "patient"
        })

        dash_res = self.client.get("/api/patient/dashboard")
        self.assertEqual(dash_res.status_code, 200)
        data = dash_res.json
        self.assertIn("patient", data)
        self.assertIn("cases", data)
        self.assertIn("approved_reports", data)

        # View approved report (report 1 was seeded in init_db)
        rep_res = self.client.get("/api/patient/reports/1/view")
        self.assertEqual(rep_res.status_code, 200)
        self.assertIn("PolyScope Diagnostic Report", rep_res.text)

if __name__ == "__main__":
    unittest.main()
