import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

load_dotenv()

class ChatbotMCP:
    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self.history = []
        self.log = []

    def ask_llm(self, prompt: str) -> str:
        messages = self.history + [{"role": "user", "content": prompt}]
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 256,
            "messages": messages
        }
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, data=json.dumps(payload), timeout=60)
        except requests.RequestException as e:
            reply = f"Error de conexión: {e}"
            self._log("LLM", prompt, reply, error=True)
            return reply
        if resp.status_code != 200:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            reply = f"Error: {resp.status_code}, {body}"
            self._log("LLM", prompt, reply, error=True)
            return reply
        data = resp.json()
        if "content" in data and data["content"]:
            reply_text = ""
            for part in data["content"]:
                if part.get("type") == "text":
                    reply_text += part.get("text", "")
            self.history.append({"role": "user", "content": prompt})
            self.history.append({"role": "assistant", "content": reply_text})
        else:
            reply_text = "(Respuesta vacía o en formato inesperado.)"
        self._log("LLM", prompt, reply_text)
        return reply_text

    def _log(self, server_name: str, request: str, response: str, error: bool=False):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.append({
            "time": timestamp,
            "server": server_name,
            "request": request,
            "response": response,
            "error": error
        })

    def show_log(self):
        print("\n=== LOG DE INTERACCIONES ===")
        for entry in self.log:
            status = "ERROR" if entry.get("error") else "OK"
            print(f"[{entry['time']}] ({entry['server']}) [{status}]")
            print(f" -> Solicitud: {entry['request']}")
            print(f" <- Respuesta: {entry['response']}\n")

if __name__ == "__main__":
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno. Exporta la variable y vuelve a ejecutar.")
    bot = ChatbotMCP(api_key=api_key, model="claude-3-haiku-20240307")
    print("Escribe tu pregunta. Comandos: log | salir/exit/quit")
    try:
        while True:
            user_in = input("> ").strip()
            if not user_in:
                continue
            if user_in.lower() in ("salir", "exit", "quit"):
                break
            if user_in.lower() == "log":
                bot.show_log()
                continue
            resp = bot.ask_llm(user_in)
            print("Bot:", resp)
    except KeyboardInterrupt:
        pass
