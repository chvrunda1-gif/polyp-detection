import cv2
import numpy as np
from PIL import Image

IMG_SIZE = 224

def preprocess_for_inference(img_bgr, target_size=(IMG_SIZE, IMG_SIZE), apply_clahe=True):
    """
    Complete clinical endoscopic image preprocessing pipeline:
    1. Specular highlight suppression
    2. Adaptive contrast enhancement (CLAHE on LAB color space)
    3. Resizing to standard neural input tensor
    4. Normalization to [0.0, 1.0] float32
    """
    if img_bgr is None or img_bgr.size == 0:
        raise ValueError("Invalid image input for preprocessing")

    # Suppress harsh specular glare (common in wet endoscopic mucosal surfaces)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, glare_mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
    glare_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    glare_mask = cv2.dilate(glare_mask, glare_kernel, iterations=1)
    
    # Inpaint small specular dots smoothly if needed
    if cv2.countNonZero(glare_mask) > 0 and cv2.countNonZero(glare_mask) < (img_bgr.shape[0] * img_bgr.shape[1] * 0.05):
        cleaned_bgr = cv2.inpaint(img_bgr, glare_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    else:
        cleaned_bgr = img_bgr.copy()

    # Apply CLAHE to reveal subtle vascular pit patterns & mucosal margins
    if apply_clahe:
        lab = cv2.cvtColor(cleaned_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_clahe = clahe.apply(l)
        enhanced_lab = cv2.merge((l_clahe, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
    else:
        enhanced_bgr = cleaned_bgr

    # Resize to target dimension
    resized_bgr = cv2.resize(enhanced_bgr, target_size, interpolation=cv2.INTER_AREA)
    resized_rgb = cv2.cvtColor(resized_bgr, cv2.COLOR_BGR2RGB)
    
    # Normalized tensor for CNN / U-Net
    normalized_tensor = resized_rgb.astype(np.float32) / 255.0
    expanded_tensor = np.expand_dims(normalized_tensor, axis=0)
    
    return {
        "resized_bgr": resized_bgr,
        "resized_rgb": resized_rgb,
        "normalized_tensor": expanded_tensor,
        "enhanced_bgr": enhanced_bgr
    }

def decode_image_bytes(image_bytes):
    """Safely decode image bytes from upload into OpenCV BGR numpy array."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image from byte buffer")
    return img
