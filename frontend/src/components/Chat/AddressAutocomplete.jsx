import { useEffect, useRef, useState } from 'react'
import { fetchAddressSuggestions } from '../../services/api'
import './AddressAutocomplete.css'

const DEBOUNCE_MS = 500
const MIN_QUERY_LENGTH = 4

// Reusable live-suggestion dropdown - doesn't own the text value itself, just
// watches `query` (whatever the caller's own input currently holds) and
// fetches/renders Nominatim candidates under it. Debounced so a request only
// fires 500ms after the customer stops typing, never on every keystroke, per
// Nominatim's usage policy.
export default function AddressAutocomplete({ query, enabled, onSelect }) {
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef(null)
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (!enabled || query.trim().length < MIN_QUERY_LENGTH) {
      setSuggestions([])
      setOpen(false)
      setLoading(false)
      return undefined
    }

    debounceRef.current = setTimeout(() => {
      const requestId = ++requestIdRef.current
      setLoading(true)
      fetchAddressSuggestions(query.trim())
        .then((results) => {
          if (requestId !== requestIdRef.current) return
          setSuggestions(results || [])
          setOpen((results || []).length > 0)
        })
        .catch(() => {
          if (requestId !== requestIdRef.current) return
          setSuggestions([])
          setOpen(false)
        })
        .finally(() => {
          if (requestId === requestIdRef.current) setLoading(false)
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(debounceRef.current)
  }, [query, enabled])

  if (!enabled || (!open && !loading)) return null
  if (!loading && suggestions.length === 0) return null

  return (
    <ul className="address-autocomplete" role="listbox" aria-label="Address suggestions">
      {loading && suggestions.length === 0 && <li className="address-autocomplete-hint">Searching addresses…</li>}
      {suggestions.map((suggestion, i) => (
        <li key={`${suggestion.lat}-${suggestion.lon}-${i}`}>
          <button
            type="button"
            className="address-autocomplete-option"
            // mousedown (not click) fires before the input's blur, so the
            // dropdown doesn't disappear before the selection registers.
            onMouseDown={(e) => {
              e.preventDefault()
              setOpen(false)
              onSelect(suggestion)
            }}
          >
            {suggestion.display_name}
          </button>
        </li>
      ))}
    </ul>
  )
}
