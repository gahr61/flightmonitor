import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from dotenv import load_dotenv

import requests

from app.config import load_config

from app.providers.serpapi_google_flights import (
    SerpApiGoogleFlights
)


load_dotenv()

config = load_config()

api = SerpApiGoogleFlights()


print("\n========================================")
print("PRUEBA BOOKING REQUEST VOLARIS")
print("========================================")


# -------------------------------------------------
# 1. BUSCAR IDA
# -------------------------------------------------

data = api.search_outbound(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    max_stops=config["max_stops"],
    currency=config["currency"]
)


flights = (
    data.get("best_flights", [])
    +
    data.get("other_flights", [])
)


volaris = [
    flight
    for flight in flights
    if any(
        segment.get("airline") == "Volaris"
        for segment in flight.get("flights", [])
    )
]


if not volaris:
    print("No se encontró Volaris.")
    sys.exit(1)


outbound = volaris[0]

departure_token = outbound.get(
    "departure_token"
)


if not departure_token:
    print("No existe departure_token.")
    sys.exit(1)


# -------------------------------------------------
# 2. BUSCAR REGRESO
# -------------------------------------------------

return_data = api.search_return(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    departure_token=departure_token,
    currency=config["currency"]
)


return_flights = (
    return_data.get("best_flights", [])
    +
    return_data.get("other_flights", [])
)


volaris_returns = [
    flight
    for flight in return_flights
    if any(
        segment.get("airline") == "Volaris"
        for segment in flight.get("flights", [])
    )
]


if not volaris_returns:
    print("No hay regresos Volaris.")
    sys.exit(1)


regreso = volaris_returns[0]

booking_token = regreso.get(
    "booking_token"
)


if not booking_token:
    print("No existe booking_token.")
    sys.exit(1)


# -------------------------------------------------
# 3. BOOKING OPTIONS
# -------------------------------------------------

booking_data = api.booking_options(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    booking_token=booking_token,
    currency=config["currency"]
)


options = booking_data.get(
    "booking_options",
    []
)


volaris_option = None


for option in options:

    together = option.get(
        "together",
        {}
    )

    if together.get(
        "book_with"
    ) == "Volaris":

        volaris_option = together
        break


if not volaris_option:
    print(
        "No se encontró opción Volaris."
    )
    sys.exit(1)


# -------------------------------------------------
# 4. BOOKING REQUEST
# -------------------------------------------------

booking_request = volaris_option.get(
    "booking_request",
    {}
)


url = booking_request.get(
    "url"
)

post_data = booking_request.get(
    "post_data"
)


if not url or not post_data:

    print(
        "No existe booking_request completo."
    )

    sys.exit(1)


print("\n========================================")
print("ENVIANDO REQUEST")
print("========================================")


response = requests.post(
    url,
    data=post_data,
    headers={
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/148.0.0.0 "
            "Safari/537.36"
        ),
        "Content-Type":
            "application/x-www-form-urlencoded"
    },
    allow_redirects=False,
    timeout=30
)


print(
    "HTTP:",
    response.status_code
)

print(
    "Content-Type:",
    response.headers.get(
        "content-type"
    )
)

print(
    "Content-Length:",
    len(response.content)
)


print("\n========================================")
print("RESPUESTA HTML")
print("========================================")


text = response.text


print(text)