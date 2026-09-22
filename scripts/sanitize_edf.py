"""CLI wrapper: strip the 'EDF Annotations' channel from an EDF+ file.

The surgery lives in ``psg_core.edf.sanitize_edf`` so the API and scripts share
one implementation.

Usage: python scripts/sanitize_edf.py <input.edf> <output.edf>
"""

from __future__ import annotations

import sys

import _common  # noqa: F401  (inserts packages/psg_core onto sys.path)

from psg_core.edf import sanitize_edf  # noqa: E402


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python scripts/sanitize_edf.py <input.edf> <output.edf>")
    info = sanitize_edf(sys.argv[1], sys.argv[2])
    steps = info.get("steps") or []
    if steps:
        print("sanitize:", "; ".join(steps))
    else:
        print("no mutations required; wrote", sys.argv[2])
