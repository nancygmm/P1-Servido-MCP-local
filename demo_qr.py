from qr_lib import generate_qr, read_qr, wifi_payload, vcard_payload

if __name__ == "__main__":
    path = generate_qr("https://uvg.edu.gt", "qr_url.png", error_correction="Q")
    print("Generado:", path, "->", read_qr(path))

    wifi = wifi_payload("MiRed", "12345", auth="WPA2")
    path = generate_qr(wifi, "qr_wifi.png")
    print("Generado:", path, "->", read_qr(path))

    vcard = vcard_payload("María Perez", "1234-5678", email="maria@example.com")
    path = generate_qr(vcard, "qr_vcard.png")
    print("Generado:", path)
    print("Leído:", read_qr(path))
