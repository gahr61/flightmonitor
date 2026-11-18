"""
Cliente directo a KAYAK (www.kayak.com.mx) usando un
navegador real (Playwright) para leer su endpoint interno
de polling (i/api/search/dynamic/flights/poll).

A diferencia de Skyscanner (bloqueado con CAPTCHA/PerimeterX)
o Despegar (bloqueado con DataDome), KAYAK no detectó ni
bloqueó el acceso automatizado en las pruebas — carga
normal, sin desafíos.

KAYAK mezcla, para cada itinerario, tanto agencias (OTA)
como la aerolínea misma como "proveedor" dentro de
bookingOptions. Este cliente filtra SOLO las opciones
donde el proveedor es la aerolínea (código IATA: AM, Y4,
VB), para no confundir precio directo con precio de
agencia.

Una sola búsqueda cubre las 3 aerolíneas a la vez (un solo
navegador por ruta, no uno por aerolínea). Se usa como
VALIDACIÓN CRUZADA adicional -- no reemplaza los clientes
directos ya existentes (VolarisDirect, booking_direct /
aeromexico_search, viva_direct).

Pendiente (no resuelto aquí):
  - Precio de maleta documentada extra.
"""

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.kayak.com.mx"

AIRLINE_CODES = {
    "Aeromexico": "AM",
    "Volaris": "Y4",
    "Viva Aerobus": "VB",
}

POLL_URL_MARKER = "search/dynamic/flights/poll"


def _search_url(
    origin, destination, departure_date, return_date,
    adults, children_ages
):

    path = (
        f"/flights/{origin}-{destination}/"
        f"{departure_date}/{return_date}/{adults}adults"
    )

    if children_ages:

        ages = "-".join(
            str(age) for age in children_ages
        )

        path += f"/children-{ages}"

    return BASE_URL + path


def fetch_results(
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children_ages,
    wait_ms=25000,
    timeout_ms=60000,
):
    """
    Abre un navegador (oculto fuera de pantalla), navega a
    la búsqueda, y devuelve la respuesta de polling MÁS
    COMPLETA capturada (dict crudo), o None si no se
    capturó ninguna.
    """

    url = _search_url(
        origin, destination, departure_date, return_date,
        adults, children_ages
    )

    responses = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=False,
            args=["--window-position=-32000,-32000"],
        )

        context = browser.new_context(locale="es-MX")

        page = context.new_page()

        def on_response(response):

            if POLL_URL_MARKER not in response.url:
                return

            try:
                responses.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout_ms,
            )

            page.wait_for_timeout(wait_ms)

        except Exception:
            pass

        browser.close()

    if not responses:
        return None

    return responses[-1]


def _leg_stops(booking_option):

    max_stops = 0

    for leg in booking_option.get("legFarings", []):

        segments = leg.get("segmentFarings", [])

        stops = max(0, len(segments) - 1)

        max_stops = max(max_stops, stops)

    return max_stops


def extract_best_price(
    data,
    airline_name,
    total_passengers,
    max_stops=1,
):
    """
    A partir de una respuesta ya obtenida con
    fetch_results(), extrae el precio directo más barato
    de la aerolínea indicada (ignorando agencias), para el
    grupo completo de pasajeros.

    Devuelve None si no hay ninguna opción válida, o el
    precio total (float).
    """

    airline_code = AIRLINE_CODES.get(airline_name)

    if not airline_code or not data:
        return None

    results = [
        r for r in data.get("results", [])
        if r.get("type") == "core"
    ]

    best = None

    for result in results:

        for booking_option in result.get(
            "bookingOptions", []
        ):

            if (
                booking_option.get("providerCode")
                != airline_code
            ):
                continue

            if _leg_stops(booking_option) > max_stops:
                continue

            fees = booking_option.get("fees", {})

            total_price = fees.get(
                "totalPrice", {}
            ).get("price")

            travelers = fees.get("numTravelers")

            if total_price is None:
                continue

            if (
                travelers
                and travelers != total_passengers
            ):
                # KAYAK a veces cotiza para un subconjunto
                # de pasajeros; solo confiamos en
                # resultados que cubren al grupo completo.
                continue

            if best is None or total_price < best:
                best = total_price

    return best


def find_best_round_trip(
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children_ages,
    airline_name,
    max_stops=1,
    max_connection_minutes=300,
    currency="MXN",
):
    """
    Busca en KAYAK (una sola carga de página) el precio
    directo más barato de la aerolínea indicada.

    Devuelve None si no se encontró, o:

      {
        "origin", "destination",
        "total_price": float,
        "per_person_price": float,
      }
    """

    total_passengers = adults + len(children_ages or [])

    data = fetch_results(
        origin, destination, departure_date, return_date,
        adults, children_ages
    )

    best = extract_best_price(
        data, airline_name, total_passengers, max_stops
    )

    if best is None:
        return None

    return {
        "origin": origin,
        "destination": destination,
        "total_price": float(best),
        "per_person_price": (
            best / total_passengers
            if total_passengers else None
        ),
    }
