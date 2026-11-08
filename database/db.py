import sqlite3
import json
import secrets
from pathlib import Path
from datetime import datetime
from contextlib import closing
from werkzeug.security import generate_password_hash
from flask import g, current_app

def get_db(db_path=None):
    if "db" not in g:
        path = db_path or current_app.config.get("DATABASE_PATH")
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db(database_path: Path):
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    
    with closing(sqlite3.connect(database_path)) as conn:
        with conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Users table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_code TEXT UNIQUE,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'patient', -- 'patient', 'doctor', 'admin'
                    phone TEXT,
                    age INTEGER,
                    gender TEXT,
                    medical_history TEXT,
                    assigned_doctor_id INTEGER,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    history_json TEXT DEFAULT '[]',
                    FOREIGN KEY (assigned_doctor_id) REFERENCES users (id) ON DELETE SET NULL
                )
            """)
            
            # Patient Clinical Cases
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_number TEXT UNIQUE NOT NULL,
                    patient_id INTEGER NOT NULL,
                    doctor_id INTEGER,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Image uploaded', 
                    -- 'Image uploaded', 'Analysis pending', 'Under doctor review', 'Follow-up required', 'Further investigation recommended', 'Resolved'
                    is_resolved TEXT NOT NULL DEFAULT 'Under review', -- 'Yes', 'No', 'Under review'
                    findings_summary TEXT,
                    doctor_conclusion TEXT,
                    patient_instructions TEXT,
                    follow_up_date TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (patient_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (doctor_id) REFERENCES users (id) ON DELETE SET NULL
                )
            """)
            
            # Case Status Audit History
            conn.execute("""
                CREATE TABLE IF NOT EXISTS case_history_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    updated_by INTEGER,
                    old_status TEXT,
                    new_status TEXT,
                    resolution_status TEXT,
                    notes TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE CASCADE,
                    FOREIGN KEY (updated_by) REFERENCES users (id) ON DELETE SET NULL
                )
            """)
            
            # Scans (Endoscopic Frames & AI / Doctor Analysis)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER,
                    patient_id INTEGER NOT NULL,
                    uploaded_by INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    original_image_path TEXT NOT NULL,
                    result_image_path TEXT,
                    mask_image_path TEXT,
                    cnn_prediction INTEGER DEFAULT 0,
                    cnn_confidence REAL DEFAULT 0.0,
                    unet_segmented INTEGER DEFAULT 0,
                    lesion_area_px REAL DEFAULT 0.0,
                    lesion_area_pct REAL DEFAULT 0.0,
                    estimated_diameter_mm REAL DEFAULT 0.0,
                    paris_classification TEXT,
                    quadrant TEXT,
                    bbox_json TEXT,
                    ai_engine_used TEXT NOT NULL DEFAULT 'CV-Feature-Extractor',
                    doctor_confirmed INTEGER, -- NULL: pending review, 1: confirmed by doctor, 0: rejected by doctor
                    doctor_notes TEXT,
                    recommendations TEXT,
                    is_approved_for_patient INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    reviewed_at TEXT,
                    FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE SET NULL,
                    FOREIGN KEY (patient_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            
            # Official Medical Reports
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_code TEXT UNIQUE NOT NULL,
                    case_id INTEGER,
                    scan_id INTEGER,
                    patient_id INTEGER NOT NULL,
                    doctor_id INTEGER NOT NULL,
                    report_title TEXT NOT NULL,
                    colonoscopy_date TEXT NOT NULL,
                    ai_findings TEXT,
                    doctor_conclusions TEXT NOT NULL,
                    clinical_observations TEXT,
                    recommendations TEXT NOT NULL,
                    follow_up_instructions TEXT,
                    resolution_status TEXT NOT NULL DEFAULT 'Under review',
                    pdf_filename TEXT,
                    is_finalized INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY (case_id) REFERENCES cases (id) ON DELETE SET NULL,
                    FOREIGN KEY (scan_id) REFERENCES scans (id) ON DELETE SET NULL,
                    FOREIGN KEY (patient_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (doctor_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            
            # Activity Audit Logs
            conn.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_email TEXT,
                    user_role TEXT,
                    action TEXT NOT NULL,
                    details TEXT,
                    ip_address TEXT,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
                )
            """)
            
            # Model Evaluation Metrics
            conn.execute("""
                CREATE TABLE IF NOT EXISTS model_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_name TEXT NOT NULL,
                    dataset_name TEXT NOT NULL,
                    accuracy REAL,
                    precision REAL,
                    recall REAL,
                    f1_score REAL,
                    dice REAL,
                    iou REAL,
                    evaluated_at TEXT NOT NULL,
                    details_json TEXT
                )
            """)
            
            run_migrations(conn)
            seed_initial_accounts(conn, database_path)

def run_migrations(conn):
    """Safely apply column migrations to existing SQLite tables."""
    # Check scans table
    cursor = conn.execute("PRAGMA table_info(scans)")
    scan_cols = {row[1] for row in cursor.fetchall()}
    if scan_cols:
        expected_scan_cols = {
            "case_id": "INTEGER",
            "cnn_prediction": "INTEGER DEFAULT 0",
            "cnn_confidence": "REAL DEFAULT 0.0",
            "unet_segmented": "INTEGER DEFAULT 0",
            "lesion_area_px": "REAL DEFAULT 0.0",
            "lesion_area_pct": "REAL DEFAULT 0.0",
            "estimated_diameter_mm": "REAL DEFAULT 0.0",
            "paris_classification": "TEXT",
            "quadrant": "TEXT",
            "bbox_json": "TEXT",
            "ai_engine_used": "TEXT DEFAULT 'CV-Feature-Extractor'",
            "doctor_confirmed": "INTEGER",
            "doctor_notes": "TEXT",
            "recommendations": "TEXT",
            "is_approved_for_patient": "INTEGER DEFAULT 0",
            "reviewed_at": "TEXT"
        }
        for col, col_type in expected_scan_cols.items():
            if col not in scan_cols:
                try:
                    conn.execute(f"ALTER TABLE scans ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

    # Check users table
    cursor = conn.execute("PRAGMA table_info(users)")
    user_cols = {row[1] for row in cursor.fetchall()}
    if user_cols and "patient_code" not in user_cols:
        try:
            conn.execute("ALTER TABLE users ADD COLUMN patient_code TEXT")
        except Exception:
            pass

    # Check reports table
    cursor = conn.execute("PRAGMA table_info(reports)")
    rep_cols = {row[1] for row in cursor.fetchall()}
    if rep_cols:
        expected_rep_cols = {
            "report_code": "TEXT",
            "case_id": "INTEGER",
            "scan_id": "INTEGER",
            "report_title": "TEXT",
            "colonoscopy_date": "TEXT",
            "ai_findings": "TEXT",
            "doctor_conclusions": "TEXT",
            "clinical_observations": "TEXT",
            "recommendations": "TEXT",
            "follow_up_instructions": "TEXT",
            "resolution_status": "TEXT DEFAULT 'Under review'",
            "pdf_filename": "TEXT",
            "is_finalized": "INTEGER DEFAULT 1"
        }
        for col, col_type in expected_rep_cols.items():
            if col not in rep_cols:
                try:
                    conn.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_type}")
                except Exception:
                    pass



def seed_initial_accounts(conn, database_path):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Admin Demo
    admin = conn.execute("SELECT id FROM users WHERE email = 'admin@polyscope.ai'").fetchone()
    if not admin:
        conn.execute("""
            INSERT INTO users (patient_code, email, name, password_hash, role, phone, medical_history, created_at, status)
            VALUES ('ADM-001', 'admin@polyscope.ai', 'Dr. Sarah Lin (Chief Clinical Administrator)', ?, 'admin', '+1-555-0199', 'System Administrator & Governance Lead', ?, 'active')
        """, (generate_password_hash('admin1234'), now))
        admin = conn.execute("SELECT id FROM users WHERE email = 'admin@polyscope.ai'").fetchone()
    
    # 2. Doctor Demo
    doctor = conn.execute("SELECT id FROM users WHERE email = 'doctor@polyscope.ai'").fetchone()
    if not doctor:
        conn.execute("""
            INSERT INTO users (patient_code, email, name, password_hash, role, phone, medical_history, created_at, status)
            VALUES ('DOC-001', 'doctor@polyscope.ai', 'Dr. Rajesh Sharma, MD', ?, 'doctor', '+1-555-0145', 'Senior Consultant Gastroenterologist & Endoscopist', ?, 'active')
        """, (generate_password_hash('doctor1234'), now))
        doctor = conn.execute("SELECT id FROM users WHERE email = 'doctor@polyscope.ai'").fetchone()
        
    doc_id = doctor[0] if doctor else None

    # 3. Patient Demo
    patient = conn.execute("SELECT id FROM users WHERE email = 'patient@polyscope.ai'").fetchone()
    if not patient:
        conn.execute("""
            INSERT INTO users (patient_code, email, name, password_hash, role, phone, age, gender, medical_history, assigned_doctor_id, created_at, status)
            VALUES ('POL-PT-101', 'patient@polyscope.ai', 'John Doe (DEMO DATA)', ?, 'patient', '+1-555-0177', 54, 'Male', 'Prior screening 3 years ago. Routine surveillance for abdominal cramping.', ?, ?, 'active')
        """, (generate_password_hash('patient1234'), doc_id, now))
        patient = conn.execute("SELECT id FROM users WHERE email = 'patient@polyscope.ai'").fetchone()
        
    pat_id = patient[0] if patient else None

    # Seed Sample Case for Patient Demo
    if pat_id and doc_id:
        existing_case = conn.execute("SELECT id FROM cases WHERE patient_id = ?", (pat_id,)).fetchone()
        if not existing_case:
            cursor = conn.execute("""
                INSERT INTO cases (case_number, patient_id, doctor_id, title, status, is_resolved, findings_summary, doctor_conclusion, patient_instructions, follow_up_date, created_at, updated_at)
                VALUES ('CAS-2026-001', ?, ?, 'Surveillance Colonoscopy Examination', 'Follow-up required', 'No', 
                        'A solitary 8.8 mm sessile adenoma was identified in the ascending colon and successfully demarcated.',
                        'Endoscopic optical biopsy consistent with tubular adenoma (Paris Type Is). Cold snare polypectomy performed with clear mucosal margins.',
                        'Avoid strenuous physical exertion for 48 hours. Maintain high-fiber hydration. Schedule repeat surveillance colonoscopy in 12 months.',
                        '2027-11-08', ?, ?)
            """, (pat_id, doc_id, now, now))
            case_id = cursor.lastrowid
            
            # Seed Scan
            scan_cursor = conn.execute("""
                INSERT INTO scans (case_id, patient_id, uploaded_by, filename, original_image_path, result_image_path, mask_image_path,
                                  cnn_prediction, cnn_confidence, unet_segmented, lesion_area_px, lesion_area_pct, estimated_diameter_mm,
                                  paris_classification, quadrant, bbox_json, ai_engine_used, doctor_confirmed, doctor_notes, recommendations, is_approved_for_patient, created_at, reviewed_at)
                VALUES (?, ?, ?, 'ascending_colon_frame_01.jpg', 'static/samples/sample_polyp_1.jpg', 'static/samples/sample_polyp_1.jpg', 'static/samples/sample_polyp_1_mask.png',
                        1, 96.4, 1, 8562.0, 2.79, 8.8, 'Type Is (Sessile)', 'Upper Right Field', '[302, 183, 118, 95]', 'TensorFlow CNN & U-Net Deep Architecture', 
                        1, 'Confirmed solitary sessile adenoma. Complete resection executed.', 'Repeat colonoscopy in 12 months. Specimen submitted to pathology.', 1, ?, ?)
            """, (case_id, pat_id, pat_id, now, now))
            scan_id = scan_cursor.lastrowid
            
            # Seed Official Approved Report
            conn.execute("""
                INSERT INTO reports (report_code, case_id, scan_id, patient_id, doctor_id, report_title, colonoscopy_date, ai_findings, doctor_conclusions, clinical_observations, recommendations, follow_up_instructions, resolution_status, is_finalized, created_at, updated_at)
                VALUES ('REP-2026-001', ?, ?, ?, ?, 'Official Endoscopy Diagnostic & Polypectomy Summary', '2026-11-08',
                        'CNN Prediction: Polyp Positive (96.4% confidence). U-Net localized Paris Type Is lesion in upper right field.',
                        'Confirmed solitary 8.8 mm sessile adenomatous polyp. Clean cold-snare margins achieved without immediate bleeding or perforation.',
                        'Mucosa glistened with clear vascular boundaries. Transverse and descending colon showed normal haustral fold architecture.',
                        'Routine surveillance colonoscopy interval adjusted to 12 months in accordance with US MSTF post-polypectomy guidelines.',
                        'Follow dietary guidance, maintain hydration, and consult Dr. Rajesh Sharma if post-procedure symptoms arise.',
                        'No', 1, ?, ?)
            """, (case_id, scan_id, pat_id, doc_id, now, now))

def log_activity(user_id, email, role, action, details="", ip=None):
    try:
        db = get_db()
        db.execute("""
            INSERT INTO activity_logs (user_id, user_email, user_role, action, details, ip_address, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, email, role, action, details, ip or "127.0.0.1", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    except Exception as e:
        print(f"[WARN] Failed to log activity: {e}")
