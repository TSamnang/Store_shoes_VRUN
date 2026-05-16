/**
 * Theme Toggle – Dark / Light Mode
 * Persists user preference in localStorage.
 * Applies [data-theme="light"] on <html> for light mode;
 * removes the attribute for dark mode (default).
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'vrun-theme';

    /* ── Apply saved theme immediately (before paint) ── */
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
    }

    /* ── Initialise toggle controls once DOM is ready ── */
    document.addEventListener('DOMContentLoaded', function () {
        /* ── Product Card Navigation ── */
        const cards = document.querySelectorAll('.product-card[data-product-id]');
        cards.forEach(card => {
            const productId = card.dataset.productId;
            if (!productId) return;

            card.addEventListener('click', function(e) {
                // Ignore clicks on buttons or links inside the card
                if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.closest('button') || e.target.closest('a')) {
                    return;
                }

                // Navigate to product detail page
                window.location.href = `/product-detail/${productId}`;
            });
        });

        const checkbox     = document.getElementById('themeToggleCheckbox');
        const checkboxMob  = document.getElementById('themeToggleCheckboxMobile');
        const icon         = document.getElementById('themeToggleIcon');
        const iconMob      = document.getElementById('themeToggleIconMobile');
        const labelText    = document.getElementById('themeToggleText');

        const isLight = document.documentElement.getAttribute('data-theme') === 'light';

        // Sync initial state
        if (checkbox)    { checkbox.checked    = isLight; }
        if (checkboxMob) { checkboxMob.checked = isLight; }
        updateUI(isLight);

        function applyTheme(light) {
            if (light) {
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem(STORAGE_KEY, 'light');
            } else {
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem(STORAGE_KEY, 'dark');
            }
            // Keep both toggles in sync
            if (checkbox)    checkbox.checked    = light;
            if (checkboxMob) checkboxMob.checked = light;
            updateUI(light);
        }

        if (checkbox) {
            checkbox.addEventListener('change', function () { applyTheme(this.checked); });
        }
        if (checkboxMob) {
            checkboxMob.addEventListener('change', function () { applyTheme(this.checked); });
        }

        function updateUI(isLight) {
            if (icon) {
                icon.className = isLight ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
            }
            if (iconMob) {
                iconMob.className = isLight ? 'fa-solid fa-sun' : 'fa-solid fa-moon';
            }
            if (labelText) {
                labelText.textContent = isLight ? 'Light Mode' : 'Dark Mode';
            }
        }


        /* ── AJAX Add to Cart ── */
        window.addToCartAjax = function(url, qty = 1, btnElement = null) {
            const formData = new FormData();
            formData.append('quantity', qty);
            
            let originalHtml = '';
            let hadBtnWarning = false;
            let hadBtnOutline = false;
            
            if (btnElement) {
                originalHtml = btnElement.innerHTML;
                hadBtnWarning = btnElement.classList.contains('btn-warning');
                hadBtnOutline = btnElement.classList.contains('btn-outline-warning');
                
                btnElement.style.width = btnElement.offsetWidth + 'px';
                btnElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
            }
            
            fetch(url, {
                method: 'POST',
                headers: { 
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                if(data.success) {
                    // Update all cart badges
                    document.querySelectorAll('.cart-badge-count').forEach(el => {
                        el.innerText = data.cart_count;
                        el.style.display = 'inline-block';
                    });
                    
                    if (btnElement) {
                        btnElement.innerHTML = '<i class="fa-solid fa-check"></i>';
                        btnElement.classList.add('btn-success');
                        btnElement.classList.remove('btn-warning', 'btn-outline-warning');
                    }
                    
                    const bgColor = document.documentElement.getAttribute('data-theme') === 'light' ? '#fff' : '#1f2937';
                    const textColor = document.documentElement.getAttribute('data-theme') === 'light' ? '#000' : '#fff';
                    
                    if (window.Swal) {
                        Swal.fire({
                            toast: true, position: 'top-end', icon: 'success',
                            title: data.message, showConfirmButton: false,
                            timer: 2000, timerProgressBar: true,
                            background: bgColor, color: textColor, iconColor: '#198754'
                        });
                    }
                    
                    if (btnElement) {
                        setTimeout(() => {
                            btnElement.innerHTML = originalHtml;
                            btnElement.style.width = 'auto';
                            btnElement.classList.remove('btn-success');
                            if (hadBtnWarning) btnElement.classList.add('btn-warning');
                            if (hadBtnOutline) btnElement.classList.add('btn-outline-warning');
                        }, 1500);
                    }
                } else {
                    if (btnElement) btnElement.innerHTML = originalHtml;
                    if (window.Swal) Swal.fire({ icon: 'error', title: 'Oops...', text: data.message });
                    else alert(data.message);
                }
            })
            .catch(err => {
                console.error(err);
                if (btnElement) btnElement.innerHTML = originalHtml;
            });
        };

        // Attach to all Add to Cart links
        document.querySelectorAll('a[href*="/add-to-cart/"]').forEach(link => {
            link.addEventListener('click', function(e) {
                if (window.location.pathname === '/cart') return; // Allow normal reload on Cart page
                e.preventDefault();
                window.addToCartAjax(this.href, 1, this);
            });
        });
    });
})();
