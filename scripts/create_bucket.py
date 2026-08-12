"""Create MinIO bucket for raw evidence storage.

Usage:
    python scripts/create_bucket.py

Creates the 'provenmesh-raw' bucket if it doesn't exist.
"""

from __future__ import annotations

import asyncio
import os

import aiobotocore.session


async def create_bucket() -> None:
    """Create the raw evidence bucket in MinIO/S3."""
    endpoint = os.getenv("S3_ENDPOINT", "http://localhost:9000")
    access_key = os.getenv("S3_ACCESS_KEY", "minioadmin")
    secret_key = os.getenv("S3_SECRET_KEY", "minioadmin")
    bucket_name = os.getenv("S3_BUCKET", "provenmesh-raw")
    region = os.getenv("S3_REGION", "us-east-1")

    session = aiobotocore.session.get_session()
    async with session.create_client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    ) as client:
        try:
            await client.head_bucket(Bucket=bucket_name)
            print(f"✓ Bucket '{bucket_name}' already exists")
        except client.exceptions.ClientError:
            await client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region}
                if region != "us-east-1"
                else {},
            )
            print(f"✓ Created bucket '{bucket_name}'")

        # Verify access
        response = await client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
        print(f"✓ Bucket accessible, contains {response.get('KeyCount', 0)} objects")


if __name__ == "__main__":
    asyncio.run(create_bucket())
