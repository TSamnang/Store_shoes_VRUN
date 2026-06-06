# =============================================================================
#  IMPORTS
# =============================================================================
import os
import base64
import mimetypes
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
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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
    try:
        if mongo_client is None:
            # Set a 5 second timeout so it doesn't hang Vercel
            mongo_client = MongoClient(app.config['MONGO_URI'], serverSelectionTimeoutMS=5000)
            # Force a connection test
            mongo_client.admin.command('ping')
        return mongo_client[app.config['MONGO_DBNAME']]
    except Exception as e:
        import traceback
        error_msg = f"Database Connection Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
        print(error_msg)
        # If we are in a web request, we can abort with 500 and the message
        from flask import make_response
        abort(make_response(f"<pre>Error connecting to MongoDB. Did you whitelist IP 0.0.0.0/0 in Atlas?\n\n{error_msg}</pre>", 500))

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
        # Ensure category is always a list
        if 'category' not in doc or not doc['category']:
            doc['category'] = []
        elif isinstance(doc['category'], str):
            doc['category'] = [c.strip() for c in doc['category'].split(',') if c.strip()]
        # Ensure variants is always a list
        if 'variants' not in doc or doc['variants'] is None:
            doc['variants'] = []
        # Ensure color_images is always a dict
        if 'color_images' not in doc or doc['color_images'] is None:
            doc['color_images'] = {}
    return doc


# =============================================================================
#  FILE UPLOAD HELPERS
# =============================================================================

def allowed_file(filename):
    """Checks if a given filename has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def save_image(upload):
    """
    Saves an uploaded image file directly as a Base64 string.
    Returns the base64 string or None if the upload is invalid.
    """
    if upload and allowed_file(upload.filename):
        encoded_string = base64.b64encode(upload.read()).decode('utf-8')
        mime_type = upload.mimetype
        return f"data:{mime_type};base64,{encoded_string}"
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

def detect_card_brand(cc_number):
    """Detects credit card brand based on card number digits."""
    clean_number = ''.join(filter(str.isdigit, str(cc_number)))
    if not clean_number:
        return 'Card'
    if clean_number.startswith('4'):
        return 'Visa'
    elif clean_number.startswith(('51', '52', '53', '54', '55')) or (len(clean_number) >= 4 and 2221 <= int(clean_number[:4]) <= 2720):
        return 'Mastercard'
    elif clean_number.startswith(('34', '37')):
        return 'Amex'
    elif clean_number.startswith('6011') or clean_number.startswith(('644', '645', '646', '647', '648', '649')) or clean_number.startswith('65'):
        return 'Discover'
    elif clean_number.startswith(('3528', '3529')) or (len(clean_number) >= 4 and 3530 <= int(clean_number[:4]) <= 3589):
        return 'JCB'
    return 'Card'

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

def get_products(category=None, limit=None, min_price=None, max_price=None, search=None, page=1, per_page=10, return_count=False, discount_only=False, sort='newest'):
    """
    Fetches products from the database, optionally filtered by category,
    min price, max price, search string, discount, or limited to a specific number of items.
    sort options: 'newest', 'price_asc', 'price_desc', 'discount'
    """
    db = get_db()
    query = {}

    if category:
        # Works whether category is stored as a string or an array in MongoDB
        if isinstance(category, (list, tuple)):
            query['category'] = {'$in': category}
        else:
            query['category'] = category  # MongoDB matches string OR array-containing-value

    price_filter = {}
    if min_price is not None and str(min_price).strip() != '':
        try:
            price_filter['$gte'] = float(min_price)
        except ValueError:
            pass

    if max_price is not None and str(max_price).strip() != '':
        try:
            price_filter['$lte'] = float(max_price)
        except ValueError:
            pass

    if price_filter:
        query['price'] = price_filter

    if discount_only:
        query['discount_percent'] = {'$gt': 0}

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

    # Build sort spec
    sort_map = {
        'price_asc':  ('price', 1),
        'price_desc': ('price', -1),
        'discount':   ('discount_percent', -1),
        'newest':     ('created_at', -1),
    }
    sort_field, sort_dir = sort_map.get(sort, ('created_at', -1))
    cursor = db.products.find(query).sort(sort_field, sort_dir)

    if limit:
        cursor = cursor.limit(int(limit))
    else:
        skip = (page - 1) * per_page
        cursor = cursor.skip(skip).limit(per_page)

    products = [format_doc(doc) for doc in cursor]
    # Compute discounted_price for every product
    for p in products:
        pct = float(p.get('discount_percent', 0) or 0)
        p['discount_percent'] = pct
        if pct > 0:
            p['discounted_price'] = round(float(p['price']) * (1 - pct / 100), 2)
        else:
            p['discounted_price'] = None

    # When sorting by price we want effective (discounted) price order.
    # MongoDB sorts on raw `price`, so re-sort in Python for discount cases.
    if sort == 'price_asc':
        products.sort(key=lambda p: p['discounted_price'] if p['discounted_price'] else p['price'])
    elif sort == 'price_desc':
        products.sort(key=lambda p: p['discounted_price'] if p['discounted_price'] else p['price'], reverse=True)

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
        {'$unwind': {'path': '$category', 'preserveNullAndEmptyArrays': False}},
        {'$group': {'_id': '$category', 'total': {'$sum': 1}}}
    ]
    results = db.products.aggregate(pipeline)
    return [{'category': r['_id'], 'count': r['total']} for r in results if r['_id']]

def get_all_categories():
    db = get_db()
    if db.categories.count_documents({}) == 0:
        defaults = ['Sneaker','Sport','Running','Casual','Formal','Basketball','Football','Sandal','Boot','Kids']
        db.categories.insert_many([{'name': c} for c in defaults])
    cats = list(db.categories.find().sort('name', 1))
    for c in cats:
        c['id'] = str(c['_id'])
    return cats

def get_discounted_products(limit=8):
    """Fetches products that have a discount_percent > 0, sorted by discount descending."""
    db = get_db()
    cursor = db.products.find({'discount_percent': {'$gt': 0}}).sort('discount_percent', -1).limit(limit)
    products = [format_doc(doc) for doc in cursor]
    for p in products:
        pct = float(p.get('discount_percent', 0))
        p['discounted_price'] = round(float(p['price']) * (1 - pct / 100), 2)
    return products

def get_effective_price(product):
    """Returns the final price for a product, applying discount_percent if set."""
    pct = float(product.get('discount_percent', 0) or 0)
    original = float(product.get('price', 0))
    if pct > 0:
        return round(original * (1 - pct / 100), 2)
    return original

# =============================================================================
#  ORDER HELPERS
# =============================================================================

def send_telegram_notification(order_id, user, shipping_address, shipping_method, shipping_cost, total, items):
    """
    Sends a formatted HTML notification message to a Telegram bot.
    Safe-guarded to fail silently if the bot is not configured or fails.
    """
    import urllib.request
    import urllib.parse
    import json

    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        print("Telegram configuration missing. Skipping order notification.")
        return False

    # Clean potential surrounding quotes (common when copying from .env to Vercel)
    token = token.strip('\'"')
    chat_id = chat_id.strip('\'"')

    def escape_html(text):
        if not text:
            return ""
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Format the item list and escape names to prevent HTML parsing errors
    item_rows = []
    for item in items:
        name = item.get('product_name', 'Product')
        qty = item.get('quantity', 1)
        price = item.get('price', 0.0)
        item_rows.append(f"• {qty}x {escape_html(name)} - ${price:.2f}")
    items_list = "\n".join(item_rows)

    username = user.get('username') or user.get('name') or 'Customer'
    email = user.get('email', '')

    message = (
        f"<b>📦 New Order Received!</b>\n\n"
        f"<b>Order ID:</b> <code>{escape_html(order_id)}</code>\n"
        f"<b>Customer:</b> {escape_html(username)} ({escape_html(email)})\n"
        f"<b>Shipping Method:</b> {escape_html(shipping_method)} (${shipping_cost:.2f})\n"
        f"<b>Address:</b> {escape_html(shipping_address)}\n"
        f"<b>Total Amount:</b> ${total:.2f}\n\n"
        f"<b>🛒 Items Ordered:</b>\n"
        f"{items_list}"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }

    try:
        data = urllib.parse.urlencode(payload).encode('utf-8')
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            res_body = response.read().decode('utf-8')
            res_json = json.loads(res_body)
            return res_json.get('ok', False)
    except Exception as e:
        print(f"Error sending Telegram notification: {e}")
        return False

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

def create_order(user_id, shipping_address, shipping_method, shipping_cost, total, items, payment_method='COD', status='Ordering'):
    """
    Creates a new order in the database.
    Order items and payment details are embedded directly inside the order document.
    """
    db = get_db()
    result = db.orders.insert_one({
        'user_id': str(user_id),
        'shipping_address': shipping_address,
        'shipping_method': shipping_method,
        'shipping_cost': float(shipping_cost),
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

def get_product_avg_rating(product_id):
    """Calculates the average star rating for a product."""
    db = get_db()
    pipeline = [
        {'$match': {'product_id': str(product_id)}},
        {'$group': {'_id': None, 'avg': {'$avg': '$rating'}, 'count': {'$sum': 1}}}
    ]
    result = list(db.reviews.aggregate(pipeline))
    if result:
        return round(result[0]['avg'], 1), result[0]['count']
    return 0.0, 0

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

    try:
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    except OSError:
        pass  # Vercel serverless has a read-only filesystem, ignore if we can't create dirs
    db = get_db()

    db.users.create_index('email', unique=True)
    db.coupons.create_index('code', unique=True)
    db.reviews.create_index([('product_id', 1), ('user_id', 1)])

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
        def get_base64_image(filepath):
            try:
                full_path = os.path.join(app.root_path, 'static', filepath)
                if not os.path.exists(full_path):
                    return filepath
                with open(full_path, 'rb') as f:
                    encoded_string = base64.b64encode(f.read()).decode('utf-8')
                mime_type, _ = mimetypes.guess_type(full_path)
                if not mime_type:
                    mime_type = 'image/png'
                return f"data:{mime_type};base64,{encoded_string}"
            except Exception:
                return filepath

        for name, category, brand, description, detail, price, stock, image_path in sample_products:
            b64_image = get_base64_image(image_path)
            db.products.insert_one({
                'name': name,
                'category': category,
                'brand': brand,
                'description': description,
                'detail': detail,
                'price': float(price),
                'stock': stock,
                'image': b64_image,
                'images': [b64_image], # additional images
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
    inbox_count = 0
    if g.user and g.user.get('role') == 'admin':
        try:
            db = get_db()
            inbox_count = db.orders.count_documents({'status': 'Ordering', 'is_read': {'$ne': True}})
        except Exception:
            inbox_count = 0
    return {
        'current_user': g.user,
        'is_admin': bool(g.user and g.user.get('role') == 'admin'),
        'cart_count': sum(session.get('cart', {}).values()),
        'active_page': active_page,
        'inbox_count': inbox_count,
    }

# =============================================================================
#  PUBLIC ROUTES
# =============================================================================

@app.route('/')
def goto():
    return redirect(url_for('homepage'))

@app.route('/about')
def about_us():
    return render_template('information/about_us.html', **common_context('about'))

@app.route('/contact')
def contact_us():
    return render_template('information/contact_us.html', **common_context('contact'))

@app.route('/homepage')
def homepage():
    featured_products = get_products(limit=4)
    latest_products = get_products(limit=8)
    categories = get_category_counts()
    discounted_products = get_discounted_products(limit=8)
    # Products for visual grid section (pick products 5-8 so they differ from featured)
    all_products = get_products(limit=12)
    grid_products = all_products[4:8] if len(all_products) > 4 else all_products[:4]
    # One hero product for the banner
    banner_product = all_products[0] if all_products else None
    return render_template(
        'shop/homepage.html',
        featured_products=featured_products,
        latest_products=latest_products,
        categories=categories,
        discounted_products=discounted_products,
        grid_products=grid_products,
        banner_product=banner_product,
        **common_context('homepage')
    )

@app.route('/product')
def product():
    selected_categories = request.args.getlist('category')
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    search_query = request.args.get('q', '').strip()
    discount_only = request.args.get('discount_only') == '1'
    sort = request.args.get('sort', 'newest')
    if sort not in ('newest', 'price_asc', 'price_desc', 'discount'):
        sort = 'newest'

    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1

    per_page = 10

    categories = get_category_counts()
    products, total_count = get_products(
        category=selected_categories or None,
        min_price=min_price,
        max_price=max_price,
        search=search_query,
        page=page,
        per_page=per_page,
        return_count=True,
        discount_only=discount_only,
        sort=sort
    )

    total_pages = (total_count + per_page - 1) // per_page

    return render_template(
        'shop/product.html',
        products=products,
        categories=categories,
        all_categories=get_all_categories(),
        selected_categories=selected_categories,
        selected_min_price=min_price or '0',
        selected_max_price=max_price or '999999',
        q=search_query,
        page=page,
        total_pages=total_pages,
        selected_discount=discount_only,
        selected_sort=sort,
        **common_context('product')
    )

@app.route('/product-detail/<product_id>')
def product_detail(product_id):
    product = get_product_by_id(product_id)
    if not product:
        return redirect(url_for('product'))

    # Compute discounted price for the detail page
    pct = float(product.get('discount_percent', 0) or 0)
    product['discount_percent'] = pct
    if pct > 0:
        product['discounted_price'] = round(float(product['price']) * (1 - pct / 100), 2)
    else:
        product['discounted_price'] = None

    related_products = [
        p for p in get_products(product['category'], limit=4)
        if p['id'] != product['id']
    ]

    reviews = get_reviews(product_id)
    avg_rating, review_count = get_product_avg_rating(product_id)

    # Check if current user already submitted a review
    user_review = None
    if g.user:
        db = get_db()
        ur = db.reviews.find_one({'product_id': str(product_id), 'user_id': str(g.user['id'])})
        user_review = format_doc(ur) if ur else None

    # Rating breakdown counts
    rating_counts = {i: 0 for i in range(1, 6)}
    for r in reviews:
        rating_counts[r.get('rating', 0)] = rating_counts.get(r.get('rating', 0), 0) + 1

    return render_template(
        'shop/product_detail.html',
        product=product,
        related_products=related_products,
        reviews=reviews,
        avg_rating=avg_rating,
        review_count=review_count,
        user_review=user_review,
        rating_counts=rating_counts,
        **common_context()
    )

@app.route('/category')
def category():
    # Build a map of category -> first product image for the category cards
    db = get_db()

    # Get ALL categories from the categories collection (not just those with products)
    all_cats = get_all_categories()  # [{'id': ..., 'name': ..., '_id': ...}, ...]

    # Get product counts per category (only those that have products)
    count_map = {item['category']: item['count'] for item in get_category_counts()}

    # Merge: every DB category gets a count (0 if no products yet)
    categories = [
        {'category': c['name'], 'count': count_map.get(c['name'], 0)}
        for c in all_cats
    ]

    # Build category -> first product image map (handles array-based category field)
    category_images = {}
    for cat in categories:
        first = db.products.find_one(
            {'category': {'$in': [cat['category']]}},
            {'image': 1}
        )
        if first and first.get('image'):
            category_images[cat['category']] = first['image']

    return render_template(
        'shop/category.html',
        categories=categories,
        category_images=category_images,
        **common_context('category')
    )

# =============================================================================
#  LIVE SEARCH API
# =============================================================================

@app.route('/api/search-products')
def api_search_products():
    from flask import jsonify
    q = request.args.get('q', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()
    categories = request.args.getlist('category')
    discount_only = request.args.get('discount_only') == '1'
    limit = int(request.args.get('limit', 20))
    sort = request.args.get('sort', 'newest')
    if sort not in ('newest', 'price_asc', 'price_desc', 'discount'):
        sort = 'newest'

    products = get_products(
        category=categories or None,
        min_price=min_price or None,
        max_price=max_price or None,
        search=q or None,
        limit=limit,
        discount_only=discount_only,
        sort=sort
    )

    results = []
    for p in products:
        results.append({
            'id': p['id'],
            'name': p['name'],
            'image': p.get('image', ''),
            'category': p.get('category', []),
            'brand': p.get('brand', ''),
            'description': p.get('description', ''),
            'price': float(p['price']),
            'discounted_price': float(p['discounted_price']) if p.get('discounted_price') else None,
            'discount_percent': int(p.get('discount_percent', 0)),
        })

    return jsonify({'products': results, 'count': len(results)})

# =============================================================================
#  CART & CHECKOUT ROUTES
# =============================================================================

@app.route('/apply-coupon', methods=['POST'])
def apply_coupon():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    code = data.get('code', '').strip().upper()
    subtotal = float(data.get('subtotal', 0))

    if not code:
        return jsonify({'success': False, 'message': 'Please enter a promo code.'})

    coupon = get_coupon(code)
    if not coupon:
        return jsonify({'success': False, 'message': f'"{code}" is not a valid promo code.'})

    # Check expiry if present
    valid_until = coupon.get('valid_until')
    if valid_until:
        from datetime import datetime as dt
        try:
            if dt.utcnow() > dt.strptime(valid_until, '%Y-%m-%d'):
                return jsonify({'success': False, 'message': 'This promo code has expired.'})
        except ValueError:
            pass

    discount_pct = float(coupon.get('discount_percent', 0))
    discount_amt = round(subtotal * discount_pct / 100, 2)

    # Save to session so it persists through to checkout
    session['coupon'] = {
        'code': code,
        'discount_percent': discount_pct,
        'discount_amount': discount_amt
    }
    session.modified = True

    return jsonify({
        'success': True,
        'message': f'🎉 {discount_pct:.0f}% discount applied!',
        'discount_percent': discount_pct,
        'discount_amount': discount_amt
    })

@app.route('/add-to-cart/<product_id>', methods=['GET', 'POST'])
def add_to_cart(product_id):
    from flask import jsonify
    product = get_product_by_id(product_id)
    if not product:
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
        if is_ajax:
            return jsonify({'success': False, 'message': 'Product not found.'})
        flash('Product not found.', 'danger')
        return redirect(request.referrer or url_for('product'))
        
    cart = session.get('cart', {})
    
    quantity = 1
    if request.method == 'POST':
        try:
            quantity = int(request.form.get('quantity', 1))
        except ValueError:
            pass
            
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session['cart'] = cart
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    if is_ajax:
        cart_count = sum(cart.values())
        return jsonify({'success': True, 'cart_count': cart_count, 'message': f'Added {product["name"]} to cart.'})
        
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

        effective_price = get_effective_price(product)
        total = Decimal(str(effective_price)) * quantity
        subtotal += total

        item = dict(product)
        item['quantity'] = quantity
        item['effective_price'] = effective_price
        item['total'] = total
        cart_items.append(item)
        
    return render_template(
        'cart/cart.html',
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

@app.route('/cart/update/<product_id>', methods=['POST'])
def cart_update(product_id):
    cart_data = session.get('cart', {})
    if str(product_id) in cart_data:
        try:
            qty = int(request.form.get('quantity', 1))
            if qty > 0:
                cart_data[str(product_id)] = qty
            else:
                cart_data.pop(str(product_id), None)
            session['cart'] = cart_data
        except ValueError:
            pass
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

        effective_price = get_effective_price(product)
        total = Decimal(str(effective_price)) * quantity
        subtotal += total

        item = dict(product)
        item['quantity'] = quantity
        item['effective_price'] = effective_price
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
        coupon_session = session.get('coupon', {})
        discount_amt = Decimal(str(coupon_session.get('discount_amount', 0)))
        discount_pct = coupon_session.get('discount_percent', 0)
        coupon_code  = coupon_session.get('code', '')
        total = max(Decimal('0.00'), subtotal - discount_amt) + shipping_cost if subtotal > Decimal('0.00') else Decimal('0.00')
        
        if not shipping_address:
            flash('Please provide a shipping address.', 'danger')
            return render_template('cart/checkout.html', cart_items=cart_items, subtotal=subtotal, total=total, shipping_cost=shipping_cost, **common_context('checkout'))
            
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
                'price': float(item['effective_price']),
                'image': item['image']
            })

        # Process payment method details
        payment_method_str = payment_method

        order_id = create_order(g.user['id'], shipping_address, shipping_method, float(shipping_cost), total, embedded_items, payment_method_str, 'Processing')

        # Send Telegram notification (fails silently if bot is not configured or fails)
        try:
            send_telegram_notification(
                order_id=order_id,
                user=g.user,
                shipping_address=shipping_address,
                shipping_method=shipping_method,
                shipping_cost=float(shipping_cost),
                total=float(total),
                items=embedded_items
            )
        except Exception as te:
            print(f"Telegram notification error: {te}")

        session['cart'] = {}
        session.pop('coupon', None)  # Clear coupon after order placed
        session.modified = True
        
        flash('Your order has been received.', 'success')
        return redirect(url_for('order_receipt', order_id=order_id))

    VALID_METHODS = {'Express', 'Standard', 'Pickup'}
    preselected_shipping = request.args.get('shipping', 'Express').strip()
    if preselected_shipping not in VALID_METHODS:
        preselected_shipping = 'Express'

    shipping_rates = {'Express': Decimal('15.00'), 'Standard': Decimal('5.00'), 'Pickup': Decimal('0.00')}
    shipping_cost = shipping_rates.get(preselected_shipping, Decimal('15.00'))
    coupon_session = session.get('coupon', {})
    discount_amt = Decimal(str(coupon_session.get('discount_amount', 0)))
    discount_pct = coupon_session.get('discount_percent', 0)
    coupon_code  = coupon_session.get('code', '')
    total = max(Decimal('0.00'), subtotal - discount_amt) + shipping_cost if subtotal > Decimal('0.00') else Decimal('0.00')
    return render_template('cart/checkout.html',
        cart_items=cart_items, subtotal=subtotal, total=total,
        shipping_cost=shipping_cost, discount_amt=discount_amt,
        discount_pct=discount_pct, coupon_code=coupon_code,
        preselected_shipping=preselected_shipping,
        **common_context('checkout'))

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
    
    return render_template('account/order_index.html', orders=orders, **common_context('order'))

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
    # Read the stored shipping_cost directly — never derive by subtraction
    shipping_cost = Decimal(str(order.get('shipping_cost', 0)))
    item_count = sum(item['quantity'] for item in items)
    
    return render_template(
        'account/order_receipt.html',
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

    if order['status'] == 'Delivered' and g.user.get('role') != 'admin':
        flash('Delivered orders cannot be cancelled.', 'danger')
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
        
    if g.user.get('role') != 'admin':
        abort(403)
        
    delete_order(order_id)
    flash(f'Order #{order_id} permanently deleted.', 'success')
    
    if g.user.get('role') == 'admin':
        return redirect(url_for('inbox'))
    return redirect(url_for('order'))

@app.route('/order/advance/<order_id>', methods=['POST'])
def order_advance_status(order_id):
    login_redirect = require_login()
    if login_redirect: return login_redirect
    
    if g.user.get('role') != 'admin':
        abort(403)
        
    order = get_order(order_id)
    if not order:
        flash('Order not found.', 'danger')
        return redirect(url_for('inbox'))
        
    status_flow = ['Ordering', 'Processing', 'Shipped', 'Delivered']
    current_status = order.get('status', 'Ordering')
    
    if current_status in status_flow:
        current_index = status_flow.index(current_status)
        if current_index < len(status_flow) - 1:
            new_status = status_flow[current_index + 1]
            db = get_db()
            db.orders.update_one({'_id': ObjectId(str(order_id))}, {'$set': {'status': new_status}})
            flash(f'Order #{str(order_id)[:8]} updated to {new_status}.', 'success')
        else:
            flash(f'Order is already {current_status}.', 'info')
    else:
        flash('Cannot advance this order.', 'warning')
    return redirect(url_for('inbox'))

@app.route('/order/demo-ship/<order_id>', methods=['POST'])
def order_demo_ship(order_id):
    if not g.user:
        return {'success': False}
    order = get_order(order_id)
    if order and order['user_id'] == str(g.user['id']) and order.get('status') == 'Processing':
        get_db().orders.update_one({'_id': ObjectId(str(order_id))}, {'$set': {'status': 'Shipped'}})
        return {'success': True}
    return {'success': False}

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
    return render_template('account/profile.html', orders=orders, order_count=len(orders), **common_context('profile'))

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



    return render_template('account/settings.html', **common_context('settings'))

# =============================================================================
#  REVIEW ROUTES
# =============================================================================

@app.route('/product-detail/<product_id>/review', methods=['POST'])
def submit_review(product_id):
    """Submit or update a review for a product."""
    login_redirect = require_login()
    if login_redirect: return login_redirect

    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('product'))

    rating_str = request.form.get('rating', '0').strip()
    comment = request.form.get('comment', '').strip()

    try:
        rating = int(rating_str)
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        flash('Please select a rating between 1 and 5.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))

    if not comment:
        flash('Please write a review comment.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))

    db = get_db()
    existing = db.reviews.find_one({'product_id': str(product_id), 'user_id': str(g.user['id'])})

    if existing:
        db.reviews.update_one(
            {'_id': existing['_id']},
            {'$set': {
                'rating': rating,
                'comment': comment,
                'updated_at': datetime.utcnow().isoformat()
            }}
        )
        flash('Your review has been updated!', 'success')
    else:
        db.reviews.insert_one({
            'product_id': str(product_id),
            'user_id': str(g.user['id']),
            'username': g.user['username'],
            'rating': rating,
            'comment': comment,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        })
        flash('Thank you for your review!', 'success')

    return redirect(url_for('product_detail', product_id=product_id) + '#reviews')


@app.route('/review/delete/<review_id>', methods=['POST'])
def delete_review(review_id):
    """Delete a review. Users can delete their own; admins can delete any."""
    login_redirect = require_login()
    if login_redirect: return login_redirect

    db = get_db()
    try:
        review = db.reviews.find_one({'_id': ObjectId(str(review_id))})
    except (InvalidId, TypeError, ValueError):
        review = None

    if not review:
        flash('Review not found.', 'danger')
        return redirect(url_for('product'))

    if review['user_id'] != str(g.user['id']) and g.user.get('role') != 'admin':
        abort(403)

    product_id = review['product_id']
    db.reviews.delete_one({'_id': ObjectId(str(review_id))})
    flash('Review deleted.', 'success')

    if g.user.get('role') == 'admin':
        return redirect(url_for('admin_reviews'))
    return redirect(url_for('product_detail', product_id=product_id) + '#reviews')


@app.route('/admin/reviews')
def admin_reviews():
    """Admin page to view and manage all reviews."""
    require_admin()
    db = get_db()
    all_reviews = list(db.reviews.find().sort('created_at', -1))
    all_reviews = [format_doc(r) for r in all_reviews]

    # Attach product name to each review
    for r in all_reviews:
        prod = get_product_by_id(r.get('product_id', ''))
        r['product_name'] = prod['name'] if prod else 'Unknown'

    return render_template('admin/reviews.html', reviews=all_reviews, **common_context('admin'))


@app.route('/admin/users', methods=['GET', 'POST'])
def admin_users():
    """Admin page to view and manage all users — assign roles, ban accounts."""
    require_admin()
    db = get_db()

    if request.method == 'POST':
        action    = request.form.get('action', '')
        target_id = request.form.get('user_id', '').strip()

        # Prevent self-demotion / self-ban
        if target_id == str(g.user['id']):
            flash('You cannot modify your own account from here.', 'danger')
            return redirect(url_for('admin_users'))

        try:
            oid = ObjectId(target_id)
        except (InvalidId, TypeError, ValueError):
            flash('Invalid user ID.', 'danger')
            return redirect(url_for('admin_users'))

        if action == 'set_role':
            new_role = request.form.get('role', 'user')
            if new_role not in ('admin', 'user'):
                flash('Invalid role.', 'danger')
                return redirect(url_for('admin_users'))
            db.users.update_one({'_id': oid}, {'$set': {'role': new_role}})
            flash(f'User role updated to "{new_role}".', 'success')

        elif action == 'ban':
            db.users.update_one({'_id': oid}, {'$set': {'banned': True}})
            flash('User has been banned.', 'warning')

        elif action == 'unban':
            db.users.update_one({'_id': oid}, {'$unset': {'banned': ''}})
            flash('User has been unbanned.', 'success')

        elif action == 'delete_user':
            db.users.delete_one({'_id': oid})
            db.orders.delete_many({'user_id': target_id})
            flash('User account deleted.', 'success')

        return redirect(url_for('admin_users'))

    # GET — fetch all users
    all_users = [format_doc(u) for u in db.users.find().sort('created_at', -1)]
    # Attach order count per user
    for u in all_users:
        u['order_count'] = db.orders.count_documents({'user_id': u['id']})

    return render_template('admin/users.html', all_users=all_users, **common_context('admin'))


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
        
    return render_template('auth/login.html', **common_context())

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
            
    return render_template('auth/register.html', **common_context())

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
    # Mark all Ordering orders as read when the admin views the inbox
    db.orders.update_many({'status': 'Ordering', 'is_read': {'$ne': True}}, {'$set': {'is_read': True}})
    
    all_orders = []
    for order in db.orders.find().sort('created_at', -1):
        user = get_user_by_id(order['user_id'])
        if user:
            order['username'] = user['username']
            order['email'] = user['email']
        all_orders.append(format_doc(order))
        
    return render_template('admin/inbox.html', all_orders=all_orders, **common_context('inbox'))

@app.route('/admin/categories', methods=['GET', 'POST'])
def admin_categories():
    require_admin()
    db = get_db()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            if name:
                db.categories.insert_one({'name': name})
                flash(f'Category "{name}" added.', 'success')
        elif action == 'edit':
            cat_id = request.form.get('category_id')
            new_name = request.form.get('name', '').strip()
            if cat_id and new_name:
                db.categories.update_one({'_id': ObjectId(cat_id)}, {'$set': {'name': new_name}})
                flash(f'Category updated to "{new_name}".', 'success')
        elif action == 'delete':
            cat_id = request.form.get('category_id')
            if cat_id:
                db.categories.delete_one({'_id': ObjectId(cat_id)})
                flash('Category deleted.', 'success')
        return redirect(url_for('admin_categories'))
        
    cats = get_all_categories()
    return render_template('admin/categories.html', 
                           categories=cats, 
                           **common_context('admin'))

@app.route('/admin', methods=['GET'])
def admin():
    require_admin()
    db = get_db()
    products = get_products(limit=100)
    discounted_products = get_discounted_products(limit=100)
    categories = get_all_categories()

    # --- Revenue stats ---
    from datetime import datetime as dt, timezone

    def _as_utc(val):
        """Safely coerce a created_at value to a UTC-aware datetime, or None."""
        if val is None:
            return None
        if isinstance(val, dt):
            # Already datetime — just attach UTC if naive
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if isinstance(val, str):
            try:
                from dateutil import parser as dparser
                parsed = dparser.parse(val)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None  # unknown type — skip

    now = dt.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    all_orders = list(db.orders.find({'status': {'$ne': 'Cancelled'}}))
    total_revenue = sum(float(o.get('total', 0)) for o in all_orders)
    today_revenue = sum(
        float(o.get('total', 0)) for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= today_start
    )
    month_revenue = sum(
        float(o.get('total', 0)) for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= month_start
    )
    month_orders = sum(
        1 for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= month_start
    )
    inbox_count = db.orders.count_documents({'status': 'Ordering', 'is_read': {'$ne': True}})

    return render_template(
        'admin/dashboard.html',
        products=products,
        discounted_products=discounted_products,
        categories=categories,
        total_revenue=total_revenue,
        today_revenue=today_revenue,
        month_revenue=month_revenue,
        month_orders=month_orders,
        **common_context('admin')
    )


@app.route('/api/admin/revenue')
def api_admin_revenue():
    """Live revenue stats endpoint — polled every 30 s by the dashboard."""
    from flask import jsonify
    require_admin()
    db = get_db()
    from datetime import datetime as dt, timezone

    def _as_utc(val):
        if val is None:
            return None
        if isinstance(val, dt):
            return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        if isinstance(val, str):
            try:
                from dateutil import parser as dparser
                parsed = dparser.parse(val)
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    now = dt.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    all_orders   = list(db.orders.find({'status': {'$ne': 'Cancelled'}}))
    total_revenue = sum(float(o.get('total', 0)) for o in all_orders)
    today_revenue = sum(
        float(o.get('total', 0)) for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= today_start
    )
    month_revenue = sum(
        float(o.get('total', 0)) for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= month_start
    )
    month_orders  = sum(
        1 for o in all_orders
        if _as_utc(o.get('created_at')) is not None and _as_utc(o['created_at']) >= month_start
    )
    total_orders  = len(all_orders)
    inbox_count   = db.orders.count_documents({'status': 'Ordering', 'is_read': {'$ne': True}})

    return jsonify({
        'total_revenue': round(total_revenue, 2),
        'today_revenue': round(today_revenue, 2),
        'month_revenue': round(month_revenue, 2),
        'month_orders':  month_orders,
        'total_orders':  total_orders,
        'inbox_count':   inbox_count,
    })


@app.route('/admin/product/new', methods=['GET', 'POST'])
def admin_product_new():
    """Single-form product creation — all fields at once."""
    require_admin()
    db = get_db()

    if request.method == 'POST':
        import json
        name        = request.form.get('name', '').strip()
        categories_raw = request.form.get('categories_json', '[]')
        try:
            categories = [c.strip() for c in json.loads(categories_raw) if c.strip()]
        except Exception:
            categories = []
        brand            = request.form.get('brand', '').strip()
        description      = request.form.get('description', '').strip()
        detail           = request.form.get('detail', '').strip()
        price            = request.form.get('price', '0').strip()
        stock_total      = request.form.get('stock', '0').strip()
        discount_percent = request.form.get('discount_percent', '0').strip()
        main_b64         = request.form.get('main_image_b64', '').strip()
        image_file       = request.files.get('image_file')

        all_cats = [c['name'] for c in get_all_categories()]

        if not name or not categories or not description or not price:
            flash('Please fill all required fields (Name, at least one Category, Description, Price).', 'danger')
            # Re-render with DB categories so the dropdown is still populated and form data is preserved
            prefill = {
                'name': name, 'brand': brand, 'description': description,
                'detail': detail, 'price': price, 'stock': int(stock_total or 0),
                'discount_percent': int(float(discount_percent or 0)),
                'category': categories, 'image': main_b64, 'variants': [], 'color_images': {},
                'id': None  # No ID means form action stays on admin_product_new
            }
            return render_template('admin/product_detail.html',
                                   all_categories=all_cats,
                                   product=None,
                                   form_prefill=prefill,
                                   **common_context('admin'))

        try:
            discount_pct_val = max(0.0, min(100.0, float(discount_percent or 0)))
        except ValueError:
            discount_pct_val = 0.0

        image = main_b64 if main_b64 else (save_image(image_file) if image_file and image_file.filename else '')

        sizes     = request.form.getlist('variant_size[]')
        colors    = request.form.getlist('variant_color[]')
        vstocks   = request.form.getlist('variant_stock[]')
        vimgs_b64 = request.form.getlist('variant_img_b64[]')
        variants = []
        color_images = {}
        for s, c, vs, vimg in zip(sizes, colors, vstocks, vimgs_b64 + [''] * len(sizes)):
            if s.strip() or c.strip():
                variants.append({'size': s.strip(), 'color': c.strip(), 'stock': int(vs.strip() or 0)})
                if vimg.strip() and c.strip():
                    color_images[c.strip()] = vimg.strip()

        if not image and color_images:
            image = next(iter(color_images.values()))

        db.products.insert_one({
            'name': name, 'category': categories, 'brand': brand,
            'description': description, 'detail': detail,
            'price': float(price), 'stock': int(stock_total or 0),
            'discount_percent': discount_pct_val,
            'image': image,
            'images': list(color_images.values()) or ([image] if image else []),
            'color_images': color_images, 'variants': variants,
            'created_at': datetime.utcnow().isoformat()
        })
        flash('Product added successfully!', 'success')
        return redirect(url_for('admin'))


    # GET — show blank form (reuse the same detail template with product=None)
    return render_template('admin/product_detail.html',
                           all_categories=[c['name'] for c in get_all_categories()],
                           product=None,
                           form_prefill=None,
                           **common_context('admin'))


@app.route('/admin/product/<product_id>/detail', methods=['GET', 'POST'])
def admin_product_detail(product_id):
    """Edit all product fields in one form."""
    require_admin()
    db = get_db()
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('admin'))

    if request.method == 'POST':
        import json
        categories_raw = request.form.get('categories_json', '[]')
        try:
            categories = [c.strip() for c in json.loads(categories_raw) if c.strip()]
        except Exception:
            categories = product.get('category', [])
        brand            = request.form.get('brand', '').strip()
        detail           = request.form.get('detail', '').strip()
        description      = request.form.get('description', '').strip()
        name             = request.form.get('name', product['name']).strip()
        price            = request.form.get('price', str(product['price'])).strip()
        stock_total      = request.form.get('stock', str(product['stock'])).strip()
        discount_percent = request.form.get('discount_percent', str(product.get('discount_percent', 0))).strip()
        main_b64         = request.form.get('main_image_b64', '').strip()
        image_file       = request.files.get('image_file')

        try:
            discount_pct_val = max(0.0, min(100.0, float(discount_percent or 0)))
        except ValueError:
            discount_pct_val = 0.0

        sizes     = request.form.getlist('variant_size[]')
        colors    = request.form.getlist('variant_color[]')
        vstocks   = request.form.getlist('variant_stock[]')
        vimgs_b64 = request.form.getlist('variant_img_b64[]')
        variants = []
        color_images = dict(product.get('color_images', {}))
        for s, c, vs, vimg in zip(sizes, colors, vstocks, vimgs_b64 + [''] * len(sizes)):
            if s.strip() or c.strip():
                variants.append({'size': s.strip(), 'color': c.strip(), 'stock': int(vs.strip() or 0)})
                if vimg.strip() and c.strip():
                    color_images[c.strip()] = vimg.strip()

        if main_b64:
            new_image = main_b64
        else:
            new_image = save_image(image_file) if image_file and image_file.filename else None
        image = new_image or product['image']
        if not image and color_images:
            image = next(iter(color_images.values()))

        db.products.update_one(
            {'_id': ObjectId(str(product_id))},
            {'$set': {
                'name': name, 'category': categories, 'brand': brand,
                'description': description, 'detail': detail,
                'price': float(price), 'stock': int(stock_total or 0),
                'discount_percent': discount_pct_val,
                'image': image,
                'images': list(color_images.values()) or ([image] if image else []),
                'color_images': color_images, 'variants': variants,
            }}
        )
        flash('Product updated successfully!', 'success')
        return redirect(url_for('admin'))


    return render_template('admin/product_detail.html',
                           all_categories=[c['name'] for c in get_all_categories()],
                           product=product,
                           form_prefill=None,
                           **common_context('admin'))


@app.route('/admin/edit/<product_id>')
def admin_edit(product_id):
    require_admin()
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('admin'))
    return redirect(url_for('admin_product_detail', product_id=product_id))


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

