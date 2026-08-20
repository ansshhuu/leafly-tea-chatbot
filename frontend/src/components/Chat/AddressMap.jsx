import { useCallback, useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import AddressAutocomplete from './AddressAutocomplete'
import { fetchReverseGeocode } from '../../services/api'
import { getUserCoordinates } from '../../services/geolocation'
import { useChat } from '../../context/ChatContext'
import './AddressMap.css'

// Vite (like most bundlers) doesn't resolve Leaflet's own relative image
// URLs for its default marker icon - point them at the bundled asset URLs
// instead, once, at module load.
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({ iconRetinaUrl: markerIcon2x, iconUrl: markerIcon, shadowUrl: markerShadow })

const GEOLOCATION_TIMEOUT_MS = 10000
const REVERSE_GEOCODE_DEBOUNCE_MS = 500
const MAP_ZOOM = 16
const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

// Bandra West, Mumbai - the ultimate fallback map center when geolocation is
// denied/unavailable AND the customer hasn't searched for anything yet
// (matches CAFE_LOCATIONS[0] in the backend).
const FALLBACK_CENTER = { lat: 19.0596, lon: 72.8295 }

// Single map component covering BOTH the geolocation-first flow (pin starts
// at the customer's real position, no search needed) and the denied/
// unavailable fallback (pin starts at a default location, a search box is
// shown so the customer can jump to their area first) - same tap-to-place
// + reverse-geocode + confirm flow either way, so there's only ever one
// component to maintain.
export default function AddressMap({ disabled, onConfirm }) {
  const { sendUserMessage } = useChat()
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markerRef = useRef(null)
  const reverseDebounceRef = useRef(null)
  const reverseRequestIdRef = useRef(0)
  // Read inside the map-click handler, which is attached once at map
  // creation - a plain closure over `disabled` would go stale if the prop
  // changes later (e.g. this message stops being the latest one).
  const disabledRef = useRef(disabled)
  disabledRef.current = disabled

  const [phase, setPhase] = useState('locating') // 'locating' | 'ready'
  const [showSearch, setShowSearch] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [pin, setPin] = useState(null)
  const [resolvedAddress, setResolvedAddress] = useState(null)
  const [resolving, setResolving] = useState(false)

  const triggerReverseGeocode = useCallback((point) => {
    setResolvedAddress(null)
    if (reverseDebounceRef.current) clearTimeout(reverseDebounceRef.current)

    reverseDebounceRef.current = setTimeout(() => {
      const requestId = ++reverseRequestIdRef.current
      setResolving(true)
      fetchReverseGeocode(point.lat, point.lon)
        .then((result) => {
          if (requestId !== reverseRequestIdRef.current) return
          setResolvedAddress(result?.display_name || null)
        })
        .catch(() => {
          if (requestId !== reverseRequestIdRef.current) return
          setResolvedAddress(null)
        })
        .finally(() => {
          if (requestId === reverseRequestIdRef.current) setResolving(false)
        })
    }, REVERSE_GEOCODE_DEBOUNCE_MS)
  }, [])

  const movePin = useCallback(
    (point, { recenter = true } = {}) => {
      setPin(point)

      if (!mapRef.current) {
        const map = L.map(containerRef.current, { zoomControl: true }).setView([point.lat, point.lon], MAP_ZOOM)
        L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map)

        const marker = L.marker([point.lat, point.lon], { draggable: false }).addTo(map)
        // Tap/click anywhere on the map to move the pin there directly -
        // simpler than dragging, same end result (reverse-geocode the
        // tapped point).
        map.on('click', (event) => {
          if (disabledRef.current) return
          movePin({ lat: event.latlng.lat, lon: event.latlng.lng }, { recenter: false })
        })

        mapRef.current = map
        markerRef.current = marker
      } else {
        markerRef.current.setLatLng([point.lat, point.lon])
        if (recenter) mapRef.current.setView([point.lat, point.lon], mapRef.current.getZoom())
      }

      triggerReverseGeocode(point)
    },
    [triggerReverseGeocode]
  )

  useEffect(() => {
    // Guards against React StrictMode's dev-only double-invoke (mount ->
    // cleanup -> mount again): the FIRST pass's cleanup fires before its
    // geolocation promise resolves, so `cancelled` skips acting on it -
    // only the second pass's promise actually creates the map. Without
    // this, the map instance created by the first pass would get torn down
    // by cleanup and never recreated, since geolocation is only requested
    // once (deliberately - see the "not on page load" requirement above).
    let cancelled = false

    getUserCoordinates(GEOLOCATION_TIMEOUT_MS).then((coords) => {
      if (cancelled) return
      if (coords) {
        movePin(coords)
      } else {
        setShowSearch(true)
        movePin(FALLBACK_CENTER)
      }
      setPhase('ready')
    })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(
    () => () => {
      if (reverseDebounceRef.current) clearTimeout(reverseDebounceRef.current)
      mapRef.current?.remove()
      mapRef.current = null
    },
    []
  )

  function handleSearchSelect(suggestion) {
    setSearchQuery('')
    movePin({ lat: suggestion.lat, lon: suggestion.lon })
  }

  function handleConfirm() {
    if (!pin || disabled) return
    const addressText = resolvedAddress || `${pin.lat.toFixed(5)}, ${pin.lon.toFixed(5)}`
    if (onConfirm) {
      onConfirm(addressText, pin)
    } else {
      sendUserMessage(addressText, pin)
    }
  }

  return (
    <div className="address-map">
      {showSearch && (
        <div className="address-map-search">
          <input
            type="text"
            className="address-map-search-input"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search for your address..."
            disabled={disabled}
          />
          <AddressAutocomplete query={searchQuery} enabled={!disabled} onSelect={handleSearchSelect} />
        </div>
      )}

      <div className="address-map-canvas-wrapper">
        <div className="address-map-canvas" ref={containerRef} />
        {phase === 'locating' && (
          <div className="address-map-overlay">
            <span>Finding your location…</span>
          </div>
        )}
      </div>

      <p className="address-map-hint">Tap anywhere on the map to place your pin exactly.</p>

      <div className="address-map-resolved">
        {resolving && <span className="address-map-resolving">Resolving address…</span>}
        {!resolving && resolvedAddress && <span>{resolvedAddress}</span>}
        {!resolving && !resolvedAddress && pin && (
          <span className="address-map-resolving">Couldn&rsquo;t auto-resolve an address for this pin - you can still confirm it.</span>
        )}
      </div>

      <button
        type="button"
        className="address-map-confirm-btn"
        onClick={handleConfirm}
        disabled={disabled || !pin || phase !== 'ready'}
      >
        Confirm this location
      </button>
    </div>
  )
}
