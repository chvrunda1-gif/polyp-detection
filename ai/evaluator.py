import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from .pipeline import run_ai_pipeline

def evaluate_on_dataset(test_pairs, cnn_path=None, unet_path=None):
    """
    Evaluates detection & segmentation on a set of (image_path, ground_truth_mask_path) pairs.
    Computes real mathematical metrics:
    - Accuracy
    - Precision
    - Recall (Sensitivity)
    - Specificity
    - F1-Score
    - Dice Similarity Coefficient (DSC)
    - Intersection-over-Union (IoU / Jaccard Index)
    """
    if not test_pairs:
        return {
            "status": "error",
            "message": "No test pairs provided for evaluation.",
            "metrics": None
        }

    tp = 0
    fp = 0
    tn = 0
    fn = 0
    
    dice_scores = []
    iou_scores = []
    sample_results = []

    for img_path, mask_path in test_pairs:
        img_path = Path(img_path)
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            continue
            
        # Ground truth status
        has_gt_mask = mask_path is not None and Path(mask_path).is_file()
        gt_mask = None
        is_ground_truth_polyp = False
        
        if has_gt_mask:
            gt_mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            if gt_mask_raw is not None:
                gt_mask = cv2.resize(gt_mask_raw, (224, 224), interpolation=cv2.INTER_NEAREST)
                gt_mask = (gt_mask > 127).astype(np.uint8)
                is_ground_truth_polyp = bool(np.sum(gt_mask) > 10)
        
        # Run AI Pipeline
        ai_res = run_ai_pipeline(img_bgr, cnn_path=cnn_path, unet_path=unet_path)
        pred_detected = ai_res["detected"]
        pred_mask = ai_res["mask_array"]
        
        if pred_mask is not None and pred_mask.shape != (224, 224):
            pred_mask = cv2.resize(pred_mask, (224, 224), interpolation=cv2.INTER_NEAREST)
        pred_binary = (pred_mask > 127).astype(np.uint8) if pred_mask is not None else np.zeros((224, 224), dtype=np.uint8)

        # Classification Matrix
        if is_ground_truth_polyp and pred_detected:
            tp += 1
        elif not is_ground_truth_polyp and pred_detected:
            fp += 1
        elif not is_ground_truth_polyp and not pred_detected:
            tn += 1
        else: # is_ground_truth_polyp and not pred_detected
            fn += 1

        # Pixel-level Dice & IoU on polyp cases
        if is_ground_truth_polyp and gt_mask is not None:
            intersection = np.sum(pred_binary * gt_mask)
            union = np.sum(np.clip(pred_binary + gt_mask, 0, 1))
            total_pixels = np.sum(pred_binary) + np.sum(gt_mask)
            
            iou = float(intersection / union) if union > 0 else 1.0
            dice = float((2.0 * intersection) / total_pixels) if total_pixels > 0 else 1.0
            
            dice_scores.append(dice)
            iou_scores.append(iou)
            sample_results.append({
                "file": img_path.name,
                "truth": "Polyp",
                "pred": "Polyp" if pred_detected else "Clear",
                "confidence": ai_res["confidence"],
                "dice": round(dice, 4),
                "iou": round(iou, 4)
            })
        else:
            sample_results.append({
                "file": img_path.name,
                "truth": "Normal",
                "pred": "Polyp" if pred_detected else "Clear",
                "confidence": ai_res["confidence"],
                "dice": 1.0 if not pred_detected else 0.0,
                "iou": 1.0 if not pred_detected else 0.0
            })

    total = tp + fp + tn + fn
    if total == 0:
        return {"status": "error", "message": "Zero readable samples in evaluation batch."}

    accuracy = (tp + tn) / total
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    mean_dice = float(np.mean(dice_scores)) if dice_scores else (1.0 if fn == 0 and fp == 0 else 0.0)
    mean_iou = float(np.mean(iou_scores)) if iou_scores else (1.0 if fn == 0 and fp == 0 else 0.0)

    return {
        "status": "success",
        "evaluated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "total_samples": total,
        "confusion_matrix": {
            "true_positives": tp,
            "false_positives": fp,
            "true_negatives": tn,
            "false_negatives": fn
        },
        "metrics": {
            "accuracy": round(accuracy * 100, 2),
            "precision": round(precision * 100, 2),
            "recall": round(recall * 100, 2),
            "specificity": round(specificity * 100, 2),
            "f1_score": round(f1 * 100, 2),
            "dice": round(mean_dice, 4),
            "iou": round(mean_iou, 4)
        },
        "sample_breakdown": sample_results
    }
