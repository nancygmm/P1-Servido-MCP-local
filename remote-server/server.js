const express = require("express");
const { WebSocketServer } = require("ws");
const http = require("http");

const app = express();
app.get("/", (_req, res) => res.json({ ok: true, service: "remote-time-mcp" }));
app.get("/health", (_req, res) => res.json({ status: "ok" }));

const server = http.createServer(app);
new WebSocketServer({ server, path: "/mcp" }).on("connection", (socket) => {
  console.log("WS /mcp conectado");
  socket.send(JSON.stringify({ jsonrpc: "2.0", result: "Hello MCP", id: 1 }));
  socket.close();
});

const port = process.env.PORT || 8080;
server.listen(port, "0.0.0.0", () => console.log("listening", port));
