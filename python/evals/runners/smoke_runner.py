from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    fixtures = sorted((root / "tests" / "fixtures").glob("*"))
    report = {
        "benchmark": "smoke",
        "fixture_count": len(fixtures),
        "fixtures": [fixture.name for fixture in fixtures],
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
