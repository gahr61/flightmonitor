from datetime import datetime

import requests


class VolarisDirect:
    """
    Cliente directo a la API pública (dotREZ) que usa
    volaris.com para buscar disponibilidad y precio.

    No requiere navegador: la sesión se obtiene con un
    token anónimo (sin login) y la búsqueda devuelve
    precios reales ya totalizados para la mezcla exacta
    de pasajeros pedida (no son precios inferidos ni de
    agencias externas).

    Pendiente (no implementado aquí todavía):
      - Precio de maletas documentadas / SSRs.
      - Confirmación de disponibilidad vía booking/quote.
    """

    SESSION_URL = (
        "https://apigw.volaris.com/prod/api/session"
    )

    SEARCH_URL = (
        "https://apigw.volaris.com/prod/api/v3/availability/search"
    )

    BASE_HEADERS = {
        "accept": "application/json",
        "accept-language": "es-MX",
        "content-type": "application/json",
        "flow": "MBS",
        "frontend": "WEB",
        "referer": "https://www.volaris.com/Flight/Select",
        "sec-ch-ua": (
            '"Chromium";v="151", "Not=A?Brand";v="99"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, timeout=30):
        self.timeout = timeout

    # -----------------------------------------------
    # SESIÓN
    # -----------------------------------------------

    def get_session_token(self):

        response = requests.get(
            self.SESSION_URL,
            headers=self.BASE_HEADERS,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()["token"]

    # -----------------------------------------------
    # FORMATO DE FECHA REQUERIDO POR LA API
    # -----------------------------------------------

    @staticmethod
    def _format_date(date_str):
        # date_str: "YYYY-MM-DD" -> "Sat, Dec 26, 2026"

        dt = datetime.strptime(date_str, "%Y-%m-%d")

        return "{}, {} {}, {}".format(
            dt.strftime("%a"),
            dt.strftime("%b"),
            dt.day,
            dt.year
        )

    # -----------------------------------------------
    # BÚSQUEDA CRUDA
    # -----------------------------------------------

    def search_round_trip(
        self,
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        children,
        currency="MXN",
        token=None
    ):
        """
        origin/destination: códigos IATA.
        departure_date/return_date: "YYYY-MM-DD".
        children: cantidad de niños (int).

        Devuelve el JSON crudo de la API, con:
          - results: [tramo_ida, tramo_regreso]
          - faresAvailable: dict fareAvailabilityKey -> totales
        """

        if token is None:
            token = self.get_session_token()

        headers = dict(self.BASE_HEADERS)
        headers["authorization"] = token

        passenger_types = [
            {"type": "ADT", "count": adults}
        ]

        if children:
            passenger_types.append(
                {"type": "CHD", "count": children}
            )

        payload = {
            "passengers": {"types": passenger_types},
            "criteria": [
                {
                    "stations": {
                        "originStationCodes": [origin],
                        "destinationStationCodes": [destination],
                    },
                    "dates": {
                        "beginDate": self._format_date(
                            departure_date
                        )
                    },
                    "filters": {
                        "fareTypes": ["R"],
                        "maxConnections": 20,
                        "bundleControlFilter": 2,
                    },
                },
                {
                    "stations": {
                        "originStationCodes": [destination],
                        "destinationStationCodes": [origin],
                    },
                    "dates": {
                        "beginDate": self._format_date(
                            return_date
                        )
                    },
                    "filters": {
                        "fareTypes": ["R"],
                        "maxConnections": 20,
                        "bundleControlFilter": 2,
                    },
                },
            ],
            "codes": {
                "currencyCode": currency,
                "promotionCode": "",
            },
            "taxesAndFees": 2,
            "shouldIncludeSoldOut": True,
            "shouldIncludeTua": True,
        }

        response = requests.post(
            self.SEARCH_URL,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()

    # -----------------------------------------------
    # PARSEO DE JOURNEYS
    # -----------------------------------------------

    @staticmethod
    def _connection_minutes(arrival_str, departure_str):

        fmt = "%Y-%m-%dT%H:%M:%S"

        arrival = datetime.strptime(arrival_str, fmt)
        departure = datetime.strptime(departure_str, fmt)

        return (departure - arrival).total_seconds() / 60.0

    def extract_journeys(
        self,
        trip_result,
        fares_available,
        max_stops=1,
        max_connection_minutes=300
    ):
        """
        Convierte un elemento de "results" (un tramo,
        ida o regreso) en una lista de journeys válidos
        (dentro de los límites de escalas/conexión),
        cada uno con su precio total real ya calculado
        para la mezcla de pasajeros pedida.
        """

        journeys = []

        for trip in trip_result.get("trips", []):

            for journey in _iter_market_journeys(trip):

                stops = journey.get("stops", 0)

                if stops > max_stops:
                    continue

                if journey.get("isSoldOutFlight"):
                    continue

                connection_minutes = None

                if stops == 1:

                    segments = journey.get("segments", [])

                    if len(segments) >= 2:

                        connection_minutes = (
                            self._connection_minutes(
                                segments[0]["designator"]["arrival"],
                                segments[1]["designator"]["departure"]
                            )
                        )

                        if (
                            connection_minutes
                            > max_connection_minutes
                        ):
                            continue

                designator = journey["designator"]

                for fare in journey.get("fares", []):

                    key = fare.get("fareAvailabilityKey")

                    fare_info = fares_available.get(key)

                    if not fare_info:
                        continue

                    totals = fare_info.get("totals", {})

                    fare_list = fare_info.get("fares", [])

                    class_of_service = (
                        fare_list[0].get("classOfService")
                        if fare_list else None
                    )

                    journeys.append({
                        "origin": designator["origin"],
                        "destination": designator["destination"],
                        "departure": designator["departure"],
                        "arrival": designator["arrival"],
                        "stops": stops,
                        "connection_minutes": connection_minutes,
                        "journeyKey": journey.get("journeyKey"),
                        "fareAvailabilityKey": key,
                        "classOfService": class_of_service,
                        "fareTotal": totals.get("fareTotal"),
                    })

        return journeys

    # -----------------------------------------------
    # BÚSQUEDA + FILTRO EN UN SOLO PASO
    # -----------------------------------------------

    def find_best_round_trip(
        self,
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        children,
        max_stops=1,
        max_connection_minutes=300,
        currency="MXN",
        token=None
    ):
        """
        Devuelve None si Volaris no tiene disponibilidad
        para alguno de los dos tramos, o un dict:

          {
            "origin", "destination",
            "outbound": {...journey...},
            "return": {...journey...},
            "total_price": float,   # SIN maletas
            "per_person_price": float,
          }

        con el combo de menor precio total que cumpla
        las restricciones de escalas/conexión. El precio
        NO incluye maletas documentadas (pendiente).
        """

        data = self.search_round_trip(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=adults,
            children=children,
            currency=currency,
            token=token
        )

        results = data.get("results", [])

        if len(results) < 2:
            return None

        fares_available = data.get("faresAvailable", {})

        outbound_journeys = self.extract_journeys(
            results[0],
            fares_available,
            max_stops=max_stops,
            max_connection_minutes=max_connection_minutes
        )

        return_journeys = self.extract_journeys(
            results[1],
            fares_available,
            max_stops=max_stops,
            max_connection_minutes=max_connection_minutes
        )

        if not outbound_journeys or not return_journeys:
            return None

        cheapest_out = min(
            outbound_journeys,
            key=lambda j: j["fareTotal"]
        )

        cheapest_ret = min(
            return_journeys,
            key=lambda j: j["fareTotal"]
        )

        total_price = (
            cheapest_out["fareTotal"] + cheapest_ret["fareTotal"]
        )

        total_passengers = adults + children

        return {
            "origin": origin,
            "destination": destination,
            "outbound": cheapest_out,
            "return": cheapest_ret,
            "total_price": total_price,
            "per_person_price": (
                total_price / total_passengers
                if total_passengers else None
            ),
        }


def _iter_market_journeys(trip):

    for journeys in trip.get(
        "journeysAvailableByMarket", {}
    ).values():

        for journey in journeys:
            yield journey
