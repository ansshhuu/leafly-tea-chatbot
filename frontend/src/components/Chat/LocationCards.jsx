import { MapPin, Phone, Clock } from 'lucide-react'
import './LocationCards.css'

export default function LocationCards({ locations }) {
  if (!locations || locations.length === 0) return null

  return (
    <div className="location-cards">
      {locations.map((loc) => (
        <div className="location-card" key={loc.name}>
          <div className="location-card-header">
            <MapPin className="location-card-icon" size={16} strokeWidth={1.75} aria-hidden="true" />
            <span>{loc.name}</span>
          </div>
          <p className="location-card-address">{loc.address}</p>
          <p className="location-card-detail">
            <Clock className="location-card-detail-icon" size={14} strokeWidth={1.75} aria-hidden="true" />
            {loc.hours}
          </p>
          <p className="location-card-detail">
            <Phone className="location-card-detail-icon" size={14} strokeWidth={1.75} aria-hidden="true" />
            {loc.phone}
          </p>
        </div>
      ))}
    </div>
  )
}
