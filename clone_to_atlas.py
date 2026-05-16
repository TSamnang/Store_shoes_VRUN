"""
Clone local MongoDB -> MongoDB Atlas
Usage: python clone_to_atlas.py
"""
from pymongo import MongoClient

# -- EDIT THESE ----------------------------------------------------------------
LOCAL_URI   = "mongodb://localhost:27017/"
ATLAS_URI   = "mongodb://TSamnang:admin123@ac-sb3etsb-shard-00-00.eptj53w.mongodb.net:27017,ac-sb3etsb-shard-00-01.eptj53w.mongodb.net:27017,ac-sb3etsb-shard-00-02.eptj53w.mongodb.net:27017/?ssl=true&replicaSet=atlas-dcmwjq-shard-0&authSource=admin&appName=shoesStore"
DB_NAME     = "StoreShoes"
# -----------------------------------------------------------------------------

COLLECTIONS = ["products", "users", "orders", "coupons", "reviews", "categories"]

def clone():
    print("Connecting to local MongoDB...")
    local_db = MongoClient(LOCAL_URI)[DB_NAME]

    print("Connecting to Atlas...")
    atlas_db = MongoClient(ATLAS_URI, serverSelectionTimeoutMS=10000)[DB_NAME]

    for col_name in COLLECTIONS:
        local_col = local_db[col_name]
        atlas_col = atlas_db[col_name]

        docs = list(local_col.find())
        if not docs:
            print(f"  [{col_name}] empty, skipping.")
            continue

        # Drop existing data on Atlas for a clean clone
        atlas_col.drop()
        atlas_col.insert_many(docs)
        print(f"  [{col_name}] {len(docs)} documents cloned [OK]")

    # Re-create indexes
    atlas_db.users.create_index("email", unique=True)
    atlas_db.coupons.create_index("code", unique=True)
    print("\nDone! All collections cloned to Atlas.")

if __name__ == "__main__":
    clone()
