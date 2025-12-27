import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials

# Indlæs .env fil
load_dotenv()

cred_path = os.getenv("FIREBASE_CRED_PATH")

# Start Firebase
cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

print("✅ Firebase connected!")
