# Servidor remoto de conversión de temperatura (Flask) + Chatbot

Publica un **servidor HTTP (Flask)** con una herramienta de **conversión de temperatura** (Celsius ↔ Fahrenheit) y un **chatbot** que lo consume vía **JSON-RPC 2.0**. Incluye endpoints de **healthcheck** para **Google App Engine**, ejemplos con **cURL/Postman** y cómo conectar el **chatbot**.

---

## Estructura

```
P1-Servido-MCP-local/
├─ remote-server/
│  ├─ app.yaml
│  ├─ requirements.txt
│  └─ server_remote_time_mcp.py   # Servidor Flask
└─ chatbot.py                      # Chatbot cliente (usa MCP_REMOTE_URL)
```

> Si renombras el archivo del servidor, actualiza el `entrypoint` en `app.yaml`.

---

## Requisitos

- **Python 3.11** (recomendado)
- **gcloud CLI** autenticado con tu proyecto de GCP
- **cURL** o **Postman** (para pruebas)

---

## Ejecutar el servidor **Flask** en local

1) Crear entorno y activar:
```bash
cd remote-server
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

2) Instalar dependencias:
```bash
pip install -r requirements.txt
```

3) Arrancar en `http://127.0.0.1:8080`:
```bash
python server_remote_time_mcp.py
# o con gunicorn:
# gunicorn -b :8080 server_remote_time_mcp:app
```

4) Probar healthchecks:
```bash
curl -i http://127.0.0.1:8080/
curl -i http://127.0.0.1:8080/health
```

5) Probar **JSON-RPC 2.0** (POST a `/`):
```bash
# Celsius → Fahrenheit
curl -i -X POST http://127.0.0.1:8080/   -H "Content-Type: application/json"   -d '{"jsonrpc":"2.0","id":1,"method":"convert_temp","params":{"value":25,"unit":"C"}}'

# Fahrenheit → Celsius
curl -i -X POST http://127.0.0.1:8080/   -H "Content-Type: application/json"   -d '{"jsonrpc":"2.0","id":2,"method":"convert_temp","params":{"value":32,"unit":"F"}}'
```

6) (Opcional) Endpoints “tipo MCP”:
```bash
# Listar herramientas
curl -i http://127.0.0.1:8080/mcp/tools/list

# Llamar herramienta
curl -i -X POST http://127.0.0.1:8080/tools/convert_temp/call   -H "Content-Type: application/json"   -d '{"arguments":{"value":100,"unit":"C"}}'
```

---

## Despliegue en **Google App Engine** (Python 3.11)

**`remote-server/app.yaml` (ejemplo):**
```yaml
runtime: python311
service: default
entrypoint: gunicorn -b :$PORT server_remote_time_mcp:app

env_variables:
  TZ: UTC

automatic_scaling:
  min_instances: 1
  max_instances: 1
```

**`remote-server/requirements.txt`:**
```txt
flask>=3.0.0
gunicorn>=21.2
```

**Desplegar (desde `remote-server/`):**
```bash
gcloud app deploy app.yaml   --project <TU_PROJECT_ID>   --version v-flask-001   --promote   --quiet
```

**Verificar versiones y logs:**
```bash
gcloud app versions list --project <TU_PROJECT_ID>
gcloud app logs read --project <TU_PROJECT_ID> --limit 50 --version v-flask-001
gcloud app logs tail --project <TU_PROJECT_ID> --version v-flask-001
```

**URL típica:**
```
https://<TU_PROJECT_ID>.uc.r.appspot.com
```

**Probar en producción:**
```bash

curl -i "https://<TU_PROJECT_ID>.uc.r.appspot.com/"
curl -i "https://<TU_PROJECT_ID>.uc.r.appspot.com/health"

curl -i -X POST "https://<TU_PROJECT_ID>.uc.r.appspot.com/"   -H "Content-Type: application/json"   -d '{"jsonrpc":"2.0","id":1,"method":"convert_temp","params":{"value":25,"unit":"C"}}'
```

---

## Usar el servidor desde el **chatbot**

1) En la **raíz** del repo (donde está `chatbot.py`), exporta:
```bash
export MCP_REMOTE_URL="https://<TU_PROJECT_ID>.uc.r.appspot.com"
# en local:
# export MCP_REMOTE_URL="http://127.0.0.1:8080"
```

2) Ejecuta el chatbot:
```bash
python chatbot.py
```

3) En el REPL:
```
> temp 100 C
> temp 32 F
> log
> salir
```

> Si tu bot usa `temp_convert`, también sirve: `temp_convert 25 C`.

---

## Troubleshooting

- **503/500:** mira **logs de la versión activa** (`--version v-flask-XXX`) y confirma que el `entrypoint` sea `server_remote_time_mcp:app`.
- **400 Bad Request:** `Content-Type` incorrecto o JSON mal formado.
- **Method not found:** `method` debe ser `"convert_temp"` y `jsonrpc` `"2.0"`.
- **El bot no conecta:** revisa `MCP_REMOTE_URL` y prueba `GET /health` en el server.
- **Cold start:** usa `min_instances: 1` en `app.yaml`.

---

## Nota (opcional)

Para identificar builds en logs, añade en `server_remote_time_mcp.py`:
```python
REV = "flask-remote-temp-mcp-XYZ"
print("### BOOT: USING FLASK SERVER"); print("### REV:", REV)
```
y despliega con `--promote` para ver el `REV` en la versión activa.
