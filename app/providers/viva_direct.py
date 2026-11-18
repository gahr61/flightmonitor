"""
Cliente directo a la API real de Viva Aerobús
(api.vivaaerobus.com/web/v1/availability/search).

Viva Aerobús usa Akamai Bot Manager: una llamada directa
con `requests` (incluso reusando las cookies "_abck" /
"bm_*" que entrega Akamai) devuelve 403 Forbidden -- el
desafío solo lo resuelve un navegador real ejecutando su
JavaScript. Por eso este cliente abre un Chromium headless
en cada consulta (más lento que VolarisDirect, que sí
funciona con requests puro) en vez de hacer la llamada
HTTP directa.

Pendiente (no resuelto aquí):
  - Precio de maleta documentada extra.
"""

from datetime import datetime

from playwright.sync_api import sync_playwright


BASE_URL = "https://www.vivaaerobus.com"

SEARCH_URL_MARKER = (
    "api.vivaaerobus.com/web/v1/availability/search"
)


def _format_itinerary_code(
    origin, destination, departure_date, return_date
):

    dep = datetime.strptime(
        departure_date, "%Y-%m-%d"
    ).strftime("%Y%m%d")

    ret = datetime.strptime(
        return_date, "%Y-%m-%d"
    ).strftime("%Y%m%d")

    return (
        f"{origin}_{destination}_{dep}."
        f"{destination}_{origin}_{ret}"
    )


def _options_url(
    origin, destination, departure_date, return_date,
    adults, children
):

    itinerary = _format_itinerary_code(
        origin, destination, departure_date, return_date
    )

    return (
        f"{BASE_URL}/es-mx/book/options"
        f"?itineraryCode={itinerary}"
        f"&passengers=A{adults}_C{children}"
    )


def fetch_availability(
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children,
    wait_ms=15000,
    timeout_ms=45000,
):
    """
    Abre un navegador headless, navega a la página de
    opciones de Viva Aerobús, y captura el JSON de la
    respuesta real de disponibilidad/precio. Devuelve el
    dict crudo, o None si no se logró capturar a tiempo.
    """

    url = _options_url(
        origin, destination, departure_date, return_date,
        adults, children
    )

    captured = {"data": None}

    with sync_playwright() as playwright:

        # Importante: headless=True es detectado y
        # bloqueado por el Akamai Bot Manager de Viva
        # Aerobús (confirmado en pruebas). headless=False
        # sí pasa el desafío, pero abre una ventana real de
        # Chrome — la posicionamos fuera de la pantalla
        # visible para que no estorbe mientras el monitor
        # corre en segundo plano.
        browser = playwright.chromium.launch(
            headless=False,
            args=[
                "--window-position=-32000,-32000",
                "--window-size=1300,900",
            ],
        )

        context = browser.new_context(locale="es-MX")

        page = context.new_page()

        def on_response(response):

            if captured["data"] is not None:
                return

            if SEARCH_URL_MARKER not in response.url:
                return

            try:
                captured["data"] = response.json()
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

    return captured["data"]


def _connection_minutes(journey):

    segments = journey.get("segments", [])

    max_minutes = 0

    for segment in segments[:-1]:

        layover = segment.get("layoverTime", "00:00:00")

        hours, minutes, _ = (
            int(part) for part in layover.split(":")
        )

        total_minutes = hours * 60 + minutes

        max_minutes = max(max_minutes, total_minutes)

    return max_minutes


def _best_journey(
    route, max_stops, max_connection_minutes
):

    best = None

    for journey in route.get("journeys", []):

        if journey.get("isSoldout"):
            continue

        if journey.get("stops", 0) > max_stops:
            continue

        if (
            _connection_minutes(journey)
            > max_connection_minutes
        ):
            continue

        # Cada journey trae varias entradas en "fares",
        # incluyendo componentes parciales/internos (ej.
        # código "L1HSO00N" con un monto absurdamente bajo,
        # visto en pruebas: $249 cuando la tarifa real
        # rondaba $2,000). journey["lowestFareKey"] indica
        # cuál de esas entradas es la tarifa real más
        # barata según Viva — usamos esa, no el mínimo
        # numérico de todo el arreglo.

        lowest_key = journey.get("lowestFareKey")

        matching_fare = next(
            (
                fare
                for fare in journey.get("fares", [])
                if fare.get("key") == lowest_key
            ),
            None,
        )

        if matching_fare is None:
            continue

        amount = matching_fare.get("fare", {}).get("amount")

        if amount is None:
            continue

        if best is None or amount < best["amount"]:

            best = {
                "amount": amount,
                "journey": journey,
            }

    return best


def find_best_round_trip(
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children_ages,
    max_stops=1,
    max_connection_minutes=300,
    currency="MXN",
):
    """
    Devuelve None si no hay combinación válida, o:

      {
        "origin", "destination",
        "outbound": {...journey...},
        "return": {...journey...},
        "total_price": float,   # ya calculado para los
                                 # pasajeros exactos pedidos
        "per_person_price": float,
      }
    """

    children = len(children_ages or [])

    data = fetch_availability(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        children=children,
    )

    if not data:
        return None

    routes = data.get("data", {}).get("routes", [])

    if len(routes) < 2:
        return None

    outbound_best = _best_journey(
        routes[0], max_stops, max_connection_minutes
    )

    return_best = _best_journey(
        routes[1], max_stops, max_connection_minutes
    )

    if not outbound_best or not return_best:
        return None

    total_price = (
        outbound_best["amount"] + return_best["amount"]
    )

    total_passengers = adults + children

    return {
        "origin": origin,
        "destination": destination,
        "outbound": outbound_best["journey"],
        "return": return_best["journey"],
        "total_price": total_price,
        "per_person_price": (
            total_price / total_passengers
            if total_passengers else None
        ),
    }
