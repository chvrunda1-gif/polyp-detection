import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    APP_NAME = "PolyScope AI"
    APP_VERSION = "2.0.0"
    SECRET_KEY = os.environ.get("SECRET_KEY", "polyscope-dev-secret-key-3289047120938")
    
    # Environment
    APP_ENV = os.environ.get("APP_ENV", "development").lower()
    DEBUG = APP_ENV == "development"
    TESTING = False
    
    # Database
    DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", str(BASE_DIR / "instance" / "polyscope.sqlite3")))
    
    # Uploads
    UPLOAD_FOLDER = BASE_DIR / "uploads"
    ORIGINALS_FOLDER = UPLOAD_FOLDER / "originals"
    RESULTS_FOLDER = UPLOAD_FOLDER / "results"
    MASKS_FOLDER = UPLOAD_FOLDER / "masks"
    MAX_CONTENT_LENGTH = 15 * 1024 * 1024  # 15 MB max upload
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "bmp", "webp"}
    
    # AI Models
    MODELS_DIR = BASE_DIR / "models"
    CNN_MODEL_PATH = MODELS_DIR / "polyp_detector_cnn.keras"
    UNET_MODEL_PATH = MODELS_DIR / "polyp_segmenter_unet.keras"
    LEGACY_MODEL_PATH = MODELS_DIR / "polyp_segmenter.keras"
    
    # Sample data
    SAMPLES_DIR = BASE_DIR / "static" / "samples"
    
    # Session & Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = APP_ENV == "production"
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours
