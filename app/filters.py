from datetime import datetime


def normalize_airline(name):
    if not name:
        return ""

    return (
        name.lower()
        .replace("é", "e")
        .replace(" ", "")
    )


def get_stops(flight):
    segments = flight.get("flights", [])

    if not segments:
        return None

    return max(len(segments) - 1, 0)


def get_airlines(flight):
    airlines = []

    for segment in flight.get("flights", []):
        airline = segment.get("airline")

        if airline and airline not in airlines:
            airlines.append(airline)

    return airlines


def get_connection_minutes(flight):
    segments = flight.get("flights", [])

    if len(segments) <= 1:
        return 0

    total_connection = 0

    for i in range(len(segments) - 1):

        current = segments[i]
        next_segment = segments[i + 1]

        arrival = current.get(
            "arrival_airport",
            {}
        ).get("time")

        departure = next_segment.get(
            "departure_airport",
            {}
        ).get("time")

        if not arrival or not departure:
            return None

        arrival_dt = datetime.strptime(
            arrival,
            "%Y-%m-%d %H:%M"
        )

        departure_dt = datetime.strptime(
            departure,
            "%Y-%m-%d %H:%M"
        )

        minutes = (
            departure_dt - arrival_dt
        ).total_seconds() / 60

        total_connection += int(minutes)

    return total_connection


def allowed_airline(flight, allowed):
    flight_airlines = get_airlines(flight)

    allowed_normalized = {
        normalize_airline(airline)
        for airline in allowed
    }

    for airline in flight_airlines:

        if normalize_airline(airline) in allowed_normalized:
            return True

    return False


def valid_price(flight, max_total_price):
    price = flight.get("price")

    if price is None:
        return False

    return price <= max_total_price


def valid_stops(flight, max_stops):
    stops = get_stops(flight)

    if stops is None:
        return False

    return stops <= max_stops


def valid_connection(flight, max_connection_minutes):
    connection = get_connection_minutes(flight)

    if connection is None:
        return False

    return connection <= max_connection_minutes


def is_valid_flight(
    flight,
    allowed_airlines,
    max_total_price,
    max_stops,
    max_connection_minutes
):
    if not valid_price(
        flight,
        max_total_price
    ):
        return False

    if not valid_stops(
        flight,
        max_stops
    ):
        return False

    if not valid_connection(
        flight,
        max_connection_minutes
    ):
        return False

    if not allowed_airline(
        flight,
        allowed_airlines
    ):
        return False

    return True