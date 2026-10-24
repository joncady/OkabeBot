"""Explicit, narrow policy for Hardware Lab MCP approvals.

This does not approve shell commands, file edits, general forms, URL requests,
other MCP servers, or tools absent from the configured allowlist.
"""

import re


def is_tool_approval(request):
    p = request.get("params", {})
    meta, schema = p.get("_meta") or {}, p.get("requestedSchema") or {}
    return (
        request.get("method") == "mcpServer/elicitation/request"
        and p.get("mode") == "form"
        and meta.get("codex_approval_kind") == "mcp_tool_call"
        and schema.get("type") == "object"
        and not schema.get("properties")
        and not schema.get("required")
    )


def tool_name(request):
    p = request.get("params", {})
    meta = p.get("_meta") or {}
    match = re.fullmatch(
        r'Allow the hardware-lab MCP server to run tool "([a-z_]+)"\?', p.get("message", "")
    )
    name = meta.get("tool_name")
    if name and match and name != match.group(1):
        return None
    return name or (match.group(1) if match else None)


def response(request, action, persist=None):
    if not is_tool_approval(request):
        raise ValueError("This form is not a supported tool approval")
    meta = request["params"].get("_meta") or {}
    if action not in ("accept", "decline", "cancel"):
        raise ValueError("Invalid approval decision")
    if persist is not None and (
        action != "accept" or persist != "session" or "session" not in meta.get("persist", [])
    ):
        raise ValueError("Session approval was not offered for this request")
    return {
        "action": action,
        "content": {} if action == "accept" else None,
        "_meta": {"persist": "session"} if persist else None,
    }


def automatic_response(request, policy):
    if not policy["auto_approve_hardware"] or not is_tool_approval(request):
        return None
    p = request["params"]
    if p.get("serverName") != "hardware-lab" or tool_name(request) not in policy["allowed_tools"]:
        return None
    meta = p.get("_meta") or {}
    # Never interpret a denial/review override or execution-bound confirmation as routine consent.
    if any(meta.get(k) for k in ("approveDisabled", "executionBound", "denied", "review_denied")):
        return None
    # Approve each eligible request separately, so narrowing the config on restart
    # never leaves an old session grant behind.
    return response(request, "accept")
