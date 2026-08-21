import { Heart, Leaf, Coffee } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import './WelcomeScreen.css'

const HEADING = 'Hi there! 👋'

const WELCOME_ACTIONS = [
  { Icon: Leaf,   label: 'Explore Tea Collections', message: 'Show me your teas' },
  { Icon: Heart,  label: 'Wellness Benefits',        message: 'What are the wellness benefits of your teas?' },
  { Icon: Coffee, label: 'Tea Brewing Guide',        message: 'How do I brew tea properly?' },
]

export default function WelcomeScreen() {
  const { sendUserMessage, isTyping } = useChat()

  return (
    <div className="welcome-screen">
      <div className="welcome-avatar">
        <img src="/bot-icon.png" alt="Leafly mascot" />
      </div>

      <div className="welcome-text">
        <h2>{HEADING}</h2>
        <p>
          <span>I'm your Leafly Assistant.</span>
          <br />
          <span>How can I help you today?</span>
        </p>
      </div>

      <div className="welcome-actions" role="group" aria-label="Quick actions">
        {WELCOME_ACTIONS.map(({ Icon, label, message }) => (
          <button
            key={label}
            type="button"
            className="welcome-action-btn"
            onClick={() => sendUserMessage(message)}
            disabled={isTyping}
          >
            <Icon className="welcome-action-icon" size={18} strokeWidth={1.5} aria-hidden="true" />
            <span>{label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
