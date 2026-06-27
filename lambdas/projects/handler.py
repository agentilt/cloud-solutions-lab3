"""Project API handler for CloudCompass Builder."""
import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import boto3

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
DATA_BUCKET_NAME = os.environ["DATA_BUCKET_NAME"]
DATA_TABLE_NAME = os.environ["DATA_TABLE_NAME"]

AGENTCORE = boto3.client("bedrock-agentcore")
DYNAMODB = boto3.resource("dynamodb")
S3 = boto3.client("s3")
LAMBDA = boto3.client("lambda")
TABLE = DYNAMODB.Table(DATA_TABLE_NAME)


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def _user_id(event: dict) -> str | None:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("sub")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _put_received_project(user_id: str, project_id: str, prompt: str, region: str) -> None:
    ttl = int((datetime.now(UTC) + timedelta(days=14)).timestamp())
    TABLE.put_item(
        Item={
            "pk": f"USER#{user_id}",
            "sk": f"PROJECT#{project_id}",
            "user_id": user_id,
            "project_id": project_id,
            "prompt": prompt,
            "region": region,
            "status": "RECEIVED",
            "created_at": _now(),
            "updated_at": _now(),
            "ttl": ttl,
        }
    )


def _read_project(user_id: str, project_id: str) -> dict | None:
    response = TABLE.get_item(Key={"pk": f"USER#{user_id}", "sk": f"PROJECT#{project_id}"})
    item = response.get("Item")
    if not item:
        return None

    artifact_key = item.get("artifact_s3_key")
    if artifact_key:
        item["cdk_artifact_download_url"] = S3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": DATA_BUCKET_NAME, "Key": artifact_key},
            ExpiresIn=900,
        )
    return item


def _invoke_agent(user_id: str, project_id: str, prompt: str, region: str) -> dict:
    response = AGENTCORE.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=project_id,
        payload=json.dumps(
            {
                "user_id": user_id,
                "project_id": project_id,
                "prompt": prompt,
                "region": region,
            }
        ).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )

    stream = response.get("response")
    raw = stream.read() if hasattr(stream, "read") else stream
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = {"response": text}
    return parsed


def _mark_failed(user_id: str, project_id: str, message: str) -> None:
    TABLE.update_item(
        Key={"pk": f"USER#{user_id}", "sk": f"PROJECT#{project_id}"},
        UpdateExpression="SET #status = :status, error_message = :error, updated_at = :updated",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "FAILED",
            ":error": message,
            ":updated": _now(),
        },
    )


def _handle_create(event: dict, user_id: str) -> dict:
    body = json.loads(event.get("body") or "{}")
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return _response(400, {"error": "missing 'prompt' in request body"})

    region = body.get("region") or os.environ.get("AWS_REGION", "us-east-1")
    project_id = str(uuid.uuid4())
    _put_received_project(user_id, project_id, prompt, region)

    # The agent run takes 1-2 min, which exceeds the API Gateway (30s) and request
    # Lambda timeouts. Kick it off on a background ("Event") invocation of this same
    # function and return immediately; the SPA polls GET /projects/{id} until the
    # agent persists a terminal status (CHANGE_SET_READY / FAILED).
    LAMBDA.invoke(
        FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps(
            {
                "task": "run_agent",
                "user_id": user_id,
                "project_id": project_id,
                "prompt": prompt,
                "region": region,
            }
        ).encode("utf-8"),
    )

    latest = _read_project(user_id, project_id) or {}
    return _response(202, {"project_id": project_id, "status": "RECEIVED", "project": latest})


def _run_agent_task(event: dict) -> dict:
    """Background worker: run the long agent call, recording failures.

    Returns normally even on error so Lambda does not retry the async invocation
    (a retry would start a second, billable agent run). The agent persists its own
    progress and final state to DynamoDB via its save_project_state tool.
    """
    user_id = event["user_id"]
    project_id = event["project_id"]
    try:
        _invoke_agent(user_id, project_id, event["prompt"], event["region"])
    except Exception as exc:  # noqa: BLE001 - background boundary should swallow + record.
        _mark_failed(user_id, project_id, str(exc))
    return {"ok": True}


def _handle_get(event: dict, user_id: str) -> dict:
    project_id = event.get("pathParameters", {}).get("project_id")
    if not project_id:
        return _response(400, {"error": "missing project_id path parameter"})

    item = _read_project(user_id, project_id)
    if not item:
        return _response(404, {"error": "project not found"})
    return _response(200, item)


def handler(event, _context):
    # Background worker path: this function invokes itself ("Event") to run the
    # long agent call outside the synchronous API request.
    if event.get("task") == "run_agent":
        return _run_agent_task(event)

    user_id = _user_id(event)
    if not user_id:
        return _response(401, {"error": "missing authenticated user claims"})

    method = event.get("requestContext", {}).get("http", {}).get("method")
    raw_path = event.get("rawPath", "")
    if method == "POST" and raw_path.endswith("/projects"):
        return _handle_create(event, user_id)
    if method == "GET" and "/projects/" in raw_path:
        return _handle_get(event, user_id)
    return _response(404, {"error": "route not found"})
