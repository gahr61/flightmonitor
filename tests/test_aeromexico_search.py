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
from app.providers.serpapi_google_flights import SerpApiGoogleFlights
from app.providers.aeromexico_search import find_best_round_trip


load_dotenv()


# -------------------------------------------------
# SALIDA A ARCHIVO
# -------------------------------------------------

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

gitignore_path = OUTPUT_DIR / ".gitignore"
if not gitignore_path.exists():
    gitignore_path.write_text(
        "*\n!.gitignore\n",
        encoding="utf-8"
    )

OUTPUT_FILE = OUTPUT_DIR / "test_aeromexico_search.txt"

_log_lines = []


def log(*parts):

    text = " ".join(
        str(part)
        for part in parts
    )

    _log_lines.append(text)

    print(text)


def flush_log():

    OUTPUT_FILE.write_text(
        "\n".join(_log_lines) + "\n",
        encoding="utf-8"
    )


# -------------------------------------------------
# CONFIG
# -------------------------------------------------

config = load_config()

ADULTS = config["adults"]
CHILDREN_AGES = config.get("children_ages", [])
CHILDREN = len(CHILDREN_AGES)

MAX_STOPS = config.get("max_stops", 1)
MAX_CONNECTION_MINUTES = config.get(
    "max_connection_minutes", 300
)

MAX_TOTAL_PRICE = config.get("max_total_price")
MAX_PRICE_PER_PERSON = config.get("max_price_per_person")

ROUTES = [
    ("SLP", "MID"),
    ("GDL", "MID"),
    ("SLP", "CUN"),
    ("GDL", "CUN"),
]


def run():

    log("=" * 60)
    log("BÚSQUEDA AEROMÉXICO (precio directo de SerpApi)")
    log("=" * 60)

    log(
        "\nPasajeros:", ADULTS, "adultos +",
        CHILDREN, "niños"
    )

    log(
        "Ida:", config["departure_date"],
        "| Regreso:", config["return_date"]
    )

    log(
        "Tope total:", MAX_TOTAL_PRICE,
        "MXN | Tope por persona:", MAX_PRICE_PER_PERSON,
        "MXN"
    )

    api = SerpApiGoogleFlights()

    all_qualifying = []

    for origin, destination in ROUTES:

        log("\n" + "-" * 60)
        log(f"RUTA: {origin} <-> {destination}")
        log("-" * 60)

        try:
            combo = find_best_round_trip(
                api,
                origin=origin,
                destination=destination,
                departure_date=config["departure_date"],
                return_date=config["return_date"],
                adults=ADULTS,
                children_ages=CHILDREN_AGES,
                max_stops=MAX_STOPS,
                max_connection_minutes=MAX_CONNECTION_MINUTES,
                currency=config.get("currency", "MXN"),
            )
        except Exception as error:
            log("  ERROR en la búsqueda:", error)
            continue

        if combo is None:
            log(
                "  Aeroméxico no tiene disponibilidad "
                "combinable (ida + vuelta) en esta ruta "
                "para estas fechas, con las escalas "
                "permitidas."
            )
            continue

        out = combo["outbound"]
        ret = combo["return"]

        out_nums = [
            seg.get("flight_number")
            for seg in out.get("flights", [])
        ]

        ret_nums = [
            seg.get("flight_number")
            for seg in ret.get("flights", [])
        ]

        log(
            f"\n  IDA: vuelos {out_nums} "
            f"escalas={len(out.get('layovers', []))}"
        )

        log(
            f"  REGRESO: vuelos {ret_nums} "
            f"escalas={len(ret.get('layovers', []))}"
        )

        total_price = combo["total_price"]
        per_person = combo["per_person_price"]

        log(
            f"\n  TOTAL REDONDO (7 pax): "
            f"${total_price:.0f} MXN "
            f"(${per_person:.0f} MXN por persona)"
        )

        qualifies = True
        reasons = []

        if MAX_TOTAL_PRICE and total_price > MAX_TOTAL_PRICE:
            qualifies = False
            reasons.append(
                f"total ${total_price:.0f} > tope "
                f"${MAX_TOTAL_PRICE}"
            )

        if (
            MAX_PRICE_PER_PERSON
            and per_person > MAX_PRICE_PER_PERSON
        ):
            qualifies = False
            reasons.append(
                f"por persona ${per_person:.0f} > tope "
                f"${MAX_PRICE_PER_PERSON}"
            )

        if qualifies:
            log("  >>> CALIFICA dentro del presupuesto <<<")
            all_qualifying.append({
                "route": f"{origin}-{destination}",
                "total_price": total_price,
                "per_person": per_person,
            })
        else:
            log("  NO califica:", "; ".join(reasons))

        log(
            "\n  NOTA: este total NO incluye maletas "
            "documentadas (pendiente de investigar)."
        )

    log("\n" + "=" * 60)
    log("RESUMEN FINAL")
    log("=" * 60)

    if all_qualifying:

        for item in sorted(
            all_qualifying, key=lambda x: x["total_price"]
        ):

            log(
                f"  {item['route']}: "
                f"${item['total_price']:.0f} MXN total "
                f"(${item['per_person']:.0f}/persona)"
            )

    else:
        log(
            "  Ninguna ruta califica dentro del "
            "presupuesto configurado (sin contar maletas)."
        )

    flush_log()

    log(
        "\nSalida completa guardada en:",
        str(OUTPUT_FILE)
    )


if __name__ == "__main__":
    run()
