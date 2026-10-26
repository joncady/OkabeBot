"""Read-only GitHub notification/deployment polling."""

import datetime as dt
import json
import subprocess
import time


def poll(context):
    def get(path, paginate=False):
        args = ["gh", "api", path]
        if paginate:
            args += ["--paginate", "--slurp"]
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=True)
        value = json.loads(result.stdout)
        return [item for page in value for item in page] if paginate else value

    now = dt.datetime.now(dt.timezone.utc).isoformat()
    since = context.state.get("github_since", now)
    from urllib.parse import urlencode

    events = get(
        "notifications?" + urlencode({"all": "true", "since": since, "per_page": 100}), True
    )
    for event in events:
        reason = event.get("reason", "subscribed")
        title = event["subject"]["title"]
        context.inbox.publish(
            "github",
            title[:100],
            event["repository"]["full_name"] + " · " + reason.replace("_", " "),
            "important" if reason in ("review_requested", "mention", "ci_activity") else "normal",
            event["id"] + "-" + event["updated_at"],
        )
    context.state["github_since"] = now
    # One paginated GraphQL request replaces hundreds of REST status requests.
    query = """query($endCursor:String){viewer{repositories(first:100,after:$endCursor,
    affiliations:[OWNER,COLLABORATOR],orderBy:{field:PUSHED_AT,direction:DESC}){
    nodes{nameWithOwner deployments(first:3,orderBy:{field:CREATED_AT,direction:DESC}){
    nodes{id environment createdAt latestStatus{state createdAt}}}}
    pageInfo{hasNextPage endCursor}}}}"""
    result = subprocess.run(
        ["gh", "api", "graphql", "-f", "query=" + query, "--paginate", "--slurp"],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    pages = json.loads(result.stdout)
    active = []
    for page in pages:
        for repo in page["data"]["viewer"]["repositories"]["nodes"]:
            name = repo["nameWithOwner"]
            if context.settings["github"] not in ("all", name):
                continue
            for deployment in repo["deployments"]["nodes"]:
                status = deployment["latestStatus"]
                if not status or status["state"] not in ("QUEUED", "PENDING", "IN_PROGRESS"):
                    continue
                updated = dt.datetime.fromisoformat(status["createdAt"].replace("Z", "+00:00"))
                if (dt.datetime.now(dt.timezone.utc) - updated).total_seconds() > 3600:
                    continue
                identifier = deployment["id"]
                active.append(
                    dict(
                        id=identifier,
                        repo=name,
                        name=deployment["environment"],
                        checked=time.time(),
                    )
                )
                context.inbox.publish(
                    "github",
                    "Deploying · " + deployment["environment"][:70],
                    name,
                    "normal",
                    "deploy-" + identifier,
                    expires_at=time.time() + 300,
                )
    context.state["deployments"] = active
