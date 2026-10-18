/**
 * AuthContext — minimal global auth state.
 *
 * Provides: user (profile object or null), loading (bool), login, logout.
 * Consumed by App.jsx to decide which page to render.
 */

import { createContext, useContext, useEffect, useState } from 'react'
import { getMe, logout as apiLogout, tokens } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser]       = useState(null)
  const [loading, setLoading] = useState(true)

  // On mount, try to restore session from stored tokens.
  useEffect(() => {
    if (!tokens.access) {
      setLoading(false)
      return
    }
    getMe()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [])

  function login(userData) {
    setUser(userData)
  }

  async function logout() {
    await apiLogout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
