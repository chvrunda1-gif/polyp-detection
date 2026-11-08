import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, session, g
from werkzeug.security import check_password_hash, generate_password_hash
from database.db import get_db, log_activity

auth_bp = Blueprint("auth", __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session and "email" not in session:
            return jsonify({"error": "Authentication required. Please log in."}), 401
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "role" not in session:
                return jsonify({"error": "Authentication required."}), 401
            if session["role"] not in allowed_roles:
                return jsonify({
                    "error": f"Access denied. Requires one of the following roles: {', '.join(allowed_roles)}"
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def csrf_protect(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method in ["POST", "PUT", "DELETE"]:
            token = request.headers.get("X-CSRF-Token", "")
            expected = session.get("csrf_token", "")
            if expected and token != expected:
                return jsonify({"error": "Invalid or missing CSRF token"}), 403
        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/api/auth/demo-login/<role>", methods=["POST", "GET"])
def demo_login(role):
    """
    Instant 1-click Demo Login for Patient, Doctor, and Admin.
    Zero-latency portal switching without manual credential entry.
    """
    clean_role = str(role).strip().lower()
    email_map = {
        "patient": "patient@polyscope.ai",
        "doctor": "doctor@polyscope.ai",
        "admin": "admin@polyscope.ai"
    }
    target_email = email_map.get(clean_role)
    if not target_email:
        return jsonify({"error": "Invalid demo role specified"}), 400

    db = get_db()
    user = db.execute("SELECT id, patient_code, email, name, role, status FROM users WHERE email = ?", (target_email,)).fetchone()
    if not user:
        return jsonify({"error": f"Demo account for {clean_role} not found"}), 404

    session.clear()
    session["user_id"] = user["id"]
    session["patient_code"] = user["patient_code"] or f"POL-{user['id']}"
    session["email"] = user["email"]
    session["name"] = user["name"]
    session["role"] = user["role"]
    session["csrf_token"] = secrets.token_urlsafe(32)

    portal_urls = {
        "patient": "/patient_portal.html",
        "doctor": "/doctor_portal.html",
        "admin": "/admin_portal.html"
    }

    log_activity(user["id"], user["email"], user["role"], "DEMO_LOGIN", f"1-Click Demo Login as {clean_role}", request.remote_addr)

    return jsonify({
        "message": f"Demo {clean_role} login successful",
        "user": {
            "id": user["id"],
            "patient_code": session["patient_code"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        },
        "portal_url": portal_urls[user["role"]],
        "csrf_token": session["csrf_token"]
    }), 200

@auth_bp.route("/api/auth/login", methods=["POST"])
@auth_bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    identifier = str(data.get("email") or data.get("username") or data.get("name") or data.get("identifier") or "").strip()
    password = str(data.get("password", "")).strip()
    selected_role = str(data.get("role", "")).strip().lower()

    if not identifier or not password:
        return jsonify({"error": "Username/Email and password are required"}), 400

    clean_id = identifier.lower()
    db = get_db()

    role_email_map = {
        "doctor": "doctor@polyscope.ai",
        "patient": "patient@polyscope.ai",
        "admin": "admin@polyscope.ai"
    }

    # Query all candidate users matching identifier by exact match, prefix, username, or substring
    query = """
        SELECT id, patient_code, email, name, password_hash, role, status,
               CASE 
                   WHEN LOWER(email) = ? OR LOWER(patient_code) = ? THEN 1
                   WHEN LOWER(name) = ? THEN 2
                   WHEN LOWER(email) LIKE ? || '@%' THEN 3
                   WHEN LOWER(name) LIKE ? || ' %' OR LOWER(name) LIKE '% ' || ? THEN 4
                   WHEN LOWER(name) LIKE ? OR LOWER(email) LIKE ? THEN 5
                   ELSE 6
               END AS match_score
        FROM users
        WHERE LOWER(email) = ? 
           OR LOWER(name) = ? 
           OR LOWER(patient_code) = ?
           OR LOWER(email) LIKE ? || '@%'
           OR LOWER(name) LIKE ?
           OR LOWER(email) LIKE ?
    """
    params = [
        # for match_score:
        clean_id, clean_id,
        clean_id,
        clean_id,
        clean_id, clean_id,
        f"%{clean_id}%", f"%{clean_id}%",
        # for WHERE:
        clean_id,
        clean_id,
        clean_id,
        clean_id,
        f"%{clean_id}%",
        f"%{clean_id}%"
    ]

    if clean_id in role_email_map:
        query += " OR LOWER(email) = ?"
        params.append(role_email_map[clean_id])

    if selected_role in ("patient", "doctor", "admin"):
        query += " ORDER BY match_score ASC, CASE WHEN LOWER(role) = ? THEN 0 ELSE 1 END, id ASC"
        params.append(selected_role)
    else:
        query += " ORDER BY match_score ASC, id ASC"

    candidates = db.execute(query, tuple(params)).fetchall()

    if not candidates:
        return jsonify({"error": "Invalid username/email or password"}), 401

    authenticated_user = None
    for candidate in candidates:
        if candidate["status"] != "active":
            continue
        valid = check_password_hash(candidate["password_hash"], password)
        if not valid:
            import hashlib
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            if secrets.compare_digest(candidate["password_hash"], legacy_hash):
                valid = True
                db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), candidate["id"]))
                db.commit()

        if valid:
            authenticated_user = candidate
            break

    if not authenticated_user:
        return jsonify({"error": "Invalid username/email or password"}), 401

    user = authenticated_user

    session.clear()
    session["user_id"] = user["id"]
    session["patient_code"] = user["patient_code"] or f"POL-{user['id']}"
    session["email"] = user["email"]
    session["name"] = user["name"]
    session["role"] = user["role"]
    session["csrf_token"] = secrets.token_urlsafe(32)

    portal_urls = {
        "patient": "/patient_portal.html",
        "doctor": "/doctor_portal.html",
        "admin": "/admin_portal.html"
    }

    log_activity(user["id"], user["email"], user["role"], "USER_LOGIN", f"Standard Login via '{identifier}'", request.remote_addr)

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "patient_code": session["patient_code"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        },
        "portal_url": portal_urls.get(user["role"], "/patient_portal.html"),
        "csrf_token": session["csrf_token"]
    }), 200


@auth_bp.route("/api/auth/register", methods=["POST"])
@auth_bp.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    age = data.get("age")
    gender = str(data.get("gender", "Other")).strip()
    phone = str(data.get("phone", "")).strip()
    role = "patient" # Public registration is always patient for safety

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400
    if len(name) > 120 or len(email) > 254 or "@" not in email:
        return jsonify({"error": "Invalid name or email format"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long"}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "An account with this email already exists"}), 409

    from datetime import datetime
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    hashed_pw = generate_password_hash(password)
    patient_code = f"POL-PT-{secrets.token_hex(3).upper()}"

    # Find a default attending doctor
    doc = db.execute("SELECT id FROM users WHERE role = 'doctor' LIMIT 1").fetchone()
    doc_id = doc["id"] if doc else 2

    cursor = db.execute("""
        INSERT INTO users (patient_code, email, name, password_hash, role, phone, age, gender, assigned_doctor_id, created_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
    """, (patient_code, email, name, hashed_pw, role, phone, age, gender, doc_id, now))
    user_id = cursor.lastrowid

    # Create baseline case for newly registered patient
    case_num = f"CASE-{secrets.token_hex(3).upper()}"
    db.execute("""
        INSERT INTO cases (case_number, patient_id, doctor_id, title, status, is_resolved, created_at, updated_at)
        VALUES (?, ?, ?, 'Initial Colonoscopy Evaluation', 'Image uploaded', 'Under review', ?, ?)
    """, (case_num, user_id, doc_id, now, now))
    db.commit()

    log_activity(user_id, email, role, "USER_REGISTER", f"Registered new patient {email}", request.remote_addr)

    return jsonify({
        "message": "Registration successful",
        "user": {"id": user_id, "patient_code": patient_code, "name": name, "email": email, "role": role}
    }), 201

@auth_bp.route("/api/auth/me", methods=["GET"])
@auth_bp.route("/api/me", methods=["GET"])
@login_required
def me():
    # Fast in-memory session return if populated
    user_id = session.get("user_id")
    email = session.get("email")
    role = session.get("role")
    name = session.get("name")
    code = session.get("patient_code")

    if user_id and email and role:
        return jsonify({
            "id": user_id,
            "patient_code": code or f"POL-{user_id}",
            "name": name,
            "email": email,
            "role": role,
            "csrf_token": session.get("csrf_token")
        }), 200

    db = get_db()
    user = db.execute("SELECT id, patient_code, email, name, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        session.clear()
        return jsonify({"error": "Session expired"}), 401

    session["name"] = user["name"]
    session["role"] = user["role"]
    session["patient_code"] = user["patient_code"] or f"POL-{user['id']}"

    return jsonify({
        "id": user["id"],
        "patient_code": session["patient_code"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "csrf_token": session.get("csrf_token")
    }), 200

@auth_bp.route("/api/auth/logout", methods=["POST"])
@auth_bp.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"message": "Successfully signed out"}), 200
