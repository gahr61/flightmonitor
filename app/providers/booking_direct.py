"""
Cliente directo a la API pública de búsqueda de vuelos
de Booking.com (flights.booking.com/api/flights/).

Descubierto durante la investigación: responde JSON real
con precio y detalle de equipaje por tarifa, sin necesitar
navegador ni SerpApi, y sin bloqueo anti-bot (a diferencia
de Aeroméxico y Despegar).

Importante: Booking.com es una AGENCIA (OTA), no la
aerolínea. En las pruebas su precio coincidió exactamente
con el de Aeroméxico vía SerpApi, pero no hay garantía de
que siempre sea así — se usa como fuente de precio
independiente y como respaldo, no como reemplazo de la
validación directa con la aerolínea cuando existe (Volaris).
"""

from datetime import datetime

import requests


BASE_URL = "https://flights.booking.com/api/flights/"

BASE_HEADERS = {
    "accept": "application/json",
    "accept-language": "es-MX",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
}


def _airport_code(code):
    return f"{code}.AIRPORT"


def search_round_trip(
    origin,
    destination,
    departure_date,
    return_date,
    adults,
    children_ages,
    currency="MXN",
    timeout=30,
):

    params = {
        "type": "ROUNDTRIP",
        "adults": adults,
        "cabinClass": "ECONOMY",
        "from": _airport_code(origin),
        "to": _airport_code(destination),
        "fromCountry": "MX",
        "toCountry": "MX",
        "depart": departure_date,
        "return": return_date,
        "sort": "BEST",
        "travelPurpose": "leisure",
        "locale": "es-mx",
        "salesCurrency": currency,
    }

    if children_ages:
        params["children"] = ",".join(
            str(age) for age in children_ages
        )

    headers = dict(BASE_HEADERS)

    headers["referer"] = (
        f"https://flights.booking.com/flights/"
        f"{origin}-{destination}/"
    )

    response = requests.get(
        BASE_URL,
        params=params,
        headers=headers,
        timeout=timeout,
    )

    response.raise_for_status()

    return response.json()


def _offer_airlines(offer):

    airlines = set()

    for segment in offer.get("segments", []):

        for leg in segment.get("legs", []):

            for carrier in leg.get("carriersData", []):

                name = carrier.get("name")

                if name:
                    airlines.add(name)

    return airlines


def _offer_stops(offer):
    # Cada "segment" es un tramo (ida o vuelta); sus "legs"
    # son las escalas dentro de ese tramo. Tomamos el máximo
    # entre ida y vuelta, igual que con Volaris/Aeroméxico.

    max_stops = 0

    for segment in offer.get("segments", []):

        stops = max(0, len(segment.get("legs", [])) - 1)

        max_stops = max(max_stops, stops)

    return max_stops


def _offer_max_connection_minutes(offer):

    fmt = "%Y-%m-%dT%H:%M:%S"

    max_connection = 0.0

    for segment in offer.get("segments", []):

        legs = segment.get("legs", [])

        for index in range(len(legs) - 1):

            arrival = datetime.strptime(
                legs[index]["arrivalTime"], fmt
            )

            departure = datetime.strptime(
                legs[index + 1]["departureTime"], fmt
            )

            minutes = (
                departure - arrival
            ).total_seconds() / 60

            max_connection = max(max_connection, minutes)

    return max_connection


def _flight_numbers(offer):

    numbers = []

    for segment in offer.get("segments", []):

        for leg in segment.get("legs", []):

            flight_info = leg.get("flightInfo", {})

            numbers.append(
                flight_info.get("flightNumber")
            )

    return tuple(numbers)


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
    airline_name="Aeromexico",
):
    """
    Busca en Booking.com y devuelve la oferta más barata
    de la aerolínea indicada (sin mezclar con otras, para
    evitar codeshares confusos) que respete el límite de
    escalas/conexión.

    Devuelve None si no hay ninguna oferta válida, o:

      {
        "origin", "destination",
        "flight_numbers": (...),
        "total_price": float,
        "per_person_price": float,
        "checked_baggage_included": bool,
      }

    El precio es el total ya calculado por Booking.com
    para la mezcla exacta de pasajeros pedida.
    """

    data = search_round_trip(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        return_date=return_date,
        adults=adults,
        children_ages=children_ages,
        currency=currency,
    )

    offers = data.get("flightOffers", [])

    total_passengers = adults + len(children_ages or [])

    best = None

    for offer in offers:

        airlines = _offer_airlines(offer)

        if airline_name not in airlines:
            continue

        if len(airlines) > 1:
            # Itinerario mezclado con otra aerolínea —
            # lo descartamos para no confundir de quién
            # es realmente el vuelo.
            continue

        if _offer_stops(offer) > max_stops:
            continue

        if (
            _offer_max_connection_minutes(offer)
            > max_connection_minutes
        ):
            continue

        total_price = (
            offer.get("priceBreakdown", {})
            .get("total", {})
            .get("units")
        )

        if total_price is None:
            continue

        if best is None or total_price < best["total_price"]:

            branded_fare = offer.get(
                "brandedFareInfo", {}
            )

            checkin_excluded = branded_fare.get(
                "checkinBaggageExcluded"
            )

            best = {
                "origin": origin,
                "destination": destination,
                "flight_numbers": _flight_numbers(offer),
                "total_price": float(total_price),
                "per_person_price": (
                    total_price / total_passengers
                    if total_passengers else None
                ),
                "checked_baggage_included": (
                    checkin_excluded is False
                ),
            }

    return best
