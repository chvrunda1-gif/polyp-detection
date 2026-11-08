// PolyScope Admin Portal JavaScript

let currentAdmin = null;

document.addEventListener('DOMContentLoaded', async () => {
  currentAdmin = await Auth.checkAuth();
  if (!currentAdmin || currentAdmin.role !== 'admin') {
    window.location.href = '/login.html';
    return;
  }

  document.getElementById('adminNameDisplay').textContent = currentAdmin.name;
  document.getElementById('adminEmailDisplay').textContent = currentAdmin.email;
  document.getElementById('adminAvatarLetter').textContent = currentAdmin.name.charAt(0).toUpperCase();

  initAdminNavigation();
  loadAdminDashboard();
  loadUsersTable();
  loadGlobalScans();
  loadAuditLogs();
});

function initAdminNavigation() {
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

async function loadAdminDashboard() {
  try {
    const res = await fetch('/api/admin/dashboard');
    if (!res.ok) return;
    const data = await res.json();
    const s = data.stats;
    const sys = data.system;

    document.getElementById('admTotalUsers').textContent = s.total_users;
    document.getElementById('admTotalPatients').textContent = s.total_patients;
    document.getElementById('admTotalDoctors').textContent = s.total_doctors;
    document.getElementById('admTotalScans').textContent = s.total_scans;
    document.getElementById('admAdrRate').textContent = `${s.adenoma_detection_rate}%`;

    // System Telemetry
    document.getElementById('sysCpu').textContent = `${sys.cpu_usage_pct}%`;
    document.getElementById('sysRam').textContent = `${sys.memory_usage_pct}% (${sys.memory_available_mb} MB free)`;
    document.getElementById('sysDisk').textContent = `${sys.disk_free_gb} GB free`;
    document.getElementById('sysEngine').textContent = sys.active_engine;
  } catch (err) {
    console.warn("Failed to load admin stats:", err);
  }
}

async function loadUsersTable(roleFilter = '') {
  try {
    const search = document.getElementById('userSearchInput')?.value || '';
    const res = await fetch(`/api/admin/users?role=${roleFilter}&q=${encodeURIComponent(search)}`);
    if (!res.ok) return;
    const data = await res.json();
    const users = data.users || [];

    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    if (!users.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">No users found matching search.</td></tr>`;
      return;
    }

    tbody.innerHTML = users.map(u => `
      <tr>
        <td><strong>#${u.id}</strong></td>
        <td><strong>${u.name}</strong><br><small style="color:var(--text-muted)">${u.email}</small></td>
        <td>
          <span class="badge ${u.role === 'admin' ? 'badge-warning' : (u.role === 'doctor' ? 'badge-cyan' : 'badge-green')}">
            ${u.role}
          </span>
        </td>
        <td>${u.assigned_doctor}</td>
        <td><strong>${u.scan_count}</strong> scans</td>
        <td>
          <span class="badge ${u.status === 'active' ? 'badge-green' : 'badge-red'}">
            ${u.status}
          </span>
        </td>
        <td>
          <button class="btn btn-secondary" style="padding:4px 8px;font-size:0.72rem;" onclick="openEditUserModal(${u.id}, '${u.name}', '${u.role}', '${u.status}')">
            Edit
          </button>
          <button class="btn btn-danger" style="padding:4px 8px;font-size:0.72rem;margin-left:4px;" onclick="deleteUserAccount(${u.id}, '${u.name}')">
            Delete
          </button>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.warn("Failed to load users:", err);
  }
}

function openCreateUserModal() {
  document.getElementById('createUserModal').classList.add('show');
}
function closeCreateUserModal() {
  document.getElementById('createUserModal').classList.remove('show');
}

async function submitCreateUser(e) {
  e.preventDefault();
  const payload = {
    name: document.getElementById('newUserName').value,
    email: document.getElementById('newUserEmail').value,
    password: document.getElementById('newUserPassword').value,
    role: document.getElementById('newUserRole').value,
    phone: document.getElementById('newUserPhone').value
  };

  try {
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Failed to create user");

    showToast("User account created successfully", "success");
    closeCreateUserModal();
    loadUsersTable();
    loadAdminDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function openEditUserModal(id, name, role, status) {
  document.getElementById('editUserId').value = id;
  document.getElementById('editUserName').value = name;
  document.getElementById('editUserRole').value = role;
  document.getElementById('editUserStatus').value = status;
  document.getElementById('editUserModal').classList.add('show');
}
function closeEditUserModal() {
  document.getElementById('editUserModal').classList.remove('show');
}

async function submitEditUser(e) {
  e.preventDefault();
  const id = document.getElementById('editUserId').value;
  const payload = {
    name: document.getElementById('editUserName').value,
    role: document.getElementById('editUserRole').value,
    status: document.getElementById('editUserStatus').value
  };

  try {
    const res = await fetch(`/api/admin/users/${id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': Auth.getCsrfToken()
      },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error("Failed to update user");

    showToast("User permissions updated successfully", "success");
    closeEditUserModal();
    loadUsersTable();
    loadAdminDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function deleteUserAccount(id, name) {
  if (!confirm(`Are you sure you want to delete account for ${name}? This action is permanent.`)) return;

  try {
    const res = await fetch(`/api/admin/users/${id}`, {
      method: 'DELETE',
      headers: { 'X-CSRF-Token': Auth.getCsrfToken() }
    });
    if (!res.ok) throw new Error("Could not delete user account");

    showToast(`Account for ${name} removed`, "success");
    loadUsersTable();
    loadAdminDashboard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadGlobalScans() {
  try {
    const res = await fetch('/api/admin/scans');
    if (!res.ok) return;
    const data = await res.json();
    const scans = data.scans || [];

    const tbody = document.getElementById('globalScansBody');
    if (!tbody) return;

    if (!scans.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:30px;">No scans recorded in platform yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = scans.map(s => `
      <tr>
        <td><strong>#${s.id}</strong></td>
        <td><strong>${s.patient_name}</strong><br><small style="color:var(--text-muted)">${s.patient_email}</small></td>
        <td>${s.filename}</td>
        <td>
          <span class="badge ${s.detected ? 'badge-green' : 'badge-cyan'}">
            ${s.detected ? 'Polyp Detected' : 'Clear'}
          </span>
        </td>
        <td><strong>${s.confidence}%</strong></td>
        <td><small>${s.ai_engine}</small></td>
        <td>${s.created_at}</td>
      </tr>
    `).join('');
  } catch (err) {
    console.warn("Failed to load global scans:", err);
  }
}

async function loadAuditLogs() {
  try {
    const res = await fetch('/api/admin/logs');
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];

    const tbody = document.getElementById('auditLogsBody');
    if (!tbody) return;

    if (!logs.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:30px;">No activity logs recorded yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(l => `
      <tr>
        <td><small style="color:var(--text-muted)">${l.timestamp}</small></td>
        <td><strong>${l.user_email}</strong> <span class="badge badge-cyan" style="font-size:0.65rem;">${l.role}</span></td>
        <td><code>${l.action}</code></td>
        <td>${l.details || ''}</td>
        <td><small style="color:var(--text-dim)">${l.ip_address}</small></td>
      </tr>
    `).join('');
  } catch (err) {
    console.warn("Failed to load audit logs:", err);
  }
}

async function triggerLiveModelEvaluation() {
  const btn = document.getElementById('evalTriggerBtn');
  const loader = document.getElementById('evalLoader');
  if (btn) btn.disabled = true;
  if (loader) loader.style.display = 'block';

  try {
    const res = await fetch('/api/ai/evaluate', {
      method: 'POST',
      headers: { 'X-CSRF-Token': Auth.getCsrfToken() }
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.message || "Evaluation failed");

    showToast("Model evaluation completed on ground truth verification set!", "success");
    
    // Display results in UI
    const m = data.metrics;
    document.getElementById('metricAccuracy').textContent = `${m.accuracy}%`;
    document.getElementById('metricPrecision').textContent = `${m.precision}%`;
    document.getElementById('metricRecall').textContent = `${m.recall}%`;
    document.getElementById('metricF1').textContent = `${m.f1_score}%`;
    document.getElementById('metricDice').textContent = `${m.dice}`;
    document.getElementById('metricIoU').textContent = `${m.iou}`;

    const cm = data.confusion_matrix;
    document.getElementById('cmTp').textContent = cm.true_positives;
    document.getElementById('cmFp').textContent = cm.false_positives;
    document.getElementById('cmTn').textContent = cm.true_negatives;
    document.getElementById('cmFn').textContent = cm.false_negatives;

    document.getElementById('evalResultsCard').style.display = 'block';
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    if (btn) btn.disabled = false;
    if (loader) loader.style.display = 'none';
  }
}
