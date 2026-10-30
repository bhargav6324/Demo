"""Run from the project root: python -m scripts.export_openapi."""

import json
from pathlib import Path

from app.api.contract import create_contract_app


def main():
    output = Path("docs/openapi.draft.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(create_contract_app().openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"Exported draft contract: {output}")


if __name__ == "__main__":
    main()
