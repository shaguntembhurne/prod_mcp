/**
 * App.jsx — root component with authentication routing.
 *
 * Shows a minimal loading state while restoring session,
 * then renders ChatPage for authenticated users or LoginPage.
 */

import { AuthProvider, useAuth } from './AuthContext'
import LoginPage from './LoginPage'
import ChatPage from './ChatPage'

function AppContent() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gray-900 flex items-center justify-center animate-pulse">
            <svg
              className="w-4 h-4 text-white"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </div>
          <span className="text-xs text-gray-400 font-medium">Loading…</span>
        </div>
      </div>
    )
  }

  return user ? <ChatPage /> : <LoginPage />
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  )
}
