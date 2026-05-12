# =============================================================================
#  IMPORTS
# =============================================================================
import os
from datetime import datetime
from decimal import Decimal
from flask import (
    Flask, render_template, redirect, url_for,
    request, session, g, flash, abort
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
from bson.objectid import ObjectId
from bson.errors import InvalidId

# =============================================================================
#  APP CONFIGURATION
# =============================================================================
app = Flask(__name__)

# Secret key — change this to a random string before deploying!
app.secret_key = 'replace-with-a-secure-secret'

# Where uploaded product images will be saved
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# MongoDB connection settings
app.config['MONGO_URI'] = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
app.config['MONGO_DBNAME'] = os.environ.get('MONGO_DBNAME', 'StoreShoes')

# Flag so we only run DB setup once per process
app.config['DB_INITIALIZED'] = False

# MongoDB Client
mongo_client = None

# =============================================================================
#  DATABASE HELPERS
# =============================================================================

def get_db():
    """
    Returns the active database connection.
    """
    global mongo_client
    if mongo_client is None:
        mongo_client = MongoClient(app.config['MONGO_URI'])
    return mongo_client[app.config['MONGO_DBNAME']]

def format_doc(doc):
    """Converts MongoDB document to use string 'id' instead of '_id'."""
    if doc:
        if '_id' in doc:
            doc['id'] = str(doc['_id'])
            del doc['_id']
        if 'created_at' in doc and isinstance(doc['created_at'], str):
            try:
                doc['created_at'] = datetime.fromisoformat(doc['created_at'])
            except ValueError:
                pass
    return doc

# =============================================================================
#  FILE UPLOAD HELPERS
# =============================================================================

def allowed_file(filename):
    """Checks if a given filename has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_image(upload):
    """
    Saves an uploaded image file securely and returns the relative path.
    Returns None if the upload is invalid.
    """
    if upload and allowed_file(upload.filename):
        filename = secure_filename(upload.filename)
        target_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        upload.save(target_path)
        return f'images/{filename}'
    return None

# =============================================================================
#  USER AUTHENTICATION HELPERS
# =============================================================================

def create_user(username, email, password, role='customer'):
    """Creates a new user in the database with a hashed password."""
    password_hash = generate_password_hash(password)
    db = get_db()
    result = db.users.insert_one({
        'username': username,
        'email': email,
        'password_hash': password_hash,
        'role': role,
        'shipping_addresses': [], # Array of addresses
        'wishlist': [],           # Array of product_ids
        'created_at': datetime.utcnow().isoformat()
    })
    return str(result.inserted_id)

def get_user_by_id(user_id):
    """Fetches a user dictionary by their primary ID."""
    db = get_db()
    try:
        user = db.users.find_one({'_id': ObjectId(str(user_id))})
        return format_doc(user)
    except (InvalidId, TypeError, ValueError):
        return None

def get_user_by_email(email):
    """Fetches a user dictionary by their email address."""
    db = get_db()
    user = db.users.find_one({'email': email})
    return format_doc(user)

def authenticate_user(email, password):
    """
    Validates a user's login credentials.
    Returns the user dictionary if valid, or None if invalid.
    """
    user = get_user_by_email(email)
    if user and check_password_hash(user['password_hash'], password):
        return user
    return None

# =============================================================================
#  PRODUCT HELPERS
# =============================================================================

def get_products(category=None, limit=None, max_price=None, search=None, page=1, per_page=10, return_count=False):
    """
    Fetches products from the database, optionally filtered by category,
    max price, search string, or limited to a specific number of items.
    """
    db = get_db()
    query = {}

    if category:
        if isinstance(category, (list, tuple)):
            query['category'] = {'$in': category}
        else:
            query['category'] = category

    if max_price is not None and str(max_price).strip() != '':
        try:
            max_price_value = float(max_price)
            query['price'] = {'$lte': max_price_value}
        except ValueError:
            pass

    if search:
        search_value = search.strip()
        query['$or'] = [
            {'name': {'$regex': search_value, '$options': 'i'}},
            {'description': {'$regex': search_value, '$options': 'i'}},
            {'category': {'$regex': search_value, '$options': 'i'}},
            {'brand': {'$regex': search_value, '$options': 'i'}}
        ]

    total_count = 0
    if return_count:
        total_count = db.products.count_documents(query)

    cursor = db.products.find(query).sort('created_at', -1)
    if limit:
        cursor = cursor.limit(int(limit))
    else:
        skip = (page - 1) * per_page
        cursor = cursor.skip(skip).limit(per_page)
        
    products = [format_doc(doc) for doc in cursor]
    if return_count:
        return products, total_count
    return products

def get_product_by_id(product_id):
    """Fetches a single product by its primary ID."""
    db = get_db()
    try:
        product = db.products.find_one({'_id': ObjectId(str(product_id))})
        return format_doc(product)
    except (InvalidId, TypeError, ValueError):
        return None

def get_category_counts():
    """
    Returns a list of dictionaries containing category names
    and the number of products in each category.
    """
    db = get_db()
    pipeline = [
        {'$group': {'_id': '$category', 'total': {'$sum': 1}}}
    ]
    results = db.products.aggregate(pipeline)
    return [{'category': r['_id'], 'count': r['total']} for r in results]

# =============================================================================
#  ORDER HELPERS
# =============================================================================

def get_order(order_id):
    """Fetches an order dictionary by its primary ID."""
    db = get_db()
    try:
        order = db.orders.find_one({'_id': ObjectId(str(order_id))})
        if order:
            order['total'] = Decimal(str(order['total']))
        return format_doc(order)
    except (InvalidId, TypeError, ValueError):
        return None

def get_order_items(order_id):
    """Fetches all items associated with a specific order ID."""
    order = get_order(order_id)
    if not order:
        return []
    items = order.get('items', [])
    for item in items:
        item['price'] = Decimal(str(item['price']))
    return items

def create_order(user_id, shipping_address, shipping_method, total, items, payment_method='COD', status='Received'):
    """
    Creates a new order in the database.
    Order items and payment details are embedded directly inside the order document.
    """
    db = get_db()
    result = db.orders.insert_one({
        'user_id': str(user_id),
        'shipping_address': shipping_address,
        'shipping_method': shipping_method,
        'total': float(total),
        'status': status,
        'items': items,
        'payment': {
            'method': payment_method,
            'status': 'Pending' if payment_method == 'COD' else 'Paid'
        },
        'created_at': datetime.utcnow().isoformat()
    })
    return str(result.inserted_id)

def delete_order(order_id):
    """Permanently deletes an order."""
    db = get_db()
    try:
        db.orders.delete_one({'_id': ObjectId(str(order_id))})
    except (InvalidId, TypeError, ValueError):
        pass

# =============================================================================
#  WISHLIST, REVIEWS & COUPON HELPERS
# =============================================================================

def get_reviews(product_id):
    db = get_db()
    reviews = list(db.reviews.find({'product_id': str(product_id)}).sort('created_at', -1))
    return [format_doc(r) for r in reviews]

def get_coupon(code):
    db = get_db()
    coupon = db.coupons.find_one({'code': code.upper(), 'active': True})
    return format_doc(coupon)

# =============================================================================
#  APP INITIALIZATION & REQUEST HOOKS
# =============================================================================

@app.before_request
def init_db():
    """
    Initializes the database schema and seeds initial data.
    """
    if app.config['DB_INITIALIZED']:
        return

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    db = get_db()

    db.users.create_index('email', unique=True)
    db.coupons.create_index('code', unique=True)

    if db.users.count_documents({}) == 0:
        create_user('admin', 'admin@werun.com', '@admin', role='admin')
        create_user('customer', 'user@werun.com', 'user123', role='customer')

    if db.products.count_documents({}) == 0:
        sample_products = [
            ('Air Jordan 1 Retro High OG', 'Sneaker Shoes', 'Nike', 'Iconic daily sneaker with premium leather.', 'The Air Jordan 1 Retro High OG is a timeless classic that started it all.', 180.00, 30, 'images/Air Jordan 1 Retro High OG.png'),
            ('Zoom Freak 4 GS', 'Sport Shoes', 'Nike', 'High performance basketball shoe built for speed.', 'Designed for explosive players.', 120.00, 24, 'images/Zoom Freak 4 GS.png'),
            ('Nike Hot Step 2 NOCTA', 'Casual Shoes', 'Nike x Drake', 'Premium street style sneakers with modern comfort.', 'A collaboration with Drake.', 200.00, 18, 'images/Nike Hot Step 2 NOCTA.png'),
            ('Nike Mens Promina', 'Casual Shoes', 'Nike', 'Comfortable running shoes for everyday wear.', 'The Nike Mens Promina delivers lightweight comfort.', 95.00, 15, 'images/Nike Mens Promina.png'),
            ('Nike LeBron Soldier 11 GS', 'Sport Shoes', 'Nike', 'Stable basketball shoe with strong lockdown.', 'Built for power and stability.', 135.00, 22, 'images/Nike LeBron Soldier 11 GS.png'),
            ('Nike Air Jordan 1 Retro High Flyknit Wolf Grey', 'Sneaker Shoes', 'Nike', 'Lightweight Air Jordan with premium Flyknit.', 'This modern take on the Jordan 1.', 110.00, 20, 'images/Nike Air Jordan 1 Retro High Flyknit Wolf Grey.png'),
            ('G176 Multi-Blend NX Sneakers', 'Casual Shoes', 'Generic', 'Fashion forward sneakers with all-day comfort.', 'The G176 Multi-Blend NX combines mixed materials.', 140.00, 15, 'images/G176 Multi-Blend NX Sneakers.png'),
            ('Nike Mercurial Superfly', 'Sport Shoes', 'Nike', 'Elite soccer cleat built for speed and touch.', 'The Mercurial Superfly is engineered for speed.', 220.00, 12, 'images/Nike Mercurial Superfly.jpg'),
        ]
        for name, category, brand, description, detail, price, stock, image in sample_products:
            db.products.insert_one({
                'name': name,
                'category': category,
                'brand': brand,
                'description': description,
                'detail': detail,
                'price': float(price),
                'stock': stock,
                'image': image,
                'images': [image], # additional images
                'variants': [{'size': '9', 'color': 'Default', 'stock': stock}], # sizing/colors
                'created_at': datetime.utcnow().isoformat()
            })

    if db.coupons.count_documents({}) == 0:
        db.coupons.insert_one({
            'code': 'WELCOME10', 
            'discount_percent': 10, 
            'active': True,
            'valid_until': '2030-01-01'
        })

    app.config['DB_INITIALIZED'] = True

@app.before_request
def load_current_user():
    g.user = None
    if session.get('user_id'):
        g.user = get_user_by_id(session['user_id'])

def common_context(active_page=None):
    return {
        'current_user': g.user,
        'is_admin': bool(g.user and g.user.get('role') == 'admin'),
        'cart_count': sum(session.get('cart', {}).values()),
        'active_page': active_page,
    }

# =============================================================================
#  PUBLIC ROUTES
# =============================================================================

@app.route('/')
def goto():
    return redirect(url_for('homepage'))

@app.route('/homepage')
def homepage():
    featured_products = get_products(limit=4)
    latest_products = get_products(limit=8)
    categories = get_category_counts()
    return render_template(
        'front/homepage.html',
        featured_products=featured_products,
        latest_products=latest_products,
        categories=categories,
        **common_context('homepage')
    )

@app.route('/product')
def product():
    selected_categories = request.args.getlist('category')
    max_price = request.args.get('max_price', '').strip()
    search_query = request.args.get('q', '').strip()
    
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
        
    per_page = 10
    
    categories = get_category_counts()
    products, total_count = get_products(
        category=selected_categories or None,
        max_price=max_price,
        search=search_query,
        page=page,
        per_page=per_page,
        return_count=True
    )
    
    total_pages = (total_count + per_page - 1) // per_page
        
    return render_template(
        'front/product.html',
        products=products,
        categories=categories,
        selected_categories=selected_categories,
        selected_max_price=max_price or '500',
        q=search_query,
        page=page,
        total_pages=total_pages,
        **common_context('product')
    )

@app.route('/product-detail/<product_id>')
def product_detail(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return redirect(url_for('product'))
        
    related_products = [
        p for p in get_products(product['category'], limit=4) 
        if p['id'] != product['id']
    ]
    
    reviews = get_reviews(product_id)
    
    return render_template(
        'front/product_detail.html',
        product=product,
        related_products=related_products,
        reviews=reviews,
        **common_context()
    )

@app.route('/category')
def category():
    selected_category = request.args.get('category')
    categories = get_category_counts()
    products = get_products(category=selected_category) if selected_category else get_products()
    return render_template(
        'front/category.html',
        categories=categories,
        products=products,
        selected_category=selected_category,
        **common_context('category')
    )

# =============================================================================
#  CART & CHECKOUT ROUTES
# =============================================================================

@app.route('/add-to-cart/<product_id>')
def add_to_cart(product_id):
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(request.referrer or url_for('product'))
        
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    
    flash(f'Added {product["name"]} to cart.', 'success')
    return redirect(request.referrer or url_for('cart'))

@app.route('/cart')
def cart():
    cart_data = session.get('cart', {})
    cart_items = []
    subtotal = Decimal('0.00')
    
    for product_id, quantity in cart_data.items():
        product = get_product_by_id(product_id)
        if not product: continue
            
        total = Decimal(str(product['price'])) * quantity
        subtotal += total
        
        item = dict(product)
        item['quantity'] = quantity
        item['total'] = total
        cart_items.append(item)
        
    return render_template(
        'front/cart.html',
        cart_items=cart_items,
        subtotal=subtotal,
        total=subtotal,
        **common_context('cart')
    )

@app.route('/cart/remove/<product_id>')
def cart_remove(product_id):
    cart_data = session.get('cart', {})
    cart_data.pop(str(product_id), None)
    session['cart'] = cart_data
    flash('Item removed from cart.', 'success')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    login_redirect = require_login()
    if login_redirect: return login_redirect

    cart_data = session.get('cart', {})
    cart_items = []
    subtotal = Decimal('0.00')
    
    for product_id, quantity in cart_data.items():
        product = get_product_by_id(product_id)
        if not product: continue
            
        total = Decimal(str(product['price'])) * quantity
        subtotal += total
        
        item = dict(product)
        item['quantity'] = quantity
        item['total'] = total
        cart_items.append(item)
        
    shipping_rates = {
        'Express': Decimal('15.00'),
        'Standard': Decimal('5.00'),
        'Pickup': Decimal('0.00')
    }

    if request.method == 'POST':
        shipping_address = request.form.get('shipping_address', '').strip()
        shipping_method = request.form.get('shipping_method', 'Express').strip()
        payment_method = request.form.get('payment', 'card').strip()
        
        shipping_cost = shipping_rates.get(shipping_method, Decimal('15.00'))
        total = subtotal + shipping_cost if subtotal > Decimal('0.00') else Decimal('0.00')
        
        if not shipping_address:
            flash('Please provide a shipping address.', 'danger')
            return render_template('front/checkout.html', cart_items=cart_items, subtotal=subtotal, total=total, shipping_cost=shipping_cost, **common_context('checkout'))
            
        if not cart_items:
            flash('Your cart is empty.', 'warning')
            return redirect(url_for('cart'))

        # Prepare embedded items list
        embedded_items = []
        for item in cart_items:
            embedded_items.append({
                'product_id': str(item['id']),
                'product_name': item['name'],
                'quantity': item['quantity'],
                'price': float(item['price']),
                'image': item['image']
            })

        order_id = create_order(g.user['id'], shipping_address, shipping_method, total, embedded_items, payment_method)
        session['cart'] = {}
        
        flash('Your order has been received.', 'success')
        return redirect(url_for('order_receipt', order_id=order_id))

    shipping_cost = Decimal('15.00') # Default to Express
    total = subtotal + shipping_cost if subtotal > Decimal('0.00') else Decimal('0.00')
    return render_template('front/checkout.html', cart_items=cart_items, subtotal=subtotal, total=total, shipping_cost=shipping_cost, **common_context('checkout'))

# =============================================================================
#  USER ACCOUNT & ORDER ROUTES
# =============================================================================

@app.route('/order')
def order():
    login_redirect = require_login()
    if login_redirect: return login_redirect

    db = get_db()
    orders = list(db.orders.find({'user_id': str(g.user['id'])}).sort('created_at', -1))
    orders = [format_doc(o) for o in orders]
    
    return render_template('front/order_index.html', orders=orders, **common_context('order'))

@app.route('/order/<order_id>')
def order_receipt(order_id):
    login_redirect = require_login()
    if login_redirect: return login_redirect

    order = get_order(order_id)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('order'))
        
    if order['user_id'] != str(g.user['id']) and g.user.get('role') != 'admin':
        abort(403)

    items = get_order_items(order_id)
    subtotal = sum(Decimal(str(item['price'])) * item['quantity'] for item in items)
    shipping_cost = Decimal(str(order['total'])) - subtotal
    item_count = sum(item['quantity'] for item in items)
    
    return render_template(
        'front/order_receipt.html',
        order=order,
        items=items,
        subtotal=subtotal,
        shipping_cost=shipping_cost if shipping_cost > 0 else Decimal('0.00'),
        item_count=item_count,
        **common_context()
    )

@app.route('/order/delete/<order_id>', methods=['POST'])
def order_delete(order_id):
    login_redirect = require_login()
    if login_redirect: return login_redirect

    order = get_order(order_id)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('order'))
        
    if order['user_id'] != str(g.user['id']) and g.user.get('role') != 'admin':
        abort(403)

    if order['status'] == 'Cancelled':
        flash('Order is already cancelled.', 'warning')
        return redirect(url_for('order'))

    db = get_db()
    db.orders.update_one({'_id': ObjectId(str(order_id))}, {'$set': {'status': 'Cancelled'}})
    flash(f'Order #{order_id} has been cancelled.', 'success')
    
    if g.user.get('role') == 'admin':
        return redirect(url_for('inbox'))
    return redirect(url_for('order'))

@app.route('/order/hard-delete/<order_id>', methods=['POST'])
def order_hard_delete(order_id):
    login_redirect = require_login()
    if login_redirect: return login_redirect
        
    order = get_order(order_id)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('order'))
        
    if order['user_id'] != str(g.user['id']) and g.user.get('role') != 'admin':
        abort(403)
        
    delete_order(order_id)
    flash(f'Order #{order_id} permanently deleted.', 'success')
    
    if g.user.get('role') == 'admin':
        return redirect(url_for('inbox'))
    return redirect(url_for('order'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    login_redirect = require_login()
    if login_redirect: return login_redirect

    db = get_db()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            new_username = request.form.get('username', '').strip()
            new_email = request.form.get('email', '').strip().lower()
            
            if not new_username or not new_email:
                flash('Username and email are required.', 'danger')
            else:
                existing = get_user_by_email(new_email)
                if existing and str(existing['id']) != str(g.user['id']):
                    flash('That email is already in use.', 'danger')
                else:
                    db.users.update_one({'_id': ObjectId(str(g.user['id']))}, {'$set': {'username': new_username, 'email': new_email}})
                    flash('Profile updated successfully.', 'success')
            return redirect(url_for('profile'))

        if action == 'change_password':
            current_pwd = request.form.get('current_password', '')
            new_pwd = request.form.get('new_password', '')
            confirm_pwd = request.form.get('confirm_password', '')
            user = get_user_by_id(g.user['id'])
            
            if not check_password_hash(user['password_hash'], current_pwd):
                flash('Current password is incorrect.', 'danger')
            elif len(new_pwd) < 6:
                flash('New password must be at least 6 characters.', 'danger')
            elif new_pwd != confirm_pwd:
                flash('Passwords do not match.', 'danger')
            else:
                db.users.update_one({'_id': ObjectId(str(g.user['id']))}, {'$set': {'password_hash': generate_password_hash(new_pwd)}})
                flash('Password changed successfully.', 'success')
            return redirect(url_for('profile'))

    orders = list(db.orders.find({'user_id': str(g.user['id'])}).sort('created_at', -1))
    orders = [format_doc(o) for o in orders]
    return render_template('front/profile.html', orders=orders, order_count=len(orders), **common_context('profile'))

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    login_redirect = require_login()
    if login_redirect: return login_redirect

    db = get_db()

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'delete_account':
            confirm_input = request.form.get('confirm_delete', '').strip()
            if confirm_input != g.user['email']:
                flash('Email confirmation did not match. Account not deleted.', 'danger')
                return redirect(url_for('settings'))
                
            db.orders.delete_many({'user_id': str(g.user['id'])})
            db.users.delete_one({'_id': ObjectId(str(g.user['id']))})
            
            session.clear()
            flash('Your account has been permanently deleted.', 'success')
            return redirect(url_for('login'))

    return render_template('front/settings.html', **common_context('settings'))

# =============================================================================
#  AUTHENTICATION ROUTES
# =============================================================================

def require_login():
    if not g.user:
        flash('Please log in to continue.', 'warning')
        return redirect(url_for('login', next=request.path))

def require_admin():
    if not g.user or g.user.get('role') != 'admin':
        abort(403)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user: return redirect(url_for('homepage'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        next_url = request.form.get('next') or request.args.get('next')
        
        user = authenticate_user(email, password)
        if user:
            session['user_id'] = str(user['id'])
            flash('Logged in successfully.', 'success')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(url_for('homepage'))
            
        flash('Invalid email or password.', 'danger')
        
    return render_template('front/login.html', **common_context())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user: return redirect(url_for('homepage'))
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()
        
        if not username or not email or not password:
            flash('Please fill out all fields.', 'danger')
        elif get_user_by_email(email):
            flash('Email already registered.', 'danger')
        else:
            create_user(username, email, password)
            user = get_user_by_email(email)
            session['user_id'] = str(user['id'])
            flash('Account created successfully.', 'success')
            return redirect(url_for('homepage'))
            
    return render_template('front/register.html', **common_context())

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# =============================================================================
#  ADMIN ROUTES
# =============================================================================

@app.route('/inbox')
def inbox():
    require_admin()
    db = get_db()
    all_orders = []
    for order in db.orders.find().sort('created_at', -1):
        user = get_user_by_id(order['user_id'])
        if user:
            order['username'] = user['username']
            order['email'] = user['email']
        all_orders.append(format_doc(order))
        
    return render_template('front/inbox.html', all_orders=all_orders, **common_context('inbox'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    require_admin()
    db = get_db()
    
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        detail = request.form.get('detail', '').strip()
        price = request.form.get('price', '0').strip()
        stock = request.form.get('stock', '0').strip()
        image_path = request.form.get('image_path', '').strip()
        image_file = request.files.get('image_file')
        
        if not name or not category or not description or not price:
            flash('Please fill all required fields.', 'danger')
        else:
            image = save_image(image_file) if image_file and image_file.filename else None
            image = image or image_path or 'images/logo.png'
            db.products.insert_one({
                'name': name,
                'category': category,
                'brand': 'Generic',
                'description': description,
                'detail': detail,
                'price': float(price),
                'stock': int(stock or 0),
                'image': image,
                'images': [image],
                'variants': [{'size': 'Default', 'color': 'Default', 'stock': int(stock or 0)}],
                'created_at': datetime.utcnow().isoformat()
            })
            flash('Product added successfully.', 'success')
            return redirect(url_for('admin'))
            
    products = get_products()
    return render_template('front/admin.html', products=products, **common_context('admin'))

@app.route('/admin/edit/<product_id>', methods=['GET', 'POST'])
def admin_edit(product_id):
    require_admin()
    db = get_db()
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('admin'))
        
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        detail = request.form.get('detail', '').strip()
        price = request.form.get('price', '0').strip()
        stock = request.form.get('stock', '0').strip()
        image_path = request.form.get('image_path', '').strip()
        image_file = request.files.get('image_file')
        
        if not name or not category or not description or not price:
            flash('Please fill all required fields.', 'danger')
        else:
            image = save_image(image_file) if image_file and image_file.filename else None
            image = image or image_path or product['image']
            
            db.products.update_one(
                {'_id': ObjectId(str(product_id))},
                {'$set': {
                    'name': name,
                    'category': category,
                    'description': description,
                    'detail': detail,
                    'price': float(price),
                    'stock': int(stock or 0),
                    'image': image
                }}
            )
            flash('Product updated successfully.', 'success')
            return redirect(url_for('admin'))
            
        product = get_product_by_id(product_id)
        
    products = get_products()
    return render_template('front/admin.html', products=products, edit_product=product, **common_context('admin'))

@app.route('/admin/delete/<product_id>', methods=['POST'])
def admin_delete(product_id):
    require_admin()
    db = get_db()
    try:
        db.products.delete_one({'_id': ObjectId(str(product_id))})
        flash('Product deleted successfully.', 'success')
    except (InvalidId, TypeError, ValueError):
        flash('Invalid product ID.', 'danger')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
