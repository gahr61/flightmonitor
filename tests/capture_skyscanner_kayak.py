"""
Diagnóstico NO interactivo: probar si Skyscanner y KAYAK
cargan resultados reales para nuestra búsqueda, o si
bloquean acceso automatizado. No pide ENTER.
"""

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)


from playwright.sync_api import sync_playwright


KEYWORDS = [
    "api", "availability", "flight", "fare", "search",
    "booking", "reservation", "price", "graphql",
    "poll", "itinerary", "quote", "results",
]


def is_interesting(url):
    lower = url.lower()
    return any(keyword in lower for keyword in KEYWORDS)


def run_site(name, url, wait_ms=20000):

    log_lines = []

    def log(*parts):
        text = " ".join(str(p) for p in parts)
        log_lines.append(text)
        print(f"[{name}]", text)

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000"],
        )

        context = browser.new_context(
            locale="es-MX",
            viewport={"width": 1440, "height": 900}
        )

        page = context.new_page()

        def on_request(request):
            if not is_interesting(request.url):
                return
            post_data = request.post_data
            log(f"\n>>> REQUEST {request.method} {request.url}")
            if post_data:
                log("POST DATA:", post_data[:500])

        page.on("request", on_request)

        def on_response(response):
            if not is_interesting(response.url) and response.status < 400:
                return
            content_type = response.headers.get("content-type", "")
            log(
                f"\n<<< RESPONSE {response.status} "
                f"{response.request.method} {response.url}"
            )
            log("CONTENT-TYPE:", content_type)
            if "json" in content_type.lower():
                try:
                    body = response.text()
                    log("BODY (primeros 1500 chars):")
                    log(body[:1500])
                except Exception as error:
                    log("No se pudo leer body:", error)

        page.on("response", on_response)

        log("Cargando:", url)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as error:
            log("ERROR AL CARGAR:", error)

        log("URL ACTUAL:", page.url)
        log("TÍTULO:", page.title())

        log(f"Esperando {wait_ms/1000:.0f} segundos...")
        page.wait_for_timeout(wait_ms)

        log("URL FINAL:", page.url)
        log("TÍTULO FINAL:", page.title())

        try:
            visible_text = page.inner_text("body")
            log("\nTEXTO VISIBLE (primeros 2000 chars):")
            log(visible_text[:2000])
        except Exception as error:
            log("No se pudo leer texto visible:", error)

        browser.close()

    output_file = OUTPUT_DIR / f"capture_{name}.txt"
    output_file.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\n[{name}] guardado en {output_file}")


SKYSCANNER_URL = (
    "https://www.skyscanner.com.mx/transporte/vuelos/"
    "gdl/mid/261226/270102/"
    "?adultsv2=5&childrenv2=6%2C5&cabinclass=economy&rtn=1"
    "&preferdirects=false&outboundaltsenabled=false"
    "&inboundaltsenabled=false"
)

KAYAK_URL = (
    "https://www.kayak.com.mx/flights/GDL-MID/"
    "2026-12-26/2027-01-02/5adults/children-6,5"
)

run_site("skyscanner", SKYSCANNER_URL)
run_site("kayak", KAYAK_URL)
