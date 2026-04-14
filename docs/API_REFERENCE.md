# API Reference

## Endpoints

### Chat
- `POST /api/v1/chat` — Send a message through the orchestrator
- `WebSocket /api/v1/ws/chat/{session_id}` — Real-time streaming chat

### Onboarding
- `POST /api/v1/onboard` — Start/continue bancarization flow

### Scoring
- `POST /api/v1/score` — Query ML credit scoring

### Notifications
- `GET /api/v1/notifications/{user_id}` — Get user notifications
- `POST /api/v1/monitor/run` — Trigger monitoring cycle (testing)

### Health
- `GET /health` — API health check

<!-- TODO: auto-generate from FastAPI OpenAPI schema -->
