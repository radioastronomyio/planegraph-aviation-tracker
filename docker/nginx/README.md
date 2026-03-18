# nginx

nginx reverse proxy configuration is implemented in WU-07.

Planned routing:
- `/`          → frontend/dist/ (SPA)
- `/api/`      → FastAPI (uvicorn)
- `/api/v1/live` → WebSocket proxy
- `/tiles/`    → PMTiles directory (range request support)
- `/tar1090/`  → ultrafeeder validation UI
