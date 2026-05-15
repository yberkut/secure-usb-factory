#!/usr/bin/env python3
from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    try:
        import pytest
    except ModuleNotFoundError:
        print("pytest is not installed for this Python environment", file=sys.stderr)
        return 2
    return int(pytest.main(sys.argv[1:]))


if __name__ == "__main__":
    exit_code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(exit_code)
