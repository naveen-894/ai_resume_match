import asyncio
import os
import uuid

import boto3
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

BUCKET = os.getenv("S3_BUCKET")
REGION = os.getenv("S3_REGION", "ap-south-1")

s3_client = boto3.client(
    "s3",
    region_name=REGION,
    endpoint_url=f"https://s3.{REGION}.amazonaws.com",
    aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
)


async def upload_to_s3(file, folder: str = "uploads") -> str:
    """Upload a FastAPI UploadFile to S3 and return its public URL."""
    content = await file.read()
    await file.seek(0)  # leave the file readable for text extraction
    ext = os.path.splitext(file.filename or "")[1]
    key = f"{folder}/{uuid.uuid4()}{ext}"

    await asyncio.to_thread(
        s3_client.put_object,
        Bucket=BUCKET,
        Key=key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    return get_public_url(key)


def get_public_url(key: str) -> str:
    """Return the permanent public URL of an S3 object (bucket allows public reads)."""
    return f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{key}"
