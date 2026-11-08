import os
import sys
import secrets
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, render_template, session, g, redirect, url_for
from werkzeug.exceptions import RequestEntityTooLarge

from config import Config
from database.db import get_db, close_db, init_db
from routes.auth import auth_bp
from routes.patient import patient_bp
from routes.doctor import doctor_bp
from routes.admin import admin_bp
from routes.ai_routes import ai_bp

app_env = os.environ.get("APP_ENV", "development").lower()
secret_key = os.environ.get("SECRET_KEY")
MODEL_PATH = Path(os.environ.get("MODEL_PATH", "models/polyp_segmenter.keras"))

if app_env == "production" and not secret_key:
    raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")

# Global variables for test compatibility
model = None
model_load_attempted = False

def load_model():
    global model, model_load_attempted
    if model is None and MODEL_PATH.is_file() and not model_load_attempted:
        model_load_attempted = True
        try:
            import tensorflow as tf
            model = tf.keras.models.load_model(MODEL_PATH, compile=False)
            print(f"[INFO] Loaded segmentation model from {MODEL_PATH}")
        except Exception as e:
            print(f"[WARN] Failed to load model from {MODEL_PATH}: {e}")
            model = None
    return model

def create_app(config_override=None):
    flask_app = Flask(__name__, template_folder="templates", static_folder="static")
    flask_app.config.from_object(Config)
    if config_override:
        flask_app.config.update(config_override)
    
    if secret_key:
        flask_app.config["SECRET_KEY"] = secret_key
    elif not flask_app.config.get("SECRET_KEY"):
        flask_app.config["SECRET_KEY"] = secrets.token_hex(32)

    flask_app.teardown_appcontext(close_db)

    # Register Blueprints
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(patient_bp)
    flask_app.register_blueprint(doctor_bp)
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(ai_bp)

    @flask_app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=()")
        return response

    @flask_app.errorhandler(RequestEntityTooLarge)
    def request_too_large(_error):
        return jsonify({"error": "Image must be 15 MB or smaller"}), 413

    # Frontend Page Routes
    @flask_app.route("/")
    @flask_app.route("/index.html")
    def landing_page():
        return render_template("index.html")

    @flask_app.route("/login")
    @flask_app.route("/login.html")
    def login_page():
        return render_template("login.html")

    @flask_app.route("/register")
    @flask_app.route("/register.html")
    def register_page():
        return render_template("register.html")

    @flask_app.route("/patient")
    @flask_app.route("/patient_portal.html")
    def patient_page():
        return render_template("patient_portal.html")

    @flask_app.route("/doctor")
    @flask_app.route("/doctor_portal.html")
    def doctor_page():
        return render_template("doctor_portal.html")

    @flask_app.route("/admin")
    @flask_app.route("/admin_portal.html")
    def admin_page():
        return render_template("admin_portal.html")

    @flask_app.route("/dashboard")
    @flask_app.route("/dashboard.html")
    @flask_app.route("/app")
    def dashboard_redirect():
        role = session.get("role", "patient")
        if role == "doctor":
            return redirect("/doctor_portal.html")
        elif role == "admin":
            return redirect("/admin_portal.html")
        return redirect("/patient_portal.html")

    @flask_app.route("/camera")
    def camera_redirect():
        return redirect("/patient_portal.html")

    @flask_app.route("/favicon.svg")
    def favicon():
        return send_from_directory(Path(flask_app.root_path) / "static", "favicon.svg")

    @flask_app.route("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(flask_app.config["UPLOAD_FOLDER"], filename)

    return flask_app

app = create_app()

def init_database():
    database_path = Path(app.config["DATABASE_PATH"])
    init_db(database_path)

init_database()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n=======================================================")
    print(f"  PolyScope AI – Medical Endoscopy Decision Platform   ")
    print(f"  Running locally on http://127.0.0.1:{port}          ")
    print(f"=======================================================\n")
    app.run(host="127.0.0.1", port=port, debug=True)
