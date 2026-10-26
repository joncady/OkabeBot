#!/usr/bin/env python3
"""Deploy/update the small signed GitHub relay. Never prints its shared secret."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from okabebot.config import get_config, state_dir
from okabebot.github_webhook import configured_secret

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "okabebot.local.json")
    parser.add_argument("--region", default="us-west-2")
    parser.add_argument("--profile", default="default")
    parser.add_argument("--stack", default="okabebot-github-relay")
    args = parser.parse_args()
    os.environ["OKABEBOT_CONFIG"] = str(args.config.resolve())
    get_config.cache_clear()
    repositories = get_config()["notifications"]["github_webhook_repositories"]
    secret = configured_secret()
    if not repositories or len(secret) < 32:
        raise SystemExit("Configure the private webhook secret and allowed repositories first")
    command = ["aws", "--profile", args.profile, "--region", args.region]

    def aws(*argv):
        return subprocess.run(
            command + list(argv),
            check=True,
            capture_output=True,
            text=True,
            env=dict(os.environ, AWS_PAGER=""),
        ).stdout

    caller = json.loads(aws("sts", "get-caller-identity"))["Arn"]
    match = re.search(r":assumed-role/(.+)/[^/]+$", caller)
    principal = (
        json.loads(aws("iam", "get-role", "--role-name", match[1].split("/")[-1]))["Role"]["Arn"]
        if match
        else caller
    )
    template = json.loads((ROOT / "infra/aws/github-relay.json").read_text())
    template["Resources"]["Receiver"]["Properties"]["Code"]["ZipFile"] = (
        ROOT / "infra/aws/github_relay.py"
    ).read_text()
    try:
        aws("cloudformation", "describe-stacks", "--stack-name", args.stack)
        exists = True
    except subprocess.CalledProcessError as exc:
        if "does not exist" not in exc.stderr:
            raise
        exists = False
    request = dict(
        StackName=args.stack,
        TemplateBody=json.dumps(template),
        Capabilities=["CAPABILITY_IAM"],
        Parameters=[
            dict(ParameterKey="WebhookSecret", ParameterValue=secret),
            dict(ParameterKey="Repositories", ParameterValue=",".join(repositories)),
            dict(ParameterKey="ConsumerPrincipalArn", ParameterValue=principal),
        ],
        Tags=[dict(Key="Project", Value="OkabeBot")],
    )
    with tempfile.TemporaryDirectory(prefix="okabebot-aws-") as folder:
        path = Path(folder) / "request.json"
        path.write_text(json.dumps(request))
        path.chmod(0o600)
        try:
            aws(
                "cloudformation",
                "update-stack" if exists else "create-stack",
                "--cli-input-json",
                "file://" + str(path),
            )
            aws(
                "cloudformation",
                "wait",
                "stack-update-complete" if exists else "stack-create-complete",
                "--stack-name",
                args.stack,
            )
        except subprocess.CalledProcessError as exc:
            if "No updates are to be performed" not in exc.stderr:
                raise SystemExit(
                    "Deployment failed. Inspect CloudFormation stack events; private parameter values were not printed."
                ) from None
    outputs = json.loads(aws("cloudformation", "describe-stacks", "--stack-name", args.stack))[
        "Stacks"
    ][0]["Outputs"]
    value = {o["OutputKey"]: o["OutputValue"] for o in outputs}
    value.update(region=args.region, stack=args.stack, source_profile=args.profile)
    path = state_dir() / "github-relay.json"
    path.write_text(json.dumps(value, indent=2))
    path.chmod(0o600)
    print("Relay deployed; private installation metadata:", path)
    print("Webhook endpoint:", value["WebhookUrl"])


if __name__ == "__main__":
    main()
