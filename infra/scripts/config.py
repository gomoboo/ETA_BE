#!/usr/bin/env python3
"""Read non-secret EC2 bootstrap configuration."""
import json
import sys
from pathlib import Path

if __name__ == "__main__":
    config = json.loads(Path("/etc/eta/config.json").read_text())
    print(config[sys.argv[1]])
