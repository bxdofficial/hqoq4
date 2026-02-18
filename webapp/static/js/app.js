/**
 * حقوقي - JavaScript الرئيسي
 * منصة قانونية مصرية احترافية
 */

// =====================================================
// Toast Notifications
// =====================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  
  let icon = 'info';
  let iconColor = 'var(--info)';
  
  switch (type) {
    case 'success':
      icon = 'check-circle';
      iconColor = 'var(--success)';
      break;
    case 'error':
      icon = 'x-circle';
      iconColor = 'var(--error)';
      break;
    case 'warning':
      icon = 'alert-triangle';
      iconColor = 'var(--warning)';
      break;
  }
  
  toast.innerHTML = `
    <i data-lucide="${icon}" style="width:20px;height:20px;color:${iconColor}"></i>
    <span>${message}</span>
  `;
  
  container.appendChild(toast);
  
  // Initialize icons
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
  
  // Auto remove after 4 seconds
  setTimeout(() => {
    toast.style.animation = 'slideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
  @keyframes slideOut {
    to {
      transform: translateX(-100%);
      opacity: 0;
    }
  }
`;
document.head.appendChild(style);

// =====================================================
// Form Handling
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
  // User type toggle for registration
  const typeSelect = document.getElementById('user_type');
  const barField = document.getElementById('bar-field');
  const barInput = document.getElementById('bar_registration_number');
  
  if (typeSelect && barField) {
    const toggle = () => {
      const isLawyer = typeSelect.value === 'lawyer';
      barField.classList.toggle('hidden', !isLawyer);
      if (barInput) barInput.required = isLawyer;
    };
    typeSelect.addEventListener('change', toggle);
    toggle();
  }
  
  // Character counter for textareas
  const textareas = document.querySelectorAll('textarea[maxlength]');
  textareas.forEach(textarea => {
    const maxLength = textarea.getAttribute('maxlength');
    const counter = document.querySelector(`#${textarea.id}-count, [data-counter="${textarea.id}"]`);
    
    if (counter) {
      textarea.addEventListener('input', () => {
        counter.textContent = textarea.value.length;
      });
    }
  });
  
  // Form validation styling
  const forms = document.querySelectorAll('form');
  forms.forEach(form => {
    const inputs = form.querySelectorAll('input, select, textarea');
    
    inputs.forEach(input => {
      input.addEventListener('invalid', (e) => {
        e.preventDefault();
        input.classList.add('error');
        showToast('يرجى ملء جميع الحقول المطلوبة', 'warning');
      });
      
      input.addEventListener('input', () => {
        input.classList.remove('error');
      });
    });
  });
});

// =====================================================
// Modal Handling
// =====================================================
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
    document.body.style.overflow = '';
  }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const activeModal = document.querySelector('.modal-overlay.active');
    if (activeModal) {
      activeModal.classList.remove('active');
      document.body.style.overflow = '';
    }
  }
});

// =====================================================
// Tabs Handling
// =====================================================
function initTabs() {
  const tabContainers = document.querySelectorAll('.tabs');
  
  tabContainers.forEach(container => {
    const tabs = container.querySelectorAll('.tab');
    const panels = document.querySelectorAll(`[data-tab-panel]`);
    
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        // Remove active from all tabs
        tabs.forEach(t => t.classList.remove('active'));
        // Add active to clicked tab
        tab.classList.add('active');
        
        // Hide all panels
        panels.forEach(panel => panel.classList.add('hidden'));
        // Show target panel
        const targetPanel = document.querySelector(`[data-tab-panel="${tab.dataset.tab}"]`);
        if (targetPanel) {
          targetPanel.classList.remove('hidden');
        }
      });
    });
  });
}

document.addEventListener('DOMContentLoaded', initTabs);

// =====================================================
// Search & Filter
// =====================================================
function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

// =====================================================
// API Helper Functions
// =====================================================
async function apiRequest(url, method = 'GET', data = null) {
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
  };
  
  if (data && method !== 'GET') {
    options.body = JSON.stringify(data);
  }
  
  try {
    const response = await fetch(url, options);
    const result = await response.json();
    
    if (!response.ok) {
      throw new Error(result.detail || 'حدث خطأ');
    }
    
    return result;
  } catch (error) {
    showToast(error.message, 'error');
    throw error;
  }
}

// =====================================================
// Date Formatting (Arabic)
// =====================================================
function formatDate(dateString) {
  if (!dateString) return '-';
  
  const date = new Date(dateString);
  return date.toLocaleDateString('ar-EG', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

function formatDateTime(dateString) {
  if (!dateString) return '-';
  
  const date = new Date(dateString);
  return date.toLocaleDateString('ar-EG', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function timeAgo(dateString) {
  if (!dateString) return '-';
  
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);
  
  const intervals = [
    { label: 'سنة', seconds: 31536000 },
    { label: 'شهر', seconds: 2592000 },
    { label: 'أسبوع', seconds: 604800 },
    { label: 'يوم', seconds: 86400 },
    { label: 'ساعة', seconds: 3600 },
    { label: 'دقيقة', seconds: 60 },
  ];
  
  for (const interval of intervals) {
    const count = Math.floor(seconds / interval.seconds);
    if (count >= 1) {
      return `منذ ${count} ${interval.label}`;
    }
  }
  
  return 'الآن';
}

// =====================================================
// Number Formatting
// =====================================================
function formatCurrency(amount) {
  return new Intl.NumberFormat('ar-EG', {
    style: 'currency',
    currency: 'EGP',
    minimumFractionDigits: 0,
  }).format(amount);
}

function formatNumber(number) {
  return new Intl.NumberFormat('ar-EG').format(number);
}

// =====================================================
// Loading State
// =====================================================
function showLoading(element) {
  if (!element) return;
  
  element.classList.add('loading');
  element.disabled = true;
  element.dataset.originalContent = element.innerHTML;
  element.innerHTML = '<span class="spinner" style="width:18px;height:18px;border-width:2px"></span>';
}

function hideLoading(element) {
  if (!element) return;
  
  element.classList.remove('loading');
  element.disabled = false;
  if (element.dataset.originalContent) {
    element.innerHTML = element.dataset.originalContent;
    delete element.dataset.originalContent;
    
    // Reinitialize icons
    if (typeof lucide !== 'undefined') {
      lucide.createIcons();
    }
  }
}

// =====================================================
// Scroll to Top
// =====================================================
function scrollToTop() {
  window.scrollTo({
    top: 0,
    behavior: 'smooth',
  });
}

// =====================================================
// Copy to Clipboard
// =====================================================
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('تم النسخ بنجاح', 'success');
  } catch (err) {
    showToast('فشل النسخ', 'error');
  }
}

// =====================================================
// Initialize Lucide Icons
// =====================================================
document.addEventListener('DOMContentLoaded', () => {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
});

// Re-initialize icons after AJAX content load
window.refreshIcons = function() {
  if (typeof lucide !== 'undefined') {
    lucide.createIcons();
  }
};

// =====================================================
// Service Worker Registration (PWA)
// =====================================================
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    // Service worker can be added later for PWA support
  });
}

// =====================================================
// Error Handling
// =====================================================
window.addEventListener('error', (e) => {
  console.error('JavaScript Error:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
  console.error('Unhandled Promise Rejection:', e.reason);
});

// =====================================================
// Export functions for global use
// =====================================================
window.showToast = showToast;
window.openModal = openModal;
window.closeModal = closeModal;
window.apiRequest = apiRequest;
window.formatDate = formatDate;
window.formatDateTime = formatDateTime;
window.timeAgo = timeAgo;
window.formatCurrency = formatCurrency;
window.formatNumber = formatNumber;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.copyToClipboard = copyToClipboard;
window.debounce = debounce;
