import os
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

app = FastMCP("remote-time-mcp")

@app.tool()
def time_now(fmt: str | None = None) -> str:
    """Devuelve la hora UTC actual. Usa 'fmt' para formatear (strftime)."""
    t = datetime.now(timezone.utc)
    return t.strftime(fmt) if fmt else t.isoformat()

@app.http.get("/")
def home():
    return {
        "name": "remote-time-mcp",
        "status": "ok",
        "endpoints": {
            "health": "/health",
            "tools_list": "/mcp/tools/list",
            "tools_call": "/mcp/tools/call"
        },
        "tools": ["time_now"],
        "try": {
            "example_call_body": {
                "id": "any-id",
                "name": "time_now",
                "arguments": {"fmt": "%Y-%m-%d %H:%M:%S UTC"}
            }
        }
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run_http(host="0.0.0.0", port=port)