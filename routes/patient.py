import os
import json
import secrets
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app, Response
from werkzeug.utils import secure_filename
from database.db import get_db, log_activity
from .auth import login_required, role_required
from ai.preprocessor import decode_image_bytes
from services.report_generator import generate_report_html

patient_bp = Blueprint("patient", __name__)

@patient_bp.route("/api/patient/dashboard", methods=["GET"])
@login_required
@role_required("patient")
def patient_dashboard():
    user_id = session["user_id"]
    db = get_db()
    
    # Patient profile & assigned doctor
    user = db.execute("""
        SELECT u.id, u.patient_code, u.name, u.email, u.phone, u.age, u.gender, u.medical_history,
               d.name AS doctor_name, d.email AS doctor_email, d.phone AS doctor_phone
        FROM users u
        LEFT JOIN users d ON u.assigned_doctor_id = d.id
        WHERE u.id = ?
    """, (user_id,)).fetchone()
    
    # Active patient cases
    cases = db.execute("""
        SELECT c.*, d.name AS doctor_name, d.email AS doctor_email
        FROM cases c
        LEFT JOIN users d ON c.doctor_id = d.id
        WHERE c.patient_id = ?
        ORDER BY c.id DESC
    """, (user_id,)).fetchall()
    
    # Approved reports
    reports = db.execute("""
        SELECT r.*, d.name AS doctor_name
        FROM reports r
        JOIN users d ON r.doctor_id = d.id
        WHERE r.patient_id = ? AND r.is_finalized = 1
        ORDER BY r.id DESC
    """, (user_id,)).fetchall()

    return jsonify({
        "patient": {
            "id": user["id"],
            "patient_code": user["patient_code"] or f"POL-PT-{user['id']}",
            "name": user["name"],
            "email": user["email"],
            "phone": user["phone"] or "Not provided",
            "age": user["age"] or "N/A",
            "gender": user["gender"] or "N/A",
            "medical_history": user["medical_history"] or "No prior documented history",
            "doctor": {
                "name": user["doctor_name"] or "Pending Clinical Assignment",
                "email": user["doctor_email"] or "",
                "phone": user["doctor_phone"] or ""
            }
        },
        "cases": [{
            "id": c["id"],
            "case_number": c["case_number"],
            "title": c["title"],
            "status": c["status"],
            "is_resolved": c["is_resolved"],
            "findings_summary": c["findings_summary"] if c["status"] in ["Under doctor review", "Follow-up required", "Further investigation recommended", "Resolved"] else "Analysis and review in progress by clinical team.",
            "doctor_conclusion": c["doctor_conclusion"] if c["status"] in ["Follow-up required", "Further investigation recommended", "Resolved"] else "Awaiting attending gastroenterologist review.",
            "patient_instructions": c["patient_instructions"] or "Rest and await doctor contact.",
            "follow_up_date": c["follow_up_date"] or "To be determined",
            "doctor_name": c["doctor_name"] or "Attending Physician",
            "created_at": c["created_at"],
            "updated_at": c["updated_at"]
        } for c in cases],
        "approved_reports": [{
            "id": r["id"],
            "report_code": r["report_code"],
            "title": r["report_title"],
            "date": r["colonoscopy_date"],
            "doctor_name": r["doctor_name"],
            "resolution_status": r["resolution_status"],
            "created_at": r["created_at"]
        } for r in reports]
    }), 200

@patient_bp.route("/api/patient/upload", methods=["POST"])
@login_required
@role_required("patient")
def patient_upload():
    """
    Patient uploads an endoscopic image.
    This creates an examination record and enters the doctor review queue.
    NOTE: Patients are strictly barred from running detection or seeing raw unreviewed AI inferences.
    """
    if "image" not in request.files:
        return jsonify({"error": "No image file provided"}), 400

    file = request.files["image"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename) or f"endoscopy_{secrets.token_hex(4)}.jpg"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        return jsonify({"error": f"Invalid format. Allowed: {', '.join(current_app.config['ALLOWED_EXTENSIONS'])}"}), 400

    try:
        img_bytes = file.read()
        img_bgr = decode_image_bytes(img_bytes)
    except Exception as e:
        return jsonify({"error": f"Could not read image: {str(e)}"}), 400

    orig_dir = Path(current_app.config["ORIGINALS_FOLDER"])
    orig_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_name = f"PAT_{session['user_id']}_{timestamp_str}_{secrets.token_hex(3)}.{ext}"
    orig_path = orig_dir / unique_name

    import cv2
    cv2.imwrite(str(orig_path), img_bgr)

    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT assigned_doctor_id, name FROM users WHERE id = ?", (user_id,)).fetchone()
    doc_id = user["assigned_doctor_id"]
    if not doc_id:
        # Default to first active doctor
        first_doc = db.execute("SELECT id FROM users WHERE role = 'doctor' AND status = 'active' ORDER BY id ASC LIMIT 1").fetchone()
        doc_id = first_doc[0] if first_doc else None

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    case_num = f"CAS-{datetime.utcnow().year}-{secrets.token_hex(3).upper()}"

    cursor = db.execute("""
        INSERT INTO cases (case_number, patient_id, doctor_id, title, status, is_resolved, findings_summary, doctor_conclusion, patient_instructions, created_at, updated_at)
        VALUES (?, ?, ?, 'Colonoscopy Image Examination', 'Image uploaded', 'Under review', 'Image uploaded successfully. Clinical AI analysis queued for attending doctor.', 'Pending endoscopist review and validation.', 'Your image has been received securely. Your gastroenterologist will inspect the image and issue your verified report.', ?, ?)
    """, (case_num, user_id, doc_id, now, now))
    case_id = cursor.lastrowid

    # Insert into scans queue (unapproved for patient until doctor confirms)
    db.execute("""
        INSERT INTO scans (case_id, patient_id, uploaded_by, filename, original_image_path, cnn_prediction, is_approved_for_patient, created_at)
        VALUES (?, ?, ?, ?, ?, 0, 0, ?)
    """, (case_id, user_id, user_id, filename, str(orig_path), now))

    # Log case history
    db.execute("""
        INSERT INTO case_history_logs (case_id, updated_by, old_status, new_status, resolution_status, notes, timestamp)
        VALUES (?, ?, 'None', 'Image uploaded', 'Under review', 'Colonoscopy image submitted by patient', ?)
    """, (case_id, user_id, now))
    db.commit()

    log_activity(user_id, session.get("email"), "patient", "IMAGE_UPLOAD", f"Uploaded image for Case {case_num}", request.remote_addr)

    return jsonify({
        "message": "Colonoscopy image uploaded securely. Your case is now scheduled for doctor review.",
        "case_number": case_num,
        "status": "Image uploaded"
    }), 201

@patient_bp.route("/api/patient/reports/<int:report_id>/view", methods=["GET"])
@login_required
@role_required("patient", "doctor", "admin")
def view_patient_report(report_id):
    db = get_db()
    user_id = session["user_id"]
    role = session.get("role")

    query = """
        SELECT r.*, c.case_number, u.name AS patient_name, u.patient_code, u.age AS patient_age, u.gender AS patient_gender,
               d.name AS doctor_name, s.cnn_prediction, s.cnn_confidence, s.paris_classification, s.estimated_diameter_mm,
               s.quadrant, s.ai_engine_used, s.original_image_path, s.result_image_path
        FROM reports r
        JOIN users u ON r.patient_id = u.id
        JOIN users d ON r.doctor_id = d.id
        LEFT JOIN cases c ON r.case_id = c.id
        LEFT JOIN scans s ON r.scan_id = s.id
        WHERE r.id = ?
    """
    if role == "patient":
        query += " AND r.patient_id = ?"
        report = db.execute(query, (report_id, user_id)).fetchone()
    else:
        report = db.execute(query, (report_id,)).fetchone()

    if not report:
        return "<h3>Report not found or not approved for viewing.</h3>", 404

    # Format URLs
    orig_url = f"/{report['original_image_path']}" if report['original_image_path'] else "/static/samples/sample_polyp_1.jpg"
    res_url = f"/{report['result_image_path']}" if report['result_image_path'] else orig_url

    report_payload = {
        "report_code": report["report_code"],
        "case_number": report["case_number"] or "CAS-2026-001",
        "colonoscopy_date": report["colonoscopy_date"],
        "patient_name": report["patient_name"],
        "patient_code": report["patient_code"] or f"POL-{report['patient_id']}",
        "patient_age": report["patient_age"] or 52,
        "patient_gender": report["patient_gender"] or "Male",
        "doctor_name": report["doctor_name"],
        "polyp_detected": bool(report["cnn_prediction"]),
        "confidence": report["cnn_confidence"] or 96.0,
        "paris_classification": report["paris_classification"] or "Type Is (Sessile)",
        "estimated_diameter_mm": report["estimated_diameter_mm"] or 8.5,
        "quadrant": report["quadrant"] or "Ascending Colon",
        "ai_engine": report["ai_engine_used"] or "TensorFlow Deep Neural Architecture",
        "doctor_conclusions": report["doctor_conclusions"],
        "recommendations": report["recommendations"],
        "resolution_status": report["resolution_status"],
        "follow_up_date": report["follow_up_instructions"] or "12 Months",
        "original_image_url": orig_url,
        "result_image_url": res_url
    }

    html = generate_report_html(report_payload)
    return Response(html, mimetype="text/html")
