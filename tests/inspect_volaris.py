import sys
from pathlib import Path
from urllib.parse import urljoin

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
print("INSPECCION VOLARIS")
print("========================================")


# -------------------------------------------------
# 1. OBTENER URL VOLARIS DESDE GOOGLE
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


regreso = volaris_returns[0]

booking_token = regreso.get(
    "booking_token"
)


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


booking_request = volaris_option.get(
    "booking_request",
    {}
)


google_response = requests.post(
    booking_request["url"],
    data=booking_request["post_data"],
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


html = google_response.text


marker = "url='"

start = html.find(marker)

if start == -1:

    print(
        "No se encontró URL."
    )

    sys.exit(1)


start += len(marker)

end = html.find(
    "'",
    start
)


volaris_url = html[start:end]

volaris_url = (
    volaris_url
    .replace("&amp;", "&")
)


# -------------------------------------------------
# 2. DESCARGAR VOLARIS
# -------------------------------------------------

print("\nDescargando Volaris...")


session = requests.Session()


response = session.get(
    volaris_url,
    headers={
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/148.0.0.0 "
            "Safari/537.36"
        ),
        "Accept":
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,"
            "image/webp,*/*;q=0.8",
        "Accept-Language":
            "es-MX,es;q=0.9,en;q=0.8"
    },
    timeout=60
)


print(
    "HTTP:",
    response.status_code
)

print(
    "HTML:",
    len(response.text),
    "bytes"
)


html = response.text


# -------------------------------------------------
# 3. EXTRAER SCRIPTS
# -------------------------------------------------

print("\n========================================")
print("JAVASCRIPT")
print("========================================")


from re import findall


scripts = findall(
    r'<script[^>]+src=["\']([^"\']+)',
    html,
    flags=0
)


print(
    "Scripts encontrados:",
    len(scripts)
)


for index, script in enumerate(
    scripts,
    start=1
):

    full_url = urljoin(
        volaris_url,
        script
    )

    print(
        f"{index:02d}: {full_url}"
    )


# -------------------------------------------------
# 4. BUSCAR REFERENCIAS DE API EN HTML
# -------------------------------------------------

print("\n========================================")
print("REFERENCIAS API EN HTML")
print("========================================")


patterns = [
    "api/",
    "/api",
    "api.",
    "availability",
    "search",
    "flight",
    "fare",
    "booking",
    "graphql"
]


lower_html = html.lower()


for pattern in patterns:

    positions = []

    start = 0

    while True:

        position = lower_html.find(
            pattern,
            start
        )

        if position == -1:
            break

        positions.append(
            position
        )

        start = position + 1


    print(
        f"{pattern}: "
        f"{len(positions)}"
    )


# -------------------------------------------------
# 5. MOSTRAR LINEAS RELEVANTES
# -------------------------------------------------

print("\n========================================")
print("FRAGMENTOS API")
print("========================================")


for pattern in [
    "/api",
    "api.",
    "availability",
    "graphql"
]:

    start = 0

    found = 0

    while found < 10:

        position = lower_html.find(
            pattern,
            start
        )

        if position == -1:
            break


        beginning = max(
            0,
            position - 150
        )

        ending = min(
            len(html),
            position + 300
        )


        fragment = (
            html[beginning:ending]
            .replace("\n", " ")
        )


        print(
            f"\n[{pattern}]"
        )

        print(
            fragment
        )


        start = position + 1

        found += 1