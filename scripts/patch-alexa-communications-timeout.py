#!/usr/bin/env python3
"""Optional guarded compatibility patch: bound ancillary Alexa preference requests.

Container updates replace this patch. Read-only unless --apply is supplied.
"""

import argparse
import ast
import inspect
import subprocess


def patch_source(source):
    marker = """        communications = (
            await self._communication_handler.get_communication_preferences(
                list(self._device_handler.devices.values())
            )
        )"""
    replacement = """        # OkabeBot compatibility: ancillary settings must not prevent sensor startup.
        try:
            communications = await asyncio.wait_for(
                self._communication_handler.get_communication_preferences(
                    list(self._device_handler.devices.values())
                ), timeout=10,
            )
        except asyncio.TimeoutError:
            communications = self._communication_handler._communication_preferences"""
    if replacement in source:
        return source
    if source.count(marker) != 1 or "import asyncio" not in source:
        raise ValueError("Unsupported Alexa API source; no changes made")
    result = source.replace(marker, replacement)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="okabebot-home-assistant")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    code = "import pathlib,shutil,time,ast,inspect\nimport aioamazondevices.api as api\n"
    code += inspect.getsource(patch_source)
    code += f"""
p=pathlib.Path(inspect.getfile(api));source=p.read_text();updated=patch_source(source)
if source == updated:
    print('Already patched')
elif {args.apply!r}:
    backup=pathlib.Path('/config/.local-compat-backups')/('communications-'+str(time.time_ns()))
    backup.mkdir(parents=True);shutil.copy2(p,backup/'api.py');p.write_text(updated)
    print('Patched optional communications deadline; process restart required')
else:
    print('Patch available; no changes made')
"""
    subprocess.run(
        ["docker", "exec", "-i", args.container, "python", "-"], input=code, text=True, check=True
    )


if __name__ == "__main__":
    main()
