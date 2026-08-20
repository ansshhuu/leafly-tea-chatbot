const SpeechRecognitionImpl =
  typeof window !== 'undefined' ? window.SpeechRecognition || window.webkitSpeechRecognition : null

export const isSpeechRecognitionSupported = Boolean(SpeechRecognitionImpl)

const LANGUAGE_TO_LOCALE = {
  en: 'en-IN',
  hi: 'hi-IN',
  mr: 'mr-IN',
  hinglish: 'hi-IN',
}

export function localeForLanguage(language) {
  return LANGUAGE_TO_LOCALE[language] || 'en-IN'
}

// Starts the browser's native SpeechRecognition (Chrome/Edge/Safari only -
// Firefox doesn't expose it, Brave doesn't implement it). Returns null
// immediately if it's unsupported OR throws synchronously on construction/
// start (some browsers expose the constructor but fail on first use) - the
// caller treats null exactly like "not available" and falls back to the
// Whisper-WASM pipeline on the audio it's already recording in parallel via
// MediaRecorder, so the customer never has to repeat themselves.
// Some browsers (Brave in particular) expose the SpeechRecognition
// constructor and accept .start() without throwing, then never fire
// onresult/onerror/onend at all - they just hang. Without a watchdog that
// looks like a legitimate long recording to the caller, so nativeResult.ok
// never resolves and handleConfirm() hangs forever waiting on it instead of
// falling through to the Whisper blob pipeline that's already recording in
// parallel. FIRST_EVENT_TIMEOUT_MS only guards the window before the engine
// shows ANY sign of life; it's cleared on the first onresult/onerror/onend so
// it never cuts off a real in-progress recognition.
const FIRST_EVENT_TIMEOUT_MS = 3000

export function startNativeRecognition(language) {
  console.log('[voice] startNativeRecognition called, supported:', isSpeechRecognitionSupported)
  if (!isSpeechRecognitionSupported) return null

  let recognition
  try {
    recognition = new SpeechRecognitionImpl()
  } catch (err) {
    console.warn('[voice] SpeechRecognition threw on construction:', err)
    return null
  }

  recognition.lang = localeForLanguage(language)
  recognition.interimResults = true
  recognition.continuous = true
  recognition.maxAlternatives = 1

  let finalTranscript = ''
  let interimTranscript = ''
  let aborted = false
  let errored = false
  let settled = false
  let sawFirstEvent = false
  let resolveResult
  const resultPromise = new Promise((resolve) => {
    resolveResult = resolve
  })

  function settle() {
    if (settled) return
    settled = true
    if (watchdogTimer) clearTimeout(watchdogTimer)
    const text = (finalTranscript + interimTranscript).trim()
    const ok = !aborted && !errored && Boolean(text)
    console.log('[voice] native recognition settled:', { ok, aborted, errored, textLength: text.length })
    resolveResult({ text, ok })
  }

  function markFirstEvent() {
    sawFirstEvent = true
    if (watchdogTimer) {
      clearTimeout(watchdogTimer)
      watchdogTimer = null
    }
  }

  let watchdogTimer = setTimeout(() => {
    if (sawFirstEvent || settled) return
    console.warn('[voice] native recognition produced no event within', FIRST_EVENT_TIMEOUT_MS, 'ms - forcing fallback')
    errored = true
    try {
      recognition.abort()
    } catch (err) {
      console.warn('[voice] recognition.abort() threw during watchdog:', err)
    }
    settle()
  }, FIRST_EVENT_TIMEOUT_MS)

  recognition.onresult = (event) => {
    markFirstEvent()
    interimTranscript = ''
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i]
      const piece = result[0]?.transcript || ''
      if (result.isFinal) {
        finalTranscript += piece
      } else {
        interimTranscript += piece
      }
    }
  }

  recognition.onerror = (event) => {
    markFirstEvent()
    console.warn('[voice] native SpeechRecognition onerror:', event.error)
    if (event.error === 'aborted') return
    errored = true
  }

  recognition.onend = () => {
    console.log('[voice] native SpeechRecognition onend fired')
    markFirstEvent()
    settle()
  }

  try {
    recognition.start()
    console.log('[voice] native SpeechRecognition.start() called successfully')
  } catch (err) {
    console.warn('[voice] SpeechRecognition threw on start():', err)
    if (watchdogTimer) clearTimeout(watchdogTimer)
    return null
  }

  // Guards stop()/abort() themselves: if the engine hangs and never fires
  // onend after being told to stop, force-settle rather than leaving the
  // caller's `await native.stop()` unresolved forever.
  function armStopSafetyNet() {
    setTimeout(() => {
      if (settled) return
      console.warn('[voice] native recognition onend never fired after stop/abort - forcing settle')
      errored = true
      settle()
    }, FIRST_EVENT_TIMEOUT_MS)
  }

  return {
    // Resolves once the engine has actually finished (native's onend can
    // lag slightly behind the stop() call) - {text, ok}. ok is false on
    // error/abort/empty result/watchdog-timeout, signalling the caller to
    // fall back to Whisper.
    stop() {
      console.log('[voice] native recognition stop() requested')
      if (!settled) {
        recognition.stop()
        armStopSafetyNet()
      }
      return resultPromise
    },
    abort() {
      console.log('[voice] native recognition abort() requested')
      aborted = true
      if (!settled) {
        recognition.abort()
        armStopSafetyNet()
      }
      return resultPromise
    },
  }
}

const RECORDER_MIME_CANDIDATES = ['audio/webm', 'audio/ogg', 'audio/mp4']

export function isBlobRecordingSupported() {
  return (
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)
  )
}

// Records raw microphone audio into a Blob via the standard MediaRecorder
// API (works in every modern browser, unlike SpeechRecognition) - this is
// what feeds the Whisper-WASM fallback, and runs alongside native
// recognition (when available) as a safety net rather than only being
// started after native fails, so no re-recording is ever needed.
export async function startBlobRecording() {
  if (!isBlobRecordingSupported()) {
    throw new Error('Recording is not supported in this browser')
  }

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const mimeType = RECORDER_MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported?.(type))
  const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
  const chunks = []

  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data)
  }

  const stopped = new Promise((resolve) => {
    recorder.onstop = () => {
      resolve(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))
    }
  })

  recorder.start()

  function releaseStream() {
    stream.getTracks().forEach((track) => track.stop())
  }

  return {
    stream,
    stop() {
      if (recorder.state !== 'inactive') recorder.stop()
      return stopped.finally(releaseStream)
    },
    discard() {
      if (recorder.state !== 'inactive') recorder.stop()
      releaseStream()
    },
  }
}

export function startAudioLevelMeterFromStream(stream, onLevels, { barCount = 24 } = {}) {
  if (!stream) return () => {}

  const AudioContextImpl = window.AudioContext || window.webkitAudioContext
  if (!AudioContextImpl) return () => {}

  let stopped = false
  let rafId = null
  const audioCtx = new AudioContextImpl()
  const source = audioCtx.createMediaStreamSource(stream)
  const analyser = audioCtx.createAnalyser()
  analyser.fftSize = 128
  analyser.smoothingTimeConstant = 0.6
  source.connect(analyser)

  const data = new Uint8Array(analyser.frequencyBinCount)
  const step = Math.max(1, Math.floor(data.length / barCount))

  const tick = () => {
    if (stopped) return
    analyser.getByteFrequencyData(data)
    const levels = new Array(barCount)
    for (let i = 0; i < barCount; i++) {
      levels[i] = data[i * step] / 255
    }
    onLevels(levels)
    rafId = requestAnimationFrame(tick)
  }
  tick()

  return () => {
    stopped = true
    if (rafId) cancelAnimationFrame(rafId)
    source.disconnect()
    audioCtx.close().catch(() => {})
  }
}

// --- Whisper-WASM fallback (Transformers.js), for browsers where native
// SpeechRecognition is unavailable or fails (Firefox, Brave, ...). Loaded
// lazily - the library and the ~40MB model are only fetched the first time
// this is actually needed, never upfront, and the model is cached by the
// browser (Transformers.js uses the Cache Storage API) so later uses are
// fast even across page reloads. ---
const WHISPER_MODEL_ID = 'Xenova/whisper-tiny.en'
const MODEL_FILES_TO_VERIFY = [
  'config.json',
  'generation_config.json',
  'preprocessor_config.json',
  'tokenizer.json',
  'tokenizer_config.json',
  'onnx/encoder_model_quantized.onnx',
  'onnx/decoder_model_merged_quantized.onnx',
]
let transcriberPromise = null
let cachePurged = false

// transformers.js caches every fetched file in the browser's Cache Storage
// API under a 'transformers-cache' bucket, keyed by the request path - and
// it does this purely on `response.status === 200`, with no content-type
// check. Earlier (before the self-hosted files existed / before
// localModelPath was configured), a request to e.g.
// /models/Xenova/whisper-tiny.en/tokenizer_config.json hit Vite's dev-server
// SPA fallback, which answers unmatched routes with index.html at HTTP 200 -
// so that broken HTML response was cached as if it were the real file. Now
// that the real files are in place, `tryCache()` still serves that stale
// 200 response first and the fetch for the correct file never happens
// again. Purging the bucket once per session guarantees we're not serving
// a cached mistake from before the self-host fix landed.
async function purgeStaleModelCache() {
  if (cachePurged) return
  cachePurged = true
  if (typeof caches === 'undefined') return
  try {
    const deleted = await caches.delete('transformers-cache')
    console.log('[voice] purged stale transformers-cache bucket:', deleted)
  } catch (err) {
    console.warn('[voice] failed to purge transformers-cache:', err)
  }
}

// One-off diagnostic: fetch every file the pipeline is about to request and
// log whether each came back as real content or an HTML fallback page, so a
// future regression shows exactly which filename broke instead of an opaque
// "Unexpected token '<'" three layers deep in the tokenizer loader.
async function verifyLocalModelFiles() {
  const base = `/models/${WHISPER_MODEL_ID}/`
  console.log('[voice] local model path set, checking files under:', base)
  await Promise.all(
    MODEL_FILES_TO_VERIFY.map(async (file) => {
      const url = base + file
      try {
        const res = await fetch(url, { cache: 'no-store' })
        const contentType = res.headers.get('content-type') || ''
        const looksLikeHtml = contentType.includes('text/html')
        if (!res.ok || looksLikeHtml) {
          console.error(`[voice] model file check FAILED for ${url}: status=${res.status} content-type=${contentType}`)
        } else {
          console.log(`[voice] model file OK: ${url} (${contentType}, ${res.headers.get('content-length')} bytes)`)
        }
      } catch (err) {
        console.error(`[voice] model file check errored for ${url}:`, err)
      }
    })
  )
}

async function getTranscriber(onProgress) {
  await purgeStaleModelCache()
  await verifyLocalModelFiles()
  if (!transcriberPromise) {
    transcriberPromise = import('@xenova/transformers').then(({ pipeline, env }) => {
      // Self-hosted under public/models/ - never reach out to huggingface.co
      // at runtime. This sidesteps Brave Shields / ad-blockers / corporate
      // filters that block the CDN request outright (confirmed via the
      // earlier raw-fetch sanity check: the direct fetch to huggingface.co
      // itself failed, so no client-side CDN-fetch config could fix this -
      // only serving the files ourselves does).
      env.allowRemoteModels = false
      env.allowLocalModels = true
      env.localModelPath = '/models/'
      env.useBrowserCache = true
      console.log('[voice] transformers env:', env)
      return pipeline('automatic-speech-recognition', WHISPER_MODEL_ID, {
        progress_callback: onProgress,
      })
    })
  }
  return transcriberPromise
}

// Decodes a recorded audio Blob into the 16kHz mono Float32 samples the
// Whisper pipeline expects. AudioContext resamples to the context's own
// sampleRate during decodeAudioData, so constructing it at 16000Hz upfront
// does the resampling for us regardless of the mic's native rate.
async function decodeToWhisperInput(audioBlob) {
  const AudioContextImpl = window.AudioContext || window.webkitAudioContext
  const audioContext = new AudioContextImpl({ sampleRate: 16000 })
  try {
    const arrayBuffer = await audioBlob.arrayBuffer()
    const decoded = await audioContext.decodeAudioData(arrayBuffer)
    return decoded.getChannelData(0)
  } finally {
    audioContext.close().catch(() => {})
  }
}

export async function transcribeWithWhisper(audioBlob, onProgress) {
  console.log('[voice] transcribeWithWhisper starting, model:', WHISPER_MODEL_ID)
  let transcriber, audioInput
  try {
    ;[transcriber, audioInput] = await Promise.all([getTranscriber(onProgress), decodeToWhisperInput(audioBlob)])
  } catch (err) {
    console.warn('[voice] Whisper transcriber/audio setup failed:', err)
    throw err
  }
  const result = await transcriber(audioInput)
  console.log('[voice] Whisper transcription complete')
  return (result?.text || '').trim()
}
