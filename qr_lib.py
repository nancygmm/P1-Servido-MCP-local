from typing import Optional
from PIL import Image
import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H

try:
    from pyzbar.pyzbar import decode as zbar_decode
    _HAS_ZBAR = True
except Exception:
    _HAS_ZBAR = False

import cv2

_EC_MAP = {
    "L": ERROR_CORRECT_L, 
    "M": ERROR_CORRECT_M,  
    "Q": ERROR_CORRECT_Q,  
    "H": ERROR_CORRECT_H,  
}

def wifi_payload(ssid: str, password: str, auth: str = "WPA", hidden: bool = False) -> str:
    auth = (auth or "WPA").upper()
    hflag = "true" if hidden else "false"
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace(":", r"\:")
    return f"WIFI:T:{esc(auth)};S:{esc(ssid)};P:{esc(password)};H:{hflag};;"

def vcard_payload(name: str, tel: str, email: Optional[str] = None) -> str:
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{name}",
        f"FN:{name}",
        f"TEL;TYPE=CELL:{tel}",
    ]
    if email:
        lines.append(f"EMAIL;TYPE=INTERNET:{email}")
    lines.append("END:VCARD")
    return "\n".join(lines)

def generate_qr(
    data: str,
    out_path: str,
    error_correction: str = "M",
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
) -> str:
    ec = _EC_MAP.get(error_correction.upper(), ERROR_CORRECT_M)
    qr = qrcode.QRCode(
        version=None,
        error_correction=ec,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color=fill_color, back_color=back_color)
    img.save(out_path)
    return out_path

def read_qr(image_path: str) -> str:
    if _HAS_ZBAR:
        img = Image.open(image_path)
        results = zbar_decode(img)
        if results:
            return "\n".join(obj.data.decode("utf-8", errors="replace") for obj in results)

    img_cv = cv2.imread(image_path)
    if img_cv is None:
        raise FileNotFoundError(f"No se pudo abrir la imagen: {image_path}")
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img_cv)
    if data:
        return data
    raise ValueError("No se detectó ningún QR en la imagen.")
