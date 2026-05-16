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
        document.querySelectorAll('a[href^="/add-to-cart/"]').forEach(link => {
            link.addEventListener('click', function(e) {
                // Let the cart page reload normally so totals and lists update
                if (window.location.pathname === '/cart') return;
                
                e.preventDefault();
                const originalHtml = this.innerHTML;
                const originalWidth = this.offsetWidth;
                const hadBtnWarning = this.classList.contains('btn-warning');
                const hadBtnOutline = this.classList.contains('btn-outline-warning');
                
                // Show loading state
                this.style.width = originalWidth + 'px';
                this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
                
                fetch(this.href)
                    .then(() => {
                        // Update the cart badge
                        const cartBadge = document.querySelector('.cart-icon .badge');
                        if (cartBadge) {
                            let current = parseInt(cartBadge.innerText);
                            cartBadge.innerText = current + 1;
                        } else {
                            // Create badge if it didn't exist
                            const cartIcon = document.querySelector('.cart-icon');
                            if (cartIcon) {
                                cartIcon.insertAdjacentHTML('beforeend', '<span class="badge rounded-pill bg-danger" style="position: absolute; top: -8px; right: -8px; font-size: 0.65rem; padding: 0.3rem 0.45rem;">1</span>');
                            }
                        }
                        
                        // Show success state
                        this.innerHTML = '<i class="fa-solid fa-check"></i>';
                        this.classList.add('btn-success');
                        this.classList.remove('btn-warning', 'btn-outline-warning');
                        
                        // Trigger SweetAlert popup
                        if (window.Swal) {
                            Swal.fire({
                                icon: 'success',
                                title: 'Success!',
                                text: 'Item added to your cart.',
                                confirmButtonColor: '#ffc107',
                                background: '#1a1a1a',
                                color: '#fff',
                                timer: 2000,
                                timerProgressBar: true
                            });
                        }
                        
                        setTimeout(() => {
                            this.innerHTML = originalHtml;
                            this.style.width = 'auto';
                            this.classList.remove('btn-success');
                            if (hadBtnWarning) this.classList.add('btn-warning');
                            if (hadBtnOutline) this.classList.add('btn-outline-warning');
                        }, 1500);
                    })
                    .catch(err => {
                        console.error('Error adding to cart:', err);
                        this.innerHTML = originalHtml;
                    });
            });
        });
    });
})();
