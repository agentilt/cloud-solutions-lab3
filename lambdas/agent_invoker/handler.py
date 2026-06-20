"""Invoke the Bedrock AgentCore runtime with a user prompt and return the response.

Request body (JSON): { "prompt": "<user message>", "sessionId": "<optional>" }
Response (JSON):     { "response": "<agent output>", "sessionId": "..." }
"""
import json
import os
import uuid

import boto3

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
CLIENT = boto3.client("bedrock-agentcore")


def _user_id(event: dict) -> str | None:
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    return claims.get("sub")


def handler(event, _context):
    body = json.loads(event.get("body") or "{}")
    prompt = body.get("prompt")
    if not prompt:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing 'prompt' in request body"}),
        }
    session_id = body.get("sessionId") or str(uuid.uuid4())
    user_id = _user_id(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "missing authenticated user claims"}),
        }

    response = CLIENT.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps(
            {
                "prompt": prompt,
                "project_id": body.get("project_id") or session_id,
                "user_id": user_id,
                "region": body.get("region") or os.environ.get("AWS_REGION", "us-east-1"),
            }
        ).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )

    stream = response.get("response")
    raw = stream.read() if hasattr(stream, "read") else stream
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"response": text, "sessionId": session_id}),
    }
