import cv2
import numpy as np
import base64
from pathlib import Path
from .preprocessor import preprocess_for_inference, decode_image_bytes
from .cnn_detector import predict_cnn, load_cnn_model
from .unet_segmenter import predict_unet, load_unet_model
from .cv_engine import detect_and_segment_cv

def draw_clinical_overlay(img_bgr, bbox=None, mask=None, detected=False, confidence=0.0):
    """
    Renders high-visibility medical HUD annotation:
    - Semi-transparent colored segmentation mask
    - Polished bounding box with corner crosshairs
    - Target reticle & telemetry tag
    """
    canvas = img_bgr.copy()
    h, w = canvas.shape[:2]
    
    if not detected or bbox is None:
        # Subtle status stamp for clear normal scans
        cv2.putText(canvas, "AI: NO LESION IDENTIFIED", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 240, 100), 2, cv2.LINE_AA)
        return canvas

    x, y, bw, bh = bbox
    
    # 1. Overlay segmentation mask if available
    if mask is not None and mask.shape[:2] == (h, w) and cv2.countNonZero(mask) > 0:
        colored_mask = np.zeros_like(canvas)
        colored_mask[mask > 127] = [0, 235, 160] # Teal/Emerald glow
        canvas = cv2.addWeighted(canvas, 1.0, colored_mask, 0.35, 0)
        
        # Draw contour line
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(canvas, contours, -1, (0, 255, 140), 2, cv2.LINE_AA)
        
    # 2. Draw styled bounding box
    box_color = (0, 240, 120)
    cv2.rectangle(canvas, (x, y), (x + bw, y + bh), box_color, 2)
    
    # Corner brackets for modern medical HUD aesthetic
    corner_len = max(12, min(bw, bh) // 4)
    thick = 3
    # Top-Left
    cv2.line(canvas, (x, y), (x + corner_len, y), box_color, thick)
    cv2.line(canvas, (x, y), (x, y + corner_len), box_color, thick)
    # Top-Right
    cv2.line(canvas, (x + bw, y), (x + bw - corner_len, y), box_color, thick)
    cv2.line(canvas, (x + bw, y), (x + bw, y + corner_len), box_color, thick)
    # Bottom-Left
    cv2.line(canvas, (x, y + bh), (x + corner_len, y + bh), box_color, thick)
    cv2.line(canvas, (x, y + bh), (x, y + bh - corner_len), box_color, thick)
    # Bottom-Right
    cv2.line(canvas, (x + bw, y + bh), (x + bw - corner_len, y + bh), box_color, thick)
    cv2.line(canvas, (x + bw, y + bh), (x + bw, y + bh - corner_len), box_color, thick)
    
    # 3. Center target reticle
    cx, cy = x + bw // 2, y + bh // 2
    cv2.drawMarker(canvas, (cx, cy), box_color, markerType=cv2.MARKER_CROSS, markerSize=14, thickness=2)
    
    # 4. Telemetry Tag Badge
    tag = f"POLYP DETECTED | {confidence}%"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.55
    (tw, th), baseline = cv2.getTextSize(tag, font, font_scale, 2)
    tag_y = max(y - 10, th + 8)
    
    cv2.rectangle(canvas, (x, tag_y - th - 6), (x + tw + 12, tag_y + baseline + 2), (10, 28, 20), -1)
    cv2.rectangle(canvas, (x, tag_y - th - 6), (x + tw + 12, tag_y + baseline + 2), box_color, 1)
    cv2.putText(canvas, tag, (x + 6, tag_y - 2), font, font_scale, (0, 255, 140), 2, cv2.LINE_AA)
    
    return canvas

def estimate_clinical_parameters(bbox, img_shape, circularity=0.7, solidity=0.8):
    """
    Estimates Paris classification, approximate diameter, and anatomical quadrant.
    """
    if bbox is None:
        return {
            "paris_classification": "N/A (Clear Mucosa)",
            "estimated_diameter_mm": 0.0,
            "quadrant": "Diffuse / Unremarkable",
            "recommendation": "Normal mucosal findings. Continue routine surveillance per clinical guidelines."
        }
        
    x, y, bw, bh = bbox
    h, w = img_shape[:2]
    
    # Working distance calibration approx ~14 px/mm in standard colonoscopy field
    scale_px_per_mm = 13.5
    dim_w = bw / scale_px_per_mm
    dim_h = bh / scale_px_per_mm
    est_diameter = round(max(dim_w, dim_h), 1)
    
    # Paris classification estimate
    aspect = max(bw, bh) / (min(bw, bh) + 1e-5)
    if aspect > 1.8:
        paris = "Type Ip (Pedunculated)"
    elif est_diameter > 10.0 or circularity < 0.4:
        paris = "Type IIa (Flat Elevated)"
    else:
        paris = "Type Is (Sessile)"
        
    # Anatomical quadrant
    cx = x + bw / 2.0
    cy = y + bh / 2.0
    vert = "Upper" if cy < (h / 2.0) else "Lower"
    horiz = "Left" if cx < (w / 2.0) else "Right"
    quadrant = f"{vert} {horiz} Field"
    
    # Recommendation
    if est_diameter < 5.0:
        rec = "Diminutive polyp (<5mm). Cold biopsy forceps resection or surveillance recommended."
    elif est_diameter <= 10.0:
        rec = "Small polyp (5-10mm). Cold snare polypectomy recommended with histopathology review."
    else:
        rec = "Significant lesion (>10mm). Endoscopic mucosal resection (EMR) or hot snare excision recommended."
        
    return {
        "paris_classification": paris,
        "estimated_diameter_mm": est_diameter,
        "quadrant": quadrant,
        "recommendation": rec
    }

def run_ai_pipeline(img_bgr, cnn_path=None, unet_path=None):
    """
    Master AI Detection & Segmentation Pipeline:
    1. Preprocesses image (glare filter, CLAHE, resizing, normalization)
    2. Runs trained CNN/U-Net models if weights are present
    3. Runs active Computer Vision Feature Extractor if weights are not present
    4. Renders medical HUD overlay
    5. Returns unified diagnostic report dictionary
    """
    prep = preprocess_for_inference(img_bgr)
    resized_bgr = prep["resized_bgr"]
    norm_tensor = prep["normalized_tensor"]
    
    # Check for deep learning models
    cnn_loaded = load_cnn_model(cnn_path) is not None if cnn_path else False
    unet_loaded = load_unet_model(unet_path) is not None if unet_path else False
    
    if cnn_loaded or unet_loaded:
        ai_engine = "TensorFlow Deep Neural Networks (CNN & U-Net)"
        # 1. CNN detection
        cnn_det, cnn_conf, _ = predict_cnn(norm_tensor, cnn_path)
        # 2. U-Net segmentation
        mask_binary, unet_conf, unet_bbox, _ = predict_unet(norm_tensor, unet_path)
        
        detected = bool(cnn_det if cnn_det is not None else (unet_bbox is not None))
        confidence = cnn_conf if cnn_conf > 0 else round(unet_conf * 100, 1)
        bbox = unet_bbox
        mask = mask_binary
        display_img = resized_bgr
        
        # Area metrics
        if mask is not None and detected:
            area_px = float(cv2.countNonZero(mask))
            area_pct = round((area_px / (mask.shape[0] * mask.shape[1])) * 100, 2)
        else:
            area_px = 0.0
            area_pct = 0.0
    else:
        # Active Computer Vision Engine operating on high-resolution endoscopic frame
        ai_engine = "Computer Vision Feature Extractor Engine"
        cv_det, cv_conf, cv_bbox, cv_mask, cv_contour, cv_metrics = detect_and_segment_cv(img_bgr)
        detected = cv_det
        confidence = cv_conf
        bbox = cv_bbox
        mask = cv_mask
        area_px = cv_metrics["area_px"]
        area_pct = cv_metrics["area_pct"]
        display_img = img_bgr

    # Generate clinical parameters
    clin_params = estimate_clinical_parameters(bbox, display_img.shape)
    
    # Generate overlaid result image
    result_bgr = draw_clinical_overlay(display_img, bbox=bbox, mask=mask, detected=detected, confidence=confidence)

    
    # Encode images to Base64 for fast API responses
    _, res_buf = cv2.imencode(".jpg", result_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    result_b64 = base64.b64encode(res_buf).decode("utf-8")
    
    mask_b64 = ""
    if mask is not None:
        _, mask_buf = cv2.imencode(".png", mask)
        mask_b64 = base64.b64encode(mask_buf).decode("utf-8")
        
    return {
        "detected": detected,
        "confidence": confidence,
        "bbox": list(bbox) if bbox else None,
        "mask_available": mask is not None,
        "lesion_area_px": area_px,
        "lesion_area_pct": area_pct,
        "estimated_diameter_mm": clin_params["estimated_diameter_mm"],
        "paris_classification": clin_params["paris_classification"],
        "quadrant": clin_params["quadrant"],
        "recommendation": clin_params["recommendation"],
        "ai_engine": ai_engine,
        "result_image_b64": result_b64,
        "mask_image_b64": mask_b64,
        "result_bgr": result_bgr,
        "mask_array": mask
    }
