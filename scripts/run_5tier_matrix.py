"""5-Tier Automated Verification Runner."""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> None:
    print("Running BHIV Enterprise Core 5-Tier Verification Matrix...")
    cmd = [sys.executable, "-m", "pytest", "-v"]
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
