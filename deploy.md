# Deployment Guide

The platform runs as a single FastAPI process that serves the API, the React dashboard SPA, and the widget IIFE bundle. Deployment is automated via GitHub Actions to EC2 with PM2 and Nginx.

## Architecture

```
GitHub Push (master)
  → GitHub Actions CI/CD
    → SSH into EC2
      → git pull, pnpm install, pnpm build, uv sync
      → PM2 startOrReload (uvicorn on port 8000)
        → FastAPI serves:
           /docs              → Swagger UI
           /dashboard/*       → React dashboard SPA (built to apps/dashboard/dist/)
           /static/widget.js  → Chat widget IIFE bundle (built to apps/widget/dist/)
           /ws                → WebSocket for real-time chat
           /api/*             → REST API endpoints
  → Nginx (:80/:443) reverse proxy → 127.0.0.1:8000
```

## Prerequisites

- Node.js 22+ and pnpm
- Python 3.12+ with uv
- MongoDB Atlas cluster
- Redis server
- OpenAI API key
- Firecrawl API key
- EC2 instance (for production) with Nginx and PM2 installed

---

## 1. Environment Setup

Copy the environment template and fill in your credentials:

```bash
cp .env.production.example .env
```

### Required Variables

```bash
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
OPENAI_API_KEY=sk-proj-...
FIRECRAWL_API_KEY=fc-...
JWT_SECRET=your-secure-random-secret
REDIS_URI=redis://localhost:6379/0
```

### CORS & Auth

```bash
ALLOWED_ORIGINS=https://your-domain.com
COOKIE_SECURE=True       # True for HTTPS
COOKIE_SAMESITE=none     # none for cross-origin, lax for same-origin
ENFORCE_DOMAIN=False
```

### Dashboard Build Config

```bash
VITE_API_BASE_URL=https://your-api-domain.com
```

This is baked into the dashboard at build time. On localhost, the Vite proxy handles routing to `:8000`.

### Optional

```bash
APP_ENV=production
MAX_CRAWL_PAGES=100
PUBLIC_URL=
ADMIN_USERNAME=admin      # Default: admin
ADMIN_PASSWORD=admin123   # Default: admin123
```

### Env File Loading Priority

The backend loads the first file it finds (in order):
1. `.env.production`
2. `.env.staging`
3. `.env`

---

## 2. Deploy via GitHub Actions (EC2) — Primary

Pushing to `master` triggers the CI/CD pipeline automatically.

### GitHub Actions Workflow (`.github/workflows/deploy.yml`)

**GitHub side:**
1. Checkout code
2. Setup Node.js 22 + pnpm 9
3. `pnpm install --frozen-lockfile`
4. `pnpm test --if-present`
5. `pnpm build` (builds dashboard + widget)
6. SSH into EC2 and run deployment script

**EC2 side:**
1. Load NVM and pnpm from PATH
2. `git pull origin master`
3. `pnpm install --frozen-lockfile`
4. `pnpm build`
5. `uv sync --frozen`
6. `pm2 startOrReload ecosystem.config.js --only ai-chatbot-backend --env production`

### Required GitHub Secrets

| Secret | Description |
|---|---|
| `EC2_HOST` | EC2 instance IP or hostname |
| `EC2_USER` | SSH username (e.g., `ubuntu`, `ec2-user`) |
| `EC2_SSH_KEY` | Private SSH key |
| `EC2_SSH_PASSPHRASE` | SSH key passphrase (if any) |
| `APP_PATH` | Absolute path to project on EC2 (e.g., `/home/ubuntu/AI_CHATBOT`) |

### Manual Deploy (without CI)

SSH into your EC2 instance and run:

```bash
cd /path/to/project
git pull origin master
pnpm install --frozen-lockfile
pnpm build
uv sync --frozen
pm2 startOrReload ecosystem.config.js --only ai-chatbot-backend --env production
```

---

## 3. PM2 Configuration (`ecosystem.config.js`)

Only one app runs in production:

| App Name | Command | Purpose |
|---|---|---|
| `ai-chatbot-backend` | `.venv/bin/uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000` | FastAPI backend + static assets |

Two optional dev-mode apps exist but are **not used in production**:
- `ai-chatbot-dashboard-dev` — Dashboard Vite dev server
- `ai-chatbot-widget-dev` — Widget Vite dev server

### PM2 Commands

```bash
pm2 status                          # Check process status
pm2 logs ai-chatbot-backend         # View real-time logs
pm2 restart ai-chatbot-backend      # Restart the app
pm2 stop ai-chatbot-backend         # Stop the app
pm2 startOrReload ecosystem.config.js --only ai-chatbot-backend --env production  # Deploy
```

### Production Settings

- `autorestart: true` — Auto-restart on crash
- `max_memory_restart: "1G"` — Restart if memory exceeds 1 GB
- `interpreter: "none"` — Runs uvicorn directly from `.venv/bin/uvicorn`

---

## 4. Nginx Reverse Proxy (`nginx.conf`)

Nginx sits in front of uvicorn, handling SSL termination, gzip, and WebSocket upgrades.

### Key Settings

- **Upstream**: `127.0.0.1:8000` with 64 keepalive connections
- **SSL**: Let's Encrypt certificates (auto-renewed via Certbot)
- **Client max body size**: 100 MB (for PDF uploads)
- **Gzip**: Enabled at level 6 for text, CSS, JSON, JS, XML, SVG
- **WebSocket**: `Upgrade` and `Connection` headers set for `/ws` routes
- **Timeouts**: `proxy_connect_timeout: 30s`, `proxy_send_timeout: 300s`, `proxy_read_timeout: 300s`

### Static File Serving

FastAPI serves all static assets directly — Nginx just proxies everything to `:8000`:

| Path | Served From |
|---|---|
| `/static/widget.js` | `apps/widget/dist/widget.js` (IIFE bundle) |
| `/dashboard/assets/*` | `apps/dashboard/dist/assets/` |
| `/dashboard/*` | `apps/dashboard/dist/index.html` (SPA catch-all) |
| `/` | Redirects to `/dashboard/` |

### Nginx Setup (Fresh EC2)

```bash
# Install Nginx + Certbot
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx

# Copy nginx.conf
sudo cp nginx.conf /etc/nginx/sites-available/chatbot
sudo ln -sf /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Reload
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Frontend Build

### Dashboard (`apps/dashboard/`)

- **Output**: `apps/dashboard/dist/` (SPA with `base: '/dashboard/'`)
- **Dev server**: Port 3000 with proxy to `:8000`
- **Build**: `pnpm build:dashboard` or `pnpm build`

### Widget (`apps/widget/`)

- **Output**: `apps/widget/dist/widget.js` (single IIFE bundle, CSS injected inline)
- **Build**: `pnpm build:widget` or `pnpm build`

### Build Commands

```bash
pnpm build              # Build both dashboard + widget
pnpm build:dashboard    # Dashboard only
pnpm build:widget       # Widget only
```

---

## 6. URLs After Deployment

| What | URL |
|---|---|
| Dashboard | `https://your-domain.com/dashboard/` |
| Widget script | `https://your-domain.com/static/widget.js` |
| API docs | `https://your-domain.com/docs` |
| WebSocket | `wss://your-domain.com/ws/chat?key_hash=...` |

---

## 7. Deploy via Render (Alternative)

If deploying on Render instead of EC2:

### Manual Web Service Setup

1. Click **New +** → **Web Service** → select your repository
2. Configure:
   - **Name**: `chatbot-backend`
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**:
     ```bash
     cd .. && npm install -g pnpm && pnpm install --frozen-lockfile && pnpm build && cd backend && uv sync --frozen && uv cache prune --ci
     ```
   - **Start Command**:
     ```bash
     uv run uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
3. Add environment variables (same as Section 1 above)

### Render Environment Variables

| Variable | Value |
|---|---|
| `APP_ENV` | `production` or `staging` |
| `MONGODB_DB_NAME` | `chatbot_db_production` or `chatbot_db_staging` |
| `MONGODB_URI` | Your Atlas connection string |
| `OPENAI_API_KEY` | Your OpenAI key |
| `FIRECRAWL_API_KEY` | Your Firecrawl key |
| `JWT_SECRET` | Secure random string |
| `ALLOWED_ORIGINS` | `*` or your dashboard domain |
| `COOKIE_SECURE` | `True` (required for HTTPS) |
| `COOKIE_SAMESITE` | `none` or `lax` |
| `VITE_API_BASE_URL` | Your Render service URL |

### Render URLs

| What | URL |
|---|---|
| Dashboard | `https://your-service.onrender.com/dashboard/` |
| Widget script | `https://your-service.onrender.com/static/widget.js` |
| API docs | `https://your-service.onrender.com/docs` |

---

## 8. Testing Locally

### Quick Test

```bash
# Terminal 1 — Backend
pnpm dev:backend

# Terminal 2 — Widget dev server
pnpm dev:widget

# Terminal 3 — Open test page
open backend/templates/test_page.html
```

### Full Stack

```bash
pnpm dev  # Runs backend :8000, dashboard :3000, widget :5174 concurrently
```

Open `http://localhost:3000/dashboard/` for the dashboard.
Open `backend/templates/test_page.html` to test the embedded widget.

### Production Simulation

```bash
pnpm build
pnpm start  # Builds + runs uvicorn on port 8000
```

Then open `http://localhost:8000/dashboard/` or `http://localhost:8000/docs`.

---

## 9. MongoDB Indexes

The backend creates 20 indexes on startup automatically. You only need to set up the Atlas Search indexes manually:

### Vector Search Index (`vector_index`)

- **Database**: `chatbot_db`, **Collection**: `chunks`
- **Index Name**: `vector_index`

```json
{
  "fields": [
    { "type": "vector", "path": "embedding", "numDimensions": 1536, "similarity": "cosine" },
    { "type": "filter", "path": "tenant_id" },
    { "type": "filter", "path": "url" }
  ]
}
```

### Full-Text Search Index (`default`)

- **Database**: `chatbot_db`, **Collection**: `chunks`
- **Index Name**: `default`

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "text": { "type": "string" },
      "section_title": { "type": "string" },
      "tenant_id": { "type": "string" }
    }
  }
}
```

---

## 10. Troubleshooting

### Widget not loading

- Check that `apps/widget/dist/widget.js` exists after `pnpm build`
- Verify `/static/widget.js` returns the IIFE bundle
- Check browser console for CORS errors — ensure `ALLOWED_ORIGINS` includes your domain

### Dashboard shows blank page

- Check that `apps/dashboard/dist/index.html` exists after `pnpm build`
- Verify `VITE_API_BASE_URL` is correct (baked in at build time)
- Check browser network tab for failed API calls

### WebSocket connection fails

- Ensure Nginx has WebSocket headers: `proxy_set_header Upgrade $http_upgrade` and `proxy_set_header Connection "upgrade"`
- Check that `proxy_read_timeout` is high enough (300s recommended)

### PDF upload fails

- Check Nginx `client_max_body_size` (default 100M in the provided config)
- Verify `backend/uploads/` directory exists and is writable

### PM2 process keeps restarting

- Check logs: `pm2 logs ai-chatbot-backend`
- Common causes: missing `.env` file, invalid `MONGODB_URI`, port 8000 already in use
