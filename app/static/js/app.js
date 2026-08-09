// Global utilities used across pages

// Auto-dismiss flash alerts
document.querySelectorAll('.alert-dismissible').forEach(el => {
  setTimeout(() => { el.classList.remove('show'); }, 4000);
});
