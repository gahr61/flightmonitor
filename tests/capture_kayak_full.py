"""
Captura la respuesta MÁS COMPLETA del polling de KAYAK
(la última, que suele traer más resultados) para analizar
la estructura completa de precios/itinerarios.
"""

import sys
import json
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from playwright.sync_api import sync_playwright


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

KAYAK_URL = (
    "https://www.kayak.com.mx/flights/GDL-MID/"
    "2026-12-26/2027-01-02/5adults/children-6,5"
)

responses = []

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False,
        args=["--window-position=-32000,-32000"],
    )

    context = browser.new_context(
        locale="es-MX",
        viewport={"width": 1440, "height": 900}
    )

    page = context.new_page()

    def on_response(response):

        if "search/dynamic/flights/poll" not in response.url:
            return

        try:
            body = response.json()
            responses.append(body)
            print(
                "capturada respuesta poll #",
                len(responses),
                "resultados:",
                len(body.get("resultsList", []) or [])
            )
        except Exception as error:
            print("no se pudo leer:", error)

    page.on("response", on_response)

    print("Cargando KAYAK...")

    page.goto(KAYAK_URL, wait_until="domcontentloaded", timeout=60000)

    page.wait_for_timeout(25000)

    browser.close()


if responses:

    last = responses[-1]

    out_file = OUTPUT_DIR / "kayak_full_response.json"

    out_file.write_text(
        json.dumps(last, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\nGuardado:", out_file)
    print("Top-level keys:", list(last.keys()))
    print("num resultsList:", len(last.get("resultsList", []) or []))

else:
    print("No se capturó ninguna respuesta de poll.")
