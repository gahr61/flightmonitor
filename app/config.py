import json
from pathlib import Path


def load_config():

    path = Path("config.json")

    if not path.exists():
        raise FileNotFoundError(
            "No existe config.json."
        )

    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)