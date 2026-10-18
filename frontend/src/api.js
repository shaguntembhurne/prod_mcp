/**
 * api.js — all backend communication in one place.
 *
 * Configured via VITE_API_URL (defaults to http://127.0.0.1:8001).
 * In development, requests can either use VITE_API_URL directly (enabled by
 * Django CORS headers) or fall back to the Vite dev proxy.
 *
 * JWT tokens are stored in localStorage under "access" and "refresh".
 * The fetch wrapper automatically refreshes an expired access token once before failing.
 */

const rawUrl = import.meta.env.VITE_API_URL || ''
const BASE_URL = rawUrl ? rawUrl.replace(/\/$/, '') : ''

// ---------------------------------------------------------------------------
// Token helpers
// ---------------------------------------------------------------------------

export const tokens = {
  get access() { return localStorage.getItem('access') },
  get refresh() { return localStorage.getItem('refresh') },
  set(access, refresh) {
    localStorage.setItem('access', access)
    if (refresh) localStorage.setItem('refresh', refresh)
  },
  clear() {
    localStorage.removeItem('access')
    localStorage.removeItem('refresh')
  },
}

// ---------------------------------------------------------------------------
// Low-level fetch with automatic token refresh
// ---------------------------------------------------------------------------

async function request(path, options = {}, retry = true) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }

  // Attach access token unless explicitly skipped (e.g. during token refresh)
  if (tokens.access && !options.skipAuth) {
    headers['Authorization'] = `Bearer ${tokens.access}`
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })

  // If the access token expired, refresh it once and retry.
  if (res.status === 401 && retry && tokens.refresh) {
    const refreshed = await refreshAccessToken()
    if (refreshed) {
      return request(path, options, false)
    }
    // Refresh also failed — clear tokens so the app redirects to login.
    tokens.clear()
    throw new AuthError('Session expired. Please log in again.')
  }

  if (!res.ok) {
    let detail = `Request failed: ${res.status}`
    try {
      const body = await res.json()
      detail = body.error ?? body.detail ?? body.message?.[0] ?? body.email?.[0] ?? body.otp?.[0] ?? detail
    } catch (_) { /* ignore */ }
    throw new ApiError(detail, res.status)
  }

  // 204 No Content
  if (res.status === 204) return null
  return res.json()
}

// ---------------------------------------------------------------------------
// Error types
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class AuthError extends Error {
  constructor(message) {
    super(message)
    this.name = 'AuthError'
  }
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

/** Send OTP to an @mituniversity.edu.in email address. */
export async function requestOtp(email) {
  return request('/api/auth/otp/request/', {
    method: 'POST',
    body: { email },
    skipAuth: true,
  })
}

/** Verify OTP — returns { access, refresh, created }. */
export async function verifyOtp(email, otp) {
  const data = await request('/api/auth/otp/verify/', {
    method: 'POST',
    body: { email, otp },
    skipAuth: true,
  })
  tokens.set(data.access, data.refresh)
  return data
}

/** Exchange refresh token for a new access token. */
export async function refreshAccessToken() {
  if (!tokens.refresh) return false
  try {
    const data = await request('/api/auth/token/refresh/', {
      method: 'POST',
      body: { refresh: tokens.refresh },
      skipAuth: true,
    }, false)
    tokens.set(data.access, data.refresh)
    return true
  } catch (_) {
    return false
  }
}

/** Blacklist the refresh token and clear local storage. */
export async function logout() {
  try {
    await request('/api/auth/logout/', {
      method: 'POST',
      body: { refresh: tokens.refresh },
    }, false)
  } finally {
    tokens.clear()
  }
}

/** Fetch the current user's profile. */
export async function getMe() {
  return request('/api/auth/me/')
}

// ---------------------------------------------------------------------------
// Chat API
// ---------------------------------------------------------------------------

/**
 * Send a user prompt to the DRF chat endpoint (POST /api/chat/).
 *
 * Backend expects: { "message": string }
 * Backend returns: { "allowed": bool, "answer": string, "reason": string, "tool_calls": [...] }
 *
 * Accepts either:
 * - A string message
 * - An array of conversation messages (extracts the latest user message)
 */
export async function sendPrompt(input) {
  let messageText = ''
  if (typeof input === 'string') {
    messageText = input
  } else if (Array.isArray(input)) {
    const lastUserMsg = [...input].reverse().find(m => m.role === 'user')
    messageText = lastUserMsg ? lastUserMsg.content : ''
  } else if (input && typeof input === 'object') {
    messageText = input.message || input.content || ''
  }

  messageText = messageText.trim()
  if (!messageText) {
    throw new ApiError('Message cannot be empty.', 400)
  }

  const data = await request('/api/chat/', {
    method: 'POST',
    body: { message: messageText },
  })

  return {
    reply: data.answer || '',
    allowed: data.allowed,
    reason: data.reason,
    tool_calls: data.tool_calls || [],
    ...data,
  }
}
