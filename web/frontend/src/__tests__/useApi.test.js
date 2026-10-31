/**
 * Tests for composables/useApi.js — the HTTP client helpers.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
globalThis.fetch = mockFetch

import { apiGet, apiPost, apiPut, apiDelete } from '../composables/useApi.js'

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
    mockFetch.mockRejectedValueOnce(new Error('Network error')).mockReturnValueOnce(mockOkResponse({ recovered: true }))
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
    const data = await apiPost('/api/thing', { name: 'Test' })
    expect(data).toEqual({ created: true })
    const [, opts] = mockFetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ name: 'Test' })
  })

  it("surfaces the error body's detail", async () => {
    mockFetch.mockReturnValueOnce(mockErrorResponse(400))
    await expect(apiPost('/api/thing', {})).rejects.toThrow('error')
  })
})

// ── apiPut ──────────────────────────────────────────────────────────

describe('apiPut', () => {
  it('sends PUT request', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ updated: true }))
    const data = await apiPut('/api/thing/test', { name: 'New' })
    expect(data).toEqual({ updated: true })
    expect(mockFetch.mock.calls[0][1].method).toBe('PUT')
  })
})

// ── apiDelete ───────────────────────────────────────────────────────

describe('apiDelete', () => {
  it('sends DELETE request', async () => {
    mockFetch.mockReturnValueOnce(mockOkResponse({ deleted: true }))
    const data = await apiDelete('/api/thing/123')
    expect(data).toEqual({ deleted: true })
    expect(mockFetch.mock.calls[0][1].method).toBe('DELETE')
  })
})
