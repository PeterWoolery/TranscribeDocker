import { useEffect, useMemo, useState } from 'react'
import { createJob, fetchOptions, getArtifactDownloadUrl, getJob } from '../api/client'
import OptionField from '../components/OptionField'

const defaultOutputFormats = ['txt', 'srt', 'vtt', 'json']
const outputFormatChoices = [
  { key: 'txt', label: 'TXT', help: 'Plain transcript with inline timestamps.' },
  { key: 'srt', label: 'SRT', help: 'Subtitle file for media players and editors.' },
  { key: 'vtt', label: 'VTT', help: 'Web subtitle format for browsers and players.' },
  { key: 'json', label: 'JSON', help: 'Structured segments with timing metadata.' },
]

function formatTime(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds))) return '--:--'
  const value = Math.max(0, Math.floor(Number(seconds)))
  const hours = Math.floor(value / 3600)
  const minutes = Math.floor((value % 3600) / 60)
  const secs = value % 60
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

export default function App() {
  const [options, setOptions] = useState({ core: [], advanced: [] })
  const [sourceType, setSourceType] = useState('upload')
  const [sourceUrl, setSourceUrl] = useState('')
  const [file, setFile] = useState(null)
  const [coreValues, setCoreValues] = useState({ task: 'transcribe', language: 'auto', model: 'medium', engine_mode: 'auto_fallback', compute_device: 'cpu' })
  const [advancedValues, setAdvancedValues] = useState({ beam_size: 5, best_of: 5, temperature: 0, vad_filter: true, compute_type: 'int8', diarization: false })
  const [outputFormats, setOutputFormats] = useState(defaultOutputFormats)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [jobId, setJobId] = useState('')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    fetchOptions().then((catalog) => {
      setOptions(catalog)
      const device = catalog.core.find((option) => option.key === 'compute_device')?.default
      if (device) setCoreValues((prev) => ({ ...prev, compute_device: device }))
    }).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!jobId) return
    const pull = async () => {
      try {
        const nextJob = await getJob(jobId)
        setJob(nextJob)
      } catch (e) {
        setError(e.message)
      }
    }
    pull()
    const id = setInterval(pull, 2500)
    return () => clearInterval(id)
  }, [jobId])

  const finished = useMemo(() => job && ['completed', 'failed', 'cancelled'].includes(job.status), [job])
  const displayedProgress = job?.progress_percent ?? job?.progress ?? 0
  const hasTiming = job?.current_time_sec != null && job?.duration_sec != null
  const progressLabel = hasTiming
    ? `${formatTime(job.current_time_sec)} / ${formatTime(job.duration_sec)}`
    : `${displayedProgress}%`
  const etaLabel = job?.eta_seconds != null && job.eta_seconds > 0 ? formatTime(job.eta_seconds) : null
  const etaDisplay = etaLabel
    ? `~${etaLabel}`
    : job?.status === 'completed'
      ? 'Done'
      : hasTiming
        ? 'Calculating...'
        : 'N/A'
  const debugArtifact = useMemo(
    () => job?.artifacts?.find((artifact) => artifact.file_name.startsWith('debug-source')),
    [job],
  )
  const debugArtifactUrl = debugArtifact ? getArtifactDownloadUrl(job.id, debugArtifact.id) : ''
  const debugIsVideo = Boolean(debugArtifact?.content_type?.startsWith('video/'))
  const debugIsAudio = Boolean(debugArtifact?.content_type?.startsWith('audio/'))

  const handleCoreChange = (key, value) => {
    setCoreValues((prev) => ({ ...prev, [key]: value }))
  }

  const handleAdvancedChange = (key, value) => {
    setAdvancedValues((prev) => ({ ...prev, [key]: value }))
  }

  const handleOutputFormatToggle = (format) => {
    setOutputFormats((prev) => (
      prev.includes(format)
        ? prev.filter((value) => value !== format)
        : [...prev, format]
    ))
  }

  const submitJob = async (e) => {
    e.preventDefault()
    setError('')
    if (outputFormats.length === 0) {
      setError('Select at least one output format.')
      return
    }
    setIsSubmitting(true)
    try {
      const formData = new FormData()
      formData.append('source_type', sourceType)
      if (sourceType === 'url') {
        formData.append('source_url', sourceUrl)
      }
      if (sourceType === 'upload' && file) {
        formData.append('file', file)
      }
      formData.append('task', coreValues.task)
      formData.append('language', coreValues.language)
      formData.append('model', coreValues.model)
      formData.append('engine_mode', coreValues.engine_mode)
      const mergedAdvanced = {
        ...advancedValues,
        compute_device: coreValues.compute_device || 'cpu',
      }
      formData.append('diarization', String(Boolean(advancedValues.diarization)))
      if (advancedValues.diarization_min_speakers) {
        formData.append('diarization_min_speakers', String(advancedValues.diarization_min_speakers))
      }
      if (advancedValues.diarization_max_speakers) {
        formData.append('diarization_max_speakers', String(advancedValues.diarization_max_speakers))
      }
      formData.append('output_formats', outputFormats.join(','))
      formData.append('advanced', JSON.stringify(mergedAdvanced))
      formData.append('metadata', JSON.stringify({ submitted_from: 'web' }))

      const created = await createJob(formData)
      setJobId(created.job_id)
      setJob(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-1" />
      <div className="ambient ambient-2" />

      <section className="hero card">
        <div>
          <p className="eyebrow">TranscribeDocker</p>
          <h1>Transcribe anything with timestamp precision.</h1>
          <p className="sub">Upload media or paste YouTube/direct URLs, then export polished transcripts in TXT, SRT, VTT, and JSON.</p>
        </div>
        <div className="hero-meta">
          <div>
            <strong>Modes</strong>
            <span>Transcribe / Translate</span>
          </div>
          <div>
            <strong>Engines</strong>
            <span>Local Whisper + OpenAI Fallback</span>
          </div>
          <div>
            <strong>Retention</strong>
            <span>30-day transcript history</span>
          </div>
        </div>
      </section>

      <section className="grid">
        <form className="panel card" onSubmit={submitJob}>
          <header className="panel-head">
            <h2>New Job</h2>
            <span className="pill">Core + Advanced</span>
          </header>

          <div className="compute-chip-group" role="radiogroup" aria-label="Compute device">
            {[
              ['cpu', 'CPU'],
              ['nvidia_gpu', 'NVIDIA GPU'],
              ['amd_vulkan', 'AMD Vulkan'],
            ].map(([device, label]) => (
              <label key={device} className={`compute-chip ${coreValues.compute_device === device ? 'active' : ''}`}>
                <input
                  type="radio"
                  name="compute_device"
                  value={device}
                  checked={coreValues.compute_device === device}
                  onChange={() => handleCoreChange('compute_device', device)}
                />
                {label}
              </label>
            ))}
          </div>

          <div className="source-toggle" role="tablist" aria-label="Source type">
            <button type="button" className={sourceType === 'upload' ? 'active' : ''} onClick={() => setSourceType('upload')}>Upload File</button>
            <button type="button" className={sourceType === 'url' ? 'active' : ''} onClick={() => setSourceType('url')}>Paste Link</button>
          </div>

          {sourceType === 'upload' ? (
            <label className="field">
              <span>Media File</span>
              <input type="file" accept="audio/*,video/*" onChange={(e) => setFile(e.target.files?.[0] || null)} required={sourceType === 'upload'} />
            </label>
          ) : (
            <label className="field">
              <span>Source URL</span>
              <input type="url" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." required={sourceType === 'url'} />
            </label>
          )}

          <div className="options-grid">
            {options.core.filter((option) => option.key !== 'compute_device').map((option) => (
              <OptionField key={option.key} option={option} value={coreValues[option.key]} onChange={handleCoreChange} />
            ))}
          </div>

          <fieldset className="format-section">
            <legend>Output Formats</legend>
            <p className="format-help">Choose which transcript artifacts to generate.</p>
            <div className="format-grid">
              {outputFormatChoices.map((format) => (
                <label key={format.key} className={`format-card ${outputFormats.includes(format.key) ? 'active' : ''}`}>
                  <input
                    type="checkbox"
                    checked={outputFormats.includes(format.key)}
                    onChange={() => handleOutputFormatToggle(format.key)}
                  />
                  <span>{format.label}</span>
                  <small>{format.help}</small>
                </label>
              ))}
            </div>
          </fieldset>

          <button type="button" className="advanced-toggle" onClick={() => setShowAdvanced((v) => !v)}>
            {showAdvanced ? 'Hide Advanced Settings' : 'Show Advanced Settings'}
          </button>

          {showAdvanced && (
            <div className="options-grid advanced">
              {options.advanced.map((option) => (
                <OptionField key={option.key} option={option} value={advancedValues[option.key]} onChange={handleAdvancedChange} />
              ))}
            </div>
          )}

          <button className="submit" type="submit" disabled={isSubmitting}>{isSubmitting ? 'Submitting...' : 'Start Transcription'}</button>
        </form>

        <aside className="panel card status-panel">
          <header className="panel-head">
            <h2>Job Status</h2>
            {job?.stage && <span className={`status-chip status-${job.status}`}>{job.stage.replaceAll('_', ' ')}</span>}
          </header>

          {!jobId && <p className="muted">Submit a job to view live progress and artifact downloads.</p>}
          {jobId && (
            <>
              <p className="job-id"><strong>Job ID:</strong> {jobId}</p>
              {job && (
                <>
                  <div className="progress-wrap" aria-label="Progress">
                    <div className="progress-bar" style={{ width: `${displayedProgress}%` }} />
                  </div>
                  <div className="status-grid">
                    <p><strong>Status</strong><span>{job.status_detail || job.status}</span></p>
                    <p><strong>Progress</strong><span>{progressLabel}</span></p>
                    <p><strong>ETA</strong><span>{etaDisplay}</span></p>
                  </div>
                  {job.error_message && <p className="error">{job.error_message}</p>}

                  {finished && job.status === 'failed' && debugArtifact && (debugIsVideo || debugIsAudio) && (
                    <div className="downloads">
                      <h3>Failure Debug Media</h3>
                      {debugIsVideo ? (
                        <video controls preload="metadata" src={debugArtifactUrl} className="debug-player" />
                      ) : (
                        <audio controls preload="metadata" src={debugArtifactUrl} className="debug-player" />
                      )}
                      <a key={debugArtifact.id} href={debugArtifactUrl} target="_blank" rel="noreferrer">
                        <span>{debugArtifact.file_name}</span>
                        <small>{Math.round(debugArtifact.size_bytes / 1024)} KB</small>
                      </a>
                    </div>
                  )}

                  {finished && job.status === 'completed' && (
                    <div className="downloads">
                      <h3>Artifacts</h3>
                      {job.artifacts?.map((artifact) => (
                        <a key={artifact.id} href={getArtifactDownloadUrl(job.id, artifact.id)} target="_blank" rel="noreferrer">
                          <span>{artifact.file_name}</span>
                          <small>{Math.round(artifact.size_bytes / 1024)} KB</small>
                        </a>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
          {error && <p className="error">{error}</p>}
        </aside>
      </section>
    </main>
  )
}
