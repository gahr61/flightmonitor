import sys
import threading
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from dotenv import load_dotenv

from app.config import load_config


# -------------------------------------------------
# SALIDA A ARCHIVO
# -------------------------------------------------
#
# Mismo enfoque que capture_volaris_network.py: todo el
# log se acumula en memoria y se escribe/actualiza en
# disco cada ~10 segundos, para no perder cuerpos de
# respuesta por I/O lento.

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

gitignore_path = OUTPUT_DIR / ".gitignore"
if not gitignore_path.exists():
    gitignore_path.write_text(
        "*\n!.gitignore\n",
        encoding="utf-8"
    )

OUTPUT_FILE = OUTPUT_DIR / "capture_vivaaerobus_network.txt"

_log_lines = []
_log_lock = threading.Lock()


def log(*parts):

    text = " ".join(
        str(part)
        for part in parts
    )

    with _log_lock:
        _log_lines.append(text)

    print(text)


def flush_log():

    with _log_lock:
        content = "\n".join(_log_lines) + "\n"

    OUTPUT_FILE.write_text(
        content,
        encoding="utf-8"
    )


# -------------------------------------------------
# ENMASCARADO DE VALORES SENSIBLES
# -------------------------------------------------

SENSITIVE_HEADER_NAMES = [
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "token",
    "apikey",
]


def mask_headers(headers):

    masked = {}

    for key, value in headers.items():

        if any(
            sensitive in key.lower()
            for sensitive in SENSITIVE_HEADER_NAMES
        ):
            masked[key] = (
                value[:6] + "...MASKED"
                if value else value
            )
        else:
            masked[key] = value

    return masked


load_dotenv()

config = load_config()


VIVA_URL = "https://www.vivaaerobus.com/"


# -------------------------------------------------
# PLAYWRIGHT
# -------------------------------------------------

from playwright.sync_api import sync_playwright


log("\n========================================")
log("INICIANDO NAVEGADOR - VIVA AEROBUS")
log("========================================")


request_counter = {"n": 0}
response_counter = {"n": 0}

KEYWORDS = [
    "api",
    "availability",
    "flight",
    "fare",
    "search",
    "booking",
    "reservation",
    "price",
    "graphql",
    "shopping",
    "bag",
    "ssr",
    "ancillary",
    "seat",
    "create",
    "checkout",
    "cart",
    "quote",
    "itinerary",
]


def is_interesting(url):

    lower = url.lower()

    return any(
        keyword in lower
        for keyword in KEYWORDS
    )


TRACKER_DOMAINS = [
    "doubleclick.net",
    "google-analytics.com",
    "analytics.google.com",
    "googletagmanager.com",
    "amplitude.com",
    "bat.bing.com",
    "uplift-platform.com",
    "facebook.com",
    "facebook.net",
    "hotjar.com",
    "securitytrfx.com",
]


try:

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context(
            locale="es-MX",
            viewport={
                "width": 1440,
                "height": 900
            }
        )


        def route_handler(route):

            url = route.request.url.lower()

            if any(
                domain in url
                for domain in TRACKER_DOMAINS
            ):
                route.abort()
            else:
                route.continue_()

        context.route("**/*", route_handler)

        page = context.new_page()


        def on_request(request):

            url = request.url

            if not is_interesting(url):
                return

            with _log_lock:
                request_counter["n"] += 1
                n = request_counter["n"]

            try:
                headers = mask_headers(request.headers)
            except Exception as error:
                headers = {"_error": str(error)}

            post_data = request.post_data

            log(
                "\n>>> REQUEST #{}\n{} {}\nHEADERS: {}{}".format(
                    n,
                    request.method,
                    url,
                    headers,
                    (
                        "\nPOST DATA (completo):\n" + post_data
                        if post_data else ""
                    )
                )
            )


        def on_response(response):

            url = response.url

            if not is_interesting(url):
                return

            body_text = None
            body_error = None

            content_type = response.headers.get(
                "content-type",
                ""
            )

            should_read_body = (
                "json" in content_type.lower()
                or "javascript" in content_type.lower()
                or "text" in content_type.lower()
            )

            if should_read_body:

                try:
                    body_text = response.text()
                except Exception as error:
                    body_error = str(error)

            with _log_lock:
                response_counter["n"] += 1
                n = response_counter["n"]

            parts = [
                "\n<<< RESPONSE #{}".format(n),
                "{} {} {}".format(
                    response.status,
                    response.request.method,
                    url
                ),
                "CONTENT-TYPE: {}".format(content_type)
            ]

            if body_text is not None:
                parts.append("RESPONSE (completo):")
                parts.append(body_text)
            elif body_error is not None:
                parts.append(
                    "No se pudo leer response: " + body_error
                )

            log("\n".join(parts))


        page.on("request", on_request)
        page.on("response", on_response)


        log("\nCargando vivaaerobus.com...")

        try:

            page.goto(
                VIVA_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

        except Exception as error:

            log("\nERROR AL CARGAR:", error)


        log("\n========================================")
        log("PÁGINA CARGADA")
        log("========================================")

        log("URL ACTUAL:", page.url)
        log("TÍTULO:", page.title())


        log(
            "\nEsperando 10 segundos para que "
            "termine de cargar la página inicial..."
        )

        page.wait_for_timeout(10000)

        flush_log()


        log("\n========================================")
        log("ACCIÓN MANUAL REQUERIDA")
        log("========================================")

        log(
            "\nEn la ventana del navegador que se abrió, "
            "por favor haz una búsqueda REAL con estos "
            "datos:"
        )

        log(
            f"  Origen/Destino: alguna de estas 4 rutas: "
            f"SLP-MID, GDL-MID, SLP-CUN, GDL-CUN"
        )

        log(
            f"  Ida: {config['departure_date']} "
            f"| Regreso: {config['return_date']}"
        )

        log(
            f"  Pasajeros: {config['adults']} adultos + "
            f"{len(config.get('children_ages', []))} niños "
            f"(edades: {config.get('children_ages', [])})"
        )

        log(
            "\nAvanza hasta ver los resultados con precios "
            "reales. Si puedes, entra a un vuelo y avanza "
            "hasta ver la opción de maleta documentada, "
            "SIN pagar ni confirmar nada."
        )

        log(
            "\nEl archivo de salida se irá actualizando "
            "cada ~10 segundos mientras el navegador esté "
            "abierto:"
        )

        log("  " + str(OUTPUT_FILE))

        log(
            "\nCuando termines, regresa aquí y presiona "
            "ENTER para cerrar el navegador."
        )


        stop_flag = threading.Event()

        def periodic_flush():

            while not stop_flag.is_set():

                stop_flag.wait(10)

                try:
                    flush_log()
                except Exception:
                    pass

        flush_thread = threading.Thread(
            target=periodic_flush,
            daemon=True
        )

        flush_thread.start()

        input()

        stop_flag.set()

        browser.close()

finally:

    flush_log()

    print(
        "\nSalida completa guardada en:",
        str(OUTPUT_FILE)
    )
