import os
from flask import Flask, request, jsonify

REV = "flask-remote-temp-mcp-002"  

print("### BOOT: USING FLASK SERVER")
print("### REV:", REV)
print("### FILE:", __file__)

app = Flask(__name__)

def convert_temp_logic(value, unit="C") -> str:
    unit = (unit or "").upper()
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "ERROR: <value> debe ser numérico."

    if unit == "C":
        result = (value * 9 / 5) + 32
        return f"{value} °C = {result:.2f} °F"
    if unit == "F":
        result = (value - 32) * 5 / 9
        return f"{value} °F = {result:.2f} °C"
    return "Unidad no válida. Usa 'C' para Celsius o 'F' para Fahrenheit."

@app.get("/")
def root():
    return jsonify({"service": "remote-temp-mcp (flask)", "rev": REV, "status": "ok"})

@app.get("/health")
def health():
    return jsonify({"status": "ok", "rev": REV})

@app.post("/")
def jsonrpc_entrypoint():
    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}), 400

    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return jsonify({"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}}), 400

    rpc_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    if method == "convert_temp":
        value = params.get("value")
        unit = params.get("unit", "C")
        result = convert_temp_logic(value, unit)
        return jsonify({"jsonrpc": "2.0", "id": rpc_id, "result": result})

    return jsonify({"jsonrpc": "2.0", "id": rpc_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}), 404

@app.get("/mcp/tools/list")
def mcp_tools_list():
    return jsonify({
        "tools": [{
            "name": "convert_temp",
            "description": "Convierte temperaturas entre Celsius y Fahrenheit.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "value": {"type": "number"},
                    "unit": {"type": "string", "enum": ["C", "F"]}
                },
                "required": ["value"],
                "additionalProperties": False
            }
        }],
        "rev": REV
    })

@app.post("/tools/convert_temp/call")
def mcp_tool_call():
    data = request.get_json(force=True, silent=True) or {}
    args = data.get("arguments", data) or {}
    value = args.get("value")
    unit = args.get("unit", "C")
    result = convert_temp_logic(value, unit)
    return jsonify({"result": result, "rev": REV})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
