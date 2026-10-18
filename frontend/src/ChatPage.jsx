/**
 * ChatPage — minimal AI prompt interface.
 *
 * Connected to Django REST Framework POST /api/chat/ endpoint.
 * Handles grounded assistant replies, tool traces, error notifications,
 * and retry capabilities.
 */

import { useEffect, useRef, useState } from 'react'
import { sendPrompt } from './api'
import { useAuth } from './AuthContext'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function Message({ role, content }) {
  const isUser = role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`
          max-w-[80%] md:max-w-[65%] px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
          ${isUser
            ? 'bg-gray-900 text-white rounded-br-sm'
            : 'bg-gray-100 text-gray-800 rounded-bl-sm'}
        `}
      >
        {content}
      </div>
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-4 py-3">
        <span className="flex gap-1 items-center h-4">
          {[0, 1, 2].map(i => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce"
              style={{ animationDelay: `${i * 120}ms` }}
            />
          ))}
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ChatPage() {
  const { user, logout } = useAuth()

  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [thinking, setThinking]   = useState(false)
  const [error, setError]         = useState('')
  const [lastFailedMessage, setLastFailedMessage] = useState(null)

  const bottomRef    = useRef(null)
  const textareaRef  = useRef(null)

  // Scroll to the bottom whenever messages change.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, thinking])

  // Auto-grow the textarea.
  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`
  }, [input])

  // ---------------------------------------------------------------------------
  // Send message & Retry
  // ---------------------------------------------------------------------------

  async function executePrompt(promptText, currentMessages) {
    setError('')
    setThinking(true)
    setLastFailedMessage(null)

    try {
      const { reply } = await sendPrompt(currentMessages)
      setMessages(prev => [...prev, { role: 'assistant', content: reply }])
    } catch (err) {
      setError(err.message || 'An error occurred while communicating with the chat service.')
      setLastFailedMessage(promptText)
    } finally {
      setThinking(false)
    }
  }

  async function handleSend(e) {
    e?.preventDefault()
    const text = input.trim()
    if (!text || thinking) return

    const userMessage = { role: 'user', content: text }
    const updated = [...messages, userMessage]

    setMessages(updated)
    setInput('')
    await executePrompt(text, updated)
  }

  async function handleRetry() {
    if (!lastFailedMessage || thinking) return
    await executePrompt(lastFailedMessage, messages)
  }

  function handleKeyDown(e) {
    // Submit on Enter (without Shift).
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  async function handleLogout() {
    try { await logout() } catch (_) { /* ignore */ }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const isEmpty = messages.length === 0

  return (
    <div className="flex flex-col h-screen bg-white">

      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-gray-900 flex items-center justify-center">
            <svg className="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor"
                 strokeWidth="2.5" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-gray-900 tracking-tight">MIT University AI</span>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden sm:block text-xs text-gray-400 truncate max-w-[180px]">
            {user?.email}
          </span>
          <button
            id="logout-btn"
            onClick={handleLogout}
            className="text-xs text-gray-400 hover:text-gray-700 transition-colors px-2 py-1
                       rounded-md hover:bg-gray-50"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Conversation area */}
      <main className="flex-1 overflow-y-auto">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <p className="text-2xl font-light text-gray-800 tracking-tight">
              What can I help with?
            </p>
            <p className="mt-2 text-sm text-gray-400 max-w-xs">
              Ask questions to find, retrieve, inspect, and analyze Indian government datasets via data.gov.in.
            </p>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto px-4 py-6 flex flex-col gap-4">
            {messages.map((msg, i) => (
              <Message key={i} role={msg.role} content={msg.content} />
            ))}
            {thinking && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </main>

      {/* Error banner */}
      {error && (
        <div className="max-w-2xl mx-auto w-full px-4">
          <div className="flex items-center justify-between gap-3 bg-red-50 border border-red-100
                          rounded-xl px-4 py-3 text-xs text-red-600 mb-2">
            <span className="flex-1">{error}</span>
            <div className="flex items-center gap-2 shrink-0">
              {lastFailedMessage && (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={thinking}
                  className="font-medium underline hover:text-red-800 disabled:opacity-50 transition-colors"
                >
                  Retry
                </button>
              )}
              <button
                type="button"
                onClick={() => setError('')}
                className="hover:text-red-900 ml-1"
                aria-label="Dismiss error"
              >
                ✕
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="border-t border-gray-100 px-4 pt-3 pb-5 md:pb-6">
        <form
          onSubmit={handleSend}
          className="max-w-2xl mx-auto flex items-end gap-2"
        >
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              id="prompt-input"
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message MIT University AI…"
              disabled={thinking}
              className="w-full resize-none px-4 py-3 pr-12 text-sm rounded-2xl
                         border border-gray-200 bg-gray-50 focus:bg-white focus:border-gray-300
                         focus:outline-none transition-colors placeholder:text-gray-300
                         disabled:opacity-50 leading-relaxed"
            />
          </div>
          <button
            type="submit"
            id="send-btn"
            disabled={!input.trim() || thinking}
            className="shrink-0 w-10 h-10 rounded-xl bg-gray-900 text-white
                       flex items-center justify-center
                       hover:bg-gray-700 active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed
                       transition-all"
            aria-label="Send message"
          >
            <svg className="w-4 h-4 rotate-90" fill="none" stroke="currentColor"
                 strokeWidth="2" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round"
                    d="M12 19V5m-7 7 7-7 7 7" />
            </svg>
          </button>
        </form>
        <p className="text-center text-[11px] text-gray-300 mt-2">
          Press Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  )
}
