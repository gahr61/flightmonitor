import sys
from pathlib import Path
from html import unescape
from urllib.parse import urlparse

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
print("PRUEBA DIRECTA VOLARIS")
print("========================================")


# -------------------------------------------------
# 1. BUSCAR VOLARIS
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

    print(
        "No se encontró Volaris."
    )

    sys.exit(1)


outbound = volaris[0]

departure_token = outbound.get(
    "departure_token"
)


if not departure_token:

    print(
        "No existe departure_token."
    )

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

    print(
        "No hay regresos Volaris."
    )

    sys.exit(1)


regreso = volaris_returns[0]

booking_token = regreso.get(
    "booking_token"
)


if not booking_token:

    print(
        "No existe booking_token."
    )

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
# 4. OBTENER DEEPLINK
# -------------------------------------------------

booking_request = volaris_option.get(
    "booking_request",
    {}
)


google_url = booking_request.get(
    "url"
)

post_data = booking_request.get(
    "post_data"
)


if not google_url or not post_data:

    print(
        "Booking request incompleto."
    )

    sys.exit(1)


print(
    "\nEnviando request a Google Flights..."
)


google_response = requests.post(
    google_url,
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


html = google_response.text


# -------------------------------------------------
# 5. EXTRAER URL DE VOLARIS
# -------------------------------------------------

marker = "url='"

start = html.find(marker)


if start == -1:

    print(
        "No se encontró URL de Volaris."
    )

    print(html)

    sys.exit(1)


start += len(marker)

end = html.find(
    "'",
    start
)


volaris_url = html[start:end]

volaris_url = unescape(
    volaris_url
)


print("\n========================================")
print("URL VOLARIS")
print("========================================")

print(
    volaris_url
)


# -------------------------------------------------
# 6. VALIDAR URL
# -------------------------------------------------

parsed = urlparse(
    volaris_url
)


print("\n========================================")
print("DATOS URL")
print("========================================")

print(
    "Scheme:",
    parsed.scheme
)

print(
    "Host:",
    parsed.netloc
)

print(
    "Path:",
    parsed.path
)

print(
    "Longitud:",
    len(volaris_url)
)


# -------------------------------------------------
# 7. CONSULTAR VOLARIS
# -------------------------------------------------

print("\n========================================")
print("CONSULTANDO VOLARIS")
print("========================================")


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
    allow_redirects=True,
    timeout=60
)


print(
    "\nHTTP:",
    response.status_code
)

print(
    "URL final:",
    response.url
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


# -------------------------------------------------
# 8. BUSCAR INDICIOS DE PRECIO
# -------------------------------------------------

text = response.text

keywords = [
    "price",
    "precio",
    "total",
    "MXN",
    "fare",
    "Volaris"
]


print("\n========================================")
print("INDICIOS EN HTML")
print("========================================")


for keyword in keywords:

    count = text.lower().count(
        keyword.lower()
    )

    print(
        f"{keyword}: {count}"
    )