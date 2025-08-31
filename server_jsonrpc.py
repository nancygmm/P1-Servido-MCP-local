from flask import Flask, request, jsonify
from qr_lib import generate_qr, read_qr, wifi_payload, vcard_payload
import os
import uuid

app = Flask(__name__)
OUTPUT_DIR = os.path.abspath("qr_codes")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _ok(id_, result):
    return {"jsonrpc": "2.0", "id": id_, "result": result}

def _err(id_, code, message):
    return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

@app.post("/rpc")
def rpc():
    try:
        payload = request.get_json(force=True, silent=False)
        method = payload.get("method")
        params = payload.get("params", {}) or {}
        id_ = payload.get("id", str(uuid.uuid4()))

        if method == "generate_qr":
            data = params["data"]
            ec = params.get("error_correction", "M")
            box_size = int(params.get("box_size", 10))
            border = int(params.get("border", 4))
            fill = params.get("fill_color", "black")
            bg = params.get("back_color", "white")
            name = params.get("filename", f"qr_{uuid.uuid4().hex[:8]}.png")
            out_path = os.path.join(OUTPUT_DIR, name)
            saved = generate_qr(
                data=data,
                out_path=out_path,
                error_correction=ec,
                box_size=box_size,
                border=border,
                fill_color=fill,
                back_color=bg,
            )
            return jsonify(_ok(id_, {"path": saved}))

        elif method == "generate_wifi_qr":
            ssid = params["ssid"]
            password = params.get("password", "")
            auth = params.get("auth", "WPA")
            hidden = bool(params.get("hidden", False))
            data = wifi_payload(ssid, password, auth, hidden)
            name = params.get("filename", f"wifi_{uuid.uuid4().hex[:8]}.png")
            out_path = os.path.join(OUTPUT_DIR, name)
            saved = generate_qr(data=data, out_path=out_path)
            return jsonify(_ok(id_, {"path": saved}))

        elif method == "generate_vcard_qr":
            name = params["name"]
            tel = params["tel"]
            email = params.get("email")
            data = vcard_payload(name, tel, email)
            fname = params.get("filename", f"vcard_{uuid.uuid4().hex[:8]}.png")
            out_path = os.path.join(OUTPUT_DIR, fname)
            saved = generate_qr(data=data, out_path=out_path)
            return jsonify(_ok(id_, {"path": saved}))

        elif method == "read_qr":
            image_path = params["image_path"]
            content = read_qr(image_path)
            return jsonify(_ok(id_, {"content": content}))

        else:
            return jsonify(_err(id_, -32601, f"Método no encontrado: {method}"))

    except KeyError as e:
        return jsonify(_err(None, -32602, f"Parámetro faltante: {e}")), 400
    except Exception as e:
        return jsonify(_err(None, -32000, f"Error interno: {e}")), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=6060, debug=True)
