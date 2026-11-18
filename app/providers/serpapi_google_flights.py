import os
import requests


def _stops_param(max_stops):
    """
    Traduce "máximo de escalas permitidas" (nuestra
    convención de negocio: 0 = solo directos, 1 = hasta
    1 escala, etc.) al parámetro "stops" de SerpApi, que
    usa una convención distinta:

        1 = solo vuelos directos
        2 = 1 escala o menos
        3 = 2 escalas o menos

    Sin esta traducción, max_stops=1 (nuestra intención:
    "acepto hasta 1 escala") se enviaba tal cual como
    stops=1, que SerpApi interpreta como "solo directos"
    — mucho más restrictivo de lo esperado.
    """

    return int(max_stops) + 1


class SerpApiGoogleFlights:

    BASE_URL = (
        "https://serpapi.com/search.json"
    )

    def __init__(self):

        self.api_key = os.getenv(
            "SERPAPI_API_KEY"
        )

        if not self.api_key:
            raise ValueError(
                "SERPAPI_API_KEY no está configurada."
            )

    def _request(self, params):

        response = requests.get(
            self.BASE_URL,
            params=params,
            timeout=60
        )

        if not response.ok:

            try:
                error_data = response.json()

            except ValueError:

                error_data = response.text

            raise RuntimeError(
                f"SerpApi HTTP "
                f"{response.status_code}: "
                f"{error_data}"
            )

        data = response.json()

        if "error" in data:

            raise RuntimeError(
                f"SerpApi: {data['error']}"
            )

        return data

    def search_outbound(
        self,
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        children_ages,
        max_stops=1,
        currency="MXN"
    ):

        params = {

            "engine": "google_flights",

            "api_key": self.api_key,

            "departure_id": origin,

            "arrival_id": destination,

            "outbound_date":
                departure_date,

            "return_date":
                return_date,

            "type": 1,

            "adults": adults,

            "children":
                len(children_ages or []),

            "currency": currency,

            "stops": _stops_param(max_stops)
        }

        return self._request(params)

    def search_return(
        self,
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        children_ages,
        departure_token,
        currency="MXN"
    ):

        params = {

            "engine": "google_flights",

            "api_key": self.api_key,

            "departure_id": origin,

            "arrival_id": destination,

            "outbound_date":
                departure_date,

            "return_date":
                return_date,

            "type": 1,

            "adults": adults,

            "children":
                len(children_ages or []),

            "currency": currency,

            "departure_token":
                departure_token
        }

        return self._request(params)

    def booking_options(
        self,
        origin,
        destination,
        departure_date,
        return_date,
        adults,
        children_ages,
        booking_token,
        currency="MXN"
    ):

        params = {

            "engine": "google_flights",

            "api_key": self.api_key,

            "departure_id": origin,

            "arrival_id": destination,

            "outbound_date":
                departure_date,

            "return_date":
                return_date,

            "type": 1,

            "adults": adults,

            "children":
                len(children_ages or []),

            "currency": currency,

            "booking_token":
                booking_token
        }

        return self._request(params)