/**
 * Tests for composables/useToast.js
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useToast } from '../composables/useToast.js'

describe('useToast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with empty toasts', () => {
    const { toasts } = useToast()
    expect(toasts.value).toEqual([])
  })

  it('showToast adds a toast', () => {
    const { toasts, showToast } = useToast()
    showToast('Hello', 'success')
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('Hello')
    expect(toasts.value[0].type).toBe('success')
  })

  it('showToast auto-removes after duration', () => {
    const { toasts, showToast } = useToast()
    showToast('Temp', 'info', 2000)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(2000)
    expect(toasts.value).toHaveLength(0)
  })

  it('showToast returns an id', () => {
    const { showToast } = useToast()
    const id = showToast('Test')
    expect(typeof id).toBe('number')
  })

  it('removeToast removes specific toast', () => {
    const { toasts, showToast, removeToast } = useToast()
    const id1 = showToast('First')
    showToast('Second')
    removeToast(id1)
    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('Second')
  })

  it('removeToast ignores invalid id', () => {
    const { toasts, showToast, removeToast } = useToast()
    showToast('Only')
    removeToast(999)
    expect(toasts.value).toHaveLength(1)
  })

  it('multiple toasts have unique ids', () => {
    const { showToast } = useToast()
    const id1 = showToast('A')
    const id2 = showToast('B')
    const id3 = showToast('C')
    expect(new Set([id1, id2, id3]).size).toBe(3)
  })

  it('default type is success', () => {
    const { toasts, showToast } = useToast()
    showToast('Test')
    expect(toasts.value[0].type).toBe('success')
  })

  it('default duration is 3000', () => {
    const { toasts, showToast } = useToast()
    showToast('Test')
    vi.advanceTimersByTime(2999)
    expect(toasts.value).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(toasts.value).toHaveLength(0)
  })
})

