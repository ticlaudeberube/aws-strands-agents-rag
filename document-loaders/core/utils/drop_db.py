#!/usr/bin/env python3
import sys
from core import drop_database
if __name__ == "__main__":
    name: str = sys.argv[1] if len(sys.argv) > 1 else None # type: ignore
    drop_database(name)