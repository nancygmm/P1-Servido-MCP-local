import os
import uuid
import asyncio
from typing import Optional, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from qr_lib import (
    generate_qr,
    read_qr,
    wifi_payload,
    vcard_payload,
)

server = Server("qr-mcp-server")

OUTPUT_DIR = os.path.abspath("qr_codes")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _new_filename(prefix: str = "qr", ext: str = "png") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}.{ext}"

@server.tool(
    name="generate_qr",
    description=(
        "Genera un código QR a partir de texto plano (URL, WiFi payload, vCard u otro). "
        "Permite configurar nivel de corrección de errores (L/M/Q/H), tamaño y colores. "
        "Devuelve la ruta absoluta del archivo PNG generado."
    ),
)
async def generate_qr_tool(
    data: str,
    error_correction: str = "M",
    box_size: int = 10,
    border: int = 4,
    fill_color: str = "black",
    back_color: str = "white",
    filename: Optional[str] = None,
) -> List[TextContent]:
    name = filename or _new_filename("qr", "png")
    out_path = os.path.join(OUTPUT_DIR, name)
    saved = generate_qr(
        data=data,
        out_path=out_path,
        error_correction=error_correction,
        box_size=box_size,
        border=border,
        fill_color=fill_color,
        back_color=back_color,
    )
    return [TextContent(type="text", text=os.path.abspath(saved))]


@server.tool(
    name="generate_wifi_qr",
    description=(
        "Genera un QR con credenciales WiFi (WIFI:T:...;S:...;P:...;H:...;;). "
        "Devuelve la ruta absoluta del PNG."
    ),
)
async def generate_wifi_qr_tool(
    ssid: str,
    password: str,
    auth: str = "WPA",
    hidden: bool = False,
    filename: Optional[str] = None,
) -> List[TextContent]:
    payload = wifi_payload(ssid=ssid, password=password, auth=auth, hidden=hidden)
    name = filename or _new_filename("wifi", "png")
    out_path = os.path.join(OUTPUT_DIR, name)
    saved = generate_qr(data=payload, out_path=out_path)
    return [TextContent(type="text", text=os.path.abspath(saved))]


@server.tool(
    name="generate_vcard_qr",
    description=(
        "Genera un QR con datos de contacto en formato vCard 3.0 (FN, TEL, EMAIL opcional). "
        "Devuelve la ruta absoluta del PNG."
    ),
)
async def generate_vcard_qr_tool(
    name: str,
    tel: str,
    email: Optional[str] = None,
    filename: Optional[str] = None,
) -> List[TextContent]:
    payload = vcard_payload(name=name, tel=tel, email=email)
    fname = filename or _new_filename("vcard", "png")
    out_path = os.path.join(OUTPUT_DIR, fname)
    saved = generate_qr(data=payload, out_path=out_path)
    return [TextContent(type="text", text=os.path.abspath(saved))]


@server.tool(
    name="read_qr",
    description=(
        "Lee/decodifica un código QR desde una imagen PNG/JPG y devuelve el contenido textual."
    ),
)
async def read_qr_tool(image_path: str) -> List[TextContent]:
    content = read_qr(image_path)
    return [TextContent(type="text", text=content)]

async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    asyncio.run(main())
