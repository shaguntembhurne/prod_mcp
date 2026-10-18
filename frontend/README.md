# MIT University AI — Frontend

A minimal, aesthetic React frontend inspired by ChatGPT for the MIT University AI application.

---

## Tech Stack
- **React 19 + Vite**
- **Tailwind CSS v4**
- **Simple JWT + OTP authentication**
- **Django REST Framework + data.gov.in MCP Integration**

---

## Setup & Running

```bash
# 1. Enter the frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Configure environment
cp .env.example .env
# Default points to http://127.0.0.1:8001

# 4. Start the development server
npm run dev
```

Visit `http://localhost:5173` in your browser.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `VITE_API_URL` | Base URL of the Django backend | `http://127.0.0.1:8001` |

> In development, requests can connect directly to `VITE_API_URL` (CORS configured in Django) or be proxied via Vite dev server.

---

## Project Structure

- `src/api.js` — Single module for all backend API communication (token management, auto-refresh on 401, error handling, OTP endpoints, and the connected DRF chat endpoint).
- `src/AuthContext.jsx` — Minimal global auth state management.
- `src/LoginPage.jsx` — Two-step OTP login screen with `@mituniversity.edu.in` validation and 60-second resend cooldown timer.
- `src/ChatPage.jsx` — Minimalist ChatGPT-style conversation interface with message bubbles, keyboard shortcuts, typing indicator, error banner with retry, and responsive input bar.
- `src/App.jsx` — Root router switching between Login and Chat based on authenticated state.

---

## Backend Endpoints Used

- `POST /api/auth/otp/request/` — Request a 6-digit OTP to a `@mituniversity.edu.in` address
- `POST /api/auth/otp/verify/` — Verify OTP and receive JWT access & refresh tokens
- `POST /api/auth/token/refresh/` — Rotate refresh token and obtain a new access token
- `POST /api/auth/logout/` — Blacklist current refresh token
- `GET /api/auth/me/` — Retrieve authenticated user profile
- `POST /api/chat/` — Submit user prompts to the data.gov.in MCP orchestrator
