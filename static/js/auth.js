// PolyScope AI Authentication & Global Utilities

const Auth = {
  getCsrfToken() {
    return sessionStorage.getItem('csrf_token') || '';
  },

  setCsrfToken(token) {
    if (token) sessionStorage.setItem('csrf_token', token);
  },

  async checkAuth() {
    try {
      const res = await fetch('/api/auth/me');
      if (!res.ok) return null;
      const data = await res.json();
      this.setCsrfToken(data.csrf_token);
      return data;
    } catch (e) {
      return null;
    }
  },

  async login(email, password) {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Login failed');
    this.setCsrfToken(data.csrf_token);
    return data;
  },

  async logout() {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'X-CSRF-Token': this.getCsrfToken() }
      });
    } catch (e) {}
    sessionStorage.clear();
    window.location.href = '/login.html';
  },

  redirectToPortal(role) {
    if (role === 'doctor') {
      window.location.href = '/doctor_portal.html';
    } else if (role === 'admin') {
      window.location.href = '/admin_portal.html';
    } else {
      window.location.href = '/patient_portal.html';
    }
  }
};

function showToast(message, type = 'info') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '⚠️';

  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(15px)';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}
