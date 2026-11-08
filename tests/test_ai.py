import unittest
import numpy as np
import cv2
from pathlib import Path

from ai.preprocessor import preprocess_for_inference
from ai.cv_engine import detect_and_segment_cv
from ai.pipeline import run_ai_pipeline
from ai.evaluator import evaluate_on_dataset

class AITests(unittest.TestCase):
    def setUp(self):
        # Load sample colonoscopy images
        self.polyp_img = cv2.imread("static/samples/sample_polyp_1.jpg")
        if self.polyp_img is None:
            self.polyp_img = np.zeros((480, 640, 3), dtype=np.uint8)
            self.polyp_img[:] = [60, 80, 160]
            cv2.ellipse(self.polyp_img, (320, 240), (60, 50), 0, 0, 360, (30, 40, 240), -1)

        self.normal_img = cv2.imread("static/samples/sample_normal_1.jpg")
        if self.normal_img is None:
            self.normal_img = np.zeros((480, 640, 3), dtype=np.uint8)
            self.normal_img[:] = [60, 80, 160]

    def test_preprocessor_output_dimensions(self):
        prep = preprocess_for_inference(self.polyp_img)
        self.assertEqual(prep["resized_bgr"].shape, (224, 224, 3))
        self.assertEqual(prep["normalized_tensor"].shape, (1, 224, 224, 3))
        self.assertTrue(0.0 <= prep["normalized_tensor"].max() <= 1.0)

    def test_cv_engine_polyp_detection(self):
        detected, conf, bbox, mask, contour, metrics = detect_and_segment_cv(self.polyp_img)
        self.assertTrue(detected)
        self.assertIsNotNone(bbox)
        self.assertGreater(conf, 50.0)
        self.assertEqual(mask.shape, (480, 640))

    def test_cv_engine_normal_tissue(self):
        detected, conf, bbox, mask, contour, metrics = detect_and_segment_cv(self.normal_img)
        self.assertFalse(detected)
        self.assertIsNone(bbox)

    def test_pipeline_integration(self):
        res = run_ai_pipeline(self.polyp_img)
        self.assertIn("detected", res)
        self.assertIn("confidence", res)
        self.assertIn("paris_classification", res)
        self.assertIn("estimated_diameter_mm", res)
        self.assertIn("result_image_b64", res)

    def test_evaluator_metrics(self):
        pairs = [
            ("static/samples/sample_polyp_1.jpg", "static/samples/sample_polyp_1_mask.png"),
            ("static/samples/sample_normal_1.jpg", "static/samples/sample_normal_1_mask.png")
        ]
        results = evaluate_on_dataset(pairs)
        self.assertEqual(results["status"], "success")
        self.assertIn("accuracy", results["metrics"])
        self.assertIn("dice", results["metrics"])
        self.assertIn("iou", results["metrics"])

if __name__ == "__main__":
    unittest.main()
