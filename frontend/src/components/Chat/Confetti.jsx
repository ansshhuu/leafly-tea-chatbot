import { useMemo } from 'react'
import './Confetti.css'

const COLORS = ['#e07a5f', '#f2cc8f', '#81b29a', '#3d405b', '#f4f1de']
const PIECE_COUNT = 24

export default function Confetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: PIECE_COUNT }, (_, i) => ({
        id: i,
        left: Math.random() * 100,
        delay: Math.random() * 0.3,
        duration: 1.1 + Math.random() * 0.6,
        color: COLORS[i % COLORS.length],
        rotate: Math.round(Math.random() * 360),
      })),
    []
  )

  return (
    <div className="confetti-burst" aria-hidden="true">
      {pieces.map((piece) => (
        <span
          key={piece.id}
          className="confetti-piece"
          style={{
            left: `${piece.left}%`,
            backgroundColor: piece.color,
            animationDelay: `${piece.delay}s`,
            animationDuration: `${piece.duration}s`,
            '--confetti-rotate': `${piece.rotate}deg`,
          }}
        />
      ))}
    </div>
  )
}
