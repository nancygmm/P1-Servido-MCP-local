import os
import re
import json
import asyncio
import requests
from datetime import datetime
from contextlib import AsyncExitStack
from dotenv import load_dotenv
import uuid


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

load_dotenv()

import textwrap

ORCHESTRATOR_SYS = """Eres un planificador que transforma la petición del usuario en UNA acción.
Responde SOLO un JSON válido y nada más, sin texto adicional.
Si la intención no coincide con las herramientas, responde {"tool":"chat","args":{"prompt":"<texto para el LLM>"}}

Herramientas permitidas (tool):
- "qr.generate_url": args = { "url": string, "filename": optional string }
- "qr.generate_text": args = { "text": string, "filename": optional string }
- "qr.generate_wifi": args = { "ssid": string, "password": string or "", "auth": "WPA"|"WEP"|"NOPASS", "hidden": boolean, "filename": optional string }
- "qr.generate_vcard": args = { "full_name": string, "org": optional string, "title": optional string, "phone": optional string, "email": optional string, "url": optional string, "filename": optional string }
- "qr.decode_image": args = { "image_path": string }
- "external.call": args = { "server": "EXT1"|"EXT2", "tool": string, "args": object }
- "temp.convert": args = { "value": float, "unit": "C"|"F" }

Reglas:
- Si el usuario pega una URL, asume "qr.generate_url".
- Si menciona WiFi/SSID/contraseña, usa "qr.generate_wifi". Si dice que no hay contraseña, usa auth="NOPASS" y password="".
- Si pide "tarjeta de contacto"/"vcard"/"contacto", usa "qr.generate_vcard".
- Si dice "texto", "mensaje", "todo lo que dice", usa "qr.generate_text".
- Si pide leer/decodificar un QR de una imagen, usa "qr.decode_image".
- Si pide usar un servidor de un compañero, usa "external.call" con el server y tool adecuados.
- Si pide convertir temperatura, usar Celsius/Fahrenheit, usa "temp.convert" con value (número) y unit ("C" o "F").
- Si suena a conversación general, usa "chat".
- Si el usuario sugiere un nombre de archivo, ponlo en filename."""

def ask_fn_with_sys(ask_fn, system: str, user: str) -> str:
    composite = textwrap.dedent(f"[SYSTEM]\n{system}\n\n[USER]\n{user}")
    return ask_fn(composite)

def plan_action_with_llm(ask_fn, user_text: str) -> dict:
    prompt = f"Convierte el siguiente pedido del usuario en una acción JSON:\n---\n{user_text}\n---\nResponde SOLO JSON:"
    raw = ask_fn_with_sys(ask_fn, ORCHESTRATOR_SYS, prompt)
    m = re.search(r'\{.*\}', raw, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else {"tool":"chat","args":{"prompt":user_text}}
    except Exception:
        return {"tool":"chat","args":{"prompt":user_text}}
    

class ChatbotMCP:
    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self.history = []
        self.log = []

        self.fs_root = os.getenv("MCP_FS_ROOT", os.path.abspath("./workspace"))
        self.qr_server_path = os.getenv("QR_MCP_PATH", os.path.abspath("./mcp-qr/server_qr_mcp.py"))
        self.git_command = os.getenv("MCP_GIT_CMD", "uvx")  
        self.git_args = os.getenv("MCP_GIT_ARGS", "mcp-server-git").split()
        
        self.temp_server_url = os.getenv("TEMP_MCP_URL", "http://localhost:8080")
        print(self.temp_server_url)

        os.makedirs(self.fs_root, exist_ok=True)
        
        self.ext_map = {}
        for key in ("EXT1","EXT2"):
            cmd = os.getenv(f"{key}_CMD", "").strip()
            args = os.getenv(f"{key}_ARGS", "").strip()
            label = os.getenv(f"{key}_LABEL", key).strip() or key
            if cmd and args:
                self.ext_map[label] = {"cmd": cmd, "args": args.split()}


    def ask_llm(self, prompt: str) -> str:
        messages = self.history + [{"role": "user", "content": prompt}]
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        payload = {"model": self.model, "max_tokens": 256, "messages": messages}
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

    def _log(self, server_name: str, request: str, response: str, error: bool = False):
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

    async def _connect_session(self, command: str, args: list[str]):
        params = StdioServerParameters(command=command, args=args)
        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            read_stream, write_stream = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            await session.list_tools()
            return session, stack
        except Exception:
            await stack.aclose()
            raise

    async def _call_tool_text(self, session: ClientSession, server_label: str, tool_name: str, arguments: dict) -> str:
        try:
            result = await session.call_tool(tool_name, arguments)
            parts = []
            for c in getattr(result, "content", []) or []:
                t = getattr(c, "type", None)
                if t == "text":
                    parts.append(getattr(c, "text", ""))
            text = "\n".join(p for p in parts if p) or str(result)
            self._log(server_label, f"{tool_name} {json.dumps(arguments)}", text)
            return text
        except Exception as e:
            msg = f"ERROR llamando {tool_name}: {e}"
            self._log(server_label, f"{tool_name} {json.dumps(arguments)}", msg, error=True)
            return msg

    def _call_remote_tool(self, server_url: str, server_label: str, tool_name: str, arguments: dict) -> str:
        try:
            url = f"{server_url}/tools/{tool_name}/call"
            
            payload = {
                "arguments": arguments
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if "content" in data and data["content"]:
                    result_text = data["content"][0].get("text", str(data))
                else:
                    result_text = str(data)
                
                self._log(server_label, f"{tool_name} {json.dumps(arguments)}", result_text)
                return result_text
            else:
                error_msg = f"Error HTTP {response.status_code}: {response.text}"
                self._log(server_label, f"{tool_name} {json.dumps(arguments)}", error_msg, error=True)
                return error_msg
                
        except Exception as e:
            error_msg = f"ERROR llamando {tool_name} en {server_url}: {e}"
            self._log(server_label, f"{tool_name} {json.dumps(arguments)}", error_msg, error=True)
            return error_msg

    async def _with_filesystem(self):
        try:
            return await self._connect_session(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", self.fs_root]
            )
        except Exception as e:
            raise RuntimeError(
                f"No se pudo iniciar el Filesystem MCP server con npx: {e}\n"
                f"Verifica que Node y npx estén instalados (ejecuta 'node -v' y 'npx -v')."
            ) from e

    async def _with_git(self):
        try:
            return await self._connect_session(self.git_command, self.git_args)
        except Exception as e1:
            if self.git_command == "python" and self.git_args == ["-m", "mcp_server_git"]:
                raise RuntimeError(f"No se pudo iniciar Git server: {e1}") from e1

            try:
                return await self._connect_session("python", ["-m", "mcp_server_git"])
            except Exception as e2:
                raise RuntimeError(
                    f"No se pudo iniciar el Git server.\n"
                    f"Intento 1: '{self.git_command} {' '.join(self.git_args)}' → {e1}\n"
                    f"Intento 2: 'python -m mcp_server_git' → {e2}\n"
                    f"Sugerencia: 'pip install mcp-server-git' en tu .venv."
                ) from e2

    async def _with_qr(self):
        return await self._connect_session(command="python", args=[self.qr_server_path])

    async def _with_external(self, label: str):
        if label not in self.ext_map:
            raise RuntimeError(f"Servidor externo no configurado: {label}")
        cfg = self.ext_map[label]
        return await self._connect_session(command=cfg["cmd"], args=cfg["args"])

    def demo_git_repo(self, repo_path: str) -> str:
        repo_abs = os.path.abspath(repo_path)
        readme_path = os.path.join(repo_abs, "README.md")
        readme_content = "# Nuevo Proyecto (MCP Demo)\n\nCreado por el chatbot vía MCP.\n"

        async def run():
            fs_session, fs_stack = await self._with_filesystem()
            await self._call_tool_text(fs_session, "MCP:filesystem", "create_directory", {"path": repo_abs})
            await self._call_tool_text(fs_session, "MCP:filesystem", "write_file", {"path": readme_path, "content": readme_content})
            git_session, git_stack = await self._with_git()
            await self._call_tool_text(git_session, "MCP:git", "git_init", {"repo_path": repo_abs})
            await self._call_tool_text(git_session, "MCP:git", "git_add", {"repo_path": repo_abs, "files": ["README.md"]})
            commit_msg = "Initial commit: add README via MCP"
            out_commit = await self._call_tool_text(git_session, "MCP:git", "git_commit", {"repo_path": repo_abs, "message": commit_msg})
            status = await self._call_tool_text(git_session, "MCP:git", "git_status", {"repo_path": repo_abs})
            await fs_stack.aclose()
            await git_stack.aclose()
            return f"Commit hecho.\n{out_commit}\n\nStatus:\n{status}"

        try:
            result = asyncio.run(run())
            return result
        except Exception as e:
            msg = f"Fallo en demo_git_repo: {e}"
            self._log("MCP:demo_git", repo_abs, msg, error=True)
            return msg

    def qr_generate_url(self, url: str, filename: str | None = None) -> str:
        async def run():
            session, stack = await self._with_qr()
            args = {"url": url}
            if filename:
                args["filename"] = filename
            result = await self._call_tool_text(session, "MCP:qr", "qr.generate_url", args)
            await stack.aclose()
            return result
        return asyncio.run(run())

    def qr_generate_text(self, text: str, filename: str | None = None) -> str:
        async def run():
            session, stack = await self._with_qr()
            args = {"text": text}
            if filename:
                args["filename"] = filename
            result = await self._call_tool_text(session, "MCP:qr", "qr.generate_text", args)
            await stack.aclose()
            return result
        return asyncio.run(run())

    def qr_generate_wifi(self, ssid: str, password: str, auth: str = "WPA", hidden: bool = False, filename: str | None = None) -> str:
        async def run():
            session, stack = await self._with_qr()
            args = {"ssid": ssid, "password": password, "auth": auth, "hidden": hidden}
            if filename:
                args["filename"] = filename
            result = await self._call_tool_text(session, "MCP:qr", "qr.generate_wifi", args)
            await stack.aclose()
            return result
        return asyncio.run(run())

    def qr_generate_vcard(self, full_name: str, **kwargs) -> str:
        async def run():
            session, stack = await self._with_qr()
            args = {"full_name": full_name}
            args.update({k: v for k, v in kwargs.items() if v})
            result = await self._call_tool_text(session, "MCP:qr", "qr.generate_vcard", args)
            await stack.aclose()
            return result
        return asyncio.run(run())

    def qr_decode(self, image_path: str) -> str:
        async def run():
            session, stack = await self._with_qr()
            result = await self._call_tool_text(session, "MCP:qr", "qr.decode_image", {"image_path": image_path})
            await stack.aclose()
            return result
        return asyncio.run(run())
    
    def external_call(self, server_label: str, tool_name: str, arguments: dict) -> str:
        async def run():
            session, stack = await self._with_external(server_label)
            result = await self._call_tool_text(session, f"MCP:{server_label}", tool_name, arguments or {})
            await stack.aclose()
            return result
        return asyncio.run(run())

    def temp_convert(self, value: float, unit: str) -> str:
        return self._call_remote_tool(
            self.temp_server_url, 
            "MCP:temp-remote", 
            "convert_temp", 
            {"value": value, "unit": unit}
        )

    
    def dispatch_nl_action(self, plan: dict) -> str:
        tool = (plan.get("tool") or "").strip()
        args = plan.get("args") or {}
        try:
            if tool == "qr.generate_url":
                return self.qr_generate_url(args["url"], args.get("filename"))
            if tool == "qr.generate_text":
                return self.qr_generate_text(args["text"], args.get("filename"))
            if tool == "qr.generate_wifi":
                return self.qr_generate_wifi(args["ssid"], args.get("password",""), args.get("auth","WPA"), bool(args.get("hidden", False)), args.get("filename"))
            if tool == "qr.generate_vcard":
                return self.qr_generate_vcard(**args)
            if tool == "qr.decode_image":
                return self.qr_decode(args["image_path"])
            if tool == "external.call":
                return self.external_call(args["server"], args["tool"], args.get("args", {}))
            if tool == "temp.convert":
                return self.temp_convert(args["value"], args["unit"])
            if tool == "chat":
                return self.ask_llm(args.get("prompt",""))
        except Exception as e:
            return f"Error ejecutando {tool}: {e}"
        return self.ask_llm(args.get("prompt",""))

def parse_bool(s: str) -> bool:
    return str(s).lower() in ("1", "true", "t", "yes", "y", "si", "sí")


if __name__ == "__main__":
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en el entorno. Exporta la variable y vuelve a ejecutar.")

    bot = ChatbotMCP(api_key=api_key, model="claude-3-haiku-20240307")
    print("Escribe tu pregunta :)")
    print("Comandos especiales:")
    print("- 'temp_convert <valor> <unidad>': Convierte temperatura (ej: temp_convert 25 C)")
    print("- 'log': Muestra el registro de actividad")
    print("- 'salir': Termina el programa")

    try:
        while True:
            user_in = input("> ").strip()
            user_in = re.sub(r'^\s*(>>>?|\$\s*|#\s*|>\s*)+', '', user_in).strip()
            if not user_in:
                continue

            if user_in.lower() in ("salir", "exit", "quit"):
                break
            if user_in.lower() == "log":
                bot.show_log(); continue

            parts = user_in.split()
            cmd = parts[0].lower()

            try:
                if cmd == "demo_git" and len(parts) >= 2:
                    path = parts[1]
                    print(bot.demo_git_repo(path))
                    continue

                if cmd == "temp_convert" and len(parts) >= 3:
                    try:
                        value = float(parts[1])
                        unit = parts[2].upper()
                        if unit not in ["C", "F"]:
                            print("Error: La unidad debe ser 'C' (Celsius) o 'F' (Fahrenheit)")
                            continue
                        print(bot.temp_convert(value, unit))
                    except ValueError:
                        print("Error: El valor debe ser un número")
                    continue

                if cmd == "qr_url" and len(parts) >= 2:
                    url = parts[1]
                    filename = parts[2] if len(parts) >= 3 else None
                    print(bot.qr_generate_url(url, filename))
                    continue

                if cmd == "qr_text" and len(parts) >= 2:
                    if user_in.count('"') >= 2:
                        between = user_in.split('"', 2)[1]
                        tail = user_in.split('"', 2)[2].strip().split()
                        filename = tail[0] if (tail and tail[0].endswith(".png")) else None
                        print(bot.qr_generate_text(between, filename))
                    else:
                        text = " ".join(parts[1:-1]) if parts[-1].endswith(".png") else " ".join(parts[1:])
                        filename = parts[-1] if parts[-1].endswith(".png") else None
                        print(bot.qr_generate_text(text, filename))
                    continue

                if cmd == "qr_wifi" and len(parts) >= 3:
                    rest = user_in[len("qr_wifi"):].strip()
                    if rest.count('"') >= 4:
                        ssid = rest.split('"', 2)[1]
                        rem = rest.split('"', 2)[2].strip()
                        password = rem.split('"', 2)[1]
                        after = rem.split('"', 2)[2].strip().split()
                    else:
                        ssid, password, *after = parts[1:]
                    auth = after[0] if after else "WPA"
                    hidden = False
                    filename = None
                    for tok in after[1:]:
                        if tok.startswith("hidden="):
                            hidden = parse_bool(tok.split("=", 1)[1])
                        elif tok.endswith(".png"):
                            filename = tok
                    print(bot.qr_generate_wifi(ssid, password, auth, hidden, filename))
                    continue

                if cmd == "qr_vcard" and len(parts) >= 2:
                    full = user_in[len("qr_vcard"):].strip()
                    if full.count('"') >= 2:
                        full_name = full.split('"', 2)[1]
                        rest = full.split('"', 2)[2].strip().split()
                    else:
                        toks = full.split()
                        stop = 1
                        while stop < len(toks) and not toks[stop].startswith("--") and not toks[stop].endswith(".png"):
                            stop += 1
                        full_name = " ".join(toks[:stop])
                        rest = toks[stop:]
                    kw = {}
                    filename = None
                    i = 0
                    while i < len(rest):
                        t = rest[i]
                        if t == "--org" and i + 1 < len(rest): kw["org"] = rest[i + 1]; i += 2; continue
                        if t == "--title" and i + 1 < len(rest): kw["title"] = rest[i + 1]; i += 2; continue
                        if t == "--phone" and i + 1 < len(rest): kw["phone"] = rest[i + 1]; i += 2; continue
                        if t == "--email" and i + 1 < len(rest): kw["email"] = rest[i + 1]; i += 2; continue
                        if t == "--url" and i + 1 < len(rest): kw["url"] = rest[i + 1]; i += 2; continue
                        if t.endswith(".png"): filename = t; i += 1; continue
                        i += 1
                    if filename: kw["filename"] = filename
                    print(bot.qr_generate_vcard(full_name, **kw))
                    continue

                if cmd == "qr_decode" and len(parts) >= 2:
                    image_path = parts[1]
                    print(bot.qr_decode(image_path))
                    continue

                plan = plan_action_with_llm(bot.ask_llm, user_in)
                out = bot.dispatch_nl_action(plan)
                print("Bot:", out)

            except Exception as e:
                print("Error procesando comando:", e)
    except KeyboardInterrupt:
        pass