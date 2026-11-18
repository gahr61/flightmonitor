class DirectAirlineValidator:

    SUPPORTED = {

        "Volaris":
            "https://www.volaris.com/",

        "Aeromexico":
            "https://www.aeromexico.com/"
    }

    def validate(
        self,
        candidate
    ):

        return {

            "available": False,

            "price": None,

            "baggage_price": None,

            "checked_bags": None,

            "reason":
                "Validación directa "
                "pendiente."
        }