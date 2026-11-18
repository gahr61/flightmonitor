import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from dotenv import load_dotenv

from app.config import load_config

from app.providers.serpapi_google_flights import (
    SerpApiGoogleFlights
)


load_dotenv()

config = load_config()

api = SerpApiGoogleFlights()

data = api.search_outbound(

    origin="GDL",

    destination="MID",

    departure_date=
        config["departure_date"],

    return_date=
        config["return_date"],

    adults=
        config["adults"],

    children_ages=
        config["children_ages"],

    max_stops=
        config["max_stops"],

    currency=
        config["currency"]
)

print(
    "\n========================================"
)

print(
    "RESULTADO SERPAPI"
)

print(
    "========================================"
)

print(
    "Best flights:",
    len(
        data.get(
            "best_flights",
            []
        )
    )
)

print(
    "Other flights:",
    len(
        data.get(
            "other_flights",
            []
        )
    )
)

for index, flight in enumerate(

    data.get(
        "best_flights",
        []
    )
    +
    data.get(
        "other_flights",
        []
    ),

    start=1
):

    airlines = [

        segment.get("airline")

        for segment
        in flight.get(
            "flights",
            []
        )
    ]

    print(

        f"{index:02d} | "

        f"Precio="
        f"{flight.get('price')} | "

        f"Aerolíneas="
        f"{airlines} | "

        f"Escalas="
        f"{max(0, len(flight.get('flights', [])) - 1)}"
    )