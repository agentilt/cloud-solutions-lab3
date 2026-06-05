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


def handler(event, _context):
    body = json.loads(event.get("body") or "{}")
    prompt = body.get("prompt")
    if not prompt:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "missing 'prompt' in request body"}),
        }
    session_id = body.get("sessionId") or str(uuid.uuid4())

    response = CLIENT.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
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
