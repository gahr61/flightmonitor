from dotenv import load_dotenv

from app.config import load_config
from app.monitor import FlightMonitor


def main():

    load_dotenv()

    config = load_config()

    monitor = FlightMonitor(
        config
    )

    monitor.run()


if __name__ == "__main__":
    main()