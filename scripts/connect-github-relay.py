#!/usr/bin/env python3
"""Connect an existing relay to local config and explicitly allowed GitHub repositories.

Creates a queue-only assumed-role AWS profile, never an IAM user or static key.
"""

import argparse
import configparser
import json
import os
from pathlib import Path
import subprocess
import time

from okabebot.config import get_config, state_dir
from okabebot.github_webhook import configured_secret
from okabebot.runtime import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("okabebot.local.json"))
    args = parser.parse_args()
    config = args.config.expanduser().resolve()
    os.environ["OKABEBOT_CONFIG"] = str(config)
    get_config.cache_clear()
    settings = get_config()["notifications"]
    metadata = json.loads((state_dir() / "github-relay.json").read_text())
    profile = metadata["stack"] + "-consumer"
    source = metadata["source_profile"]
    if source == profile:
        raise SystemExit("Consumer source profile cannot refer to itself")
    aws_config = configparser.RawConfigParser()
    aws_config.read(Path(os.environ.get("AWS_CONFIG_FILE", str(Path.home() / ".aws/config"))))
    section = "profile " + profile
    if (
        aws_config.has_section(section)
        and aws_config.get(section, "role_arn", fallback="") != metadata["ConsumerRoleArn"]
    ):
        raise SystemExit(
            "AWS profile already belongs to a different role; choose a different stack name"
        )
    for key, value in [
        ("role_arn", metadata["ConsumerRoleArn"]),
        ("source_profile", source),
        ("region", metadata["region"]),
    ]:
        subprocess.run(
            ["aws", "configure", "set", key, value, "--profile", profile],
            check=True,
            capture_output=True,
        )
    subprocess.run(
        [
            "aws",
            "--profile",
            profile,
            "--region",
            metadata["region"],
            "sqs",
            "get-queue-attributes",
            "--queue-url",
            metadata["QueueUrl"],
            "--attribute-names",
            "QueueArn",
        ],
        check=True,
        capture_output=True,
    )
    hooks = []
    for repo in settings["github_webhook_repositories"]:
        pages = json.loads(
            subprocess.check_output(
                ["gh", "api", "repos/" + repo + "/hooks", "--paginate", "--slurp"], text=True
            )
        )
        existing = next(
            (
                h
                for page in pages
                for h in page
                if h.get("config", {}).get("url") == metadata["WebhookUrl"]
            ),
            None,
        )
        payload = dict(
            name="web",
            active=True,
            events=["workflow_run", "deployment_status"],
            config=dict(
                url=metadata["WebhookUrl"],
                content_type="json",
                secret=configured_secret(),
                insecure_ssl="0",
            ),
        )
        path = "repos/" + repo + "/hooks" + ("/" + str(existing["id"]) if existing else "")
        result = subprocess.run(
            ["gh", "api", path, "--method", "PATCH" if existing else "POST", "--input", "-"],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=True,
        )
        hook = json.loads(result.stdout)
        hooks.append(dict(repo=repo, id=hook["id"]))
    raw = json.loads(config.read_text())
    backup = state_dir() / "backups"
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(backup / ("config-before-relay-" + str(int(time.time())) + ".json"), raw)
    raw.setdefault("notifications", {}).update(
        github_queue_url=metadata["QueueUrl"],
        github_queue_region=metadata["region"],
        github_queue_profile=profile,
    )
    atomic_json(config, raw)
    metadata["hooks"] = hooks
    metadata["consumer_profile"] = profile
    atomic_json(state_dir() / "github-relay.json", metadata)
    print("Queue-only AWS profile verified; GitHub hooks registered:", len(hooks))
    print("Restart the controller to start outbound queue consumption.")


if __name__ == "__main__":
    main()
