"""Build custom_components/ess_manager/frontend/ess-manager-cards.js from
tools/cards_template.js. Run from the repo root:

    python3 tools/build_cards.py          # write the file
    python3 tools/build_cards.py --check  # fail if it's out of date

The cards are drawn by the template itself (as of v0.5.1 all three - the
battery and price cards used to be generated from the dashboard/*.yaml
apexcharts examples). The build only makes the output pure ASCII.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "tools", "cards_template.js")
OUT = os.path.join(ROOT, "custom_components", "ess_manager", "frontend", "ess-manager-cards.js")


def build():
    with open(TEMPLATE, encoding="utf-8") as handle:
        content = handle.read()
    # Pure ASCII output (non-ASCII as \uXXXX escapes, valid in JS strings,
    # template literals and comments), so the file reads the same whatever
    # charset the browser assumes for it.
    return "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in content)


if __name__ == "__main__":
    content = build()
    if "--check" in sys.argv:
        with open(OUT, encoding="utf-8") as handle:
            if handle.read() != content:
                sys.exit("ess-manager-cards.js is out of date - run python3 tools/build_cards.py")
        print("ess-manager-cards.js is up to date")
    else:
        with open(OUT, "w", encoding="utf-8") as handle:
            handle.write(content)
        print(f"wrote {os.path.relpath(OUT, ROOT)} ({len(content)} bytes)")
