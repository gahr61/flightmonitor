import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
    )
)

from dotenv import load_dotenv

from app.telegram import TelegramBot


load_dotenv()

bot = TelegramBot()

result = bot.send_message(
    "✈️ <b>Prueba del monitor</b>\n"
    "Telegram funciona correctamente."
)

print(result)