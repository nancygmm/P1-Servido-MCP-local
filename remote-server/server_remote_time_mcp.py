import os
from datetime import datetime, timezone
from mcp.server.fastmcp import FastMCP

app = FastMCP("remote-time-mcp")

@app.tool()
def time_now(fmt: str | None = None) -> str:
    t = datetime.now(timezone.utc)
    return t.strftime(fmt) if fmt else t.isoformat()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run_http(host="0.0.0.0", port=port)
