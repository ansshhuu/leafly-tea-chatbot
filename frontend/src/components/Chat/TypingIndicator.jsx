import { useEffect, useState } from 'react'
import './TypingIndicator.css'

const CYCLE_MS = 800

const DEFAULT_PHRASES = ['Checking menu...', 'Thinking...', 'Almost there...']

export default function TypingIndicator({ show }) {
  const phrases = DEFAULT_PHRASES
  const [phraseIndex, setPhraseIndex] = useState(0)

  useEffect(() => {
    if (!show) {
      setPhraseIndex(0)
      return
    }
    const interval = setInterval(() => {
      setPhraseIndex((prev) => (prev + 1) % phrases.length)
    }, CYCLE_MS)
    return () => clearInterval(interval)
  }, [show, phrases])

  if (!show) return null

  return (
    <div className="message-row message-row--assistant">
      <div className="typing-indicator-wrap">
        <span className="typing-status-text">{phrases[phraseIndex]}</span>
        <div className="message-bubble message-bubble--assistant typing-indicator">
          <span className="typing-dot" />
          <span className="typing-dot" />
          <span className="typing-dot" />
        </div>
      </div>
    </div>
  )
}
