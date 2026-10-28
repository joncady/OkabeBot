"""Protocol-only model double for portable CI, never used as an inference backend."""

import json
import sys

json.loads(sys.stdin.readline())
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    json.loads(line)
    print(
        json.dumps(
            {
                "text": '<tool_call>{"name":"set_speaker_volume","arguments":{"percent":5}}</tool_call>',
                "selection_s": 0.001,
            }
        ),
        flush=True,
    )
