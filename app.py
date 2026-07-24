#!/usr/bin/env python3
"""
Documentary Studio - launch the dashboard.

    python app.py                 # opens the dashboard in your browser
    python app.py --port 9000     # custom port
    python app.py --no-browser    # don't auto-open

Everything (input, footage, indexing, selection, narration, motion
graphics, rendering, validation, logs) is driven from the dashboard.
"""

import argparse

from dashboard import server


def main():
    ap = argparse.ArgumentParser(description="Documentary Studio dashboard")
    ap.add_argument("--port", type=int, default=8760)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server.serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
