// PolyScope AI Interactive Clinical Viewer

class PolyScopeViewer {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;
    this.options = options;
    this.zoomLevel = 1.0;
    this.splitPercent = 50;
    this.isDragging = false;
    this.showMask = true;
    this.showBbox = true;
    this.initSlider();
  }

  initSlider() {
    this.sliderLine = this.container.querySelector('.split-slider-line');
    this.overlay = this.container.querySelector('.split-overlay');
    if (!this.sliderLine || !this.overlay) return;

    const onPointerMove = (e) => {
      if (!this.isDragging) return;
      const rect = this.container.getBoundingClientRect();
      const clientX = e.clientX || (e.touches && e.touches[0].clientX);
      if (!clientX) return;
      let x = clientX - rect.left;
      x = Math.max(0, Math.min(x, rect.width));
      const pct = (x / rect.width) * 100;
      this.setSplit(pct);
    };

    const stopDrag = () => {
      this.isDragging = false;
    };

    this.sliderLine.addEventListener('mousedown', () => { this.isDragging = true; });
    this.sliderLine.addEventListener('touchstart', () => { this.isDragging = true; });

    window.addEventListener('mousemove', onPointerMove);
    window.addEventListener('touchmove', onPointerMove);
    window.addEventListener('mouseup', stopDrag);
    window.addEventListener('touchend', stopDrag);
  }

  setSplit(pct) {
    this.splitPercent = pct;
    if (this.sliderLine) this.sliderLine.style.left = `${pct}%`;
    if (this.overlay) this.overlay.style.width = `${pct}%`;
  }

  updateImages(originalSrc, annotatedSrc) {
    const origImg = this.container.querySelector('.split-base img');
    const annotImg = this.container.querySelector('.split-overlay img');
    if (origImg) origImg.src = originalSrc;
    if (annotImg) annotImg.src = annotatedSrc;
    this.setSplit(50);
  }
}

// Global helper to load pre-loaded samples
async function loadSampleCases(callback) {
  try {
    const res = await fetch('/api/ai/samples');
    if (!res.ok) return [];
    const data = await res.json();
    if (callback) callback(data.samples);
    return data.samples;
  } catch (e) {
    console.warn("Failed to load sample cases:", e);
    return [];
  }
}
