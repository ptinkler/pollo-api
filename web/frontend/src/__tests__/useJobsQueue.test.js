/**
 * Tests for composables/useJobsQueue.js
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// We need to mock useApi before importing useJobsQueue
vi.mock('../composables/useApi.js', () => ({
  fetchJob: vi.fn(),
  fetchJobs: vi.fn(),
}))

import { useJobsQueue } from '../composables/useJobsQueue.js'
import { fetchJob } from '../composables/useApi.js'

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  // Reset the queue state between tests
  const { activeJobs, cleanup } = useJobsQueue()
  cleanup()
  activeJobs.value = []
})

afterEach(() => {
  const { cleanup } = useJobsQueue()
  cleanup()
  vi.useRealTimers()
})

describe('useJobsQueue', () => {
  it('returns expected interface', () => {
    const queue = useJobsQueue()
    expect(queue.activeJobs).toBeDefined()
    expect(queue.isMinimized).toBeDefined()
    expect(queue.runningJobs).toBeDefined()
    expect(queue.hasRunningJobs).toBeDefined()
    expect(typeof queue.addJob).toBe('function')
    expect(typeof queue.dismissJob).toBe('function')
    expect(typeof queue.dismissAllCompleted).toBe('function')
    expect(typeof queue.toggleMinimized).toBe('function')
    expect(typeof queue.initialize).toBe('function')
    expect(typeof queue.cleanup).toBe('function')
    expect(typeof queue.setNotifyCallback).toBe('function')
    expect(typeof queue.onJobComplete).toBe('function')
  })

  it('addJob adds to activeJobs', () => {
    const { activeJobs, addJob } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'Working...' })
    addJob('j1', 'pollodance20', 'test prompt', 'myproj')
    expect(activeJobs.value).toHaveLength(1)
    expect(activeJobs.value[0].jobId).toBe('j1')
    expect(activeJobs.value[0].model).toBe('pollodance20')
    expect(activeJobs.value[0].project).toBe('myproj')
    expect(activeJobs.value[0].status).toBe('sending')
  })

  it('addJob truncates long prompts', () => {
    const { activeJobs, addJob } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'Working...' })
    const longPrompt = 'a'.repeat(100)
    addJob('j1', 'pollodance20', longPrompt, 'myproj')
    expect(activeJobs.value[0].prompt.length).toBeLessThanOrEqual(63)
    expect(activeJobs.value[0].prompt).toContain('...')
  })

  it('addJob does not truncate short prompts', () => {
    const { activeJobs, addJob } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'test' })
    addJob('j1', 'pollodance20', 'short', 'myproj')
    expect(activeJobs.value[0].prompt).toBe('short')
  })

  it('dismissJob removes job and stops polling', () => {
    const { activeJobs, addJob, dismissJob } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'Working...' })
    addJob('j1', 'pollodance20', 'test', 'proj')
    expect(activeJobs.value).toHaveLength(1)
    dismissJob('j1')
    expect(activeJobs.value).toHaveLength(0)
  })

  it('dismissAllCompleted removes done and error jobs', () => {
    const { activeJobs, addJob, dismissAllCompleted } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'test' })
    addJob('j1', 'pollodance20', 'a', 'p')
    addJob('j2', 'pollodance20', 'b', 'p')
    addJob('j3', 'pollodance20', 'c', 'p')
    // Mark some as completed (find by jobId since unshift reverses order)
    activeJobs.value.find(j => j.jobId === 'j1').status = 'done'
    activeJobs.value.find(j => j.jobId === 'j2').status = 'error'
    activeJobs.value.find(j => j.jobId === 'j3').status = 'processing'
    dismissAllCompleted()
    expect(activeJobs.value).toHaveLength(1)
    expect(activeJobs.value[0].jobId).toBe('j3')
  })

  it('toggleMinimized toggles state', () => {
    const { isMinimized, toggleMinimized } = useJobsQueue()
    const initial = isMinimized.value
    toggleMinimized()
    expect(isMinimized.value).toBe(!initial)
    toggleMinimized()
    expect(isMinimized.value).toBe(initial)
  })

  it('runningJobs filters correctly', () => {
    const { activeJobs, addJob, runningJobs } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'test' })
    addJob('j1', 'pollodance20', 'a', 'p')
    addJob('j2', 'pollodance20', 'b', 'p')
    activeJobs.value[0].status = 'done'
    expect(runningJobs.value).toHaveLength(1)
  })

  it('hasRunningJobs returns correct boolean', () => {
    const { activeJobs, addJob, hasRunningJobs } = useJobsQueue()
    expect(hasRunningJobs.value).toBe(false)
    fetchJob.mockResolvedValue({ status: 'processing', message: 'test' })
    addJob('j1', 'pollodance20', 'a', 'p')
    expect(hasRunningJobs.value).toBe(true)
    activeJobs.value[0].status = 'done'
    expect(hasRunningJobs.value).toBe(false)
  })

  it('polling updates job status on done', async () => {
    const { activeJobs, addJob, setNotifyCallback } = useJobsQueue()
    const notify = vi.fn()
    setNotifyCallback(notify)

    fetchJob.mockResolvedValue({
      status: 'done',
      message: 'Ready!',
      video_path: '/path/video.mp4',
    })

    addJob('j1', 'pollodance20', 'test', 'p')
    // pollJob is called immediately in addJob -> startPolling
    await vi.runAllTimersAsync()

    expect(activeJobs.value[0].status).toBe('done')
    expect(notify).toHaveBeenCalledWith('Video ready! 🎉', 'success')
  })

  it('polling updates job status on error', async () => {
    const { activeJobs, addJob, setNotifyCallback } = useJobsQueue()
    const notify = vi.fn()
    setNotifyCallback(notify)

    fetchJob.mockResolvedValue({
      status: 'error',
      message: 'Generation failed',
    })

    addJob('j1', 'pollodance20', 'test', 'p')
    await vi.runAllTimersAsync()

    expect(activeJobs.value[0].status).toBe('error')
    expect(notify).toHaveBeenCalledWith(
      expect.stringContaining('Generation failed'),
      'error',
      5000
    )
  })

  it('onJobComplete callback fires on done', async () => {
    const { addJob, onJobComplete } = useJobsQueue()
    const callback = vi.fn()
    const unsubscribe = onJobComplete(callback)

    fetchJob.mockResolvedValue({
      status: 'done',
      message: 'Ready!',
      video_path: '/path/video.mp4',
    })

    addJob('j1', 'pollodance20', 'test', 'p')
    await vi.runAllTimersAsync()

    expect(callback).toHaveBeenCalledWith(expect.objectContaining({ status: 'done' }))
    
    // Unsubscribe should work
    unsubscribe()
  })

  it('cleanup stops all polling', () => {
    const { addJob, cleanup } = useJobsQueue()
    fetchJob.mockResolvedValue({ status: 'processing', message: 'test' })
    addJob('j1', 'pollodance20', 'a', 'p')
    addJob('j2', 'pollodance20', 'b', 'p')
    // Should not throw
    cleanup()
  })
})

