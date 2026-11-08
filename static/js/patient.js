// PolyScope Patient Portal - Clinical Client Script
let currentPatient = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentPatient = await Auth.checkAuth();
  if (!currentPatient) {
    window.location.href = '/login.html';
    return;
  }

  // Prevent doctors or admins from confusing portals
  if (currentPatient.role !== 'patient') {
    if (currentPatient.role === 'doctor') {
      window.location.href = '/doctor_portal.html';
      return;
    } else if (currentPatient.role === 'admin') {
      window.location.href = '/admin_portal.html';
      return;
    }
  }

  // Initialize UI
  setupSidebarUser();
  initNavigation();
  await loadDashboard();
});

function setupSidebarUser() {
  const nameEl = document.getElementById('patientNameDisplay');
  const codeEl = document.getElementById('patientIdDisplay');
  const avatarEl = document.getElementById('avatarLetter');

  if (nameEl) nameEl.textContent = currentPatient.name || 'Patient';
  if (codeEl) codeEl.textContent = currentPatient.patient_code || `POL-PT-${currentPatient.id}`;
  if (avatarEl) avatarEl.textContent = (currentPatient.name || 'P').charAt(0).toUpperCase();
}

function initNavigation() {
  const links = document.querySelectorAll('.nav-link[data-tab]');
  links.forEach(link => {
    link.addEventListener('click', () => {
      links.forEach(l => l.classList.remove('active'));
      link.classList.add('active');

      const targetTab = link.getAttribute('data-tab');
      document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
      });
      const activeTab = document.getElementById(targetTab);
      if (activeTab) activeTab.classList.add('active');
    });
  });
}

async function loadDashboard() {
  try {
    const res = await fetch('/api/patient/dashboard');
    if (!res.ok) {
      if (res.status === 401) {
        window.location.href = '/login.html';
        return;
      }
      throw new Error('Could not load dashboard data');
    }

    const data = await res.json();
    renderProfile(data.patient);
    renderCases(data.cases, data.patient);
    renderReports(data.approved_reports);
  } catch (err) {
    console.error('Patient dashboard loading error:', err);
    showToast(err.message, 'error');
  }
}

function renderProfile(patient) {
  if (!patient) return;

  // Sidebar
  const nameEl = document.getElementById('patientNameDisplay');
  const codeEl = document.getElementById('patientIdDisplay');
  if (nameEl) nameEl.textContent = patient.name;
  if (codeEl) codeEl.textContent = patient.patient_code;

  // Profile tab fields
  const pName = document.getElementById('profPatientName');
  const pCode = document.getElementById('profPatientCode');
  const pAge = document.getElementById('profPatientAge');
  const pGen = document.getElementById('profPatientGender');
  const pDoc = document.getElementById('profPatientDoctor');

  if (pName) pName.value = patient.name || '';
  if (pCode) pCode.value = patient.patient_code || '';
  if (pAge) pAge.value = patient.age ? `${patient.age} years old` : 'Not specified';
  if (pGen) pGen.value = patient.gender || 'Not specified';
  if (pDoc) pDoc.value = patient.doctor?.name ? `${patient.doctor.name} (${patient.doctor.email || ''})` : 'Pending Assignment';

  // Stats
  const statPatientId = document.getElementById('statPatientId');
  const statPatientEmail = document.getElementById('statPatientEmail');
  const statDoctorName = document.getElementById('statDoctorName');
  const statDoctorPhone = document.getElementById('statDoctorPhone');

  if (statPatientId) statPatientId.textContent = patient.patient_code;
  if (statPatientEmail) statPatientEmail.textContent = patient.email;
  if (statDoctorName) statDoctorName.textContent = patient.doctor?.name || 'Dr. Assigned';
  if (statDoctorPhone) statDoctorPhone.textContent = patient.doctor?.phone || patient.doctor?.email || 'Digestive Health Dept.';
}

function renderCases(cases, patient) {
  const badge = document.getElementById('caseStatusBadge');
  const statStatus = document.getElementById('statCaseStatus');
  const statResolution = document.getElementById('statResolution');
  const statFollowupDate = document.getElementById('statFollowupDate');

  if (!cases || cases.length === 0) {
    if (badge) badge.textContent = 'No Active Cases';
    if (statStatus) statStatus.textContent = 'No Cases';
    if (statResolution) statResolution.textContent = 'Upload image to start';
    if (statFollowupDate) statFollowupDate.textContent = 'N/A';
    updateStepper('Image uploaded');
    return;
  }

  // Active / primary case is the first one
  const c = cases[0];

  if (badge) badge.textContent = c.status;
  if (statStatus) statStatus.textContent = c.status;
  if (statResolution) statResolution.textContent = c.is_resolved ? 'Resolved: Yes' : 'Resolved: No (Active)';
  if (statFollowupDate) statFollowupDate.textContent = c.follow_up_date || 'Per Clinical Plan';

  // Update Stepper
  updateStepper(c.status, c.is_resolved);

  // Update Doctor-Reviewed Clinical Findings
  const obsEl = document.getElementById('findingObservation');
  const polypEl = document.getElementById('findingPolypStatus');
  const conclEl = document.getElementById('findingConclusion');
  const nextEl = document.getElementById('findingNextSteps');
  const docContactEl = document.getElementById('findingDoctorContact');
  const resStatusEl = document.getElementById('findingResolutionStatus');
  const approvedBadge = document.getElementById('approvedBadge');

  if (obsEl) obsEl.textContent = c.findings_summary || 'Colonoscopy imagery received and queued for gastroenterologist evaluation.';
  if (conclEl) conclEl.textContent = c.doctor_conclusion || 'Case currently under examination by your assigned physician.';
  if (nextEl) nextEl.textContent = c.patient_instructions || 'Rest, stay hydrated, and await follow-up from the gastroenterology clinic.';
  if (docContactEl) docContactEl.textContent = `${c.doctor_name || patient.doctor?.name || 'Attending Physician'} — Department of Gastroenterology & Endoscopy.`;

  if (c.is_resolved) {
    if (resStatusEl) resStatusEl.innerHTML = '<span style="color:var(--accent);font-weight:700;">Case Resolved</span> — Standard surveillance cycle.';
    if (approvedBadge) {
      approvedBadge.textContent = '✓ CASE RESOLVED';
      approvedBadge.className = 'badge badge-green';
    }
  } else {
    if (resStatusEl) resStatusEl.innerHTML = `<span style="color:var(--warning);font-weight:700;">Under Active Management</span> (${c.status})`;
    if (approvedBadge) {
      approvedBadge.textContent = c.status.toUpperCase();
      approvedBadge.className = 'badge badge-cyan';
    }
  }

  if (polypEl) {
    if (c.status === 'Resolved') {
      polypEl.textContent = 'Polyp management finalized. Margin clear.';
      polypEl.style.color = 'var(--accent)';
    } else if (c.status.toLowerCase().includes('follow-up') || c.status.toLowerCase().includes('further')) {
      polypEl.textContent = 'Suspected lesion under medical surveillance.';
      polypEl.style.color = 'var(--warning)';
    } else {
      polypEl.textContent = 'Under clinical analysis by medical team.';
      polypEl.style.color = 'var(--accent2)';
    }
  }
}

function updateStepper(status, isResolved) {
  const steps = [
    { id: 'step1', label: 'Image uploaded' },
    { id: 'step2', label: 'Analysis pending' },
    { id: 'step3', label: 'Under doctor review' },
    { id: 'step4', label: 'Follow-up required' },
    { id: 'step5', label: 'Resolved' }
  ];

  const statusHierarchy = {
    'image uploaded': 1,
    'analysis pending': 2,
    'under doctor review': 3,
    'follow-up required': 4,
    'further investigation recommended': 4,
    'resolved': 5
  };

  const currentLevel = isResolved ? 5 : (statusHierarchy[(status || '').toLowerCase()] || 1);

  steps.forEach((step, idx) => {
    const el = document.getElementById(step.id);
    if (!el) return;
    el.classList.remove('completed', 'active');

    const stepLevel = idx + 1;
    if (stepLevel < currentLevel) {
      el.classList.add('completed');
    } else if (stepLevel === currentLevel) {
      if (currentLevel === 5) {
        el.classList.add('completed');
      } else {
        el.classList.add('active');
      }
    }
  });
}

function renderReports(reports) {
  const tbody = document.getElementById('approvedReportsTableBody');
  if (!tbody) return;

  if (!reports || reports.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center;padding:36px;color:var(--muted);">
          No approved clinical endoscopy reports published yet.
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = reports.map(r => `
    <tr>
      <td><strong style="color:var(--accent);">${r.report_code}</strong></td>
      <td>${r.title}</td>
      <td>${r.date || r.created_at || 'Recent'}</td>
      <td>${r.doctor_name}</td>
      <td>
        <span class="badge ${r.resolution_status === 'Resolved' ? 'badge-green' : 'badge-warning'}">
          ${r.resolution_status || 'Under Surveillance'}
        </span>
      </td>
      <td>
        <a href="/api/patient/reports/${r.id}/view" target="_blank" class="btn btn-secondary" style="padding:6px 14px;font-size:0.75rem;text-decoration:none;display:inline-flex;align-items:center;gap:6px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
          View PDF Report
        </a>
      </td>
    </tr>
  `).join('');
}
