const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

export async function fetchOptions() {
  const res = await fetch(`${API_BASE}/options`)
  if (!res.ok) throw new Error('Failed to load options')
  return res.json()
}

export async function createJob(formData) {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    body: formData,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create job')
  }
  return res.json()
}

export async function getJob(jobId) {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`)
  if (!res.ok) throw new Error('Failed to fetch job')
  return res.json()
}

export function getArtifactDownloadUrl(jobId, artifactId) {
  return `${API_BASE}/jobs/${jobId}/artifacts/${artifactId}/download`
}
