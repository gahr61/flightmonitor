"""
Diagnóstico rápido y NO interactivo: ¿Booking.com
bloquea acceso automatizado (como Despegar) o carga
normal (como Volaris)?

No pide ENTER ni requiere interacción manual — solo
carga la página, espera un poco, y cierra solo. Si el
resultado es que SÍ carga bien, ahí se justifica hacer
una captura interactiva completa como con Aeroméxico.
"""

import sys
import threading
from pathlib import Path

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


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

gitignore_path = OUTPUT_DIR / ".gitignore"
if not gitignore_path.exists():
    gitignore_path.write_text(
        "*\n!.gitignore\n",
        encoding="utf-8"
    )

OUTPUT_FILE = OUTPUT_DIR / "capture_booking_network.txt"

_log_lines = []
_log_lock = threading.Lock()


def log(*parts):

    text = " ".join(str(part) for part in parts)

    with _log_lock:
        _log_lines.append(text)

    print(text)


def flush_log():

    with _log_lock:
        content = "\n".join(_log_lines) + "\n"

    OUTPUT_FILE.write_text(content, encoding="utf-8")


load_dotenv()

config = load_config()
api = SerpApiGoogleFlights()


ROUTES = [
    ("SLP", "MID"),
    ("GDL", "MID"),
    ("SLP", "CUN"),
    ("GDL", "CUN"),
]

MAX_OUTBOUND_CANDIDATES = 3
MAX_RETURN_CANDIDATES = 3

TARGET_SELLER = "booking.com"

log("========================================")
log("BUSCANDO OFERTA CON BOOKING.COM")
log("========================================")

booking_request = None
found_route = None
all_sellers_seen = set()

for origin, destination in ROUTES:

    outbound_data = api.search_outbound(
        origin=origin,
        destination=destination,
        departure_date=config["departure_date"],
        return_date=config["return_date"],
        adults=config["adults"],
        children_ages=config["children_ages"],
        max_stops=config["max_stops"],
        currency=config["currency"]
    )

    flights = (
        outbound_data.get("best_flights", [])
        + outbound_data.get("other_flights", [])
    )

    for outbound in flights[:MAX_OUTBOUND_CANDIDATES]:

        return_data = api.search_return(
            origin=origin,
            destination=destination,
            departure_date=config["departure_date"],
            return_date=config["return_date"],
            adults=config["adults"],
            children_ages=config["children_ages"],
            departure_token=outbound["departure_token"],
            currency=config["currency"]
        )

        return_flights = (
            return_data.get("best_flights", [])
            + return_data.get("other_flights", [])
        )

        for regreso in return_flights[:MAX_RETURN_CANDIDATES]:

            booking_data = api.booking_options(
                origin=origin,
                destination=destination,
                departure_date=config["departure_date"],
                return_date=config["return_date"],
                adults=config["adults"],
                children_ages=config["children_ages"],
                booking_token=regreso["booking_token"],
                currency=config["currency"]
            )

            options = booking_data.get("booking_options", [])

            for option in options:

                together = option.get("together", {})

                book_with = together.get("book_with", "")

                all_sellers_seen.add(book_with)

                if book_with.lower() == TARGET_SELLER:

                    booking_request = together.get(
                        "booking_request"
                    )

                    found_route = (origin, destination)

                    break

            if booking_request:
                break

        if booking_request:
            break

    if booking_request:
        break


if not booking_request:

    log(
        "No se encontró a Booking.com como vendedor en "
        "ninguna de las combinaciones probadas."
    )

    log("Vendedores vistos:", sorted(all_sellers_seen))

    flush_log()

    sys.exit(1)


log(f"\nEncontrado en ruta {found_route[0]} -> {found_route[1]}")


google_response = requests.post(
    booking_request["url"],
    data=booking_request["post_data"],
    headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/148.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded"
    },
    allow_redirects=False,
    timeout=30
)

html = google_response.text
marker = "url='"
start = html.find(marker)

if start == -1:
    log("No se encontró URL de Booking.com.")
    flush_log()
    sys.exit(1)

start += len(marker)
end = html.find("'", start)

target_url = html[start:end].replace("&amp;", "&")

log("\nURL:")
log(target_url)


from playwright.sync_api import sync_playwright


log("\n========================================")
log("INICIANDO NAVEGADOR (modo diagnóstico, sin espera de ENTER)")
log("========================================")


KEYWORDS = [
    "api", "availability", "flight", "fare", "search",
    "booking", "reservation", "price", "graphql",
    "shopping", "captcha", "challenge", "block",
]


def is_interesting(url):
    lower = url.lower()
    return any(keyword in lower for keyword in KEYWORDS)


with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    context = browser.new_context(
        locale="es-MX",
        viewport={"width": 1440, "height": 900}
    )

    page = context.new_page()

    def on_request(request):

        url = request.url

        if not is_interesting(url):
            return

        post_data = request.post_data

        if not post_data:
            return

        log(f"\n>>> REQUEST {request.method} {url}")
        log("POST DATA (completo):")
        log(post_data)

    page.on("request", on_request)

    def on_response(response):

        url = response.url

        interesting = is_interesting(url)

        if not interesting and response.status < 400:
            return

        content_type = response.headers.get("content-type", "")

        log(
            f"\n<<< RESPONSE {response.status} "
            f"{response.request.method} {url}"
        )

        log("CONTENT-TYPE:", content_type)

        should_read_body = (
            response.status >= 400
            or "captcha" in url.lower()
            or "json" in content_type.lower()
        )

        if should_read_body:

            try:
                body = response.text()
                log("BODY (completo):")
                log(body)
            except Exception as error:
                log("No se pudo leer body:", error)

    page.on("response", on_response)

    log("\nCargando Booking.com...")

    try:
        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    except Exception as error:
        log("\nERROR AL CARGAR:", error)

    log("\nURL ACTUAL:", page.url)
    log("TÍTULO:", page.title())

    log("\nEsperando 15 segundos...")
    page.wait_for_timeout(15000)

    log("\nURL FINAL:", page.url)
    log("TÍTULO FINAL:", page.title())

    try:
        visible_text = page.inner_text("body")
        log("\nTEXTO VISIBLE DE LA PÁGINA (completo):")
        log(visible_text)
    except Exception as error:
        log("No se pudo leer el texto visible:", error)

    try:
        html = page.content()

        marker = "__NEXT_DATA__"
        idx = html.find(marker)

        if idx != -1:
            snippet = html[idx: idx + 20000]
            log("\nHTML cerca de __NEXT_DATA__:")
            log(snippet)
        else:
            log(
                "\nNo se encontró __NEXT_DATA__ en el HTML "
                f"(longitud total: {len(html)} chars)."
            )

    except Exception as error:
        log("No se pudo leer el HTML completo:", error)

    flush_log()

    browser.close()


flush_log()

print("\nSalida completa guardada en:", str(OUTPUT_FILE))
