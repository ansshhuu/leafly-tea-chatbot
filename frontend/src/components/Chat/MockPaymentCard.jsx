import { useState } from 'react'
import { useChat } from '../../context/ChatContext'
import './MockPaymentCard.css'

const PAYMENT_COMPLETE_MESSAGE = 'Payment completed'
const PROCESSING_MS = 1400
const SUCCESS_DISPLAY_MS = 900

export default function MockPaymentCard({ amount, label, disabled = false }) {
  const { sendUserMessage, isTyping } = useChat()
  const [phase, setPhase] = useState('idle')

  function handlePay() {
    if (phase !== 'idle' || isTyping || disabled) return
    setPhase('processing')
    setTimeout(() => {
      setPhase('success')
      setTimeout(() => {
        sendUserMessage(PAYMENT_COMPLETE_MESSAGE)
      }, SUCCESS_DISPLAY_MS)
    }, PROCESSING_MS)
  }

  return (
    <div className="mock-payment-card">
      <div className="mock-payment-header">
        <span className="mock-payment-label">{label}</span>
        <span className="mock-payment-amount">Rs.{amount.toFixed(2)}</span>
      </div>

      {phase === 'idle' && (
        <button type="button" className="mock-payment-btn" onClick={handlePay} disabled={isTyping || disabled}>
          Pay Rs.{amount.toFixed(2)}
        </button>
      )}

      {phase === 'processing' && (
        <div className="mock-payment-status mock-payment-status--processing" role="status">
          <span className="mock-payment-spinner" aria-hidden="true" />
          Processing payment...
        </div>
      )}

      {phase === 'success' && (
        <div className="mock-payment-status mock-payment-status--success" role="status">
          <span className="mock-payment-check" aria-hidden="true">
            ✓
          </span>
          Payment successful
        </div>
      )}

      <p className="mock-payment-disclaimer">Demo payment - no real charges</p>
    </div>
  )
}
