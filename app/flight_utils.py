from datetime import datetime


def total_stops(segments):

    return max(
        0,
        len(segments) - 1
    )


def connection_minutes(segments):

    if len(segments) < 2:
        return 0

    total = 0

    for index in range(
        len(segments) - 1
    ):

        current = segments[index]

        next_segment = segments[
            index + 1
        ]

        arrival = (
            current
            .get("arrival_airport", {})
            .get("time")
        )

        departure = (
            next_segment
            .get("departure_airport", {})
            .get("time")
        )

        if not arrival or not departure:
            return None

        try:

            a = datetime.fromisoformat(
                arrival
            )

            d = datetime.fromisoformat(
                departure
            )

            total += int(
                (
                    d - a
                ).total_seconds()
                / 60
            )

        except ValueError:

            return None

    return total


def airline_names(flight):

    result = set()

    for segment in flight.get(
        "flights",
        []
    ):

        airline = segment.get(
            "airline"
        )

        if airline:
            result.add(airline)

    return result


def is_allowed_airline(
    flight,
    allowed
):

    names = {
        name.lower()
        for name in airline_names(flight)
    }

    allowed_names = {
        name.lower()
        for name in allowed
    }

    return bool(
        names & allowed_names
    )


def is_valid_stops_and_connections(
    flight,
    max_stops,
    max_connection_minutes
):

    segments = flight.get(
        "flights",
        []
    )

    stops = total_stops(
        segments
    )

    if stops > max_stops:
        return False

    connection = connection_minutes(
        segments
    )

    if connection is None:
        return False

    return (
        connection
        <= max_connection_minutes
    )