"""Return a presigned S3 PUT URL so clients can upload directly to the bucket.

Request body (JSON): { "key": "<object-key>", "contentType": "<mime>" }
Response (JSON):     { "url": "...", "key": "..." }
"""
import json
import os
import uuid

import boto3

S3 = boto3.client("s3")
BUCKET = os.environ["DATA_BUCKET_NAME"]
PRESIGN_TTL_SECONDS = 300


def handler(event, _context):
    body = json.loads(event.get("body") or "{}")
    key = body.get("key") or f"uploads/{uuid.uuid4()}"
    content_type = body.get("contentType", "application/octet-stream")

    url = S3.generate_presigned_url(
        ClientMethod="put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGN_TTL_SECONDS,
        HttpMethod="PUT",
    )

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"url": url, "key": key}),
    }
