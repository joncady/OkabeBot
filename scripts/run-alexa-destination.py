#!/usr/bin/env python3
"""Run the opt-in paired-screen relay; requires an enabled development deployment.

No dashboard token is needed. Approve the discovered screen and assign its scene
in the controller dashboard. The worker cannot approve itself. An explicit Visit
request can summon the actor only to its own approved screen.
"""

import argparse
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment", type=Path, default=Path(".local/alexa-skill/deployment.json")
    )
    parser.add_argument("--controller", required=True, help="Base URL without the dashboard token")
    parser.add_argument("--profile", required=True, help="Scoped AWS profile for relay objects")
    parser.add_argument("--name", default="Alexa screen")
    parser.add_argument("--lock", type=Path, default=Path(".local/alexa-destination/worker.lock"))
    args = parser.parse_args()
    if not 1 <= len(args.name.strip()) <= 40:
        parser.error("Use a short screen name")
    deployment = json.loads(args.deployment.read_text())
    if not deployment.get("destination_enabled"):
        parser.error("Enable the experimental destination deployment first")
    import fcntl

    args.lock.parent.mkdir(parents=True, exist_ok=True)
    with args.lock.open("a") as lock:
        args.lock.chmod(0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("A destination worker already holds this lock")
        import boto3
        from botocore.config import Config
        from okabebot.alexa_destination_relay import PrivateDestinationStore
        from okabebot.alexa_destination_bridge import ControllerDestination, SurfaceClient

        session = boto3.Session(profile_name=args.profile, region_name=deployment["region"])
        client = session.client(
            "s3", config=Config(connect_timeout=2, read_timeout=2, retries={"max_attempts": 1})
        )
        worker = ControllerDestination(
            PrivateDestinationStore(client, deployment["AudioBucket"]),
            SurfaceClient(args.controller),
            args.name.strip(),
        )
        previous = None
        try:
            while True:
                try:
                    status = worker.step()
                except Exception as exc:
                    status = "error:" + type(exc).__name__
                if status != previous:
                    print("Alexa destination:", status, flush=True)
                    previous = status
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("Destination worker stopped; receiver and controller leases recover ownership.")


if __name__ == "__main__":
    main()
