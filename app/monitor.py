import json
import logging
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote

# La consola de Windows usa cp1252 por defecto, que no
# puede imprimir caracteres como "→" o los emoji de las
# alertas. Forzamos UTF-8 para evitar UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

from app.providers.serpapi_google_flights import (
    SerpApiGoogleFlights
)

from app.providers.volaris_direct import VolarisDirect

from app.providers.aeromexico_search import (
    find_best_round_trip as find_best_aeromexico_serpapi
)

from app.providers.booking_direct import (
    find_best_round_trip as find_best_aeromexico_booking
)

from app.providers.viva_direct import (
    find_best_round_trip as find_best_viva
)

from app.providers.kayak_direct import (
    fetch_results as kayak_fetch_results,
    extract_best_price as kayak_extract_best_price,
)

from app.telegram import TelegramBot


DATA_DIR = Path("data")
LOG_DIR = Path("logs")

SENT_ALERTS_FILE = DATA_DIR / "sent_alerts.json"


# -------------------------------------------------
# LOGGING (consola + archivo con rotación)
# -------------------------------------------------

LOG_DIR.mkdir(exist_ok=True, parents=True)

_logger = logging.getLogger("flight_monitor")
_logger.setLevel(logging.INFO)

if not _logger.handlers:

    _file_handler = RotatingFileHandler(
        LOG_DIR / "monitor.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    _file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(message)s")
    )

    _logger.addHandler(_file_handler)
    _logger.propagate = False


def log(*parts):

    text = " ".join(str(part) for part in parts)

    print(text)

    for line in text.splitlines() or [""]:
        _logger.info(line)


# -------------------------------------------------
# URLS DE OFERTA
# -------------------------------------------------

def _volaris_search_url(
    origin, destination, departure_date, return_date,
    adults, children
):
    # Formato de deeplink real de Volaris, verificado
    # manualmente durante la investigación (abre la
    # búsqueda ya con origen/destino/fechas/pasajeros
    # precargados, no el vuelo exacto — los precios
    # cambian en tiempo real, así que mandamos a buscar
    # de nuevo en vez de un enlace que puede caducar).

    def fmt(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f"{dt.month}/{dt.day}/{dt.year}"

    return (
        "https://www.volaris.com/Flight/Select?"
        f"s=true&rr=true&o1={origin}&d1={destination}"
        f"&dd1={fmt(departure_date)}&cc=MXN&culture=es-MX"
        f"&adt={adults}&chd={children}&in1=0"
        f"&o2={destination}&d2={origin}"
        f"&dd2={fmt(return_date)}"
    )


def _google_flights_search_url(
    origin, destination, departure_date, return_date
):
    # Aeroméxico bloquea accesos automatizados a su
    # sitio (ver hallazgos de la investigación), así que
    # en vez de adivinar el formato de su buscador
    # mandamos a Google Flights con la misma búsqueda —
    # es de donde ya sacamos el precio, así que es
    # consistente y siempre funciona.

    query = (
        f"Flights from {origin} to {destination} "
        f"on {departure_date} through {return_date}"
    )

    return (
        "https://www.google.com/travel/flights?q="
        + quote(query)
    )


def _viva_search_url(
    origin, destination, departure_date, return_date,
    adults, children
):
    # Mismo formato de "opciones" que ya verificamos que
    # funciona (sin número de vuelo específico, solo
    # ruta+fecha), muestra todos los vuelos disponibles
    # ese día para que la persona elija.

    dep = departure_date.replace("-", "")
    ret = return_date.replace("-", "")

    itinerary = (
        f"{origin}_{destination}_{dep}."
        f"{destination}_{origin}_{ret}"
    )

    return (
        "https://www.vivaaerobus.com/es-mx/book/options"
        f"?itineraryCode={itinerary}"
        f"&passengers=A{adults}_C{children}"
    )


def _flight_signature(flight):
    # Los combos de VolarisDirect/VivaDirect traen
    # "journeyKey"/"key" (identifica el vuelo exacto). Los
    # de Aeroméxico vía SerpApi son objetos crudos con una
    # lista "flights" de segmentos con "flight_number".

    if "journeyKey" in flight:
        return flight.get("journeyKey")

    if "key" in flight:
        return flight.get("key")

    return tuple(
        segment.get("flight_number")
        for segment in flight.get("flights", [])
    )


def _combo_signature(combo):
    # Los combos de Booking.com ya traen "flight_numbers"
    # directo (una sola tupla para ida+vuelta). Los de
    # VolarisDirect/SerpApi/VivaDirect traen "outbound"/
    # "return" por separado. Los de KAYAK no traen vuelo
    # específico (solo el precio agregado), así que no hay
    # nada más que agregar a la firma.

    if "flight_numbers" in combo:
        return combo["flight_numbers"]

    if "outbound" not in combo or "return" not in combo:
        return None

    return (
        _flight_signature(combo["outbound"]),
        _flight_signature(combo["return"]),
    )


def _to_hashable(value):
    # Convierte las listas que vienen de JSON de vuelta a
    # tuplas, para poder usarlas dentro de un set().

    if isinstance(value, list):
        return tuple(_to_hashable(item) for item in value)

    return value


class FlightMonitor:

    def __init__(self, config):

        self.config = config

        self.telegram = TelegramBot()

        self.volaris = VolarisDirect()

        self.serpapi = SerpApiGoogleFlights()

        # Ofertas ya notificadas, persistidas en disco para
        # no repetir la misma alerta si el proceso se
        # reinicia.
        self.sent_alerts = self._load_sent_alerts()

        # Aeroméxico se revisa cada ciclo vía la API de
        # Booking.com (gratuita, sin límite de cuota). Como
        # respaldo/validación cruzada usamos SerpApi, cada
        # 36 horas por defecto: el plan da 250 consultas al
        # mes y cada validación gasta ~12 (3 por ruta x 4
        # rutas), así que cada 36h usa ~248/mes en el peor
        # caso (mes de 31 días) — casi toda la cuota, sin
        # pasarse.
        self.last_aeromexico_crosscheck = None

        # En algunas máquinas (Windows viejo, anterior a
        # Windows 10 / Server 2016) Playwright no puede
        # lanzar Chromium (Node.js ya no lo soporta). En
        # vez de reintentar y fallar en cada ruta de cada
        # ciclo para siempre, lo probamos una sola vez aquí
        # y desactivamos Viva Aerobús + la validación
        # cruzada de KAYAK (ambos necesitan navegador real)
        # con un solo aviso si no funciona.
        self.playwright_enabled = (
            self._check_playwright_available()
        )

    def _check_playwright_available(self):

        needs_playwright = (
            "Viva Aerobus"
            in self.config.get("airlines", [])
            or self.config.get("kayak_crosscheck", True)
        )

        if not needs_playwright:
            return False

        try:

            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:

                browser = playwright.chromium.launch(
                    headless=False,
                    args=["--window-position=-32000,-32000"],
                )

                browser.close()

            return True

        except Exception as error:

            log(
                "\nAVISO: Viva Aerobús y la validación "
                "cruzada de KAYAK quedan desactivados en "
                f"esta máquina — no se pudo lanzar el "
                f"navegador ({error}). Probablemente esta "
                "versión de Windows ya no es compatible "
                "con Playwright. El resto de aerolíneas "
                "sigue funcionando normalmente."
            )

            return False

    # ---------------------------------------------
    # PERSISTENCIA DE ALERTAS ENVIADAS
    # ---------------------------------------------

    def _load_sent_alerts(self):

        if not SENT_ALERTS_FILE.exists():
            return set()

        try:

            with SENT_ALERTS_FILE.open(
                "r", encoding="utf-8"
            ) as file:

                raw = json.load(file)

            return {_to_hashable(item) for item in raw}

        except (json.JSONDecodeError, OSError) as error:

            log(
                "  No se pudo leer el historial de "
                f"alertas enviadas: {error}"
            )

            return set()

    def _save_sent_alerts(self):

        DATA_DIR.mkdir(exist_ok=True, parents=True)

        with SENT_ALERTS_FILE.open(
            "w", encoding="utf-8"
        ) as file:

            json.dump(
                list(self.sent_alerts),
                file,
                ensure_ascii=False,
                indent=2,
            )

    # ---------------------------------------------
    # RUTAS
    # ---------------------------------------------

    def build_routes(self):

        routes = []

        for origin in self.config["origins"]:

            for destination in self.config["destinations"]:

                routes.append({
                    "origin": origin,
                    "destination": destination
                })

        return routes

    def run_once(self):

        airlines = self.config.get("airlines", [])

        crosscheck_now = (
            "Aeromexico" in airlines
            and self._should_crosscheck_aeromexico()
        )

        for route in self.build_routes():

            if "Volaris" in airlines:

                try:
                    self.check_volaris(route)

                except Exception as error:

                    log(
                        f"ERROR Volaris "
                        f"{route['origin']} → "
                        f"{route['destination']}: {error}"
                    )

            if "Aeromexico" in airlines:

                try:
                    self.check_aeromexico(route)

                except Exception as error:

                    log(
                        f"ERROR Aeroméxico (Booking.com) "
                        f"{route['origin']} → "
                        f"{route['destination']}: {error}"
                    )

                if crosscheck_now:

                    try:
                        self.check_aeromexico_serpapi(route)

                    except Exception as error:

                        log(
                            f"ERROR Aeroméxico (SerpApi) "
                            f"{route['origin']} → "
                            f"{route['destination']}: {error}"
                        )

            if (
                "Viva Aerobus" in airlines
                and self.playwright_enabled
            ):

                try:
                    self.check_viva(route)

                except Exception as error:

                    log(
                        f"ERROR Viva Aerobús "
                        f"{route['origin']} → "
                        f"{route['destination']}: {error}"
                    )

            if (
                self.config.get("kayak_crosscheck", True)
                and self.playwright_enabled
            ):

                try:
                    self.check_kayak(route)

                except Exception as error:

                    log(
                        f"ERROR KAYAK "
                        f"{route['origin']} → "
                        f"{route['destination']}: {error}"
                    )

        if crosscheck_now:
            self.last_aeromexico_crosscheck = time.monotonic()

    def _should_crosscheck_aeromexico(self):

        if self.last_aeromexico_crosscheck is None:
            return True

        interval_minutes = self.config.get(
            "aeromexico_serpapi_crosscheck_interval_minutes",
            7 * 24 * 60,
        )

        elapsed_minutes = (
            time.monotonic() - self.last_aeromexico_crosscheck
        ) / 60

        return elapsed_minutes >= interval_minutes

    def check_volaris(self, route):

        log(
            "\n" + "=" * 60 +
            f"\nVOLARIS {route['origin']} → "
            f"{route['destination']}\n" + "=" * 60
        )

        combo = self.volaris.find_best_round_trip(
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
            adults=self.config["adults"],
            children=len(
                self.config.get("children_ages", [])
            ),
            max_stops=self.config["max_stops"],
            max_connection_minutes=self.config[
                "max_connection_minutes"
            ],
            currency=self.config.get("currency", "MXN"),
        )

        if combo is None:
            log(
                "  Sin disponibilidad combinable "
                "(ida + vuelta) dentro de las escalas "
                "permitidas."
            )
            return

        self.evaluate_and_alert(
            route, "Volaris", combo,
            source="Volaris (API directa)"
        )

    def check_viva(self, route):
        # Viva Aerobús usa Akamai Bot Manager -- este
        # cliente abre un navegador real (oculto fuera de
        # pantalla) en cada consulta para pasar el
        # desafío. Más lento que Volaris, pero no depende
        # de SerpApi ni de Booking.com.

        log(
            "\n" + "=" * 60 +
            f"\nVIVA AEROBÚS {route['origin']} → "
            f"{route['destination']}\n" + "=" * 60
        )

        combo = find_best_viva(
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
            adults=self.config["adults"],
            children_ages=self.config.get(
                "children_ages", []
            ),
            max_stops=self.config["max_stops"],
            max_connection_minutes=self.config[
                "max_connection_minutes"
            ],
            currency=self.config.get("currency", "MXN"),
        )

        if combo is None:
            log(
                "  Sin disponibilidad combinable "
                "(ida + vuelta) dentro de las escalas "
                "permitidas."
            )
            return

        self.evaluate_and_alert(
            route, "Viva Aerobus", combo,
            source="Viva Aerobús (API directa)"
        )

    def check_kayak(self, route):
        # Validación cruzada: KAYAK no está bloqueado (a
        # diferencia de Skyscanner/Despegar) y una sola
        # carga de página trae precio directo (no de
        # agencia) de las 3 aerolíneas a la vez. No
        # reemplaza los clientes directos, solo compara.

        log(
            "\n" + "=" * 60 +
            f"\nKAYAK (validación cruzada) {route['origin']} → "
            f"{route['destination']}\n" + "=" * 60
        )

        children_ages = self.config.get("children_ages", [])

        data = kayak_fetch_results(
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
            adults=self.config["adults"],
            children_ages=children_ages,
        )

        if data is None:
            log("  No se pudo obtener resultados de KAYAK.")
            return

        total_passengers = (
            self.config["adults"] + len(children_ages)
        )

        for airline in self.config.get("airlines", []):

            total_price = kayak_extract_best_price(
                data,
                airline,
                total_passengers,
                max_stops=self.config["max_stops"],
            )

            if total_price is None:
                log(
                    f"  {airline}: sin oferta directa "
                    "encontrada en KAYAK para el grupo "
                    "completo."
                )
                continue

            combo = {
                "origin": route["origin"],
                "destination": route["destination"],
                "total_price": float(total_price),
                "per_person_price": (
                    total_price / total_passengers
                    if total_passengers else None
                ),
            }

            self.evaluate_and_alert(
                route, airline, combo,
                source="KAYAK (validación cruzada)"
            )

    def check_aeromexico(self, route):
        # Fuente principal: API de Booking.com (gratuita,
        # sin límite de cuota). Nota: en algunas rutas donde
        # Volaris domina (ej. GDL-MID, GDL-CUN), Booking no
        # siempre trae a Aeroméxico "puro" entre sus mejores
        # resultados — para eso está la validación cruzada
        # periódica con SerpApi (check_aeromexico_serpapi).

        log(
            "\n" + "=" * 60 +
            f"\nAEROMÉXICO (Booking.com) {route['origin']} → "
            f"{route['destination']}\n" + "=" * 60
        )

        combo = find_best_aeromexico_booking(
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
            adults=self.config["adults"],
            children_ages=self.config.get(
                "children_ages", []
            ),
            max_stops=self.config["max_stops"],
            max_connection_minutes=self.config[
                "max_connection_minutes"
            ],
            currency=self.config.get("currency", "MXN"),
        )

        if combo is None:
            log(
                "  Sin disponibilidad combinable de "
                "Aeroméxico (sola) en Booking.com ahora "
                "mismo."
            )
            return

        if combo.get("checked_baggage_included") is False:
            log(
                "  (Booking.com confirma: maleta "
                "documentada NO incluida en esta tarifa)"
            )

        self.evaluate_and_alert(
            route, "Aeromexico", combo,
            source="Booking.com (agencia)"
        )

    def check_aeromexico_serpapi(self, route):
        # Validación cruzada, muy poco frecuente (ver
        # aeromexico_serpapi_crosscheck_interval_minutes)
        # para no agotar la cuota mensual de SerpApi.

        log(
            "\n" + "=" * 60 +
            f"\nAEROMÉXICO (SerpApi, validación cruzada) "
            f"{route['origin']} → "
            f"{route['destination']}\n" + "=" * 60
        )

        combo = find_best_aeromexico_serpapi(
            self.serpapi,
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
            adults=self.config["adults"],
            children_ages=self.config.get(
                "children_ages", []
            ),
            max_stops=self.config["max_stops"],
            max_connection_minutes=self.config[
                "max_connection_minutes"
            ],
            currency=self.config.get("currency", "MXN"),
        )

        if combo is None:
            log(
                "  Sin disponibilidad combinable "
                "(ida + vuelta) dentro de las escalas "
                "permitidas."
            )
            return

        self.evaluate_and_alert(
            route, "Aeromexico", combo,
            source="Google Flights / SerpApi"
        )

    def evaluate_and_alert(
        self, route, airline, combo, source="directo"
    ):

        total_price = combo.get("total_price")

        per_person = combo.get("per_person_price")

        if total_price is None or per_person is None:

            log("  Precio incompleto. NO ALERTA.")

            return

        log(
            f"  Total: ${total_price:,.2f} MXN "
            f"(${per_person:,.2f} por persona)"
        )

        min_sanity_price = self.config.get(
            "min_sanity_price_per_person", 0
        )

        if min_sanity_price and per_person < min_sanity_price:

            log(
                f"  Precio sospechosamente bajo "
                f"(${per_person:,.2f}/persona < "
                f"${min_sanity_price} mínimo de "
                "seguridad) — probablemente un error de "
                "datos. Se descarta."
            )

            return

        min_total_price = self.config.get("min_total_price")

        if min_total_price and total_price < min_total_price:

            log(
                f"  Fuera del rango (muy barato): "
                f"${total_price:,.2f} < "
                f"${min_total_price} mínimo del rango"
            )

            return

        if total_price > self.config["max_total_price"]:

            log(
                f"  No cumple tope total: "
                f"${total_price:,.2f} > "
                f"${self.config['max_total_price']}"
            )

            return

        min_price_per_person = self.config.get(
            "min_price_per_person"
        )

        if (
            min_price_per_person
            and per_person < min_price_per_person
        ):

            log(
                f"  Fuera del rango (muy barato): "
                f"${per_person:,.2f}/persona < "
                f"${min_price_per_person} mínimo del rango"
            )

            return

        if per_person > self.config["max_price_per_person"]:

            log(
                f"  No cumple tope por persona: "
                f"${per_person:,.2f} > "
                f"${self.config['max_price_per_person']}"
            )

            return

        alert_key = (
            route["origin"],
            route["destination"],
            airline,
            round(total_price),
            _combo_signature(combo),
        )

        if alert_key in self.sent_alerts:

            log(
                "  Ya se envió esta oferta antes. "
                "NO se repite la alerta."
            )

            return

        self.sent_alerts.add(alert_key)

        self._save_sent_alerts()

        self.send_alert(route, airline, combo, source)

    def build_offer_url(self, route, airline):

        if airline == "Volaris":

            return _volaris_search_url(
                origin=route["origin"],
                destination=route["destination"],
                departure_date=self.config["departure_date"],
                return_date=self.config["return_date"],
                adults=self.config["adults"],
                children=len(
                    self.config.get("children_ages", [])
                ),
            )

        if airline == "Viva Aerobus":

            return _viva_search_url(
                origin=route["origin"],
                destination=route["destination"],
                departure_date=self.config["departure_date"],
                return_date=self.config["return_date"],
                adults=self.config["adults"],
                children=len(
                    self.config.get("children_ages", [])
                ),
            )

        return _google_flights_search_url(
            origin=route["origin"],
            destination=route["destination"],
            departure_date=self.config["departure_date"],
            return_date=self.config["return_date"],
        )

    def send_alert(self, route, airline, combo, source):

        total_price = combo["total_price"]

        per_person = combo["per_person_price"]

        offer_url = self.build_offer_url(route, airline)

        baggage_included = combo.get(
            "checked_baggage_included"
        )

        if baggage_included is True:
            baggage_line = (
                "🧳 Equipaje documentado: incluido según "
                "la fuente consultada."
            )
        else:
            baggage_line = (
                "⚠️ Equipaje documentado: pendiente de "
                "confirmar (NO incluido en este precio)."
            )

        message = (
            "✈️ <b>OFERTA ENCONTRADA</b>\n\n"

            f"{route['origin']} → "
            f"{route['destination']}\n"

            f"Aerolínea: {airline}\n"

            f"Fuente: {source}\n"

            f"Ida: {self.config['departure_date']}\n"

            f"Regreso: {self.config['return_date']}\n\n"

            f"<b>Total: ${total_price:,.2f} MXN</b>\n"

            f"Por persona: ${per_person:,.2f} MXN\n\n"

            f"{baggage_line}\n\n"

            "✅ Precio dentro del rango configurado "
            f"(${self.config.get('min_price_per_person', 0):,.0f}"
            f" - ${self.config['max_price_per_person']:,.0f} "
            "por persona).\n\n"

            f"🔗 <a href=\"{offer_url}\">Buscar este "
            f"vuelo</a>"
        )

        log("  >>> ENVIANDO ALERTA POR TELEGRAM <<<")

        self.telegram.send_message(message)

    def run(self):

        interval = (
            self.config["check_interval_minutes"] * 60
        )

        while True:

            log("\n" + "#" * 70)
            log("INICIO DE MONITOREO")
            log("#" * 70)

            self.run_once()

            log(
                f"\nEsperando "
                f"{self.config['check_interval_minutes']} "
                f"minutos..."
            )

            time.sleep(interval)
