import { useEffect, useRef, useState } from 'react'
import {
  isBlobRecordingSupported,
  isSpeechRecognitionSupported,
  startAudioLevelMeterFromStream,
  startBlobRecording,
  startNativeRecognition,
  transcribeWithWhisper,
} from '../../services/speech'
import './VoiceInput.css'

const BAR_COUNT = 24
const MIN_BAR_SCALE = 0.15
const FIRST_USE_NOTE_KEY = 'cafe.voiceInputNoteSeen'
const FIRST_USE_NOTE_MS = 5000

export default function VoiceInput({ language, onFinalTranscript, disabled, onRecordingChange }) {
  // 'idle' | 'recording' | 'transcribing'
  const [phase, setPhase] = useState('idle')
  const [error, setError] = useState(null)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [showFirstUseNote, setShowFirstUseNote] = useState(false)

  const startingRef = useRef(false)
  const nativeSessionRef = useRef(null)
  const blobRecordingRef = useRef(null)
  const meterStopRef = useRef(null)
  const barRefs = useRef([])
  const cancelledRef = useRef(false)
  const noteTimerRef = useRef(null)

  useEffect(
    () => () => {
      nativeSessionRef.current?.abort()
      blobRecordingRef.current?.discard()
      meterStopRef.current?.()
      if (noteTimerRef.current) clearTimeout(noteTimerRef.current)
    },
    []
  )

  if (!isSpeechRecognitionSupported && !isBlobRecordingSupported()) return null

  function resetBars() {
    barRefs.current.forEach((el) => {
      if (el) el.style.transform = `scaleY(${MIN_BAR_SCALE})`
    })
  }

  function maybeShowFirstUseNote() {
    let seen = true
    try {
      seen = localStorage.getItem(FIRST_USE_NOTE_KEY) === 'true'
    } catch {
      // localStorage unavailable (private mode etc.) - just skip the note
      // rather than showing it every time.
    }
    if (seen) return
    setShowFirstUseNote(true)
    try {
      localStorage.setItem(FIRST_USE_NOTE_KEY, 'true')
    } catch {
      // ignore
    }
    noteTimerRef.current = setTimeout(() => setShowFirstUseNote(false), FIRST_USE_NOTE_MS)
  }

  async function handleStart() {
    console.log('[voice] mic clicked')
    console.log('[voice] SpeechRecognition exists:', isSpeechRecognitionSupported)
    // phase only flips to 'recording' after the permission prompt resolves,
    // so a rapid second click while still awaiting it would otherwise pass
    // the `phase !== 'idle'` check twice and start two concurrent
    // recordings - startingRef closes that window synchronously.
    if (phase !== 'idle' || disabled || startingRef.current) {
      console.log('[voice] mic click ignored (already starting/recording or disabled)')
      return
    }
    startingRef.current = true
    setError(null)
    cancelledRef.current = false
    maybeShowFirstUseNote()

    let recording
    try {
      recording = await startBlobRecording()
      console.log('[voice] blob recording started')
    } catch (err) {
      console.warn('[voice] startBlobRecording failed:', err)
      startingRef.current = false
      setError('Microphone permission was denied - please allow access to use voice input.')
      return
    }
    startingRef.current = false
    if (cancelledRef.current) {
      recording.discard()
      return
    }

    blobRecordingRef.current = recording
    setPhase('recording')
    onRecordingChange?.(true)

    meterStopRef.current = startAudioLevelMeterFromStream(
      recording.stream,
      (levels) => {
        levels.forEach((level, i) => {
          const el = barRefs.current[i]
          if (!el) return
          const scale = Math.max(MIN_BAR_SCALE, Math.min(1, level))
          el.style.transform = `scaleY(${scale})`
        })
      },
      { barCount: BAR_COUNT }
    )

    // Native recognition runs alongside the blob recording (not instead of
    // it) - if it's unavailable or errors out, the audio we're already
    // capturing feeds Whisper-WASM without asking the customer to repeat
    // themselves. Returns null synchronously for unsupported/broken
    // browsers (Firefox, Brave), which is treated identically to an error.
    nativeSessionRef.current = startNativeRecognition(language)
    console.log('[voice] native recognition session:', nativeSessionRef.current ? 'started' : 'unavailable, relying on Whisper fallback')
  }

  async function handleConfirm() {
    if (phase !== 'recording') return
    const recording = blobRecordingRef.current
    const native = nativeSessionRef.current

    meterStopRef.current?.()
    meterStopRef.current = null
    resetBars()
    setPhase('transcribing')
    setLoadingLabel('')

    const blobPromise = recording.stop()
    const nativePromise = native ? native.stop() : Promise.resolve({ text: '', ok: false })

    const nativeResult = await nativePromise
    console.log('[voice] native result:', nativeResult)
    if (nativeResult.ok) {
      blobPromise.catch(() => {})
      finish(nativeResult.text)
      return
    }

    console.log('[voice] native unavailable/failed, falling back to Whisper')
    try {
      const blob = await blobPromise
      setLoadingLabel('Loading voice model…')
      const text = await transcribeWithWhisper(blob, (progress) => {
        if (progress?.status === 'progress' && typeof progress.progress === 'number') {
          setLoadingLabel(`Loading voice model (${Math.round(progress.progress)}%)…`)
        } else if (progress?.status === 'done' || progress?.status === 'ready') {
          setLoadingLabel('Transcribing…')
        }
      })
      if (!text) throw new Error('No speech detected')
      console.log('[voice] Whisper fallback succeeded')
      finish(text)
    } catch (err) {
      console.warn('[voice] Whisper fallback failed:', err)
      if (cancelledRef.current) return
      setError('Could not hear that - please try again.')
      setPhase('idle')
      setLoadingLabel('')
      onRecordingChange?.(false)
    }
  }

  function finish(text) {
    if (cancelledRef.current) return
    setPhase('idle')
    setLoadingLabel('')
    onRecordingChange?.(false)
    onFinalTranscript(text)
  }

  function handleCancel() {
    cancelledRef.current = true
    setError(null)
    setLoadingLabel('')
    nativeSessionRef.current?.abort()
    blobRecordingRef.current?.discard()
    meterStopRef.current?.()
    meterStopRef.current = null
    resetBars()
    setPhase('idle')
    onRecordingChange?.(false)
  }

  const isRecordingPill = phase === 'recording' || phase === 'transcribing'

  return (
    <div className="voice-input">
      {isRecordingPill ? (
        <div
          className={`voice-record-bar voice-record-bar--enter ${phase === 'transcribing' ? 'voice-record-bar--transcribing' : ''}`}
          role="group"
          aria-label={phase === 'transcribing' ? 'Transcribing voice message' : 'Recording voice message'}
        >
          <div className="voice-waveform" aria-hidden="true">
            {Array.from({ length: BAR_COUNT }).map((_, i) => (
              <span key={i} className="voice-waveform-bar" ref={(el) => (barRefs.current[i] = el)} />
            ))}
          </div>
          {phase === 'transcribing' && loadingLabel && <span className="voice-loading-label">{loadingLabel}</span>}
          <button
            type="button"
            className="voice-record-btn voice-record-btn--cancel"
            onClick={handleCancel}
            aria-label="Cancel recording"
            title="Cancel"
          >
            ✕
          </button>
          <button
            type="button"
            className="voice-record-btn voice-record-btn--confirm"
            onClick={handleConfirm}
            disabled={phase === 'transcribing'}
            aria-label="Stop and use transcript"
            title="Done"
          >
            {phase === 'transcribing' ? <span className="voice-spinner" aria-hidden="true" /> : '✓'}
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="voice-input-btn voice-input-btn--fade-in"
          onClick={handleStart}
          disabled={disabled}
          aria-label="Speak your message"
          title="Speak your message"
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
            <rect x="9" y="2" width="6" height="12" rx="3" stroke="currentColor" strokeWidth="1.8" />
            <path d="M5 11v1a7 7 0 0 0 14 0v-1M12 19v3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </button>
      )}
      {showFirstUseNote && (
        <span className="voice-input-note" role="status">
          Voice input may take a moment to load the first time.
        </span>
      )}
      {error && (
        <span className="voice-input-error" role="status">
          {error}
        </span>
      )}
    </div>
  )
}
