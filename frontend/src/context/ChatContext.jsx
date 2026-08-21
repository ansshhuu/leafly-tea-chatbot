import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { fetchChatHistory, sendMessage } from '../services/api'

const ChatContext = createContext(null)

const SESSION_ID_KEY = 'cafe.sessionId'
const MESSAGES_KEY = 'cafe.messages'

const WELCOME_QUICK_ACTIONS = ['Explore Tea Collections', 'Wellness Benefits', 'Ask About a Tea', 'Gift Hampers']

const initialMessages = [
  {
    id: 'welcome-1',
    role: 'assistant',
    text: "Hi there! 👋 I'm your Leafly Assistant. How can I help you today?",
    timestamp: new Date().toISOString(),
    quickReplyOptions: WELCOME_QUICK_ACTIONS,
  },
]

function createSessionId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function readSessionStorage(key) {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function writeSessionStorage(key, value) {
  try {
    sessionStorage.setItem(key, value)
  } catch {
  }
}

function loadStoredMessages() {
  const raw = readSessionStorage(MESSAGES_KEY)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) && parsed.length > 0 ? parsed : null
  } catch {
    return null
  }
}

function historyRowToMessage(row) {
  return {
    id: `history-${row.id}`,
    role: row.role,
    text: row.message,
    timestamp: row.created_at,
  }
}

export function ChatProvider({ children }) {
  const [sessionId] = useState(() => readSessionStorage(SESSION_ID_KEY) || createSessionId())
  const [messages, setMessages] = useState(() => loadStoredMessages() || initialMessages)
  const [isTyping, setIsTyping] = useState(false)
  const [language, setLanguage] = useState('en')

  useEffect(() => {
    writeSessionStorage(SESSION_ID_KEY, sessionId)
  }, [sessionId])

  useEffect(() => {
    writeSessionStorage(MESSAGES_KEY, JSON.stringify(messages))
  }, [messages])

  useEffect(() => {
    let cancelled = false

    fetchChatHistory(sessionId)
      .then((rows) => {
        if (cancelled) return
        setMessages((current) => {
          const confirmedCount = current.filter(
            (msg) => msg.id !== 'welcome-1' && (msg.role === 'user' || msg.role === 'assistant')
          ).length
          if (rows.length <= confirmedCount) return current
          return rows.length > 0 ? rows.map(historyRowToMessage) : initialMessages
        })
      })
      .catch(() => {
      })

    return () => {
      cancelled = true
    }
  }, [sessionId])

  const addMessage = useCallback((role, text, extra = {}) => {
    const id = `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`
    setMessages((prev) => [
      ...prev,
      {
        id,
        role,
        text,
        timestamp: new Date().toISOString(),
        ...extra,
      },
    ])
    return id
  }, [])

  const setMessageStatus = useCallback((id, status) => {
    setMessages((prev) => prev.map((msg) => (msg.id === id ? { ...msg, status } : msg)))
  }, [])

  const handleAssistantReply = useCallback(
    (data) => {
      addMessage('assistant', data.reply, {
        timestamp: data.timestamp,
        intent: data.intent,
        sentiment: data.sentiment,
        menuDisplay: data.menu_display || null,
        suggestedItems: data.suggested_items || null,
        quickReplyOptions: data.quick_reply_options || null,
        locationCards: data.location_cards || null,
      })
      if (data.language) setLanguage(data.language)
    },
    [addMessage]
  )

  const sendUserMessage = useCallback(
    async (text) => {
      const trimmed = text.trim()
      if (!trimmed || isTyping) return

      const userMsgId = addMessage('user', trimmed, { status: 'sent' })
      setIsTyping(true)

      try {
        const data = await sendMessage(sessionId, trimmed)
        setMessageStatus(userMsgId, 'delivered')
        handleAssistantReply(data)
      } catch {
        addMessage('system', "Sorry, I couldn't reach the kitchen just now - please try again in a moment.")
      } finally {
        setIsTyping(false)
      }
    },
    [addMessage, handleAssistantReply, isTyping, sessionId, setMessageStatus]
  )

  const value = useMemo(
    () => ({
      sessionId,
      messages,
      isTyping,
      language,
      sendUserMessage,
    }),
    [sessionId, messages, isTyping, language, sendUserMessage]
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

export function useChat() {
  const ctx = useContext(ChatContext)
  if (!ctx) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return ctx
}
