"""
Búsqueda de precio real para Aeroméxico usando
directamente los datos de SerpApi / Google Flights.

A diferencia de Volaris (que oculta su precio a Google
y siempre da price=None), Aeroméxico sí publica precio
real en Google Flights, así que no necesitamos scraping
directo de su sitio (que además está bloqueando accesos
automatizados vía Playwright con una defensa anti-bot).

Pendiente (no resuelto aquí):
  - Precio de maleta documentada extra. Google Flights
    solo indica qué va incluido gratis (ej. "1 free
    carry-on"), no el costo de agregar una maleta.
"""


def _is_airline(flight, airline_name):

    target = airline_name.lower().replace("é", "e")

    return all(
        target in (
            segment.get("airline", "")
            .lower()
            .replace("é", "e")
        )
        for segment in flight.get("flights", [])
    )


def _stops_ok(flight, max_stops, max_connection_minutes):

    layovers = flight.get("layovers", [])

    if len(layovers) > max_stops:
        return False

    for layover in layovers:

        if layover.get("duration", 0) > max_connection_minutes:
            return False

    return True


def _is_consistent_price(
    return_total_price,
    outbound_price_estimate,
    tolerance_low=0.5,
    tolerance_high=2.0,
):
    """
    El precio final (junto al vuelo de regreso) debería
    quedar cerca del precio ya estimado para ese mismo
    vuelo de ida en solitario — normalmente son iguales o
    muy parecidos. Si se alejan demasiado, es señal de un
    error de datos de Google Flights, no de un precio real.
    """

    if not outbound_price_estimate:
        return True

    ratio = return_total_price / outbound_price_estimate

    return tolerance_low <= ratio <= tolerance_high


def _candidates(flights, airline_name, max_stops, max_connection_minutes):

    return [
        flight
        for flight in flights
        if _is_airline(flight, airline_name)
        and _stops_ok(flight, max_stops, max_connection_minutes)
    ]


def find_best_round_trip(
    api,
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children_ages,
    max_stops=1,
    max_connection_minutes=300,
    currency="MXN",
    airline_name="Aeromexico",
    max_outbound_candidates=2,
):
    """
    Busca, entre varias combinaciones de vuelo de ida +
    vuelta de la aerolínea indicada, la de menor precio
    total que respete el límite de escalas/conexión.

    Usa el precio final que da la búsqueda del tramo de
    REGRESO (search_return), no el de la búsqueda de ida
    en solitario: ese precio es solo una estimación
    provisional en el flujo de Google Flights, mientras
    que el precio junto al vuelo de regreso ya es el
    total real para esa combinación específica.

    Devuelve None si no hay combinación válida, o:

      {
        "origin", "destination",
        "outbound": {...},   # datos crudos de SerpApi
        "return": {...},     # datos crudos de SerpApi
        "total_price": float,  # SIN maletas documentadas
        "per_person_price": float,
      }
    """

    outbound_data = api.search_outbound(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        children_ages=children_ages,
        max_stops=max_stops,
        currency=currency,
    )

    outbound_flights = (
        outbound_data.get("best_flights", [])
        + outbound_data.get("other_flights", [])
    )

    outbound_candidates = _candidates(
        outbound_flights,
        airline_name,
        max_stops,
        max_connection_minutes,
    )

    if not outbound_candidates:
        return None

    outbound_candidates.sort(
        key=lambda f: f.get("price") or float("inf")
    )

    total_passengers = adults + len(children_ages or [])

    best = None

    for outbound in outbound_candidates[:max_outbound_candidates]:

        return_data = api.search_return(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            children_ages=children_ages,
            departure_token=outbound["departure_token"],
            currency=currency,
        )

        return_flights = (
            return_data.get("best_flights", [])
            + return_data.get("other_flights", [])
        )

        return_candidates = _candidates(
            return_flights,
            airline_name,
            max_stops,
            max_connection_minutes,
        )

        outbound_price_estimate = outbound.get("price")

        for regreso in return_candidates:

            total_price = regreso.get("price")

            if total_price is None:
                continue

            if not _is_consistent_price(
                total_price, outbound_price_estimate
            ):
                # Google Flights a veces muestra un precio
                # con error para una combinación específica
                # de ida+vuelta (visto: el mismo vuelo de
                # ida cotiza $97,245 en solitario, pero al
                # combinarlo con cierto regreso cae a
                # $5,645 — 1/16 del valor esperado). No es
                # una oferta real, es un glitch de datos.
                # Si el precio final se aleja demasiado del
                # estimado que Google dio para este mismo
                # vuelo de ida, lo descartamos.
                continue

            if best is None or total_price < best["total_price"]:

                best = {
                    "origin": origin,
                    "destination": destination,
                    "outbound": outbound,
                    "return": regreso,
                    "total_price": total_price,
                    "per_person_price": (
                        total_price / total_passengers
                        if total_passengers else None
                    ),
                }

    return best
