import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

import requests

from dotenv import load_dotenv

from app.config import load_config
from app.providers.serpapi_google_flights import (
    SerpApiGoogleFlights
)


load_dotenv()

config = load_config()
api = SerpApiGoogleFlights()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/148.0.0.0 "
        "Safari/537.36"
    )
}


print("\n========================================")
print("INSPECCION JAVASCRIPT VOLARIS")
print("========================================")


# -------------------------------------------------
# 1. OBTENER URL DE VOLARIS
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

return_data = api.search_return(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    departure_token=outbound["departure_token"],
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
    print("No se encontró regreso Volaris.")
    sys.exit(1)


booking_data = api.booking_options(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    booking_token=volaris_returns[0]["booking_token"],
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

    if together.get("book_with") == "Volaris":

        volaris_option = together
        break


if not volaris_option:

    print("No se encontró opción directa Volaris.")
    sys.exit(1)


booking_request = volaris_option.get(
    "booking_request"
)

if not booking_request:

    print("No existe booking_request.")
    sys.exit(1)


# -------------------------------------------------
# 2. GOOGLE -> VOLARIS
# -------------------------------------------------

google_response = requests.post(
    booking_request["url"],
    data=booking_request["post_data"],
    headers={
        **HEADERS,
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

    print("No se encontró URL de Volaris.")
    sys.exit(1)

start += len(marker)

end = html.find(
    "'",
    start
)

volaris_url = (
    html[start:end]
    .replace("&amp;", "&")
)


print("\nURL VOLARIS:")
print(volaris_url)


# -------------------------------------------------
# 3. DESCARGAR PÁGINA
# -------------------------------------------------

session = requests.Session()

response = session.get(
    volaris_url,
    headers=HEADERS,
    timeout=60
)

html = response.text

print("\nHTTP:", response.status_code)
print("HTML:", len(html), "bytes")


# -------------------------------------------------
# 4. EXTRAER JAVASCRIPT
# -------------------------------------------------

import re

scripts = re.findall(
    r'<script[^>]+src=["\']([^"\']+)',
    html
)

print("\n========================================")
print("SCRIPTS")
print("========================================")

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
# 5. DESCARGAR JS
# -------------------------------------------------

output_dir = Path(
    "tests",
    "volaris_js"
)

output_dir.mkdir(
    parents=True,
    exist_ok=True
)


downloaded = []

for script in scripts:

    url = urljoin(
        volaris_url,
        script
    )

    filename = url.split("/")[-1]

    print(
        "\nDescargando:",
        filename
    )

    try:

        js_response = session.get(
            url,
            headers=HEADERS,
            timeout=60
        )

        print(
            "HTTP:",
            js_response.status_code,
            "bytes:",
            len(js_response.content)
        )

        if js_response.ok:

            path = output_dir / filename

            path.write_bytes(
                js_response.content
            )

            downloaded.append(path)

    except Exception as error:

        print(
            "ERROR:",
            error
        )


# -------------------------------------------------
# 6. BUSCAR ENDPOINTS
# -------------------------------------------------

print("\n========================================")
print("ENDPOINTS / API")
print("========================================")


patterns = [
    r'https?://[^"\']+',
    r'["\'][^"\']*/api/[^"\']*["\']',
    r'["\'][^"\']*api\.[^"\']+["\']',
    r'["\'][^"\']*availability[^"\']*["\']',
    r'["\'][^"\']*search[^"\']*["\']',
    r'["\'][^"\']*fare[^"\']*["\']',
    r'["\'][^"\']*flight[^"\']*["\']',
    r'["\'][^"\']*booking[^"\']*["\']',
    r'["\'][^"\']*reservation[^"\']*["\']',
    r'["\'][^"\']*price[^"\']*["\']',
]


for path in downloaded:

    print("\n----------------------------------------")
    print(path.name)
    print("----------------------------------------")

    try:

        text = path.read_text(
            encoding="utf-8",
            errors="ignore"
        )

    except Exception as error:

        print("ERROR:", error)
        continue


    found = set()

    for pattern in patterns:

        matches = re.findall(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        for match in matches:

            value = match.strip(
                "\"'"
            )

            if len(value) > 500:
                continue

            found.add(value)


    for value in sorted(found):

        print(value)


# -------------------------------------------------
# 7. PALABRAS CLAVE
# -------------------------------------------------

print("\n========================================")
print("PALABRAS CLAVE")
print("========================================")


keywords = [
    "availability",
    "availabilities",
    "fare",
    "fares",
    "flight",
    "flights",
    "booking",
    "reservation",
    "searchFlights",
    "searchFlight",
    "price",
    "prices",
    "lowFare",
    "shopping",
    "schedule",
    "journey",
    "journeys"
]


for path in downloaded:

    text = path.read_text(
        encoding="utf-8",
        errors="ignore"
    ).lower()

    print(
        f"\n{path.name}"
    )

    for keyword in keywords:

        count = text.count(
            keyword.lower()
        )

        if count:

            print(
                f"  {keyword}: {count}"
            )


print("\n========================================")
print("FIN")
print("========================================")

print(
    "\nLos archivos JS quedaron en:",
    output_dir
)