import { useEffect, useMemo, useState } from 'react'
import { createJob, fetchOptions, getArtifactDownloadUrl, getJob } from '../api/client'
import OptionField from '../components/OptionField'

const defaultOutputFormats = ['txt', 'srt', 'vtt', 'json']

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
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [jobId, setJobId] = useState('')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    fetchOptions().then(setOptions).catch((e) => setError(e.message))
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

  const handleCoreChange = (key, value) => {
    setCoreValues((prev) => ({ ...prev, [key]: value }))
  }

  const handleAdvancedChange = (key, value) => {
    setAdvancedValues((prev) => ({ ...prev, [key]: value }))
  }

  const submitJob = async (e) => {
    e.preventDefault()
    setError('')
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
      formData.append('output_formats', defaultOutputFormats.join(','))
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
            <button
              type="button"
              role="radio"
              aria-checked={coreValues.compute_device === 'cpu'}
              className={`compute-chip ${coreValues.compute_device === 'cpu' ? 'active' : ''}`}
              onClick={() => handleCoreChange('compute_device', 'cpu')}
            >
              CPU
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={coreValues.compute_device === 'nvidia_gpu'}
              className={`compute-chip ${coreValues.compute_device === 'nvidia_gpu' ? 'active' : ''}`}
              onClick={() => handleCoreChange('compute_device', 'nvidia_gpu')}
            >
              NVIDIA GPU
            </button>
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
