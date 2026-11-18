from app.flight_utils import (
    is_allowed_airline,
    is_valid_stops_and_connections
)


def extract_price(value):

    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def normalize_flight(
    flight,
    route,
    direction,
    config
):

    if not is_allowed_airline(
        flight,
        config["airlines"]
    ):
        return None

    if not is_valid_stops_and_connections(
        flight,
        config["max_stops"],
        config["max_connection_minutes"]
    ):
        return None

    airlines = list({
        segment.get("airline")
        for segment
        in flight.get("flights", [])
        if segment.get("airline")
    })

    return {

        "source":
            "google_flights_serpapi",

        "origin":
            route["origin"],

        "destination":
            route["destination"],

        "direction":
            direction,

        "airline":
            airlines,

        "price":
            extract_price(
                flight.get("price")
            ),

        "stops":
            max(
                0,
                len(
                    flight.get(
                        "flights",
                        []
                    )
                ) - 1
            ),

        "duration":
            flight.get(
                "total_duration"
            ),

        "flights":
            flight.get(
                "flights",
                []
            ),

        "departure_token":
            flight.get(
                "departure_token"
            ),

        "booking_token":
            flight.get(
                "booking_token"
            ),

        "raw":
            flight
    }