# Desarrollo Local — Helpyy Hand

## Prerequisitos

- Python 3.12+
- Node.js 18+
- AWS CLI con perfil `helpyy` configurado (SSO)

## Setup (primera vez)

```bash
cd /Users/payo/Desktop/BBVA/Helpy
pip install -e ".[dev]"
cd frontend/app-mockup && npm install && cd ../..
```

## Levantar todo

```bash
make dev-local
```

Levanta 4 servicios:

| Servicio | URL |
|----------|-----|
| App móvil (React) | http://localhost:5173 |
| Web widget | http://localhost:3000 |
| API backend | http://localhost:8000/docs |
| ML mock | http://localhost:8001/docs |

Usa **Bedrock Haiku** (AWS) para el LLM y **SQLite** para la base de datos.

## Reiniciar

```bash
lsof -ti:3000 -ti:5173 -ti:8000 -ti:8001 | xargs kill -9; make dev-local
```

## Si la sesión AWS expira

```bash
aws sso login --profile helpyy
```

Luego reinicia el backend.

## Flujo de deploy

```
dev (trabajas aquí)
 → PR a qa (corre tests)
   → PR a main (corre tests, merge = deploy a AWS)
```

## URLs de producción

| Servicio | URL |
|----------|-----|
| App | https://duerut86hk6v3.cloudfront.net |
| Widget | https://dryy62wia55ws.cloudfront.net |
| API | https://zprbmey4sf.us-east-1.awsapprunner.com |
