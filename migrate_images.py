import os
import base64
import mimetypes
from pymongo import MongoClient

mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
db_name = os.environ.get('MONGO_DBNAME', 'StoreShoes')
client = MongoClient(mongo_uri)
db = client[db_name]

app_root = r'd:\year 3\sa\Store_shoes_VRUN'

def get_base64_image(filepath):
    try:
        full_path = os.path.join(app_root, 'static', filepath)
        if not os.path.exists(full_path):
            return filepath
        with open(full_path, 'rb') as f:
            encoded_string = base64.b64encode(f.read()).decode('utf-8')
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type:
            mime_type = 'image/png'
        return f'data:{mime_type};base64,{encoded_string}'
    except Exception:
        return filepath

# Update products
for product in db.products.find():
    if product.get('image', '').startswith('images/'):
        b64_img = get_base64_image(product['image'])
        b64_images = [get_base64_image(img) if img.startswith('images/') else img for img in product.get('images', [])]
        db.products.update_one({'_id': product['_id']}, {'$set': {'image': b64_img, 'images': b64_images}})

# Update orders (embedded items)
for order in db.orders.find():
    updated = False
    items = order.get('items', [])
    for item in items:
        if item.get('image', '').startswith('images/'):
            item['image'] = get_base64_image(item['image'])
            updated = True
    if updated:
        db.orders.update_one({'_id': order['_id']}, {'$set': {'items': items}})

print('Migration complete')
