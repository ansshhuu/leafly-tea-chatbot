import './FloatingBotButton.css'

export default function FloatingBotButton({ hasUnread, onOpen }) {
  return (
    <button type="button" className="floating-bot-btn" onClick={onOpen} aria-label="Open chat">
      <img src="/leaf.png" alt="" className="floating-bot-btn-icon" />
      {hasUnread && <span className="floating-bot-btn-dot" aria-hidden="true" />}
    </button>
  )
}
