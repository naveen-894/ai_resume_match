import requests
import os

CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
API_KEY = os.getenv("CLOUDINARY_API_KEY")
API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

async def upload_to_cloudinary(file):
    url = f"https://api.cloudinary.com/v1_1/{CLOUD_NAME}/upload"

    files = {"file": await file.read()}
    data = {"upload_preset": "resume"}  # signed preset

    response = requests.post(url, files=files, data=data, auth=(API_KEY, API_SECRET))
    print("CLOUDINARY RESPONSE:", response.text)
    response.raise_for_status()

    return response.json()["secure_url"]