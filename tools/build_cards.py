"""Build custom_components/ess_manager/frontend/ess-manager-cards.js from
tools/cards_template.js and the dashboard/*.yaml examples, so the cards the
integration loads are exactly the examples. Run from the repo root:

    python3 tools/build_cards.py          # write the file
    python3 tools/build_cards.py --check  # fail if it's out of date
"""
import json
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "tools", "cards_template.js")
OUT = os.path.join(ROOT, "custom_components", "ess_manager", "frontend", "ess-manager-cards.js")
SOURCES = {
    "battery": "dashboard/battery_forecast_chart.yaml",
    "price": "dashboard/price_apexcharts_card.yaml",
}


def _card(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    # battery / price examples are a one-card list (paste-ready for a view)
    return data[0] if isinstance(data, list) else data


def build():
    templates = {key: _card(path) for key, path in SOURCES.items()}
    with open(TEMPLATE, encoding="utf-8") as handle:
        template = handle.read()
    body = "const TEMPLATES = " + json.dumps(templates, indent=2, ensure_ascii=False) + ";"
    content = template.replace("// @@TEMPLATES@@", body)
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
