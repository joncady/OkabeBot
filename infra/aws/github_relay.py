"""GitHub -> signed, bounded SQS envelope. Deployed as a Lambda function URL."""

import base64
import hashlib
import hmac
import json
import os
import re
import time


def response(status, value):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(value),
    }


def handle(event, sqs, queue_url, secret, repositories):
    if (
        event.get("rawPath") != "/webhooks/github"
        or event.get("requestContext", {}).get("http", {}).get("method") != "POST"
    ):
        return response(404, {"error": "Not found"})
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    try:
        body = event.get("body", "")
        if len(body) > 750_000:
            return response(413, {"error": "Too large"})
        raw = (
            base64.b64decode(body, validate=True) if event.get("isBase64Encoded") else body.encode()
        )
        if len(raw) > 524_288:
            return response(413, {"error": "Too large"})
        signature = headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if (
            not secret
            or not re.fullmatch(r"sha256=[a-f0-9]{64}", signature)
            or not hmac.compare_digest(signature, expected)
        ):
            return response(403, {"error": "Forbidden"})
        payload = json.loads(raw)
        repo = payload.get("repository", {}).get("full_name")
        if repo not in repositories:
            return response(403, {"error": "Forbidden"})
        kind = headers.get("x-github-event")
        if kind == "ping":
            return response(200, {"accepted": True, "ping": True})
        if kind not in ("workflow_run", "deployment_status"):
            return response(200, {"accepted": True, "ignored": True})
        if kind == "workflow_run" and payload.get("action") != "completed":
            return response(200, {"accepted": True, "ignored": True})
        envelope = dict(
            version=1,
            event=kind,
            signature=signature,
            body_base64=base64.b64encode(raw).decode(),
            received_at=time.time(),
        )
    except (ValueError, TypeError, AttributeError):
        return response(400, {"error": "Invalid payload"})
    try:
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(envelope))
    except Exception:
        return response(503, {"error": "Queue unavailable"})
    return response(202, {"accepted": True})


def handler(event, context):
    import boto3

    return handle(
        event,
        boto3.client("sqs"),
        os.environ["QUEUE_URL"],
        os.environ["WEBHOOK_SECRET"],
        set(os.environ["REPOSITORIES"].split(",")),
    )
