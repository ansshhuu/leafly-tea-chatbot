import { Gift, HelpCircle, Leaf, Sparkles } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import './QuickActions.css'

export const QUICK_ACTION_LABELS = [
  'Explore Tea Collections',
  'Wellness Benefits',
  'Ask About a Tea',
  'Gift Hampers',
]

const ACTIONS = [
  { Icon: Leaf, label: 'Explore Tea Collections', message: 'Show me your teas' },
  { Icon: Sparkles, label: 'Wellness Benefits', message: 'What are the wellness benefits of your teas?' },
  { Icon: HelpCircle, label: 'Ask About a Tea', message: 'Tell me about your teas' },
  { Icon: Gift, label: 'Gift Hampers', message: 'Do you have gift hampers?' },
]

export function isQuickActionLabelSet(options) {
  if (!options || options.length !== QUICK_ACTION_LABELS.length) return false
  const asSet = new Set(options)
  return QUICK_ACTION_LABELS.every((label) => asSet.has(label))
}

export default function QuickActions({ disabled = false }) {
  const { sendUserMessage, isTyping } = useChat()

  return (
    <div className="quick-actions" role="group" aria-label="Quick actions">
      {ACTIONS.map(({ Icon, label, message }) => (
        <button
          key={label}
          type="button"
          className="quick-action-btn"
          onClick={() => sendUserMessage(message)}
          disabled={isTyping || disabled}
        >
          <Icon className="quick-action-icon" size={16} strokeWidth={1.75} aria-hidden="true" />
          {label}
        </button>
      ))}
    </div>
  )
}
