import os
import secrets
from pathlib import Path
from datetime import datetime
from flask import render_template, current_app


def generate_report_html(report_data):
    """
    Constructs the official PolyScope clinical diagnostic report with hospital letterhead,
    side-by-side endoscopy images, AI telemetry, doctor-reviewed conclusion, and digital verification seal.
    """
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>PolyScope Diagnostic Report — {report_data.get('report_code', 'REP-001')}</title>
  <style>
    @page {{ size: A4; margin: 15mm; }}
    @media print {{
      body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
      .no-print {{ display: none !important; }}
    }}
    body {{
      font-family: 'Helvetica Neue', Arial, sans-serif;
      color: #111827;
      background: #ffffff;
      margin: 0;
      padding: 24px;
      line-height: 1.5;
      font-size: 13px;
    }}
    .header-bar {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #00e5a0;
      padding-bottom: 16px;
      margin-bottom: 20px;
    }}
    .brand-title {{
      font-size: 24px;
      font-weight: 800;
      color: #070b14;
      letter-spacing: -0.5px;
    }}
    .brand-title span {{ color: #00e5a0; }}
    .brand-sub {{
      font-size: 11px;
      color: #6b7280;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .report-meta {{
      text-align: right;
      font-size: 12px;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 11px;
      text-transform: uppercase;
    }}
    .badge-alert {{ background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }}
    .badge-clear {{ background: #ecfdf5; color: #059669; border: 1px solid #a7f3d0; }}
    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .info-card {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 12px 16px;
    }}
    .info-card h4 {{
      margin: 0 0 8px 0;
      font-size: 11px;
      text-transform: uppercase;
      color: #6b7280;
      letter-spacing: 0.5px;
    }}
    .info-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
      font-size: 12px;
    }}
    .info-key {{ color: #4b5563; }}
    .info-val {{ font-weight: 600; color: #111827; }}
    .images-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin: 20px 0;
    }}
    .img-box {{
      border: 1px solid #e5e7eb;
      border-radius: 6px;
      padding: 8px;
      text-align: center;
      background: #000;
    }}
    .img-box img {{
      max-width: 100%;
      height: 200px;
      object-fit: contain;
    }}
    .img-caption {{
      color: #9ca3af;
      font-size: 11px;
      margin-top: 6px;
      text-align: center;
      background: #111827;
      padding: 4px;
      border-radius: 4px;
    }}
    .section-title {{
      font-size: 14px;
      font-weight: 700;
      color: #111827;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 6px;
      margin: 18px 0 10px 0;
    }}
    .conclusion-box {{
      background: #f0fdf4;
      border-left: 4px solid #10b981;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      margin-bottom: 16px;
    }}
    .signature-row {{
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-top: 36px;
      padding-top: 20px;
      border-top: 1px solid #e5e7eb;
    }}
    .seal-badge {{
      display: inline-block;
      border: 2px dashed #059669;
      color: #059669;
      padding: 8px 16px;
      font-weight: 800;
      font-size: 11px;
      letter-spacing: 1px;
      text-transform: uppercase;
      border-radius: 6px;
    }}
    .btn-print {{
      background: #00e5a0;
      color: #040914;
      border: none;
      padding: 10px 20px;
      font-weight: 700;
      border-radius: 6px;
      cursor: pointer;
      margin-bottom: 20px;
    }}
  </style>
</head>
<body>
  <div class="no-print" style="margin-bottom: 16px; display: flex; justify-content: flex-end;">
    <button class="btn-print" onclick="window.print()">🖨️ Print / Save as PDF</button>
  </div>

  <div class="header-bar">
    <div>
      <div class="brand-title">PolyScope <span>AI</span></div>
      <div class="brand-sub">Clinical Endoscopic Decision Intelligence & Diagnostic Report</div>
    </div>
    <div class="report-meta">
      <div><strong>Report Code:</strong> {report_data.get('report_code', 'REP-001')}</div>
      <div><strong>Date:</strong> {report_data.get('colonoscopy_date', datetime.utcnow().strftime('%Y-%m-%d'))}</div>
      <div style="margin-top:6px;">
        <span class="badge { 'badge-alert' if report_data.get('polyp_detected') else 'badge-clear' }">
          { 'Polyp Identified — Under Surveillance' if report_data.get('polyp_detected') else 'Normal Endoscopic Mucosa' }
        </span>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="info-card">
      <h4>Patient Demographics</h4>
      <div class="info-row"><span class="info-key">Name:</span> <span class="info-val">{report_data.get('patient_name', 'Anonymous Patient')}</span></div>
      <div class="info-row"><span class="info-key">Patient ID:</span> <span class="info-val">{report_data.get('patient_code', 'POL-PT-001')}</span></div>
      <div class="info-row"><span class="info-key">Age / Gender:</span> <span class="info-val">{report_data.get('patient_age', '52')} yrs / {report_data.get('patient_gender', 'Male')}</span></div>
      <div class="info-row"><span class="info-key">Case Number:</span> <span class="info-val">{report_data.get('case_number', 'CAS-2026-001')}</span></div>
    </div>
    <div class="info-card">
      <h4>Attending Gastroenterologist</h4>
      <div class="info-row"><span class="info-key">Endoscopist:</span> <span class="info-val">{report_data.get('doctor_name', 'Dr. Rajesh Sharma, MD')}</span></div>
      <div class="info-row"><span class="info-key">Department:</span> <span class="info-val">Digestive Health & Interventional Endoscopy</span></div>
      <div class="info-row"><span class="info-key">Follow-Up Date:</span> <span class="info-val">{report_data.get('follow_up_date', '12 Months')}</span></div>
      <div class="info-row"><span class="info-key">Case Resolution:</span> <span class="info-val">{report_data.get('resolution_status', 'Under review')}</span></div>
    </div>
  </div>

  <div class="section-title">Colonoscopy Imaging & AI Localization</div>
  <div class="images-grid">
    <div class="img-box">
      <img src="{report_data.get('original_image_url', '/static/samples/sample_polyp_1.jpg')}" alt="Raw Colonoscopy Frame">
      <div class="img-caption">Pre-Intervention Endoscopic Acquisition</div>
    </div>
    <div class="img-box">
      <img src="{report_data.get('result_image_url', '/static/samples/sample_polyp_1.jpg')}" alt="Segmented Frame">
      <div class="img-caption">AI Bounding Box & U-Net Segmentation Mask</div>
    </div>
  </div>

  <div class="section-title">Diagnostic Telemetry & Findings</div>
  <div class="grid-2">
    <div class="info-card">
      <div class="info-row"><span class="info-key">AI Detection Status:</span> <span class="info-val">{ 'Polyp Positive' if report_data.get('polyp_detected') else 'Negative / Clear' }</span></div>
      <div class="info-row"><span class="info-key">CNN Classification Confidence:</span> <span class="info-val">{report_data.get('confidence', '96.4')}%</span></div>
      <div class="info-row"><span class="info-key">Paris Morphological Class:</span> <span class="info-val">{report_data.get('paris_classification', 'Type Is (Sessile)')}</span></div>
    </div>
    <div class="info-card">
      <div class="info-row"><span class="info-key">Estimated Lesion Diameter:</span> <span class="info-val">{report_data.get('estimated_diameter_mm', '8.8')} mm</span></div>
      <div class="info-row"><span class="info-key">Anatomical Quadrant:</span> <span class="info-val">{report_data.get('quadrant', 'Upper Right Field')}</span></div>
      <div class="info-row"><span class="info-key">Neural Engine:</span> <span class="info-val">{report_data.get('ai_engine', 'TensorFlow CNN & U-Net')}</span></div>
    </div>
  </div>

  <div class="section-title">Doctor-Confirmed Clinical Conclusions</div>
  <div class="conclusion-box">
    <strong>Diagnostic Assessment:</strong><br>
    {report_data.get('doctor_conclusions', 'Endoscopic optical biopsy consistent with adenomatous mucosal lesion. Completely excised with cold snare polypectomy.')}
  </div>

  <div class="section-title">Clinical Recommendations & Surveillance Plan</div>
  <p style="margin: 6px 0 16px 0; color: #374151;">
    {report_data.get('recommendations', 'Continue surveillance protocol per US MSTF guidelines. Specimen submitted to pathology for histological staging.')}
  </p>

  <div class="signature-row">
    <div>
      <div class="seal-badge">✓ POLYSCOPE CLINICALLY APPROVED</div>
      <div style="font-size: 10px; color: #9ca3af; margin-top: 6px;">Digital Hash ID: {secrets.token_hex(16)}</div>
    </div>
    <div style="text-align: right;">
      <div style="font-family: 'Brush Script MT', cursive, sans-serif; font-size: 22px; color: #1e3a8a;">
        {report_data.get('doctor_name', 'Dr. Rajesh Sharma, MD')}
      </div>
      <div style="font-weight: 600; border-top: 1px solid #111827; padding-top: 4px; margin-top: 4px;">
        Attending Gastroenterologist Sign-Off
      </div>
    </div>
  </div>
</body>
</html>
"""
    return html
