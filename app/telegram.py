import os
import requests


class TelegramBot:

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self):

        self.token = os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )

        chat_ids_raw = os.getenv(
            "TELEGRAM_CHAT_ID"
        )

        if not self.token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN no configurado."
            )

        if not chat_ids_raw:
            raise ValueError(
                "TELEGRAM_CHAT_ID no configurado."
            )

        # Admite uno o varios chat_id separados por coma,
        # para mandar la misma alerta a varias personas.
        self.chat_ids = [
            chat_id.strip()
            for chat_id in chat_ids_raw.split(",")
            if chat_id.strip()
        ]

    def send_message(self, message):

        url = (
            f"{self.BASE_URL}"
            f"{self.token}"
            f"/sendMessage"
        )

        results = []

        for chat_id in self.chat_ids:

            response = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=30
            )

            response.raise_for_status()

            results.append(response.json())

        return results