"""
Diagnóstico NO interactivo: cargar directamente una URL
de "opciones" de Viva Aerobús (proporcionada a mano) y
ver qué llamadas de red aparecen. No pide ENTER.
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


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

OUTPUT_FILE = OUTPUT_DIR / "capture_vivaaerobus_options.txt"

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


TARGET_URL = (
    "https://www.vivaaerobus.com/es-mx/book/options"
    "?itineraryCode=SLP_MID_20261226.MID_SLP_20270103"
    "&passengers=A5_C2"
)


from playwright.sync_api import sync_playwright


KEYWORDS = [
    "api", "availability", "flight", "fare", "search",
    "booking", "reservation", "price", "graphql",
    "shopping", "bag", "ssr", "ancillary", "seat",
    "options", "itinerary", "quote",
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

        log(f"\n>>> REQUEST {request.method} {url}")

        if post_data:
            log("POST DATA (completo):")
            log(post_data)

    page.on("request", on_request)

    def on_response(response):

        url = response.url

        if not is_interesting(url):
            return

        content_type = response.headers.get("content-type", "")

        log(
            f"\n<<< RESPONSE {response.status} "
            f"{response.request.method} {url}"
        )

        log("CONTENT-TYPE:", content_type)

        if "json" in content_type.lower():

            try:
                body = response.text()
                log("BODY (completo):")
                log(body)
            except Exception as error:
                log("No se pudo leer body:", error)

    page.on("response", on_response)

    log("Cargando:", TARGET_URL)

    try:
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
    except Exception as error:
        log("ERROR AL CARGAR:", error)

    log("\nURL ACTUAL:", page.url)
    log("TÍTULO:", page.title())

    log("\nEsperando 20 segundos...")
    page.wait_for_timeout(20000)

    log("\nURL FINAL:", page.url)
    log("TÍTULO FINAL:", page.title())

    try:
        visible_text = page.inner_text("body")
        log("\nTEXTO VISIBLE (completo):")
        log(visible_text)
    except Exception as error:
        log("No se pudo leer texto visible:", error)

    flush_log()

    browser.close()


flush_log()

print("\nSalida completa guardada en:", str(OUTPUT_FILE))
