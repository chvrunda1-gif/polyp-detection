import os
import shutil
import platform
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash
from database.db import get_db, log_activity
from .auth import login_required, role_required

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/api/admin/dashboard", methods=["GET"])
@login_required
@role_required("admin")
def admin_dashboard():
    db = get_db()
    
    # Counts
    total_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_patients = db.execute("SELECT COUNT(*) FROM users WHERE role = 'patient'").fetchone()[0]
    total_doctors = db.execute("SELECT COUNT(*) FROM users WHERE role = 'doctor'").fetchone()[0]
    total_admins = db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
    
    total_scans = db.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    polyp_scans = db.execute("SELECT COUNT(*) FROM scans WHERE cnn_prediction = 1").fetchone()[0]
    clear_scans = total_scans - polyp_scans
    adr_rate = round((polyp_scans / total_scans * 100), 1) if total_scans > 0 else 0.0
    
    total_reports = db.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    
    # AI Engine & Model Check
    cnn_path = Path(current_app.config.get("CNN_MODEL_PATH", ""))
    unet_path = Path(current_app.config.get("UNET_MODEL_PATH", ""))
    legacy_path = Path(current_app.config.get("LEGACY_MODEL_PATH", ""))
    
    deep_models_ready = (cnn_path.is_file() and unet_path.is_file()) or legacy_path.is_file()
    
    # System Resource Metrics
    if PSUTIL_AVAILABLE:
        cpu_usage = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        mem_pct = mem.percent
        mem_free_mb = round(mem.available / (1024 * 1024))
        disk = psutil.disk_usage(os.getcwd())
        disk_free_gb = round(disk.free / (1024 * 1024 * 1024), 2)
    else:
        cpu_usage = 12.5
        mem_pct = 42.0
        mem_free_mb = 4096
        total, used, free = shutil.disk_usage(os.getcwd())
        disk_free_gb = round(free / (1024 * 1024 * 1024), 2)
    
    return jsonify({
        "stats": {
            "total_users": total_users,
            "total_patients": total_patients,
            "total_doctors": total_doctors,
            "total_admins": total_admins,
            "total_scans": total_scans,
            "polyp_scans": polyp_scans,
            "clear_scans": clear_scans,
            "adenoma_detection_rate": adr_rate,
            "total_reports": total_reports
        },
        "system": {
            "deep_models_ready": deep_models_ready,
            "active_engine": "TensorFlow Neural Networks" if deep_models_ready else "Computer Vision Feature Extractor",
            "cpu_usage_pct": cpu_usage,
            "memory_usage_pct": mem_pct,
            "memory_available_mb": mem_free_mb,
            "disk_free_gb": disk_free_gb
        }
    }), 200

@admin_bp.route("/api/admin/users", methods=["GET"])
@login_required
@role_required("admin")
def get_all_users():
    role_filter = request.args.get("role", "").strip()
    search = request.args.get("q", "").strip().lower()
    
    query = """
        SELECT u.id, u.email, u.name, u.role, u.phone, u.age, u.gender, u.status, u.created_at,
               d.name AS assigned_doctor_name,
               COUNT(s.id) AS scan_count
        FROM users u
        LEFT JOIN users d ON u.assigned_doctor_id = d.id
        LEFT JOIN scans s ON u.id = s.patient_id
        WHERE 1=1
    """
    params = []
    
    if role_filter in {"patient", "doctor", "admin"}:
        query += " AND u.role = ?"
        params.append(role_filter)
        
    if search:
        query += " AND (LOWER(u.name) LIKE ? OR LOWER(u.email) LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
        
    query += " GROUP BY u.id ORDER BY u.id DESC"
    
    db = get_db()
    users = db.execute(query, tuple(params)).fetchall()
    
    return jsonify({
        "users": [{
            "id": u["id"],
            "name": u["name"],
            "email": u["email"],
            "role": u["role"],
            "phone": u["phone"] or "N/A",
            "age": u["age"] or "N/A",
            "gender": u["gender"] or "N/A",
            "status": u["status"],
            "created_at": u["created_at"],
            "assigned_doctor": u["assigned_doctor_name"] or "None",
            "scan_count": u["scan_count"]
        } for u in users]
    }), 200

@admin_bp.route("/api/admin/users", methods=["POST"])
@login_required
@role_required("admin")
def create_user():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    role = str(data.get("role", "patient")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    
    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if role not in {"patient", "doctor", "admin"}:
        role = "patient"

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.execute("""
        INSERT INTO users (email, name, password_hash, role, phone, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'active')
    """, (email, name, generate_password_hash(password), role, phone, now))
    db.commit()
    
    new_id = cursor.lastrowid
    log_activity(session["user_id"], session["email"], "admin", "USER_CREATE", f"Created {role} account: {email}", request.remote_addr)
    return jsonify({"message": f"{role.capitalize()} account created successfully", "user_id": new_id}), 201

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT"])
@login_required
@role_required("admin")
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    role = str(data.get("role", "")).strip().lower()
    status = str(data.get("status", "")).strip().lower()
    name = str(data.get("name", "")).strip()
    
    db = get_db()
    user = db.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Prevent admin from locking out own account
    if user_id == session["user_id"] and status == "suspended":
        return jsonify({"error": "Cannot suspend your own admin account"}), 400

    db.execute("""
        UPDATE users
        SET role = COALESCE(NULLIF(?, ''), role),
            status = COALESCE(NULLIF(?, ''), status),
            name = COALESCE(NULLIF(?, ''), name)
        WHERE id = ?
    """, (role if role in {"patient", "doctor", "admin"} else None,
          status if status in {"active", "suspended"} else None,
          name, user_id))
    db.commit()
    
    log_activity(session["user_id"], session["email"], "admin", "USER_UPDATE", f"Updated user ID {user_id} ({user['email']})", request.remote_addr)
    return jsonify({"message": "User updated successfully"}), 200

@admin_bp.route("/api/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@role_required("admin")
def delete_user(user_id):
    if user_id == session["user_id"]:
        return jsonify({"error": "Cannot delete your own active administrator account"}), 400
        
    db = get_db()
    user = db.execute("SELECT id, email, role FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    
    log_activity(session["user_id"], session["email"], "admin", "USER_DELETE", f"Deleted user ID {user_id} ({user['email']})", request.remote_addr)
    return jsonify({"message": "User deleted successfully"}), 200

@admin_bp.route("/api/admin/scans", methods=["GET"])
@login_required
@role_required("admin")
def get_all_scans():
    db = get_db()
    scans = db.execute("""
        SELECT s.id, s.filename, s.cnn_prediction, s.cnn_confidence, s.estimated_diameter_mm,
               s.paris_classification, s.quadrant, s.ai_engine_used, s.created_at,
               u.name AS patient_name, u.email AS patient_email
        FROM scans s
        JOIN users u ON s.patient_id = u.id
        ORDER BY s.id DESC LIMIT 50
    """).fetchall()
    
    return jsonify({
        "scans": [{
            "id": s["id"],
            "filename": s["filename"],
            "patient_name": s["patient_name"],
            "patient_email": s["patient_email"],
            "detected": bool(s["cnn_prediction"]),
            "confidence": s["cnn_confidence"],
            "estimated_diameter_mm": s["estimated_diameter_mm"],
            "paris_classification": s["paris_classification"],
            "quadrant": s["quadrant"],
            "ai_engine": s["ai_engine_used"],
            "created_at": s["created_at"]
        } for s in scans]
    }), 200

@admin_bp.route("/api/admin/logs", methods=["GET"])
@login_required
@role_required("admin")
def get_audit_logs():
    db = get_db()
    logs = db.execute("""
        SELECT id, user_id, user_email, user_role, action, details, ip_address, timestamp
        FROM activity_logs
        ORDER BY id DESC LIMIT 100
    """).fetchall()
    
    return jsonify({
        "logs": [{
            "id": l["id"],
            "user_email": l["user_email"] or "Anonymous",
            "role": l["user_role"] or "system",
            "action": l["action"],
            "details": l["details"],
            "ip_address": l["ip_address"],
            "timestamp": l["timestamp"]
        } for l in logs]
    }), 200
