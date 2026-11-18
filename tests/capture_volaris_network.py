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


# -------------------------------------------------
# SALIDA A ARCHIVO
# -------------------------------------------------
#
# Todo el log se acumula en memoria y se escribe al
# archivo al final (o si el script se interrumpe).
# Esto evita que la escritura a disco retrase la
# lectura del cuerpo de las respuestas de red, que
# es lo que estaba causando pérdida de datos
# ("No data found for resource with given identifier")
# en respuestas rápidas como /booking/quote.

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

gitignore_path = OUTPUT_DIR / ".gitignore"
if not gitignore_path.exists():
    gitignore_path.write_text(
        "*\n!.gitignore\n",
        encoding="utf-8"
    )

OUTPUT_FILE = OUTPUT_DIR / "capture_volaris_network.txt"

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
api = SerpApiGoogleFlights()


# -------------------------------------------------
# OBTENER DEEPLINK DE VOLARIS
# -------------------------------------------------

log("\n========================================")
log("OBTENIENDO URL VOLARIS")
log("========================================")


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

    log("No se encontró un vuelo Volaris.")

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

    log("No se encontró regreso Volaris.")

    sys.exit(1)


regreso = volaris_returns[0]


booking_data = api.booking_options(
    origin="GDL",
    destination="MID",
    departure_date=config["departure_date"],
    return_date=config["return_date"],
    adults=config["adults"],
    children_ages=config["children_ages"],
    booking_token=regreso["booking_token"],
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

    log("No se encontró vendedor Volaris.")

    sys.exit(1)


booking_request = volaris_option.get(
    "booking_request"
)


if not booking_request:

    log("No existe booking_request.")

    sys.exit(1)


# -------------------------------------------------
# GOOGLE -> VOLARIS
# -------------------------------------------------

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

    log("No se encontró URL de Volaris.")

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

# Forzamos mercado/idioma México explícitamente.
# El deeplink que genera Google Flights suele traer
# culture=en-US aunque la moneda ya sea MXN; queremos
# la experiencia real de Volaris México (es-MX).
volaris_url = volaris_url.replace(
    "culture=en-US",
    "culture=es-MX"
)


log("\nURL:")
log(volaris_url)


# -------------------------------------------------
# PLAYWRIGHT
# -------------------------------------------------

from playwright.sync_api import (
    sync_playwright
)


log("\n========================================")
log("INICIANDO NAVEGADOR")
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
    "cart"
]


def is_interesting(url):

    lower = url.lower()

    return any(
        keyword in lower
        for keyword in KEYWORDS
    )


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


        # -----------------------------------------
        # BLOQUEAR TRACKERS DE TERCEROS
        # -----------------------------------------
        #
        # Estos no aportan nada a la captura y
        # generan mucho ruido de red concurrente que
        # parece saturar el buffer de Chrome y hacer
        # que se pierdan cuerpos de respuestas
        # importantes como /booking/quote.

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


        # ---------------------------------------------
        # REQUESTS
        # ---------------------------------------------

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


        # ---------------------------------------------
        # RESPONSES
        # ---------------------------------------------

        def on_response(response):

            url = response.url

            if not is_interesting(url):
                return

            # Leemos el cuerpo INMEDIATAMENTE, antes de
            # cualquier print/log, para minimizar el
            # riesgo de que el buffer de Chrome ya haya
            # descartado la respuesta.
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


        # ---------------------------------------------
        # CARGAR VOLARIS
        # ---------------------------------------------

        log("\nCargando Volaris...")

        try:

            page.goto(
                volaris_url,
                wait_until="domcontentloaded",
                timeout=120000
            )

        except Exception as error:

            log("\nERROR AL CARGAR:", error)


        log("\n========================================")
        log("PÁGINA CARGADA")
        log("========================================")

        log("URL ACTUAL:", page.url)
        log("TÍTULO:", page.title())


        log(
            "\nEsperando 25 segundos "
            "para que carguen los resultados..."
        )

        page.wait_for_timeout(25000)

        flush_log()


        # ---------------------------------------------
        # NAVEGACIÓN MANUAL
        # ---------------------------------------------
        #
        # No hacemos clic automático: el DOM de Volaris
        # usa clases genéricas de Angular y un clic a
        # ciegas termina activando cosas como filtros
        # de tarifa en vez de seleccionar un vuelo real.
        #
        # En su lugar, el navegador se queda abierto y
        # tú avanzas el flujo a mano. Todo lo que hagas
        # se sigue registrando en memoria y se vuelca al
        # archivo cada vez que se detecta una respuesta
        # de booking/quote, y también al cerrar.

        log("\n========================================")
        log("ACCIÓN MANUAL REQUERIDA")
        log("========================================")

        log(
            "\nEn la ventana del navegador que se abrió, "
            "por favor:"
        )

        log(
            "  1. Elige CUALQUIER vuelo de ida "
            "(preferentemente uno sin escala) y una "
            "tarifa (Zero/Basic/Classic/Plus)."
        )

        log(
            "  2. Continúa hasta la selección del "
            "vuelo de regreso y elige uno."
        )

        log(
            "  3. Avanza hasta la pantalla donde se "
            "ofrece AGREGAR MALETA DOCUMENTADA, pero "
            "NO agregues datos de pago ni confirmes "
            "la compra."
        )

        log(
            "\nEl archivo de salida se irá actualizando "
            "cada ~10 segundos mientras el navegador "
            "esté abierto:"
        )

        log("  " + str(OUTPUT_FILE))

        log(
            "\nCuando llegues a la pantalla de maletas "
            "(o si prefieres detenerte antes), regresa "
            "aquí y presiona ENTER para cerrar el "
            "navegador."
        )


        # Volcado periódico mientras esperamos el ENTER,
        # para que puedas revisar el archivo sin tener
        # que cerrar el navegador primero.

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
