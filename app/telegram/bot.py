import os
import requests


class TelegramBot:

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self):

        self.token = os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )

        self.chat_id = os.getenv(
            "TELEGRAM_CHAT_ID"
        )

        if not self.token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN no configurado."
            )

        if not self.chat_id:
            raise ValueError(
                "TELEGRAM_CHAT_ID no configurado."
            )

    def send_message(self, message):

        url = (
            f"{self.BASE_URL}"
            f"{self.token}/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=30
        )

        response.raise_for_status()

        return response.json()