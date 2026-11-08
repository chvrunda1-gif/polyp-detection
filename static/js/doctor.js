// PolyScope Doctor Clinical Workstation JavaScript

let currentDoctor = null;
let viewerInstance = null;
let allPatients = [];
let allReports = [];
let selectedSourceMode = 'sample';
let activeSampleId = 'sample_polyp_1';
let uploadedFile = null;
let currentScanId = null;
let activeCaseId = null;
let activePatientId = null;
let doctorConfirmedPolyp = true;
let modalPatientId = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentDoctor = await Auth.checkAuth();
  if (!currentDoctor || (currentDoctor.role !== 'doctor' && currentDoctor.role !== 'admin')) {
    window.location.href = '/login.html';
    return;
  }

  // Set user badge
  const docName = document.getElementById('docNameDisplay');
  const docEmail = document.getElementById('docEmailDisplay');
  const docAvatar = document.getElementById('docAvatarLetter');

  if (docName) docName.textContent = currentDoctor.name || 'Dr. Attending';
  if (docEmail) docEmail.textContent = currentDoctor.email || 'Doctor';
  if (docAvatar) docAvatar.textContent = (currentDoctor.name || 'D').charAt(0).toUpperCase();

  initNavigation();
  initDropzone();
  initDedicatedDropzone();
  initSplitViewer();

  // Load initial data
  await Promise.all([
    loadDoctorDashboard(),
    loadPatients(),
    loadReports()
  ]);
});

function initNavigation() {
  const links = document.querySelectorAll('.nav-link[data-tab]');
  links.forEach(link => {
    link.addEventListener('click', () => {
      const tabId = link.getAttribute('data-tab');
      switchToTab(tabId);
    });
  });
}

function switchToTab(tabId) {
  document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
  const activeLink = document.querySelector(`.nav-link[data-tab="${tabId}"]`);
  if (activeLink) activeLink.classList.add('active');

  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
  const targetTab = document.getElementById(tabId);
  if (targetTab) targetTab.classList.add('active');

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function initSplitViewer() {
  viewerInstance = new PolyScopeViewer('doctorSplitViewer');
}

function initDropzone() {
  const dropzone = document.getElementById('doctorDropzone');
  const fileInput = document.getElementById('doctorFileInput');
  if (!dropzone || !fileInput) return;

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUploadedFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) {
      handleUploadedFile(fileInput.files[0]);
    }
  });
}

let dedicatedUploadedFile = null;

function initDedicatedDropzone() {
  const dropzone = document.getElementById('doctorDedicatedDropzone');
  const fileInput = document.getElementById('doctorDedicatedFileInput');
  if (!dropzone || !fileInput) return;

  dropzone.addEventListener('click', () => fileInput.click());

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
  });

  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setDedicatedUploadedFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) {
      setDedicatedUploadedFile(fileInput.files[0]);
    }
  });
}

function setDedicatedUploadedFile(file) {
  dedicatedUploadedFile = file;
  uploadedFile = file;
  const label = document.getElementById('dedicatedUploadFileName');
  const previewBox = document.getElementById('dedicatedUploadPreviewBox');
  const previewImg = document.getElementById('dedicatedUploadPreviewImg');

  if (label) label.textContent = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

  const reader = new FileReader();
  reader.onload = (e) => {
    if (previewImg) previewImg.src = e.target.result;
    if (previewBox) previewBox.style.display = 'block';
  };
  reader.readAsDataURL(file);
}

async function handleDoctorDirectUpload(e) {
  if (e) e.preventDefault();
  const patientId = document.getElementById('uploadSelectPatient').value;
  if (!patientId) {
    showToast('Please select an assigned patient', 'error');
    return;
  }
  if (!dedicatedUploadedFile) {
    showToast('Please choose or drag a colonoscopy image file', 'error');
    return;
  }

  const formData = new FormData();
  formData.append('patient_id', patientId);
  formData.append('case_title', document.getElementById('uploadCaseTitle').value.trim() || 'Colonoscopy Procedure Frame');
  formData.append('colonic_location', document.getElementById('uploadColonicLocation').value);
  formData.append('image', dedicatedUploadedFile);

  const btn = document.getElementById('btnUploadOnly');
  btn.disabled = true;
  btn.textContent = 'Saving to Patient Chart...';

  try {
    const res = await fetch('/api/doctor/upload', {
      method: 'POST',
      headers: {
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to upload image');

    showToast(data.message || 'Colonoscopy image uploaded successfully', 'success');
    await Promise.all([loadDoctorDashboard(), loadPatients()]);
    btn.disabled = false;
    btn.textContent = '💾 Save Image to Patient Record';
  } catch (err) {
    showToast(err.message, 'error');
    btn.disabled = false;
    btn.textContent = '💾 Save Image to Patient Record';
  }
}

async function uploadAndLaunchAiDetection() {
  const patientId = document.getElementById('uploadSelectPatient').value;
  if (!patientId) {
    showToast('Please select an assigned patient first', 'error');
    return;
  }
  if (!dedicatedUploadedFile) {
    showToast('Please choose or drag a colonoscopy image file first', 'error');
    return;
  }

  // Set patient in AI Detection tab
  activePatientId = patientId;
  const aiSelect = document.getElementById('aiSelectPatient');
  if (aiSelect) aiSelect.value = patientId;

  // Set mode to upload in AI detection tab
  setImageSourceMode('upload');
  handleUploadedFile(dedicatedUploadedFile);

  // Switch tab and run detection
  switchToTab('aiDetectionTab');
  showToast('Image staged into AI Detection Centre. Running analysis...', 'info');
  setTimeout(() => {
    triggerDoctorDetection();
  }, 400);
}

function setImageSourceMode(mode) {
  selectedSourceMode = mode;
  const pillSample = document.getElementById('srcPillSample');
  const pillUpload = document.getElementById('srcPillUpload');
  const sampleContainer = document.getElementById('sourceSampleContainer');
  const uploadContainer = document.getElementById('sourceUploadContainer');

  if (mode === 'sample') {
    pillSample.classList.add('active');
    pillUpload.classList.remove('active');
    sampleContainer.style.display = 'block';
    uploadContainer.style.display = 'none';
  } else {
    pillUpload.classList.add('active');
    pillSample.classList.remove('active');
    sampleContainer.style.display = 'none';
    uploadContainer.style.display = 'block';
  }
}

function selectSampleImage(sampleId, title) {
  activeSampleId = sampleId;
  const cards = document.querySelectorAll('#doctorSamplesRow .sample-card-btn');
  cards.forEach(c => c.style.borderColor = 'var(--border)');

  // Highlight selected card
  const clicked = event ? event.currentTarget : null;
  if (clicked) clicked.style.borderColor = 'var(--accent)';

  showToast(`Selected reference sample: ${title}`, 'info');
}

function handleUploadedFile(file) {
  uploadedFile = file;
  const label = document.getElementById('docUploadLabel');
  if (label) {
    label.innerHTML = `Selected: <span style="color:var(--accent);">${file.name}</span> (${(file.size / 1024).toFixed(1)} KB)`;
  }
  showToast(`Loaded image: ${file.name}`, 'info');
}

// ── DASHBOARD LOADER ──────────────────────────────────────────────────────────

async function loadDoctorDashboard() {
  try {
    const res = await fetch('/api/doctor/dashboard');
    if (!res.ok) return;
    const data = await res.json();
    const stats = data.stats || {};

    document.getElementById('docAssignedCount').textContent = stats.total_patients || 0;
    document.getElementById('docPendingCount').textContent = stats.pending_analyses || 0;
    document.getElementById('docFollowupCount').textContent = stats.followup_cases || 0;
    document.getElementById('docResolvedCount').textContent = stats.resolved_cases || 0;

    const tbody = document.getElementById('recentCasesBody');
    if (!tbody) return;

    const cases = data.recent_cases || [];
    if (!cases.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:28px;color:var(--muted);">No cases logged yet in database.</td></tr>`;
      return;
    }

    tbody.innerHTML = cases.map(c => `
      <tr>
        <td><strong style="color:var(--accent);">${c.case_number}</strong></td>
        <td>
          <strong>${c.patient_name}</strong><br>
          <small style="color:var(--muted);">${c.patient_code}</small>
        </td>
        <td>${c.title}</td>
        <td>
          <span class="badge ${getStatusBadgeClass(c.status)}">${c.status}</span>
        </td>
        <td>
          <span class="badge ${c.is_resolved === 'Yes' ? 'badge-green' : 'badge-warning'}">
            ${c.is_resolved === 'Yes' ? 'Resolved' : (c.is_resolved || 'Under Review')}
          </span>
        </td>
        <td>${c.updated_at || 'Recent'}</td>
        <td>
          <button class="btn btn-primary" style="padding:6px 12px;font-size:0.75rem;" onclick="launchAiForPatientCase(${c.patient_id || 1}, ${c.id})">
            Open AI Workspace
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.warn("Failed to load doctor dashboard:", err);
  }
}

function getStatusBadgeClass(status) {
  if (!status) return 'badge-cyan';
  const s = status.toLowerCase();
  if (s.includes('resolved')) return 'badge-green';
  if (s.includes('follow-up') || s.includes('further')) return 'badge-red';
  if (s.includes('under') || s.includes('review')) return 'badge-warning';
  return 'badge-cyan';
}

// ── PATIENTS DIRECTORY ────────────────────────────────────────────────────────

async function loadPatients() {
  try {
    const res = await fetch('/api/doctor/patients');
    if (!res.ok) return;
    const data = await res.json();
    allPatients = data.patients || [];

    // Populate AI Detection Patient Dropdown
    const select = document.getElementById('aiSelectPatient');
    const uploadSelect = document.getElementById('uploadSelectPatient');
    const patientOptions = `<option value="">-- Choose Assigned Patient --</option>` +
      allPatients.map(p => `
        <option value="${p.id}">${p.patient_code} — ${p.name} (${p.email})</option>
      `).join('');

    if (select) {
      select.innerHTML = patientOptions;
      if (allPatients.length > 0) {
        select.value = allPatients[0].id;
        activePatientId = allPatients[0].id;
      }
    }
    if (uploadSelect) {
      uploadSelect.innerHTML = patientOptions;
      if (allPatients.length > 0) {
        uploadSelect.value = allPatients[0].id;
      }
    }

    renderPatientsTable(allPatients);
  } catch (err) {
    console.warn("Failed to load patients:", err);
  }
}

function renderPatientsTable(patients) {
  const tbody = document.getElementById('patientsDirectoryBody');
  if (!tbody) return;

  if (!patients.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:28px;color:var(--muted);">No matching patients found.</td></tr>`;
    return;
  }

  tbody.innerHTML = patients.map(p => `
    <tr>
      <td><strong style="color:var(--accent);">${p.patient_code}</strong></td>
      <td>
        <strong>${p.name}</strong><br>
        <small style="color:var(--muted);">${p.email} • ${p.phone}</small>
      </td>
      <td>${p.age} yrs • ${p.gender}</td>
      <td><strong>${p.total_scans}</strong> scans</td>
      <td><span class="badge ${getStatusBadgeClass(p.latest_case_status)}">${p.latest_case_status}</span></td>
      <td>
        <span class="badge ${p.latest_resolution === 'Yes' ? 'badge-green' : 'badge-warning'}">
          ${p.latest_resolution === 'Yes' ? 'Resolved' : p.latest_resolution}
        </span>
      </td>
      <td>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-primary" style="padding:6px 10px;font-size:0.75rem;" onclick="launchAiForPatientCase(${p.id}, ${p.latest_case_id || 'null'})">
            AI Scan
          </button>
          <button class="btn btn-secondary" style="padding:6px 10px;font-size:0.75rem;" onclick="inspectPatientModal(${p.id})">
            History
          </button>
        </div>
      </td>
    </tr>
  `).join('');
}

function filterPatientsList() {
  const q = document.getElementById('patientSearchInput').value.toLowerCase().trim();
  if (!q) {
    renderPatientsTable(allPatients);
    return;
  }
  const filtered = allPatients.filter(p =>
    (p.name && p.name.toLowerCase().includes(q)) ||
    (p.email && p.email.toLowerCase().includes(q)) ||
    (p.patient_code && p.patient_code.toLowerCase().includes(q))
  );
  renderPatientsTable(filtered);
}

// ── PATIENT HISTORY MODAL ─────────────────────────────────────────────────────

async function inspectPatientModal(patientId) {
  modalPatientId = patientId;
  const modal = document.getElementById('patientHistoryModal');
  const body = document.getElementById('modalPatientBody');
  const title = document.getElementById('modalPatientName');

  try {
    const res = await fetch(`/api/doctor/patients/${patientId}`);
    if (!res.ok) throw new Error("Could not load patient profile");
    const data = await res.json();
    const p = data.patient;

    title.textContent = `${p.name} (${p.patient_code})`;

    body.innerHTML = `
      <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:12px;margin-bottom:18px;">
        <div class="param-item">
          <div class="param-key">Demographics</div>
          <div class="param-val">${p.age} yrs • ${p.gender}</div>
        </div>
        <div class="param-item">
          <div class="param-key">Contact Phone</div>
          <div class="param-val">${p.phone || 'N/A'}</div>
        </div>
        <div class="param-item">
          <div class="param-key">Email Address</div>
          <div class="param-val" style="font-size:0.8rem;">${p.email}</div>
        </div>
      </div>

      <div class="glass-card" style="padding:14px;margin-bottom:18px;">
        <div class="param-key">Documented Medical History</div>
        <div style="font-size:0.88rem;color:var(--text);margin-top:4px;">
          ${p.medical_history || 'No prior gastrointestinal or oncological history documented.'}
        </div>
      </div>

      <h4 style="font-size:1rem;margin-bottom:10px;color:var(--accent);">Previous Colonoscopy Scans &amp; AI Inferences (${data.scans.length})</h4>
      <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(200px, 1fr));gap:12px;margin-bottom:18px;">
        ${data.scans.length ? data.scans.map(s => `
          <div style="background:rgba(255,255,255,0.02);border:1px solid var(--border);border-radius:10px;padding:10px;text-align:center;">
            <div style="font-weight:700;font-size:0.85rem;margin-bottom:4px;">Scan #${s.id}</div>
            <span class="badge ${s.cnn_prediction ? 'badge-red' : 'badge-green'}" style="margin-bottom:6px;">
              ${s.cnn_prediction ? `Polyp (${s.cnn_confidence}%)` : `Clear (${s.cnn_confidence}%)`}
            </span>
            <div style="font-size:0.75rem;color:var(--muted);">${s.paris_classification || 'Normal Mucosa'}</div>
            <div style="font-size:0.7rem;color:var(--text-dim);margin-top:4px;">${s.created_at}</div>
          </div>
        `).join('') : '<div style="color:var(--muted);font-size:0.85rem;">No scans recorded yet.</div>'}
      </div>

      <h4 style="font-size:1rem;margin-bottom:10px;color:var(--accent2);">Approved Clinical Reports (${data.reports.length})</h4>
      <div class="data-table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>Report Code</th>
              <th>Date</th>
              <th>Resolution</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${data.reports.length ? data.reports.map(r => `
              <tr>
                <td><strong>${r.report_code}</strong></td>
                <td>${r.date || 'Recent'}</td>
                <td><span class="badge ${r.resolution_status === 'Resolved' ? 'badge-green' : 'badge-warning'}">${r.resolution_status}</span></td>
                <td><a href="/api/patient/reports/${r.id}/view" target="_blank" class="btn btn-secondary" style="padding:4px 8px;font-size:0.72rem;text-decoration:none;">View PDF</a></td>
              </tr>
            `).join('') : '<tr><td colspan="4" style="text-align:center;color:var(--muted);">No reports signed yet.</td></tr>'}
          </tbody>
        </table>
      </div>
    `;

    modal.classList.add('show');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function closePatientModal() {
  document.getElementById('patientHistoryModal').classList.remove('show');
}

function launchAiForModalPatient() {
  closePatientModal();
  if (modalPatientId) {
    launchAiForPatientCase(modalPatientId, null);
  }
}

function launchAiForPatientCase(patientId, caseId) {
  activePatientId = patientId;
  activeCaseId = caseId;

  // Set patient select
  const select = document.getElementById('aiSelectPatient');
  if (select) select.value = patientId;

  switchToTab('aiDetectionTab');
  showToast(`Patient #${patientId} loaded into AI Detection Centre`, 'info');
}

// ── AI DETECTION CENTRE EXECUTION ─────────────────────────────────────────────

async function triggerDoctorDetection() {
  const patientSelect = document.getElementById('aiSelectPatient');
  const patientId = patientSelect.value;
  activePatientId = patientId;

  const btn = document.getElementById('btnRunDetection');
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="pulse-dot" style="margin-right:8px;"></span> Analyzing with CNN &amp; U-Net...`;

  const formData = new FormData();
  if (patientId) formData.append('patient_id', patientId);
  if (activeCaseId) formData.append('case_id', activeCaseId);

  if (selectedSourceMode === 'upload') {
    if (!uploadedFile) {
      showToast('Please select or drag an image file first', 'error');
      btn.disabled = false;
      btn.innerHTML = originalText;
      return;
    }
    formData.append('image', uploadedFile);
  } else {
    formData.append('sample_id', activeSampleId);
  }

  try {
    showToast('Executing neural polyp detection and segmentation...', 'info');

    const res = await fetch('/api/doctor/detect', {
      method: 'POST',
      headers: {
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: formData
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'AI Detection failed');

    currentScanId = data.scan_id;
    renderDetectionResults(data);
    showToast('AI analysis completed successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}

function renderDetectionResults(res) {
  const workspaceGrid = document.getElementById('detectionWorkspaceGrid');
  workspaceGrid.style.display = 'grid';

  // Finding Badge
  const badge = document.getElementById('workspaceFindingBadge');
  if (res.detected) {
    badge.textContent = `POLYP DETECTED (${res.confidence}%)`;
    badge.className = 'badge badge-green';
  } else {
    badge.textContent = `CLEAR / NO POLYP (${res.confidence}%)`;
    badge.className = 'badge badge-cyan';
  }

  // Update Split Images
  const origSrc = selectedSourceMode === 'upload' && uploadedFile
    ? URL.createObjectURL(uploadedFile)
    : `/static/samples/${activeSampleId}.jpg`;
  const annotSrc = 'data:image/jpeg;base64,' + res.result_image_b64;

  if (viewerInstance) {
    viewerInstance.updateImages(origSrc, annotSrc);
  } else {
    document.getElementById('doctorSplitOrig').src = origSrc;
    document.getElementById('doctorSplitAnnot').src = annotSrc;
  }

  // Telemetry items
  document.getElementById('telPolypPrediction').textContent = res.detected ? 'Positive (Suspected Adenoma)' : 'Negative (Normal Mucosa)';
  document.getElementById('telConfidence').textContent = `${res.confidence}%`;
  document.getElementById('telParis').textContent = res.paris_classification || 'Normal / Flat (Type IIb)';
  document.getElementById('telDiameter').textContent = res.estimated_diameter_mm ? `${res.estimated_diameter_mm} mm` : 'N/A';
  document.getElementById('telQuadrant').textContent = res.quadrant || 'Ascending Colon';
  document.getElementById('telArea').textContent = res.lesion_area_pct ? `${res.lesion_area_pct}%` : '<0.1%';
  document.getElementById('telEngine').textContent = res.ai_engine || 'CNN Classifier + U-Net Mask Engine';

  // Populate doctor review form defaults
  setDoctorConfirmation(res.detected);

  const notesInput = document.getElementById('docClinicalNotes');
  const recInput = document.getElementById('docRecommendations');
  const statusSelect = document.getElementById('docCaseStatusSelect');
  const resSelect = document.getElementById('docResolutionSelect');

  if (res.detected) {
    notesInput.value = `Endoscopic optical assessment reveals a mucosal lesion matching ${res.paris_classification} morphology in the ${res.quadrant}. Distinct vascular pattern observed.`;
    recInput.value = `Indicated for endoscopic snare resection / optical biopsy. Histopathology submitted for confirmation. Follow-up colonoscopy advised.`;
    statusSelect.value = 'Follow-up required';
    resSelect.value = 'No';
  } else {
    notesInput.value = `Normal mucosal architecture inspected throughout the visualized bowel segment. No suspicious adenomatous polyps or dysplastic alterations identified.`;
    recInput.value = `Standard population colorectal cancer surveillance protocol. Maintain high-fiber dietary lifestyle.`;
    statusSelect.value = 'Resolved';
    resSelect.value = 'Yes';
  }

  // Scroll smoothly to workspace
  workspaceGrid.scrollIntoView({ behavior: 'smooth' });
}

function setDoctorConfirmation(isConfirmed) {
  doctorConfirmedPolyp = isConfirmed;
  const btnYes = document.getElementById('btnConfirmPolyp');
  const btnNo = document.getElementById('btnRejectPolyp');

  if (isConfirmed) {
    btnYes.classList.add('active');
    btnNo.classList.remove('active');
  } else {
    btnNo.classList.add('active');
    btnYes.classList.remove('active');
  }
}

async function saveDoctorDraft() {
  if (!currentScanId) {
    showToast('Run AI detection first to create a scan record', 'warning');
    return;
  }

  const payload = {
    doctor_confirmed: doctorConfirmedPolyp,
    doctor_notes: document.getElementById('docClinicalNotes').value,
    recommendations: document.getElementById('docRecommendations').value,
    approve_for_patient: false
  };

  try {
    const res = await fetch(`/api/doctor/scans/${currentScanId}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to save draft');
    showToast('Clinical impressions saved as draft', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function generateOfficialReportFromWorkspace() {
  const patientSelect = document.getElementById('aiSelectPatient');
  const patientId = patientSelect.value;
  if (!patientId) {
    showToast('Please select a patient to attach this official report', 'error');
    return;
  }

  const conclusions = document.getElementById('docClinicalNotes').value;
  const recs = document.getElementById('docRecommendations').value;
  const status = document.getElementById('docCaseStatusSelect').value;
  const isResolved = document.getElementById('docResolutionSelect').value;
  const followup = document.getElementById('docFollowupInterval').value;

  if (!conclusions) {
    showToast('Please enter doctor clinical impressions before signing report', 'error');
    return;
  }

  const payload = {
    patient_id: patientId,
    case_id: activeCaseId || null,
    scan_id: currentScanId || null,
    report_title: `Colonoscopy AI Diagnostic Report – ${doctorConfirmedPolyp ? 'Polyp Identified' : 'Mucosa Normal'}`,
    doctor_conclusions: conclusions,
    recommendations: recs,
    follow_up_date: followup,
    resolution_status: isResolved === 'Yes' ? 'Resolved' : 'Follow-up required'
  };

  try {
    showToast('Signing and publishing official clinical report...', 'info');

    const res = await fetch('/api/doctor/reports/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Failed to generate report');

    showToast(`Report ${data.report_code} finalized and published!`, 'success');

    // Reload dashboard & reports archive
    loadDoctorDashboard();
    loadReports();

    // Open report in new tab
    if (data.view_url) {
      window.open(data.view_url, '_blank');
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// ── REPORTS ARCHIVE ───────────────────────────────────────────────────────────

async function loadReports() {
  try {
    const res = await fetch('/api/doctor/reports');
    if (!res.ok) return;
    const data = await res.json();
    allReports = data.reports || [];
    renderReportsTable(allReports);
  } catch (err) {
    console.warn("Failed to load reports archive:", err);
  }
}

function renderReportsTable(reports) {
  const tbody = document.getElementById('reportsArchiveBody');
  if (!tbody) return;

  if (!reports.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:28px;color:var(--muted);">No reports signed yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = reports.map(r => `
    <tr>
      <td><strong style="color:var(--accent);">${r.report_code}</strong></td>
      <td>${r.case_number || 'CAS-2026-001'}</td>
      <td>
        <strong>${r.patient_name}</strong><br>
        <small style="color:var(--muted);">${r.patient_code}</small>
      </td>
      <td>${r.date || r.created_at || 'Recent'}</td>
      <td>
        <span class="badge ${r.resolution_status === 'Resolved' ? 'badge-green' : 'badge-warning'}">
          ${r.resolution_status || 'Under Surveillance'}
        </span>
      </td>
      <td>
        <a href="${r.view_url}" target="_blank" class="btn btn-secondary" style="padding:6px 14px;font-size:0.75rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          View PDF Report
        </a>
      </td>
    </tr>
  `).join('');
}

function filterReportsList() {
  const q = document.getElementById('reportsSearchInput').value.toLowerCase().trim();
  if (!q) {
    renderReportsTable(allReports);
    return;
  }
  const filtered = allReports.filter(r =>
    (r.report_code && r.report_code.toLowerCase().includes(q)) ||
    (r.patient_name && r.patient_name.toLowerCase().includes(q)) ||
    (r.patient_code && r.patient_code.toLowerCase().includes(q))
  );
  renderReportsTable(filtered);
}
