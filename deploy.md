# Deployment Guide — Single-Platform (Render)

Everything runs from one service on Render: FastAPI backend + dashboard + widget.

## Prerequisites
1. Push your code to a GitHub repository.
2. Have your MongoDB Atlas connection string and OpenAI API key ready.

---

## Staging vs. Production Setup

We support separate environments for staging and production:
1. **Staging**: Connects to a staging database (e.g., `chatbot_db_staging`).
2. **Production**: Connects to the main production database (e.g., `chatbot_db_production`).

Each environment can load a custom `.env` file based on the `APP_ENV` environment variable (e.g., `APP_ENV=staging` loads `.env.staging` and `APP_ENV=production` loads `.env.production` from the project root).

---

## Deploy via Render Blueprints (Recommended)

You can automatically spin up staging and production environments using the included Render Blueprints.

### Production Environment
Deploy using [render.yaml](file:///home/pawanm992002/Documents/Schoollog/AI_Chatbot_widget/render.yaml):
1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **Blueprints** → **New Blueprint Instance**.
3. Select your repository.
4. Under **Blueprint Path**, keep it as `render.yaml` (default).
5. Fill in the required environment variables:
   - `MONGODB_URI` — Your MongoDB Atlas connection string.
   - `OPENAI_API_KEY` — Your OpenAI API Key.
   - `FIRECRAWL_API_KEY` — Your Firecrawl API Key.
6. Click **Approve** to deploy.

### Staging Environment
Deploy using [render.staging.yaml](file:///home/pawanm992002/Documents/Schoollog/AI_Chatbot_widget/render.staging.yaml):
1. Go to [Render Dashboard](https://dashboard.render.com).
2. Click **Blueprints** → **New Blueprint Instance**.
3. Select your repository.
4. Under **Blueprint Path**, change it to `render.staging.yaml`.
5. Fill in the required environment variables:
   - `MONGODB_URI` — Your MongoDB Atlas connection string.
   - `OPENAI_API_KEY` — Your OpenAI API Key.
   - `FIRECRAWL_API_KEY` — Your Firecrawl API Key.
6. Click **Approve** to deploy.

---

## Manual Deploy on Render

If you prefer to configure the Web Services manually instead of using blueprints:

1. Click **New +** → **Web Service** → select your repository.
2. Fill in the following details:
   - **Name**: `chatbot-backend-prod` (or `chatbot-backend-staging`)
   - **Root Directory**: `backend`
   - **Environment**: `Python 3`
   - **Build Command**:
     ```bash
     cd .. && npm install -g pnpm && pnpm install --frozen-lockfile && pnpm build && cd backend && uv sync --frozen && uv cache prune --ci
     ```
   - **Start Command**:
     ```
     uv run uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
3. Add environment variables:
   - `APP_ENV` — `production` or `staging`
   - `MONGODB_DB_NAME` — `chatbot_db_production` or `chatbot_db_staging`
   - `MONGODB_URI` — your Atlas connection string
   - `OPENAI_API_KEY` — your OpenAI key
   - `JWT_SECRET` — a secure random secret string
   - `ALLOWED_ORIGINS` — `*` or your custom dashboard domain
   - `COOKIE_SECURE` — `True` (required for HTTPS)
   - `COOKIE_SAMESITE` — `none` (or `lax`)
   - `VITE_API_BASE_URL` — your Render service URL (e.g. `https://chatbot-backend-prod.onrender.com`)

---

## URLs after deployment

| What | URL |
|---|---|
| Dashboard | `https://chatbot-backend-xyz.onrender.com/dashboard/` |
| Widget script | `https://chatbot-backend-xyz.onrender.com/static/widget.js` |
| API docs | `https://chatbot-backend-xyz.onrender.com/docs` |

---

## Rebuilding the Frontend

After pushing changes to GitHub, Render automatically builds and deploys both the frontend and backend together.

---

## Deploy via PM2 (Self-Hosted / VPS)

For deploying on a self-hosted Linux server or VPS using PM2:

1. **Build the frontend assets and sync Python dependencies**:
   ```bash
   pnpm install
   pnpm build
   uv sync
   ```

2. **Configure environment variables**:
   Ensure you have a `.env` or `.env.production` file in your project root with the correct credentials.

3. **Start the application with PM2**:
   ```bash
   pm2 start ecosystem.config.js --env production
   ```

4. **Manage the process**:
   - Check status: `pm2 status`
   - View real-time logs: `pm2 logs ai-chatbot-backend`
   - Restart the app: `pm2 restart ai-chatbot-backend`
   - Stop the app: `pm2 stop ai-chatbot-backend`

