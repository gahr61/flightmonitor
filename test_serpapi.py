import json

with open(
    "booking_response.json",
    "r",
    encoding="utf-8"
) as file:
    data = json.load(file)


options = data.get("booking_options", [])


print("\n========================================")
print("BUSCANDO OPCIÓN DIRECTA VOLARIS")
print("========================================")


for index, option in enumerate(options, start=1):

    together = option.get("together", {})

    seller = together.get("book_with")

    if seller != "Volaris":
        continue

    print(f"\nOPCIÓN #{index}")
    print("=" * 70)

    print("VENDEDOR:")
    print(seller)

    print("\nPRECIO:")
    print(together.get("price"))

    print("\nPRECIO LOCAL:")
    print(together.get("local_prices"))

    print("\nMARKETED AS:")
    print(together.get("marketed_as"))

    print("\nBOOKING REQUEST:")
    booking_request = together.get("booking_request")

    if booking_request:
        print("URL:")
        print(booking_request.get("url"))

        print("\nPOST DATA:")
        print(booking_request.get("post_data"))

    print("\nTODOS LOS CAMPOS:")
    for key, value in together.items():
        print(f"{key}: {value}")