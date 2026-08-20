import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { fetchChatHistory, fetchWelcome, sendCartReminder, sendImageMessage, sendMessage } from '../services/api'
import { getUserCoordinates } from '../services/geolocation'

const ChatContext = createContext(null)

const SESSION_ID_KEY = 'cafe.sessionId'
const MESSAGES_KEY = 'cafe.messages'

const CART_ABANDON_DELAY_MS = 3 * 60 * 1000

const WELCOME_QUICK_ACTIONS = ['View Menu', 'Café Location', 'Book a Table', 'Events & Offers']

const initialMessages = [
  {
    id: 'welcome-1',
    role: 'assistant',
    text: "Hi there! 👋 Welcome to Rasa Café. I'm Rumi - how can I help you today?",
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
  const isFreshSessionRef = useRef(loadStoredMessages() === null)
  const [messages, setMessages] = useState(() => loadStoredMessages() || initialMessages)
  const [isTyping, setIsTyping] = useState(false)
  const [language, setLanguage] = useState('en')

  const abandonTimerRef = useRef(null)
  const cartHasItemsRef = useRef(false)
  const cartReminderFiredRef = useRef(false)

  const clearAbandonTimer = useCallback(() => {
    if (abandonTimerRef.current) {
      clearTimeout(abandonTimerRef.current)
      abandonTimerRef.current = null
    }
  }, [])

  const scheduleAbandonTimer = useCallback(() => {
    clearAbandonTimer()
    if (!cartHasItemsRef.current || cartReminderFiredRef.current) return
    abandonTimerRef.current = setTimeout(() => {
      cartReminderFiredRef.current = true
      sendCartReminder(sessionId).catch(() => {
      })
    }, CART_ABANDON_DELAY_MS)
  }, [clearAbandonTimer, sessionId])

  useEffect(() => clearAbandonTimer, [clearAbandonTimer])

  useEffect(() => {
    writeSessionStorage(SESSION_ID_KEY, sessionId)
  }, [sessionId])

  useEffect(() => {
    writeSessionStorage(MESSAGES_KEY, JSON.stringify(messages))
  }, [messages])

  useEffect(() => {
    if (!isFreshSessionRef.current) return
    let cancelled = false

    // Geolocation permission is requested here, but never blocks chat load -
    // getUserCoordinates always resolves (never rejects) within its own
    // timeout, falling back to null (cafe-location weather) on denial,
    // unavailability, or timeout.
    getUserCoordinates()
      .then((coords) => (cancelled ? null : fetchWelcome(coords)))
      .then((data) => {
        if (!data) return
        if (cancelled || !data.reply) return
        setMessages((current) =>
          current.map((msg) =>
            msg.id === 'welcome-1'
              ? { ...msg, text: data.reply, quickReplyOptions: data.quick_reply_options || msg.quickReplyOptions }
              : msg
          )
        )
      })
      .catch(() => {
      })

    return () => {
      cancelled = true
    }
  }, [])

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
        orderSummary: data.order_summary || null,
        quickReplyOptions: data.quick_reply_options || null,
        datePickerOptions: data.date_picker_options || null,
        paymentRequest: data.payment_request || null,
        loyaltyCard: data.loyalty_card || null,
        locationCards: data.location_cards || null,
        awaitingAddressInput: data.awaiting_address_input || false,
      })
      if (data.language) setLanguage(data.language)

      if (data.order_summary) {
        if (data.order_summary.status === 'confirmed') {
          cartHasItemsRef.current = false
          cartReminderFiredRef.current = false
          clearAbandonTimer()
        } else {
          cartHasItemsRef.current = (data.order_summary.items || []).length > 0
          scheduleAbandonTimer()
        }
      }
    },
    [addMessage, clearAbandonTimer, scheduleAbandonTimer]
  )

  const sendUserMessage = useCallback(
    async (text, addressCoords) => {
      const trimmed = text.trim()
      if (!trimmed || isTyping) return

      const userMsgId = addMessage('user', trimmed, { status: 'sent' })
      setIsTyping(true)
      scheduleAbandonTimer()

      try {
        const data = await sendMessage(sessionId, trimmed, addressCoords)
        setMessageStatus(userMsgId, 'delivered')
        handleAssistantReply(data)
      } catch {
        addMessage('system', "Sorry, I couldn't reach the kitchen just now - please try again in a moment.")
      } finally {
        setIsTyping(false)
      }
    },
    [addMessage, handleAssistantReply, isTyping, scheduleAbandonTimer, sessionId, setMessageStatus]
  )

  const sendUserImage = useCallback(
    async (file, caption) => {
      if (!file || isTyping) return

      const previewUrl = URL.createObjectURL(file)
      const userMsgId = addMessage('user', caption?.trim() || '', { imageUrl: previewUrl, status: 'sent' })
      setIsTyping(true)
      scheduleAbandonTimer()

      try {
        const data = await sendImageMessage(sessionId, file, caption?.trim())
        setMessageStatus(userMsgId, 'delivered')
        handleAssistantReply(data)
      } catch {
        addMessage('system', "Sorry, I couldn't look at that image just now - please try again in a moment.")
      } finally {
        setIsTyping(false)
      }
    },
    [addMessage, handleAssistantReply, isTyping, scheduleAbandonTimer, sessionId, setMessageStatus]
  )

  const value = useMemo(
    () => ({
      sessionId,
      messages,
      isTyping,
      language,
      sendUserMessage,
      sendUserImage,
    }),
    [sessionId, messages, isTyping, language, sendUserMessage, sendUserImage]
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
