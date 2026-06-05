"""Strands @tool functions. Replace with the group's real tools.

Each tool must:
  - have a clear docstring (the model reads it to decide when to call)
  - validate inputs
  - interact with a real AWS service (rubric requirement)
  - return a JSON-serializable value
"""
import json
import os
from datetime import UTC, datetime

import boto3
from strands import tool

DATA_TABLE_NAME = os.environ["DATA_TABLE_NAME"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]
EVENT_SOURCE = "lab3.agent"

_dynamodb = boto3.resource("dynamodb")
_events = boto3.client("events")
_table = _dynamodb.Table(DATA_TABLE_NAME)


@tool
def lookup_record(pk: str, sk: str) -> dict:
    """Fetch a single record from the application DynamoDB table.

    Args:
        pk: Partition key value (e.g. "user#123", "vendor#acme").
        sk: Sort key value (e.g. "profile", "order#2026-01-15").

    Returns:
        The record as a dict, or {"found": False} if the key does not exist.
    """
    response = _table.get_item(Key={"pk": pk, "sk": sk})
    item = response.get("Item")
    if not item:
        return {"found": False, "pk": pk, "sk": sk}
    return {"found": True, "item": item}


@tool
def record_event(event_type: str, detail: dict) -> dict:
    """Emit a domain event onto the application EventBridge bus.

    Use this when the agent observes something the rest of the system should
    react to (e.g. a flagged anomaly, a completed step, a downstream trigger).

    Args:
        event_type: Short DetailType for the event (e.g. "AnomalyDetected").
        detail: Arbitrary JSON-serializable payload describing the event.

    Returns:
        {"eventId": "<id>", "timestamp": "<iso8601>"} on success.
    """
    entry = {
        "Source": EVENT_SOURCE,
        "DetailType": event_type,
        "Detail": json.dumps(detail),
        "EventBusName": EVENT_BUS_NAME,
        "Time": datetime.now(UTC),
    }
    response = _events.put_events(Entries=[entry])
    failed = response.get("FailedEntryCount", 0)
    if failed:
        return {"error": "put_events failed", "details": response["Entries"]}
    return {
        "eventId": response["Entries"][0]["EventId"],
        "timestamp": entry["Time"].isoformat(),
    }
