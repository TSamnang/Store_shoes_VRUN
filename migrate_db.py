from pymongo import MongoClient
import urllib.parse
import sys

# --- CONFIGURATION ---
# IMPORTANT: Replace the string below with your actual connection string from MongoDB Atlas!
# Example: "mongodb+srv://admin:mysecretpassword@cluster0.abc.mongodb.net/?retryWrites=true&w=majority"
ATLAS_URI = "mongodb+srv://TSamnang:admin123@shoesstore.eptj53w.mongodb.net/?appName=shoesStore"

LOCAL_URI = "mongodb+srv://TSamnang:admin123@shoesstore.eptj53w.mongodb.net/?appName=shoesStore"
DB_NAME = "StoreShoes"

def migrate():
    if "<db_password>" in ATLAS_URI:
        print("ERROR: You still have '<db_password>' in your connection string! You need to change that to your actual MongoDB Atlas database user password in migrate_db.py before running this.")
        sys.exit(1)

    print("Connecting to databases...")
    try:
        local_client = MongoClient(LOCAL_URI, serverSelectionTimeoutMS=5000)
        # Quick check if local DB is running
        local_client.admin.command('ping')
    except Exception as e:
        print("ERROR: Could not connect to your local MongoDB. Make sure it is running!")
        sys.exit(1)

    try:
        atlas_client = MongoClient(ATLAS_URI, serverSelectionTimeoutMS=5000)
        # Quick check if Atlas DB is accessible
        atlas_client.admin.command('ping')
    except Exception as e:
        print("ERROR: Could not connect to MongoDB Atlas. Check your connection string and ensure your IP is whitelisted in Atlas Network Access!")
        sys.exit(1)
    
    local_db = local_client[DB_NAME]
    atlas_db = atlas_client[DB_NAME]
    
    # List of collections we want to transfer
    collections_to_copy = ['users', 'products', 'orders', 'coupons', 'reviews']
    
    for coll_name in collections_to_copy:
        local_data = list(local_db[coll_name].find())
        
        if len(local_data) > 0:
            print(f"Transferring {len(local_data)} documents from '{coll_name}'...")
            
            # Clear the Atlas collection first so we don't get duplicates
            atlas_db[coll_name].delete_many({})
            
            # Insert the local data into Atlas
            atlas_db[coll_name].insert_many(local_data)
            print(f"- '{coll_name}' transferred successfully.")
        else:
            print(f"Skipping '{coll_name}' (empty locally).")

    print("\n Migration Complete!")
    print("Don't forget to set the MONGO_URI environment variable in Vercel to your Atlas connection string!")

if __name__ == "__main__":
    migrate()
