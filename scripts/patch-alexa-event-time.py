#!/usr/bin/env python3
"""Optional version-guarded HA backport: expose original Alexa history time.

Read-only unless --apply is supplied. Container updates replace this backport;
missing source time makes the companion voice bridge fail closed.
"""

import argparse
import ast
import inspect
import subprocess


def patch_source(source):
    marker = '                "intent": vocal_record.intent,'
    addition = '                "source_timestamp_ms": vocal_record.timestamp,\n'
    if addition.strip() in source:
        return source
    if source.count(marker) != 1 or "class AlexaVoiceEvent(" not in source:
        raise ValueError("Unsupported Alexa event source; no changes made")
    result = source.replace(marker, addition + marker)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="okabebot-home-assistant")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    code = (
        """import ast,json,pathlib,shutil,time
from homeassistant.const import __version__
"""
        + inspect.getsource(patch_source)
        + f"""
if __version__ != "2026.10.4":
    raise SystemExit("Only validated for HA 2026.10.4; inspect your version before applying")
p=pathlib.Path("/usr/src/homeassistant/homeassistant/components/alexa_devices/event.py")
source=p.read_text(); updated=patch_source(source)
if updated == source:
    print(json.dumps({{"status":"already_present"}}))
elif {args.apply!r}:
    backup=pathlib.Path("/config/.local-compat-backups")/("alexa-event-time-"+str(time.time_ns()))
    backup.mkdir(parents=True);shutil.copy2(p,backup/"event.py")
    p.write_text(updated)
    print(json.dumps({{"status":"patched","reload_required":True}}))
else:
    print(json.dumps({{"status":"patch_needed","changed":False}}))
"""
    )
    subprocess.run(
        ["docker", "exec", "-i", args.container, "python", "-"], input=code, text=True, check=True
    )


if __name__ == "__main__":
    main()
