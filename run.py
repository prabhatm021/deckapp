#!/usr/bin/env python3
"""Run DeckApp straight from a git checkout: python3 run.py"""
import os
import sys

# Make the parent directory importable so `import deckapp` finds this checkout
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deckapp.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
