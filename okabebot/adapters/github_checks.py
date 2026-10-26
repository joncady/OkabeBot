"""Workflow failures independent of GitHub's notification inbox."""

from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import subprocess
import time
from urllib.parse import urlencode, quote

FAILURES = {"failure", "timed_out", "action_required", "startup_failure", "stale"}


def api(path):
    result = subprocess.run(
        ["gh", "api", path, "--paginate", "--slurp"],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    return json.loads(result.stdout)


def poll(context):
    now = dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat()
    selected = context.settings["github"]
    if selected == "all":
        cache = context.state.get("github_checks_repositories", {})
        if time.time() - cache.get("at", 0) > 900:
            pages = api("user/repos?affiliation=owner,collaborator&per_page=100")
            names = sorted(
                {
                    r["full_name"]
                    for page in pages
                    for r in page
                    if not r.get("archived") and not r.get("disabled")
                }
            )
            cache = {"at": time.time(), "names": names}
            context.state["github_checks_repositories"] = cache
        names = cache["names"]
    else:
        names = [selected]
    states = context.state.setdefault("github_checks", {})
    cutoff = (
        (now - dt.timedelta(days=context.settings.get("workflow_lookback_days", 30)))
        .date()
        .isoformat()
    )

    def fetch(name):
        # First enablement establishes a baseline, never announces old failures.
        since = states.get(name, {}).get("since", stamp)
        path = (
            "repos/"
            + quote(name, safe="/")
            + "/actions/runs?"
            + urlencode({"per_page": 100, "status": "completed", "created": ">=" + cutoff})
        )
        try:
            pages = api(path)
            runs = [run for page in pages for run in page["workflow_runs"]]
            for run in runs:
                updated = dt.datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
                if updated <= dt.datetime.fromisoformat(since.replace("Z", "+00:00")):
                    continue
                if run.get("conclusion") not in FAILURES:
                    continue
                attempt = run.get("run_attempt", 1)
                context.inbox.publish(
                    "github",
                    ("Checks failed · " + (run.get("name") or "Workflow"))[:100],
                    (
                        name
                        + " · "
                        + (run.get("head_branch") or "detached")
                        + " · run "
                        + str(run.get("run_number", run["id"]))
                        + " · attempt "
                        + str(attempt)
                    )[:500],
                    "important",
                    "workflow-" + str(run["id"]) + "-" + str(attempt),
                    audio="chime",
                    expires_at=time.time() + 3600,
                )
            # Advance only after every page and publish succeeds. Overlap handles timestamp precision.
            return name, {"since": (now - dt.timedelta(seconds=2)).isoformat()}, None
        except Exception:
            return name, None, "Workflow access or polling failed"

    failures = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, state, error in pool.map(fetch, names):
            if state:
                states[name] = state
            elif name not in states:
                # Preserve initial baseline across a transient first fetch failure.
                states[name] = {"since": stamp}
            if error:
                failures.append(name)
    context.state["github_checks_health"] = {
        "checked_at": time.time(),
        "repositories": len(names),
        "failed_repositories": failures,
        "lookback_days": context.settings.get("workflow_lookback_days", 30),
    }
    if failures:
        raise RuntimeError("Some workflow repositories could not be checked")
