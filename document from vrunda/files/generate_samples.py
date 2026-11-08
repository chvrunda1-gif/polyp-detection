import cv2
import numpy as np
from pathlib import Path

def create_sample_images(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Normal colonoscopy 1
    np.random.seed(101)
    img_normal = np.zeros((480, 640, 3), dtype=np.uint8)
    # Background pink-orange mucosa
    for r in range(480):
        factor = 1.0 - 0.5 * (r / 480.0)
        img_normal[r, :] = [int(70 * factor), int(90 * factor), int(170 * factor)]
    # Add gentle mucosal folds (curves)
    cv2.ellipse(img_normal, (320, 240), (280, 180), 15, 0, 360, (50, 70, 150), 30)
    cv2.ellipse(img_normal, (320, 240), (200, 120), 10, 0, 360, (40, 50, 120), 20)
    # Add noise & blur for organic look
    noise = np.random.normal(0, 10, img_normal.shape).astype(np.int16)
    img_normal = np.clip(img_normal.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    img_normal = cv2.GaussianBlur(img_normal, (15, 15), 0)
    # Specular reflections
    cv2.circle(img_normal, (260, 210), 8, (240, 245, 250), -1)
    cv2.circle(img_normal, (380, 270), 5, (230, 240, 250), -1)
    cv2.imwrite(str(output_dir / "sample_normal_1.jpg"), img_normal)

    # 2. Normal colonoscopy 2
    np.random.seed(102)
    img_normal2 = np.zeros((480, 640, 3), dtype=np.uint8)
    for c in range(640):
        factor = 0.8 + 0.2 * np.sin(c / 50.0)
        img_normal2[:, c] = [int(65 * factor), int(85 * factor), int(160 * factor)]
    cv2.ellipse(img_normal2, (310, 260), (220, 140), -20, 0, 360, (45, 60, 130), 25)
    noise2 = np.random.normal(0, 8, img_normal2.shape).astype(np.int16)
    img_normal2 = np.clip(img_normal2.astype(np.int16) + noise2, 0, 255).astype(np.uint8)
    img_normal2 = cv2.GaussianBlur(img_normal2, (11, 11), 0)
    cv2.circle(img_normal2, (290, 230), 6, (235, 240, 245), -1)
    cv2.imwrite(str(output_dir / "sample_normal_2.jpg"), img_normal2)

    # 3. Polyp sample 1 (Sessile polyp)
    img_polyp1 = img_normal.copy()
    # Draw prominent reddish/vascular raised polyp in center-right
    center1 = (360, 230)
    axes1 = (60, 48)
    cv2.ellipse(img_polyp1, center1, axes1, -10, 0, 360, (40, 50, 210), -1)
    # Texture inside polyp
    for _ in range(8):
        vx = int(center1[0] + np.random.randint(-35, 35))
        vy = int(center1[1] + np.random.randint(-25, 25))
        cv2.line(img_polyp1, (vx, vy), (vx + np.random.randint(-10, 10), vy + np.random.randint(-10, 10)), (20, 20, 160), 2)
    cv2.ellipse(img_polyp1, center1, (axes1[0]-10, axes1[1]-8), -10, 0, 360, (50, 70, 230), -1)
    cv2.circle(img_polyp1, (center1[0] - 15, center1[1] - 10), 6, (245, 250, 255), -1)
    img_polyp1 = cv2.GaussianBlur(img_polyp1, (7, 7), 0)
    cv2.imwrite(str(output_dir / "sample_polyp_1.jpg"), img_polyp1)

    # 4. Polyp sample 2 (Pedunculated / Elevated polyp)
    img_polyp2 = img_normal2.copy()
    center2 = (270, 240)
    axes2 = (55, 50)
    cv2.ellipse(img_polyp2, center2, axes2, 15, 0, 360, (30, 40, 220), -1)
    cv2.ellipse(img_polyp2, center2, (axes2[0]-8, axes2[1]-8), 15, 0, 360, (45, 60, 240), -1)
    cv2.circle(img_polyp2, (center2[0] - 10, center2[1] - 12), 7, (250, 250, 255), -1)
    img_polyp2 = cv2.GaussianBlur(img_polyp2, (5, 5), 0)
    cv2.imwrite(str(output_dir / "sample_polyp_2.jpg"), img_polyp2)

    print("Created 4 sample colonoscopy images in", output_dir)

if __name__ == "__main__":
    out_dir = Path(__file__).parent / "static" / "samples"
    create_sample_images(out_dir)
