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


def _user_id(event: dict) -> str | None:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("sub")


def handler(event, _context):
    user_id = _user_id(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "missing authenticated user claims"}),
        }

    body = json.loads(event.get("body") or "{}")
    requested_key = (body.get("key") or str(uuid.uuid4())).lstrip("/")
    key = f"users/{user_id}/uploads/{requested_key}"
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
