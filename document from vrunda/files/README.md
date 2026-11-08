# PolyScope – AI-Based Detection of Elusive Polyps in Colonoscopy Images

PolyScope is a complete medical-AI web application designed for early detection, localization, and semantic segmentation of colorectal polyps in colonoscopy images. It integrates deep learning neural networks (CNN & U-Net) and deterministic computer vision algorithms within a multi-portal clinical healthcare workflow.

---

## 🌟 Application Portals

PolyScope provides three role-based, distinct application portals connected to a unified SQLite database:

### 1. 👤 Patient Portal (`/patient_portal.html`)
- **Patient Registration & Login**: Role-based authentication with secure session cookies and CSRF safeguards.
- **Personal Profile**: Update age, gender, contact information, prior endoscopic history, and assign an attending gastroenterologist.
- **Colonoscopy Upload & Scan**: Upload endoscopic frames or select from pre-loaded clinical sample cases.
- **AI Detection & Segmentation Viewer**:
  - Interactive split-slider comparing original endoscopic frame with AI-annotated output.
  - Telemetry: CNN confidence percentage, Paris classification (e.g. Type Is, Type Ip), lesion dimensions (mm), and anatomical quadrant localization.
- **Scan History**: Full searchable archive of all past procedures and findings.
- **Post-Colonoscopy Surveillance Guide**: Personalized screening intervals based on US Multi-Society Task Force (MSTF) guidelines, preparation instructions, and dietary recommendations.

### 2. 🩺 Doctor Portal (`/doctor_portal.html`)
- **Clinical Dashboard**: Real-time caseload telemetry (assigned patients, pending reviews, flagged polyps).
- **Assigned Patient Directory**: Patient cohort with procedure count, last exam date, and risk tier.
- **Diagnostic Workstation**:
  - Inspect patient endoscopy images with CNN probability scores and U-Net segmentation masks.
  - Review lesion area percentage, morphology, and demarcated boundaries.
- **Clinical Notes & Recommendations**:
  - Document endoscopist observations, pit pattern assessment, and optical biopsy findings.
  - Specify pathology and intervention orders (e.g., cold snare polypectomy, EMR).
  - Formally finalize and sign diagnostic reports.
  - One-click print/PDF clinical report letterhead export.

### 3. ⚙️ Admin Portal (`/admin_portal.html`)
- **Governance Dashboard**: Platform-wide telemetry (user distribution, scan volume, Adenoma Detection Rate - ADR).
- **Host Server Health**: Live CPU utilization, RAM usage, storage availability, and database metrics.
- **User Management**:
  - Search, filter, and inspect user accounts.
  - Create new Patient, Doctor, or Admin accounts.
  - Edit user permissions, assign roles, or suspend/activate accounts.
  - Securely delete accounts.
- **Global Scan Monitor**: Real-time stream of all uploaded scans across the platform.
- **AI Model Diagnostics & Live Evaluator**:
  - Status of CNN and U-Net weights vs active Computer Vision feature extractor.
  - **1-Click Live Ground Truth Evaluation**: Computes real mathematical validation metrics (Accuracy, Precision, Recall, Specificity, F1-Score, Dice Coefficient, and IoU) against ground truth masks with Confusion Matrix breakdown.
- **Security Audit Logs**: Track all system events, logins, uploads, and administrative actions with IP addresses and timestamps.

---

## 🧠 AI Architecture & Implementation

### 1. Preprocessing Pipeline (`ai/preprocessor.py`)
- Glare and specular reflection highlight reduction.
- Contrast-Limited Adaptive Histogram Equalization (CLAHE) on the LAB color space to enhance mucosal vascular patterns.
- Bilinear resizing to neural tensor dimensions ($224 \times 224 \times 3$) and float32 normalization ($[0.0, 1.0]$).

### 2. CNN Polyp Detection (`ai/cnn_detector.py`)
- Deep binary Convolutional Neural Network with 3 convolution blocks, Batch Normalization, ReLU activation, MaxPooling, Global Average Pooling, Dropout ($0.4$), and a Sigmoid classification head.

### 3. U-Net Semantic Segmentation (`ai/unet_segmenter.py`)
- Symmetrical 4-level encoder-decoder with skip connections, bottleneck convolution ($512$ filters), bilinear upsampling, and sigmoid mask prediction.
- Trained with combined Binary Cross-Entropy + Dice Loss.

### 4. Active Computer Vision Feature Extractor (`ai/cv_engine.py`)
- When deep learning weights are not yet trained on a new installation, PolyScope automatically activates the deterministic OpenCV mucosal color-opponency and morphological feature extractor.
- Ensures all uploads, detection overlays, and bounding boxes execute reliably without errors.

### 5. Quantitative Model Evaluation (`ai/evaluator.py`)
- Evaluates test image pairs against ground truth binary masks.
- Computes genuine metrics:
  $$\text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN}$$
  $$\text{Precision} = \frac{TP}{TP + FP}$$
  $$\text{Recall} = \frac{TP}{TP + FN}$$
  $$\text{F1-Score} = \frac{2 \times \text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$
  $$\text{Dice} = \frac{2 \times |P \cap G|}{|P| + |G|}$$
  $$\text{IoU} = \frac{|P \cap G|}{|P \cup G|}$$

---

## 🚀 Quick Setup & Run Locally

### 1. Requirements
- Python 3.10+ (Python 3.11 recommended)
- Standard packages in `requirements.txt`

### 2. Installation
```powershell
# Clone or navigate to the project directory
cd "polypop backup"

# Install dependencies
pip install -r requirements.txt

# Start the PolyScope application
python app.py
```

### 3. Access Application
Open your web browser and navigate to:
**<http://127.0.0.1:5000>**

---

## 🔑 Pre-Configured Demo Accounts

For instant evaluation, 1-click login buttons are provided on the Sign-In page (`/login.html`):

| Role | Email | Password | Default Portal |
|---|---|---|---|
| **Patient** | `patient@polyscope.ai` | `patient1234` | `/patient_portal.html` |
| **Doctor** | `doctor@polyscope.ai` | `doctor1234` | `/doctor_portal.html` |
| **Admin** | `admin@polyscope.ai` | `admin1234` | `/admin_portal.html` |

---

## 🔬 Training Deep Learning Models

To train the CNN and U-Net models on the Kvasir-SEG clinical dataset:
1. Download Kvasir-SEG (`images/` and `masks/`) from [Simula Datasets](https://datasets.simula.no/kvasir-seg/).
2. Place the unzipped folders in `Kvasir-seg/images` and `Kvasir-seg/masks`.
3. Run the training script:
```powershell
python train_models.py --epochs 20 --batch-size 8
```
The trained weights are automatically saved to `models/polyp_detector_cnn.keras` and `models/polyp_segmenter_unet.keras`.

---

## 🧪 Running Automated Tests

Run the full automated test suite (including security, authentication, API, and AI pipeline tests):
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

---

## 📜 Ethical & Medical Disclaimer
PolyScope is a research and academic prototype developed to demonstrate artificial intelligence assistance in endoscopic computer vision. It is not an FDA/CE-cleared primary diagnostic device and must not replace professional clinical evaluation or histopathological diagnosis.
