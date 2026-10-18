# MIT University Auth Backend

A minimal Django REST Framework backend providing email OTP authentication with JWT tokens.

---

## What it does

- Sends a 6-digit OTP to a `@mituniversity.edu.in` email address.
- Verifies the OTP and issues JWT access + refresh tokens.
- Supports token refresh, logout (blacklist), and a protected profile endpoint.

---

## Setup

```bash
# 1. Clone and enter the project directory
git clone <repo-url>
cd <project-dir>

# 2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and your SMTP credentials.
```

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (long random string) |
| `DEBUG` | — | `True` for development, `False` for production (default: `False`) |
| `ALLOWED_HOSTS` | — | Comma-separated hostnames (default: `127.0.0.1,localhost`) |
| `DATABASE_URL` | — | Leave blank for SQLite; set `postgres://user:pass@host:5432/db` for PostgreSQL |
| `EMAIL_HOST` | ✅ | SMTP server hostname |
| `EMAIL_PORT` | — | SMTP port (default: `587`) |
| `EMAIL_USE_TLS` | — | `True` / `False` (default: `True`) |
| `EMAIL_HOST_USER` | ✅ | SMTP username / sender address |
| `EMAIL_HOST_PASSWORD` | ✅ | SMTP password |
| `DEFAULT_FROM_EMAIL` | — | "From" address in OTP emails |

> In development, if `EMAIL_HOST_USER` is blank, emails are printed to the console instead of being sent.

---

## Migrations and startup

```bash
python manage.py migrate
python manage.py runserver
```

---

## API endpoints

### `POST /api/auth/otp/request/`
Request a 6-digit OTP sent to your email.

```json
{ "email": "student@mituniversity.edu.in" }
```

### `POST /api/auth/otp/verify/`
Verify the OTP. Returns JWT tokens. Creates the user account on first login.

```json
{ "email": "student@mituniversity.edu.in", "otp": "123456" }
```

Response:
```json
{ "access": "<jwt>", "refresh": "<jwt>", "created": true }
```

### `POST /api/auth/token/refresh/`
Exchange a refresh token for a new access token (refresh token is rotated).

```json
{ "refresh": "<refresh-token>" }
```

### `POST /api/auth/logout/`
Blacklist the refresh token. Requires `Authorization: Bearer <access-token>`.

```json
{ "refresh": "<refresh-token>" }
```

### `GET /api/auth/me/`
Return the authenticated user's profile. Requires `Authorization: Bearer <access-token>`.

---

## How authentication works

1. Call `/api/auth/otp/request/` with your `@mituniversity.edu.in` email.
2. Check your email for a 6-digit code (valid for 5 minutes, single use).
3. Call `/api/auth/otp/verify/` with the email and code to receive tokens.
4. Include `Authorization: Bearer <access-token>` in requests to protected endpoints.
5. When the access token expires (15 min), call `/api/auth/token/refresh/` with the refresh token.
6. On logout, call `/api/auth/logout/` to blacklist the refresh token.

---

## Running tests

```bash
python manage.py test authentication
```
