const path = require('path');

module.exports = {
  apps: [
    // 1. Backend API Server (Serves the API and also serves the built dashboard/widget assets in production)
    {
      name: "ai-chatbot-backend",
      script: path.join(__dirname, ".venv/bin/uvicorn"),
      args: "main:app --app-dir backend --host 0.0.0.0 --port 8000",
      cwd: __dirname,
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production",
        PYTHONUNBUFFERED: "1",
        PORT: "8000"
      },
      env_production: {
        NODE_ENV: "production"
      }
    },

    // 2. Dashboard Dev Server (Optional, only for local development using PM2)
    {
      name: "ai-chatbot-dashboard-dev",
      script: "pnpm",
      args: "--filter dashboard dev",
      cwd: __dirname,
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development"
      }
    },

    // 3. Widget Dev Server (Optional, only for local development using PM2)
    {
      name: "ai-chatbot-widget-dev",
      script: "pnpm",
      args: "--filter widget dev",
      cwd: __dirname,
      autorestart: true,
      watch: false,
      env: {
        NODE_ENV: "development"
      }
    }
  ]
};
