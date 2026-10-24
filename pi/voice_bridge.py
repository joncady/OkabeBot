"""Compatibility entrypoint for old SSH registrations."""

import sys
from bridge import main

if __name__ == "__main__":
    sys.argv.extend(["--port", "8766"])
    main()
