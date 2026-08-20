import { useEffect, useRef, useState } from 'react'
import ChatWindow from './ChatWindow'
import FloatingBotButton from './FloatingBotButton'
import { useChat } from '../../context/ChatContext'
import './ChatWidget.css'

const OPEN_STATE_KEY = 'cafe.chatOpen'

function readStoredOpenState() {
  try {
    return sessionStorage.getItem(OPEN_STATE_KEY) === 'true'
  } catch {
    return false
  }
}

function writeStoredOpenState(isOpen) {
  try {
    sessionStorage.setItem(OPEN_STATE_KEY, String(isOpen))
  } catch {
  }
}

export default function ChatWidget() {
  const { messages } = useChat()
  const [isOpen, setIsOpen] = useState(readStoredOpenState)
  const [hasUnread, setHasUnread] = useState(false)
  const seenCountRef = useRef(messages.length)

  useEffect(() => {
    writeStoredOpenState(isOpen)
  }, [isOpen])

  useEffect(() => {
    if (isOpen) {
      seenCountRef.current = messages.length
      setHasUnread(false)
      return
    }
    if (messages.length > seenCountRef.current) {
      const arrived = messages.slice(seenCountRef.current)
      if (arrived.some((msg) => msg.role === 'assistant' || msg.role === 'system')) {
        setHasUnread(true)
      }
      seenCountRef.current = messages.length
    }
  }, [messages, isOpen])

  function close() {
    setIsOpen(false)
  }

  return (
    <>
      <div className={`chat-widget-panel ${isOpen ? 'chat-widget-panel--open' : ''}`} aria-hidden={!isOpen}>
        <header className="bot-header">
          <div className="bot-header-identity">
            <span className="bot-header-avatar">
              <img src="/bot-icon.png" alt="" />
            </span>
            <h1>Rumi</h1>
          </div>
          <div className="bot-header-controls">
            <button type="button" className="bot-header-icon-btn" onClick={close} aria-label="Close chat" title="Close">
              &#10005;
            </button>
          </div>
        </header>
        <div className="chat-widget-body">
          <ChatWindow />
        </div>
      </div>

      {!isOpen && <FloatingBotButton hasUnread={hasUnread} onOpen={() => setIsOpen(true)} />}
    </>
  )
}
