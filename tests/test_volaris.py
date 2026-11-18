import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from dotenv import load_dotenv

from app.config import load_config

from app.providers.serpapi_google_flights import (
    SerpApiGoogleFlights
)


load_dotenv()

config = load_config()

api = SerpApiGoogleFlights()


print("\n========================================")
print("VALIDACION BOOKING REQUEST VOLARIS")
print("========================================")


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


for ida_index, outbound in enumerate(
    volaris,
    start=1
):

    print("\n========================================")
    print(f"IDA VOLARIS #{ida_index}")
    print("========================================")

    departure_token = outbound.get(
        "departure_token"
    )

    if not departure_token:
        continue


    return_data = api.search_return(
        origin="GDL",
        destination="MID",
        departure_date=config["departure_date"],
        return_date=config["return_date"],
        adults=config["adults"],
        children_ages=config["children_ages"],
        departure_token=departure_token,
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


    for regreso_index, regreso in enumerate(
        volaris_returns,
        start=1
    ):

        booking_token = regreso.get(
            "booking_token"
        )

        if not booking_token:
            continue


        booking_data = api.booking_options(
            origin="GDL",
            destination="MID",
            departure_date=config["departure_date"],
            return_date=config["return_date"],
            adults=config["adults"],
            children_ages=config["children_ages"],
            booking_token=booking_token,
            currency=config["currency"]
        )


        options = booking_data.get(
            "booking_options",
            []
        )


        for option_index, option in enumerate(
            options,
            start=1
        ):

            together = option.get(
                "together",
                {}
            )


            seller = together.get(
                "book_with"
            )


            if seller != "Volaris":
                continue


            booking_request = together.get(
                "booking_request",
                {}
            )


            url = booking_request.get(
                "url"
            )

            post_data = booking_request.get(
                "post_data"
            )


            print(
                "\n----------------------------------------"
            )

            print(
                f"IDA #{ida_index} | "
                f"REGRESO #{regreso_index} | "
                f"OPCION #{option_index}"
            )

            print(
                "Vendedor:",
                seller
            )

            print(
                "Precio:",
                together.get("price")
            )

            print(
                "URL:",
                url
            )

            print(
                "Tiene post_data:",
                bool(post_data)
            )

            print(
                "Longitud post_data:",
                len(post_data)
                if post_data
                else 0
            )

            print(
                "Vuelos:",
                together.get("marketed_as")
            )