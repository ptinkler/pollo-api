/**
 * Tests for composables/useApi.js — API client functions
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

// Now import the module under test
import {
  apiGet, apiPost, apiPut, apiDelete,
  fetchProjects, fetchProject, createProject, updateProject,
  fetchJobs, fetchJob, checkJob, downloadJobVideo,
  deleteJob, archiveJob, unarchiveJob,
  generateVideo, fetchModels, deleteVideo,
  getImageUrl, getVideoUrl, getVideoThumbUrl,
} from '../composables/useApi.js'

beforeEach(() => {
  mockFetch.mockReset()
})

function mockOkResponse(data) {
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(data),
  })
}

function mockErrorResponse(status) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve({ detail: 'error' }),
  })
}

// ── apiGet ──────────────────────────────────────────────────────────

describe('apiGet', () => {
  it('fetches data from endpoint', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ result: 'ok' }))
    const data = await apiGet('/api/test')
    expect(data).toEqual({ result: 'ok' })
    expect(mockFetch).toHaveBeenCalledWith('/api/test', expect.any(Object))
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockReturnValueOnce(mockErrorResponse(404))
    await expect(apiGet('/api/test')).rejects.toThrow('API error: 404')
  })

  it('retries on 500 errors', async () => {
    mockFetch
      .mockReturnValueOnce(Promise.resolve({ ok: false, status: 500 }))
      .mockReturnValueOnce(mockOkResponse({ retried: true }))
    const data = await apiGet('/api/test')
    expect(data).toEqual({ retried: true })
    expect(mockFetch).toHaveBeenCalledTimes(2)
  })

  it('retries on network errors', async () => {
    mockFetch
      .mockRejectedValueOnce(new Error('Network error'))
      .mockReturnValueOnce(mockOkResponse({ recovered: true }))
    const data = await apiGet('/api/test')
    expect(data).toEqual({ recovered: true })
  })

  it('throws after max retries', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'))
    await expect(apiGet('/api/test')).rejects.toThrow('Network error')
    // 1 initial + 3 retries = 4
    expect(mockFetch).toHaveBeenCalledTimes(4)
  })
})

// ── apiPost ─────────────────────────────────────────────────────────

describe('apiPost', () => {
  it('posts data with JSON content type', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ created: true }))
    const data = await apiPost('/api/projects', { name: 'Test' })
    expect(data).toEqual({ created: true })
    const [, opts] = mockFetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ name: 'Test' })
  })
})

// ── apiPut ──────────────────────────────────────────────────────────

describe('apiPut', () => {
  it('sends PUT request', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ updated: true }))
    const data = await apiPut('/api/projects/test', { name: 'New' })
    expect(data).toEqual({ updated: true })
    expect(mockFetch.mock.calls[0][1].method).toBe('PUT')
  })
})

// ── apiDelete ───────────────────────────────────────────────────────

describe('apiDelete', () => {
  it('sends DELETE request', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ deleted: true }))
    const data = await apiDelete('/api/jobs/123')
    expect(data).toEqual({ deleted: true })
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })
})

// ── Project API functions ───────────────────────────────────────────

describe('Project API', () => {
  it('fetchProjects calls correct endpoint', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse([]))
    await fetchProjects()
    expect(mockFetch.mock.calls[0][0]).toBe('/api/projects')
  })

  it('fetchProject with params', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ slug: 'test' }))
    await fetchProject('test', { archived: true })
    expect(mockFetch.mock.calls[0][0]).toContain('/api/projects/test')
    expect(mockFetch.mock.calls[0][0]).toContain('archived=true')
  })

  it('fetchProject without params', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ slug: 'test' }))
    await fetchProject('test')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/projects/test')
  })

  it('createProject sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ created: true }))
    await createProject({ name: 'New' })
    expect(mockFetch.mock.calls[0][1].method).toBe('POST')
  })

  it('updateProject sends PUT', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ updated: true }))
    await updateProject('test', { name: 'Updated' })
    expect(mockFetch.mock.calls[0][1].method).toBe('PUT')
  })

  it('encodes project name in URL', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await fetchProject('my project')
    expect(mockFetch.mock.calls[0][0]).toContain('my%20project')
  })
})

// ── Job API functions ───────────────────────────────────────────────

describe('Job API', () => {
  it('fetchJobs with params', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse([]))
    await fetchJobs({ active: true })
    expect(mockFetch.mock.calls[0][0]).toContain('active=true')
  })

  it('fetchJobs without params', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse([]))
    await fetchJobs()
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs')
  })

  it('fetchJob by ID', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ job_id: 'j1' }))
    await fetchJob('j1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs/j1')
  })

  it('checkJob sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await checkJob('j1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs/j1/check')
  })

  it('downloadJobVideo sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await downloadJobVideo('j1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs/j1/download')
  })

  it('deleteJob sends DELETE', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await deleteJob('j1')
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })

  it('archiveJob sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await archiveJob('j1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs/j1/archive')
  })

  it('unarchiveJob sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await unarchiveJob('j1')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/jobs/j1/unarchive')
  })
})

// ── Generate API ────────────────────────────────────────────────────

describe('Generate API', () => {
  it('generateVideo sends POST', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ job_id: 'j1' }))
    await generateVideo({ model: 'pollodance20', prompt: 'test' })
    expect(mockFetch.mock.calls[0][0]).toBe('/api/generate')
    expect(mockFetch.mock.calls[0][1].method).toBe('POST')
  })
})

// ── Models API ──────────────────────────────────────────────────────

describe('Models API', () => {
  it('fetchModels calls correct endpoint', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await fetchModels()
    expect(mockFetch.mock.calls[0][0]).toBe('/api/models')
  })
})

// ── Video API ───────────────────────────────────────────────────────

describe('Video API', () => {
  it('deleteVideo sends DELETE', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await deleteVideo('myproj', 'vid.mp4')
    expect(mockFetch.mock.calls[0][0]).toBe('/api/videos/myproj/vid.mp4')
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })

  it('encodes video filename', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({}))
    await deleteVideo('proj', 'my video.mp4')
    expect(mockFetch.mock.calls[0][0]).toContain('my%20video.mp4')
  })
})

// ── URL helpers ─────────────────────────────────────────────────────

describe('URL helpers', () => {
  it('getImageUrl without thumbTs', () => {
    expect(getImageUrl('proj')).toBe('/image/proj')
  })

  it('getImageUrl with thumbTs', () => {
    expect(getImageUrl('proj', '123')).toBe('/image/proj?t=123')
  })

  it('getVideoUrl', () => {
    expect(getVideoUrl('proj', 'vid.mp4')).toBe('/video/proj/vid.mp4')
  })

  it('getVideoThumbUrl', () => {
    expect(getVideoThumbUrl('proj', 'vid.mp4')).toBe('/video-thumb/proj/vid.mp4')
  })

  it('encodes special chars in URLs', () => {
    expect(getVideoUrl('my proj', 'my vid.mp4')).toBe('/video/my%20proj/my%20vid.mp4')
  })
})

