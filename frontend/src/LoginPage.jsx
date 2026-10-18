/**
 * LoginPage — two-step OTP authentication.
 *
 * Step 1: enter @mituniversity.edu.in email → request OTP
 * Step 2: enter the 6-digit code → verify → receive JWT tokens
 */

import { useState } from 'react'
import { requestOtp, verifyOtp, getMe } from './api'
import { useAuth } from './AuthContext'

const DOMAIN = '@mituniversity.edu.in'

export default function LoginPage() {
  const { login } = useAuth()

  const [email, setEmail]         = useState('')
  const [otp, setOtp]             = useState('')
  const [step, setStep]           = useState('email')   // 'email' | 'otp'
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState('')
  const [resendTimer, setResendTimer] = useState(0)

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function startResendTimer() {
    setResendTimer(60)
    const interval = setInterval(() => {
      setResendTimer(t => {
        if (t <= 1) { clearInterval(interval); return 0 }
        return t - 1
      })
    }, 1000)
  }

  function validateEmail(value) {
    const val = value.toLowerCase().trim()
    const domain = val.split('@')[1] || ''
    if (!domain || (domain !== 'mituniversity.edu.in' && !domain.endsWith('.mituniversity.edu.in'))) {
      return 'Only @mituniversity.edu.in addresses (e.g. @students.mituniversity.edu.in) are accepted.'
    }
    return ''
  }

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  async function handleRequestOtp(e) {
    e.preventDefault()
    const err = validateEmail(email.trim())
    if (err) { setError(err); return }

    setError('')
    setLoading(true)
    try {
      await requestOtp(email.trim().toLowerCase())
      setStep('otp')
      startResendTimer()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    if (resendTimer > 0) return
    setError('')
    setLoading(true)
    try {
      await requestOtp(email.trim().toLowerCase())
      startResendTimer()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleVerifyOtp(e) {
    e.preventDefault()
    if (otp.length !== 6) { setError('Enter the 6-digit code from your email.'); return }

    setError('')
    setLoading(true)
    try {
      await verifyOtp(email.trim().toLowerCase(), otp.trim())
      const profile = await getMe()
      login(profile)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="min-h-screen flex items-center justify-center bg-white px-4">
      <div className="w-full max-w-sm">

        {/* Logo / heading */}
        <div className="mb-10 text-center">
          <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-gray-900 mb-5">
            <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" strokeWidth="2"
                 viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                    d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-900 tracking-tight">MIT University AI</h1>
          <p className="mt-1.5 text-sm text-gray-400">
            {step === 'email'
              ? 'Sign in with your university email'
              : `We sent a code to ${email}`}
          </p>
        </div>

        {/* Email step */}
        {step === 'email' && (
          <form onSubmit={handleRequestOtp} noValidate>
            <label className="block text-sm font-medium text-gray-700 mb-1.5" htmlFor="email-input">
              Email address
            </label>
            <input
              id="email-input"
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={e => { setEmail(e.target.value); setError('') }}
              placeholder="you@students.mituniversity.edu.in"
              className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-gray-200
                         bg-gray-50 focus:bg-white focus:border-gray-400 focus:outline-none
                         transition-colors placeholder:text-gray-300"
            />
            {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
            <button
              type="submit"
              disabled={loading || !email}
              id="send-otp-btn"
              className="mt-4 w-full py-2.5 rounded-lg bg-gray-900 text-white text-sm font-medium
                         hover:bg-gray-700 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-all"
            >
              {loading ? 'Sending…' : 'Continue'}
            </button>
          </form>
        )}

        {/* OTP step */}
        {step === 'otp' && (
          <form onSubmit={handleVerifyOtp} noValidate>
            <label className="block text-sm font-medium text-gray-700 mb-1.5" htmlFor="otp-input">
              One-time code
            </label>
            <input
              id="otp-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              autoFocus
              maxLength={6}
              value={otp}
              onChange={e => { setOtp(e.target.value.replace(/\D/g, '')); setError('') }}
              placeholder="123456"
              className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-gray-200
                         bg-gray-50 focus:bg-white focus:border-gray-400 focus:outline-none
                         transition-colors tracking-[0.3em] font-mono placeholder:tracking-normal
                         placeholder:font-sans placeholder:text-gray-300"
            />
            {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
            <button
              type="submit"
              disabled={loading || otp.length !== 6}
              id="verify-otp-btn"
              className="mt-4 w-full py-2.5 rounded-lg bg-gray-900 text-white text-sm font-medium
                         hover:bg-gray-700 active:scale-[0.98] disabled:opacity-40 disabled:cursor-not-allowed
                         transition-all"
            >
              {loading ? 'Verifying…' : 'Sign in'}
            </button>

            {/* Resend + back */}
            <div className="mt-4 flex items-center justify-between text-xs text-gray-400">
              <button
                type="button"
                onClick={() => { setStep('email'); setOtp(''); setError('') }}
                className="hover:text-gray-700 transition-colors"
              >
                ← Change email
              </button>
              <button
                type="button"
                onClick={handleResend}
                disabled={resendTimer > 0 || loading}
                className="hover:text-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {resendTimer > 0 ? `Resend in ${resendTimer}s` : 'Resend code'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
