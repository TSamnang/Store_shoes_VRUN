"""
One-shot template reorganizer for VRUN Flask project.
Run: python reorganize_templates.py
"""
import os, shutil, re

ROOT     = os.path.dirname(os.path.abspath(__file__))
OLD_DIR  = os.path.join(ROOT, 'templates', 'front')
TMPL_DIR = os.path.join(ROOT, 'templates')
APP_FILE = os.path.join(ROOT, 'app.py')

# ── New folder structure map: old filename -> new relative path ─────────────
FILE_MAP = {
    'navbar.html'               : 'base/navbar.html',
    'flash_messages.html'       : 'base/flash_messages.html',
    'login.html'                : 'auth/login.html',
    'register.html'             : 'auth/register.html',
    'homepage.html'             : 'shop/homepage.html',
    'category.html'             : 'shop/category.html',
    'product.html'              : 'shop/product.html',
    'product_detail.html'       : 'shop/product_detail.html',
    'cart.html'                 : 'cart/cart.html',
    'checkout.html'             : 'cart/checkout.html',
    'profile.html'              : 'account/profile.html',
    'settings.html'             : 'account/settings.html',
    'order.html'                : 'account/order.html',
    'order_index.html'          : 'account/order_index.html',
    'order_receipt.html'        : 'account/order_receipt.html',
    'admin.html'                : 'admin/dashboard.html',
    'admin_categories.html'     : 'admin/categories.html',
    'admin_product_detail.html' : 'admin/product_detail.html',
    'admin_reviews.html'        : 'admin/reviews.html',
    'admin_users.html'          : 'admin/users.html',
    'inbox.html'                : 'admin/inbox.html',
}

# ── app.py render_template replacements ─────────────────────────────────────
RENDER_MAP = {
    "render_template('front/homepage.html'"              : "render_template('shop/homepage.html'",
    "render_template('front/category.html'"              : "render_template('shop/category.html'",
    "render_template('front/product.html'"               : "render_template('shop/product.html'",
    "render_template('front/product_detail.html'"        : "render_template('shop/product_detail.html'",
    "render_template('front/cart.html'"                  : "render_template('cart/cart.html'",
    "render_template('front/checkout.html'"              : "render_template('cart/checkout.html'",
    "render_template('front/login.html'"                 : "render_template('auth/login.html'",
    "render_template('front/register.html'"              : "render_template('auth/register.html'",
    "render_template('front/profile.html'"               : "render_template('account/profile.html'",
    "render_template('front/settings.html'"              : "render_template('account/settings.html'",
    "render_template('front/order.html'"                 : "render_template('account/order.html'",
    "render_template('front/order_index.html'"           : "render_template('account/order_index.html'",
    "render_template('front/order_receipt.html'"         : "render_template('account/order_receipt.html'",
    "render_template('front/admin.html'"                 : "render_template('admin/dashboard.html'",
    "render_template('front/admin_categories.html'"      : "render_template('admin/categories.html'",
    "render_template('front/admin_product_detail.html'"  : "render_template('admin/product_detail.html'",
    "render_template('front/admin_reviews.html'"         : "render_template('admin/reviews.html'",
    "render_template('front/admin_users.html'"           : "render_template('admin/users.html'",
    "render_template('front/inbox.html'"                 : "render_template('admin/inbox.html'",
}

def run():
    # 1. Create new subdirectories
    for folder in ('base', 'auth', 'shop', 'cart', 'account', 'admin'):
        os.makedirs(os.path.join(TMPL_DIR, folder), exist_ok=True)
        print(f'  [DIR] templates/{folder}/')

    # 2. Copy + patch each template file
    for old_name, new_rel in FILE_MAP.items():
        src = os.path.join(OLD_DIR, old_name)
        dst = os.path.join(TMPL_DIR, new_rel.replace('/', os.sep))

        if not os.path.exists(src):
            print(f'  [SKIP] {old_name} — not found')
            continue

        with open(src, 'r', encoding='utf-8') as f:
            content = f.read()

        # Fix include paths inside templates
        content = content.replace(
            "{% include 'front/navbar.html' %}",
            "{% include 'base/navbar.html' %}"
        )
        content = content.replace(
            "{% include 'front/flash_messages.html' %}",
            "{% include 'base/flash_messages.html' %}"
        )

        with open(dst, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f'  [OK]   front/{old_name} -> {new_rel}')

    # 3. Update render_template() calls in app.py
    with open(APP_FILE, 'r', encoding='utf-8') as f:
        app_content = f.read()

    for old_call, new_call in RENDER_MAP.items():
        app_content = app_content.replace(old_call, new_call)

    with open(APP_FILE, 'w', encoding='utf-8') as f:
        f.write(app_content)

    print('\n  [OK]   app.py render_template paths updated')
    print('\nDone! Old templates/front/ folder is kept as backup.')
    print('Flask MUST restart to pick up the new template paths.\n')

if __name__ == '__main__':
    run()
