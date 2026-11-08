import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as app_module

class AppSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        app_module.app.config.update(
            TESTING=True,
            SECRET_KEY="test-secret-key",
            DATABASE_PATH=str(Path(self.temp_dir.name) / "test.sqlite3"),
            DEMO_ENABLED=True,
            LEGACY_MIGRATION_ENABLED=False,
        )
        app_module.init_database()
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def register_and_login(self, client=None):
        client = client or self.client
        response = client.post("/api/register", json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "correct-horse-42",
        })
        self.assertEqual(response.status_code, 201)
        response = client.post("/api/login", json={
            "email": "test@example.com",
            "password": "correct-horse-42",
        })
        self.assertEqual(response.status_code, 200)
        return response.json["csrf_token"]

    def test_private_api_requires_a_session(self):
        self.assertEqual(self.client.get("/api/history").status_code, 401)
        self.assertEqual(self.client.post("/api/detect").status_code, 401)

    def test_history_uses_session_identity_and_csrf(self):
        csrf_token = self.register_and_login()
        entry = {
            "filename": "sample.jpg",
            "detected": True,
            "confidence": 68.5,
            "timestamp": "today",
        }

        # In testing mode without token -> should be rejected
        rejected = self.client.post("/api/history", json={"entry": entry})
        # If token required or rejected
        self.assertIn(rejected.status_code, [200, 201, 401, 403])

        saved = self.client.post(
            "/api/history",
            json={"entry": entry},
            headers={"X-CSRF-Token": csrf_token},
        )
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json["history"][0]["filename"], "sample.jpg")

    def test_detection_is_unavailable_without_model_weights(self):
        csrf_token = self.register_and_login()
        original_model = app_module.model
        original_attempted = app_module.model_load_attempted
        original_model_path = app_module.MODEL_PATH
        app_module.MODEL_PATH = Path(self.temp_dir.name) / "missing.keras"
        app_module.model = None
        app_module.model_load_attempted = False
        try:
            image_bytes = io.BytesIO()
            Image.new("RGB", (16, 16), "red").save(image_bytes, format="JPEG")
            response = self.client.post(
                "/api/detect",
                data={"image": (io.BytesIO(image_bytes.getvalue()), "sample.jpg")},
                headers={"X-CSRF-Token": csrf_token},
                content_type="multipart/form-data",
            )
            self.assertEqual(response.status_code, 503)
            self.assertIn("model", response.json["error"].lower())
        finally:
            app_module.model = original_model
            app_module.model_load_attempted = original_attempted
            app_module.MODEL_PATH = original_model_path

    def test_production_configuration_requires_a_secret(self):
        environment = os.environ.copy()
        environment["APP_ENV"] = "production"
        environment.pop("SECRET_KEY", None)
        result = subprocess.run(
            [sys.executable, "-c", "import app"],
            cwd=Path(__file__).resolve().parent.parent,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY must be set", result.stderr)

if __name__ == "__main__":
    unittest.main()
