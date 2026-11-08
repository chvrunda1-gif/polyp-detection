import os
import json
import base64
import secrets
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app, Response
from werkzeug.utils import secure_filename
from database.db import get_db, log_activity
from .auth import login_required, role_required
from ai.pipeline import run_ai_pipeline
from ai.preprocessor import decode_image_bytes
from services.report_generator import generate_report_html

doctor_bp = Blueprint("doctor", __name__)

@doctor_bp.route("/api/doctor/dashboard", methods=["GET"])
@login_required
@role_required("doctor", "admin")
def doctor_dashboard():
    doc_id = session["user_id"]
    db = get_db()

    total_patients = db.execute("SELECT COUNT(*) FROM users WHERE role = 'patient' AND (assigned_doctor_id = ? OR assigned_doctor_id IS NULL)", (doc_id,)).fetchone()[0]
    new_patients = db.execute("SELECT COUNT(*) FROM users WHERE role = 'patient' AND created_at >= date('now', '-7 days')", ()).fetchone()[0]
    
    pending_analyses = db.execute("SELECT COUNT(*) FROM cases WHERE status IN ('Image uploaded', 'Analysis pending')").fetchone()[0]
    completed_analyses = db.execute("SELECT COUNT(*) FROM cases WHERE status IN ('Follow-up required', 'Resolved', 'Further investigation recommended')").fetchone()[0]
    followup_cases = db.execute("SELECT COUNT(*) FROM cases WHERE status = 'Follow-up required'").fetchone()[0]
    resolved_cases = db.execute("SELECT COUNT(*) FROM cases WHERE is_resolved = 'Yes'").fetchone()[0]

    # Recent Cases Table
    recent_cases = db.execute("""
        SELECT c.*, u.name AS patient_name, u.patient_code, u.email AS patient_email
        FROM cases c
        JOIN users u ON c.patient_id = u.id
        ORDER BY c.updated_at DESC LIMIT 10
    """).fetchall()

    return jsonify({
        "stats": {
            "total_patients": total_patients,
            "new_patients": new_patients,
            "pending_analyses": pending_analyses,
            "completed_analyses": completed_analyses,
            "followup_cases": followup_cases,
            "resolved_cases": resolved_cases
        },
        "recent_cases": [{
            "id": c["id"],
            "case_number": c["case_number"],
            "patient_name": c["patient_name"],
            "patient_code": c["patient_code"] or f"POL-{c['patient_id']}",
            "title": c["title"],
            "status": c["status"],
            "is_resolved": c["is_resolved"],
            "updated_at": c["updated_at"]
        } for c in recent_cases]
    }), 200

@doctor_bp.route("/api/doctor/patients", methods=["GET"])
@login_required
@role_required("doctor", "admin")
def get_all_patients():
    search = request.args.get("q", "").strip().lower()
    db = get_db()

    query = """
        SELECT u.id, u.patient_code, u.name, u.email, u.phone, u.age, u.gender, u.medical_history, u.created_at,
               c.status AS latest_case_status, c.is_resolved AS latest_resolution, c.id AS latest_case_id,
               COUNT(s.id) AS total_scans
        FROM users u
        LEFT JOIN cases c ON c.patient_id = u.id AND c.id = (SELECT MAX(id) FROM cases WHERE patient_id = u.id)
        LEFT JOIN scans s ON s.patient_id = u.id
        WHERE u.role = 'patient'
    """
    params = []
    if search:
        query += " AND (LOWER(u.name) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(u.patient_code) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " GROUP BY u.id ORDER BY u.id DESC"
    patients = db.execute(query, tuple(params)).fetchall()

    return jsonify({
        "patients": [{
            "id": p["id"],
            "patient_code": p["patient_code"] or f"POL-PT-{p['id']}",
            "name": p["name"],
            "email": p["email"],
            "phone": p["phone"] or "N/A",
            "age": p["age"] or "N/A",
            "gender": p["gender"] or "N/A",
            "medical_history": p["medical_history"] or "",
            "latest_case_status": p["latest_case_status"] or "No active cases",
            "latest_resolution": p["latest_resolution"] or "Under review",
            "latest_case_id": p["latest_case_id"],
            "total_scans": p["total_scans"],
            "created_at": p["created_at"]
        } for p in patients]
    }), 200

@doctor_bp.route("/api/doctor/patients/<int:patient_id>", methods=["GET"])
@login_required
@role_required("doctor", "admin")
def get_patient_profile(patient_id):
    db = get_db()
    patient = db.execute("SELECT * FROM users WHERE id = ? AND role = 'patient'", (patient_id,)).fetchone()
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    cases = db.execute("SELECT * FROM cases WHERE patient_id = ? ORDER BY id DESC", (patient_id,)).fetchall()
    scans = db.execute("SELECT * FROM scans WHERE patient_id = ? ORDER BY id DESC", (patient_id,)).fetchall()
    reports = db.execute("SELECT * FROM reports WHERE patient_id = ? ORDER BY id DESC", (patient_id,)).fetchall()

    return jsonify({
        "patient": {
            "id": patient["id"],
            "patient_code": patient["patient_code"] or f"POL-PT-{patient['id']}",
            "name": patient["name"],
            "email": patient["email"],
            "phone": patient["phone"],
            "age": patient["age"],
            "gender": patient["gender"],
            "medical_history": patient["medical_history"]
        },
        "cases": [{
            "id": c["id"],
            "case_number": c["case_number"],
            "title": c["title"],
            "status": c["status"],
            "is_resolved": c["is_resolved"],
            "doctor_conclusion": c["doctor_conclusion"],
            "follow_up_date": c["follow_up_date"],
            "created_at": c["created_at"],
            "updated_at": c["updated_at"]
        } for c in cases],
        "scans": [{
            "id": s["id"],
            "filename": s["filename"],
            "cnn_prediction": s["cnn_prediction"],
            "cnn_confidence": s["cnn_confidence"],
            "doctor_confirmed": s["doctor_confirmed"],
            "paris_classification": s["paris_classification"],
            "estimated_diameter_mm": s["estimated_diameter_mm"],
            "created_at": s["created_at"]
        } for s in scans],
        "reports": [{
            "id": r["id"],
            "report_code": r["report_code"],
            "title": r["report_title"],
            "date": r["colonoscopy_date"],
            "resolution_status": r["resolution_status"]
        } for r in reports]
    }), 200

# ── AI DETECTION CENTRE (DOCTOR ONLY) ─────────────────────────────────────────

@doctor_bp.route("/api/doctor/detect", methods=["POST"])
@login_required
@role_required("doctor", "admin")
def doctor_run_ai_detection():
    """
    Exclusively available to authenticated Doctors & Admins.
    Runs CNN polyp classification & U-Net semantic lesion segmentation.
    """
    db = get_db()
    patient_id = request.form.get("patient_id")
    case_id = request.form.get("case_id")
    sample_id = request.form.get("sample_id")

    img_bgr = None
    filename = "endoscopic_frame.jpg"
    orig_path_str = "static/samples/sample_polyp_1.jpg"

    if "image" in request.files and request.files["image"].filename:
        file = request.files["image"]
        filename = secure_filename(file.filename) or "endoscopic_frame.jpg"
        img_bytes = file.read()
        img_bgr = decode_image_bytes(img_bytes)

        orig_dir = Path(current_app.config["ORIGINALS_FOLDER"])
        orig_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"DOC_ORIG_{patient_id or session['user_id']}_{secrets.token_hex(4)}_{filename}"
        orig_path = orig_dir / unique_name
        import cv2
        cv2.imwrite(str(orig_path), img_bgr)
        orig_path_str = str(orig_path)
    elif sample_id:
        # Load preloaded sample
        sample_path = Path("static/samples") / f"{sample_id}.jpg"
        if not sample_path.is_file():
            sample_path = Path("static/samples/sample_polyp_1.jpg")
        import cv2
        img_bgr = cv2.imread(str(sample_path))
        filename = sample_path.name
        orig_path_str = str(sample_path)
    elif request.form.get("existing_scan_id"):
        scan = db.execute("SELECT original_image_path, filename FROM scans WHERE id = ?", (request.form["existing_scan_id"],)).fetchone()
        if scan and Path(scan["original_image_path"]).is_file():
            import cv2
            img_bgr = cv2.imread(scan["original_image_path"])
            filename = scan["filename"]
            orig_path_str = scan["original_image_path"]

    if img_bgr is None:
        return jsonify({"error": "No valid endoscopic image provided for analysis"}), 400

    # Execute Master AI Pipeline
    cnn_path = current_app.config.get("CNN_MODEL_PATH")
    unet_path = current_app.config.get("UNET_MODEL_PATH") or current_app.config.get("LEGACY_MODEL_PATH")
    ai_result = run_ai_pipeline(img_bgr, cnn_path=cnn_path, unet_path=unet_path)

    # Save outputs if patient is specified
    scan_id = None
    if patient_id:
        res_dir = Path(current_app.config["RESULTS_FOLDER"])
        mask_dir = Path(current_app.config["MASKS_FOLDER"])
        res_dir.mkdir(parents=True, exist_ok=True)
        mask_dir.mkdir(parents=True, exist_ok=True)

        token = secrets.token_hex(4)
        res_path = res_dir / f"DOC_RES_{patient_id}_{token}.jpg"
        mask_path = mask_dir / f"DOC_MASK_{patient_id}_{token}.png"

        import cv2
        cv2.imwrite(str(res_path), ai_result["result_bgr"])
        if ai_result["mask_array"] is not None:
            cv2.imwrite(str(mask_path), ai_result["mask_array"])

        # Record scan
        cursor = db.execute("""
            INSERT INTO scans (case_id, patient_id, uploaded_by, filename, original_image_path, result_image_path, mask_image_path,
                              cnn_prediction, cnn_confidence, unet_segmented, lesion_area_px, lesion_area_pct, estimated_diameter_mm,
                              paris_classification, quadrant, bbox_json, ai_engine_used, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (case_id, patient_id, session["user_id"], filename, orig_path_str, str(res_path), str(mask_path),
              1 if ai_result["detected"] else 0, ai_result["confidence"], ai_result["lesion_area_px"],
              ai_result["lesion_area_pct"], ai_result["estimated_diameter_mm"], ai_result["paris_classification"],
              ai_result["quadrant"], json.dumps(ai_result["bbox"]) if ai_result["bbox"] else None,
              ai_result["ai_engine"], datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        scan_id = cursor.lastrowid
        db.commit()

    return jsonify({
        "scan_id": scan_id,
        "filename": filename,
        "detected": ai_result["detected"],
        "confidence": ai_result["confidence"],
        "bbox": ai_result["bbox"],
        "lesion_area_px": ai_result["lesion_area_px"],
        "lesion_area_pct": ai_result["lesion_area_pct"],
        "estimated_diameter_mm": ai_result["estimated_diameter_mm"],
        "paris_classification": ai_result["paris_classification"],
        "quadrant": ai_result["quadrant"],
        "ai_engine": ai_result["ai_engine"],
        "result_image_b64": ai_result["result_image_b64"],
        "mask_image_b64": ai_result["mask_image_b64"]
    }), 200

@doctor_bp.route("/api/doctor/upload", methods=["POST"])
@login_required
@role_required("doctor", "admin")
def doctor_upload_image():
    """
    Attending physician uploads a new colonoscopy procedure image for an assigned patient.
    """
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400
    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    patient_id = request.form.get("patient_id")
    if not patient_id:
        return jsonify({"error": "Please select a patient"}), 400

    db = get_db()
    patient = db.execute("SELECT id, name, patient_code FROM users WHERE id = ? AND role = 'patient'", (patient_id,)).fetchone()
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    filename = secure_filename(file.filename) or f"endoscopy_{secrets.token_hex(4)}.jpg"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    if ext not in current_app.config.get("ALLOWED_EXTENSIONS", {"jpg", "jpeg", "png", "webp"}):
        return jsonify({"error": "Invalid format. Allowed: JPG, PNG, WEBP"}), 400

    try:
        img_bytes = file.read()
        img_bgr = decode_image_bytes(img_bytes)
    except Exception as e:
        return jsonify({"error": f"Invalid image: {str(e)}"}), 400

    orig_dir = Path(current_app.config["ORIGINALS_FOLDER"])
    orig_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_name = f"DOC_PAT_{patient_id}_{timestamp_str}_{secrets.token_hex(3)}.{ext}"
    orig_path = orig_dir / unique_name

    import cv2
    cv2.imwrite(str(orig_path), img_bgr)

    case_id = request.form.get("case_id")
    case_title = request.form.get("case_title") or "Colonoscopy Procedure Frame"
    colonic_location = request.form.get("colonic_location") or "Ascending Colon"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    if not case_id:
        case_num = f"CAS-{datetime.utcnow().year}-{secrets.token_hex(3).upper()}"
        cursor = db.execute("""
            INSERT INTO cases (case_number, patient_id, doctor_id, title, status, is_resolved, findings_summary, doctor_conclusion, patient_instructions, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'Image uploaded', 'Under review', 'Endoscopy frame acquired and uploaded by attending doctor.', 'Pending AI detection & physician sign-off.', 'Colonoscopy still uploaded to record. Awaiting review.', ?, ?)
        """, (case_num, patient_id, session["user_id"], f"{case_title} ({colonic_location})", now, now))
        case_id = cursor.lastrowid

    scan_cursor = db.execute("""
        INSERT INTO scans (case_id, patient_id, uploaded_by, filename, original_image_path, cnn_prediction, quadrant, is_approved_for_patient, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?)
    """, (case_id, patient_id, session["user_id"], filename, str(orig_path), colonic_location, now))
    scan_id = scan_cursor.lastrowid
    db.commit()

    log_activity(session["user_id"], session["email"], "doctor", "DOCTOR_IMAGE_UPLOAD", f"Uploaded image for Patient #{patient_id}", request.remote_addr)

    return jsonify({
        "message": f"Colonoscopy image uploaded successfully for {patient['name']}",
        "scan_id": scan_id,
        "case_id": case_id,
        "patient_id": int(patient_id),
        "filename": filename,
        "image_url": f"/{str(orig_path)}"
    }), 201

@doctor_bp.route("/api/doctor/scans/<int:scan_id>/review", methods=["POST"])
@login_required
@role_required("doctor", "admin")
def review_and_confirm_scan(scan_id):
    """
    Doctor confirms or rejects the AI finding and adds observations.
    """
    data = request.get_json(silent=True) or {}
    doctor_confirmed = 1 if data.get("doctor_confirmed") else 0
    doctor_notes = str(data.get("doctor_notes", "")).strip()
    recommendations = str(data.get("recommendations", "")).strip()
    approve_for_patient = 1 if data.get("approve_for_patient", True) else 0

    db = get_db()
    scan = db.execute("SELECT id, case_id, patient_id FROM scans WHERE id = ?", (scan_id,)).fetchone()
    if not scan:
        return jsonify({"error": "Scan record not found"}), 404

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        UPDATE scans
        SET doctor_confirmed = ?,
            doctor_notes = ?,
            recommendations = ?,
            is_approved_for_patient = ?,
            reviewed_at = ?
        WHERE id = ?
    """, (doctor_confirmed, doctor_notes, recommendations, approve_for_patient, now, scan_id))

    # Also update associated case if exists
    if scan["case_id"]:
        conclusion_text = f"Doctor Confirmed: {'Polyp Identified' if doctor_confirmed else 'Lesion Excluded / Clear Mucosa'}. {doctor_notes}"
        db.execute("""
            UPDATE cases
            SET status = 'Under doctor review',
                doctor_conclusion = ?,
                patient_instructions = ?,
                updated_at = ?
            WHERE id = ?
        """, (conclusion_text, recommendations, now, scan["case_id"]))

    db.commit()
    log_activity(session["user_id"], session["email"], "doctor", "CONFIRM_AI_SCAN", f"Reviewed scan #{scan_id}", request.remote_addr)

    return jsonify({
        "message": "Doctor clinical review recorded successfully",
        "scan_id": scan_id,
        "doctor_confirmed": doctor_confirmed
    }), 200

@doctor_bp.route("/api/doctor/cases/<int:case_id>/status", methods=["POST"])
@login_required
@role_required("doctor", "admin")
def update_case_status(case_id):
    data = request.get_json(silent=True) or {}
    new_status = str(data.get("status", "Under doctor review")).strip()
    is_resolved = str(data.get("is_resolved", "Under review")).strip()
    doctor_conclusion = str(data.get("doctor_conclusion", "")).strip()
    patient_instructions = str(data.get("patient_instructions", "")).strip()
    follow_up_date = str(data.get("follow_up_date", "")).strip()

    valid_statuses = {"Image uploaded", "Analysis pending", "Under doctor review", "Follow-up required", "Further investigation recommended", "Resolved"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400

    db = get_db()
    case = db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
    if not case:
        return jsonify({"error": "Case not found"}), 404

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    db.execute("""
        UPDATE cases
        SET status = ?,
            is_resolved = ?,
            doctor_conclusion = COALESCE(NULLIF(?, ''), doctor_conclusion),
            patient_instructions = COALESCE(NULLIF(?, ''), patient_instructions),
            follow_up_date = COALESCE(NULLIF(?, ''), follow_up_date),
            updated_at = ?
        WHERE id = ?
    """, (new_status, is_resolved, doctor_conclusion, patient_instructions, follow_up_date, now, case_id))

    # Audit history log
    db.execute("""
        INSERT INTO case_history_logs (case_id, updated_by, old_status, new_status, resolution_status, notes, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (case_id, session["user_id"], case["status"], new_status, is_resolved, doctor_conclusion, now))
    db.commit()

    return jsonify({"message": f"Case updated to '{new_status}' (Resolved: {is_resolved})"}), 200

@doctor_bp.route("/api/doctor/reports/generate", methods=["POST"])
@login_required
@role_required("doctor", "admin")
def generate_official_report():
    data = request.get_json(silent=True) or {}
    patient_id = data.get("patient_id")
    case_id = data.get("case_id")
    scan_id = data.get("scan_id")
    title = str(data.get("report_title", "Colonoscopy AI Diagnostic & Pathology Report")).strip()
    doctor_conclusions = str(data.get("doctor_conclusions", "")).strip()
    recommendations = str(data.get("recommendations", "")).strip()
    follow_up_date = str(data.get("follow_up_date", "12 Months")).strip()
    resolution_status = str(data.get("resolution_status", "Under review")).strip()

    if not patient_id or not doctor_conclusions:
        return jsonify({"error": "Patient ID and Doctor conclusions are required to finalize report"}), 400

    db = get_db()
    patient = db.execute("SELECT * FROM users WHERE id = ?", (patient_id,)).fetchone()
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    doc_id = session["user_id"]
    report_code = f"REP-{datetime.utcnow().year}-{secrets.token_hex(3).upper()}"
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    exam_date = datetime.utcnow().strftime("%Y-%m-%d")

    cursor = db.execute("""
        INSERT INTO reports (report_code, case_id, scan_id, patient_id, doctor_id, report_title, colonoscopy_date,
                            ai_findings, doctor_conclusions, recommendations, follow_up_instructions, resolution_status, is_finalized, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'AI Telemetry Included', ?, ?, ?, ?, 1, ?, ?)
    """, (report_code, case_id, scan_id, patient_id, doc_id, title, exam_date,
          doctor_conclusions, recommendations, follow_up_date, resolution_status, now, now))
    report_id = cursor.lastrowid


    # If scan specified, approve for patient view
    if scan_id:
        db.execute("UPDATE scans SET is_approved_for_patient = 1 WHERE id = ?", (scan_id,))

    # If case specified, update status
    if case_id:
        case_status = "Resolved" if resolution_status == "Yes" else "Follow-up required"
        db.execute("""
            UPDATE cases
            SET status = ?,
                is_resolved = ?,
                doctor_conclusion = ?,
                patient_instructions = ?,
                updated_at = ?
            WHERE id = ?
        """, (case_status, resolution_status, doctor_conclusions, recommendations, now, case_id))

    db.commit()
    log_activity(doc_id, session["email"], "doctor", "GENERATE_REPORT", f"Generated report {report_code}", request.remote_addr)

    return jsonify({
        "message": "Official clinical report generated and saved to patient record.",
        "report_id": report_id,
        "report_code": report_code,
        "view_url": f"/api/patient/reports/{report_id}/view"
    }), 201

@doctor_bp.route("/api/doctor/reports", methods=["GET"])
@login_required
@role_required("doctor", "admin")
def list_doctor_reports():
    search = request.args.get("q", "").strip().lower()
    db = get_db()

    query = """
        SELECT r.*, u.name AS patient_name, u.patient_code, d.name AS doctor_name, c.case_number
        FROM reports r
        JOIN users u ON r.patient_id = u.id
        JOIN users d ON r.doctor_id = d.id
        LEFT JOIN cases c ON r.case_id = c.id
        WHERE 1=1
    """
    params = []
    if search:
        query += " AND (LOWER(u.name) LIKE ? OR LOWER(r.report_code) LIKE ? OR LOWER(u.patient_code) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

    query += " ORDER BY r.id DESC"
    reports = db.execute(query, tuple(params)).fetchall()

    return jsonify({
        "reports": [{
            "id": r["id"],
            "report_code": r["report_code"],
            "title": r["report_title"],
            "patient_name": r["patient_name"],
            "patient_code": r["patient_code"] or f"POL-{r['patient_id']}",
            "doctor_name": r["doctor_name"],
            "case_number": r["case_number"] or "CAS-2026-001",
            "date": r["colonoscopy_date"],
            "resolution_status": r["resolution_status"],
            "created_at": r["created_at"],
            "view_url": f"/api/patient/reports/{r['id']}/view"
        } for r in reports]
    }), 200
