import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const active = vi.fn()
vi.mock('../composables/useChat', () => ({
  fetchActiveGenerations: (...a) => active(...a),
  chatMediaUrl: (c, f) => `/m/${c}/${f}`,
  chatMediaPreviewUrl: (c, f) => `/p/${c}/${f}`,
}))

// A fresh pending descriptor each call — never share a mutable object between
// polls/tests (poll does Object.assign on the stored entry).
const pend = (over = {}) => ({
  media_id: 'p1',
  message_id: 5,
  conversation_id: 'c',
  conversation_title: 'T',
  kind: 'image',
  status: 'pending',
  ...over,
})

describe('useGenQueue reconciliation', () => {
  beforeEach(() => {
    vi.resetModules()
    active.mockReset()
    localStorage.clear()
  })

  it('discovers pending gens, flips them to done, then clears them', async () => {
    const { useGenQueue } = await import('../composables/useGenQueue')
    const q = useGenQueue()
    active.mockResolvedValueOnce({ items: [pend()] })
    await q.refresh()
    expect(q.entries.value.map(e => e.media_id)).toEqual(['p1'])
    expect(q.pending.value).toBe(1)
    // next poll returns it finished — the same entry updates in place
    active.mockResolvedValueOnce({ items: [pend({ status: 'done', file: 'a.png' })] })
    await q.refresh()
    expect(q.entries.value[0].status).toBe('done')
    expect(q.pending.value).toBe(0)
    expect(q.done.value).toBe(1)
    q.clearDone()
    expect(q.entries.value).toHaveLength(0)
  })

  it('ignores finished gens it never tracked (history), keeps pending', async () => {
    const { useGenQueue } = await import('../composables/useGenQueue')
    const q = useGenQueue()
    active.mockResolvedValueOnce({
      items: [pend(), { media_id: 'old', message_id: 9, kind: 'image', status: 'done', file: 'o.png' }],
    })
    await q.refresh()
    expect(q.entries.value.map(e => e.media_id)).toEqual(['p1'])
  })

  it('drops a tracked item whose message was queried but no longer returned', async () => {
    const { useGenQueue } = await import('../composables/useGenQueue')
    const q = useGenQueue()
    active.mockResolvedValueOnce({ items: [pend()] })
    await q.refresh()
    expect(q.entries.value).toHaveLength(1)
    active.mockResolvedValueOnce({ items: [] }) // message 5 gone
    await q.refresh()
    expect(active).toHaveBeenLastCalledWith([5]) // it was asked about
    expect(q.entries.value).toHaveLength(0)
  })

  it('keeps the last state when the poll fails', async () => {
    const { useGenQueue } = await import('../composables/useGenQueue')
    const q = useGenQueue()
    active.mockResolvedValueOnce({ items: [pend()] })
    await q.refresh()
    active.mockRejectedValueOnce(new Error('offline'))
    await q.refresh()
    expect(q.entries.value).toHaveLength(1)
  })
})

describe('GenerationQueueDock', () => {
  const items = [
    pend(),
    { media_id: 'd1', conversation_id: 'c', conversation_title: 'T', kind: 'image', status: 'done', file: 'a.png' },
    { media_id: 'e1', conversation_id: 'c', conversation_title: 'T', kind: 'video', status: 'error', moderated: true },
  ]

  it('renders a row per item and labels each by status', async () => {
    const { default: Dock } = await import('../components/studio/GenerationQueueDock.vue')
    const w = mount(Dock, { props: { entries: items, pending: 1, done: 2 } })
    const rows = w.findAll('.qrow')
    expect(rows).toHaveLength(3)
    expect(rows[0].text()).toContain('Creating image…')
    expect(rows[1].find('img').attributes('src')).toBe('/p/c/a.png')
    expect(rows[2].text()).toContain('Blocked')
    expect(w.find('.qtitle').text()).toContain('1 generating')
  })

  it('emits open, clear and clear-one; hides when empty', async () => {
    const { default: Dock } = await import('../components/studio/GenerationQueueDock.vue')
    const w = mount(Dock, { props: { entries: items, pending: 1, done: 2 } })
    await w.find('.qrow').trigger('click')
    expect(w.emitted('open')[0][0].media_id).toBe('p1')
    await w.find('.qclear').trigger('click')
    expect(w.emitted('clear')).toBeTruthy()
    await w.findAll('.qx')[1].trigger('click')
    expect(w.emitted('clear-one')[0][0]).toBe('d1')

    const empty = mount(Dock, { props: { entries: [], pending: 0, done: 0 } })
    expect(empty.find('.qdock').exists()).toBe(false)
  })
})
