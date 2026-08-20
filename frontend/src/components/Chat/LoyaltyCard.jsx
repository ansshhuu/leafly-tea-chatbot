import Confetti from './Confetti'
import './LoyaltyCard.css'

export default function LoyaltyCard({ card }) {
  if (!card) return null

  const progressPct =
    card.next_reward_points > 0
      ? Math.min(100, Math.round((card.current_points / card.next_reward_points) * 100))
      : 100

  const milestone = card.milestone

  return (
    <div className={`loyalty-card ${milestone ? 'loyalty-card--milestone' : ''}`}>
      {milestone && <Confetti />}

      <div className="loyalty-card-header">
        <span>Your Rewards</span>
        <span className="loyalty-card-points">{card.current_points} pts</span>
      </div>

      {milestone && (
        <p className="loyalty-card-milestone">
          🎉 You&apos;ve unlocked <strong>{milestone.reward}</strong>!
        </p>
      )}

      <div className="loyalty-card-progress-track" role="progressbar" aria-valuenow={progressPct} aria-valuemin={0} aria-valuemax={100}>
        <div className="loyalty-card-progress-fill" style={{ width: `${progressPct}%` }} />
      </div>

      <p className="loyalty-card-label">{card.progress_label}</p>
      <p className="loyalty-card-next-reward">
        Next reward: <strong>{card.next_reward}</strong>
      </p>
    </div>
  )
}
