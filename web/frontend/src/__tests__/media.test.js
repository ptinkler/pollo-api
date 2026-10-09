import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import MediaPicker from '../components/media/MediaPicker.vue'
import { useMediaFilters, mediaOrigin } from '../composables/useMedia'

const ITEMS = [
  { id: 'lib:a.png', kind: 'image', source: 'upload', origin: 'library', name: 'a.png', url: '/a', created_at: '2026-10-07' },
  { id: 'proj:p:v.mp4', kind: 'video', source: 'generated', origin: 'project', name: 'v.mp4', url: '/v',
    project: 'p', project_name: 'Trailer', prompt: 'a fox runs' },
  { id: 'chat:c:g.png', kind: 'image', source: 'generated', origin: 'chat', name: 'g.png', url: '/g',
    conversation_title: 'Fox chat', prompt: 'fox in snow' },
]

describe('useMediaFilters', () => {
  it('filters by kind, source, origin and search', () => {
    const { filters, filtered } = useMediaFilters(ref(ITEMS))
    expect(filtered.value).toHaveLength(3)
    filters.kind = 'image'
    expect(filtered.value.map(i => i.id)).toEqual(['lib:a.png', 'chat:c:g.png'])
    filters.source = 'generated'
    expect(filtered.value.map(i => i.id)).toEqual(['chat:c:g.png'])
    filters.kind = 'all'
    filters.source = 'all'
    filters.q = 'trailer'   // matches where it's from
    expect(filtered.value.map(i => i.id)).toEqual(['proj:p:v.mp4'])
  })

  it('names where an item is from', () => {
    expect(ITEMS.map(mediaOrigin)).toEqual(['Library', 'Trailer', 'Fox chat'])
  })
})

describe('MediaPicker', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (url) => {
      const body = String(url).endsWith('/api/media/upload')
        ? { id: 'lib:new.png', kind: 'image', source: 'upload', origin: 'library', name: 'new.png', url: '/n' }
        : { items: ITEMS }
      return { ok: true, status: 200, json: async () => body }
    })
  })

  async function open(props = {}) {
    const w = mount(MediaPicker, { props: { open: false, ...props }, attachTo: document.body })
    await w.setProps({ open: true })
    await flushPromises()
    return w
  }

  it('offers only images and emits the picked ones', async () => {
    const w = await open()
    const tiles = document.body.querySelectorAll('.tile')
    expect(tiles).toHaveLength(2)                     // the video isn't offered
    tiles[0].click()
    tiles[1].click()
    await flushPromises()
    document.body.querySelector('.actions .btn-primary').click()
    expect(w.emitted('pick')[0][0].map(i => i.id)).toEqual(['lib:a.png', 'chat:c:g.png'])
    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('single mode swaps the selection', async () => {
    const w = await open({ multiple: false })
    const tiles = document.body.querySelectorAll('.tile')
    tiles[0].click()
    tiles[1].click()
    await flushPromises()
    expect(document.body.querySelectorAll('.tile.selected')).toHaveLength(1)
    w.unmount()
  })

  it('uploads go to the library and come back selected', async () => {
    const w = await open()
    const input = document.body.querySelector('input[type=file]')
    Object.defineProperty(input, 'files', { value: [new File(['x'], 'n.png', { type: 'image/png' })] })
    input.dispatchEvent(new Event('change'))
    await flushPromises()
    expect(document.body.querySelectorAll('.tile.selected')).toHaveLength(1)
    expect(document.body.querySelectorAll('.tile')).toHaveLength(3)
    w.unmount()
  })
})

describe('MediaGrid lazy rendering', () => {
  it('renders a batch of thumbnail tiles, then more as the end scrolls into view', async () => {
    const { default: MediaGrid } = await import('../components/media/MediaGrid.vue')
    let trigger
    const observed = []
    globalThis.IntersectionObserver = class {
      constructor(cb) { trigger = cb }
      observe(el) { observed.push(el) }
      unobserve() {}
      disconnect() {}
    }
    const items = Array.from({ length: 130 }, (_, n) => ({
      id: `lib:${n}.png`, kind: 'image', source: 'upload', origin: 'library', name: `${n}.png`,
      url: `/full/${n}`, thumb_url: `/thumb/${n}`,
    }))
    const w = mount(MediaGrid, { props: { items, pageSize: 50 } })
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(50)
    // Tiles use the small thumbnail and load lazily — never the full file
    const img = w.find('.tile img')
    expect(img.attributes('src')).toBe('/thumb/0')
    expect(img.attributes('loading')).toBe('lazy')
    trigger([{ isIntersecting: true }])
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(100)
    trigger([{ isIntersecting: true }])
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(130)
    expect(w.find('.sentinel').exists()).toBe(false)
    // New filter results start from the first page again
    await w.setProps({ items: items.slice(0, 80) })
    expect(w.findAll('.tile')).toHaveLength(50)
    delete globalThis.IntersectionObserver
    w.unmount()
  })
})


describe('MediaGrid thumbnails', () => {
  it('defaults to batches of 20, retries a failed thumbnail once, then shows a placeholder', async () => {
    vi.useFakeTimers()
    const { default: MediaGrid } = await import('../components/media/MediaGrid.vue')
    globalThis.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} }
    const items = Array.from({ length: 30 }, (_, n) => ({
      id: `lib:${n}.png`, kind: 'image', source: 'upload', origin: 'library', name: `${n}.png`, thumb_url: `/thumb/${n}`,
    }))
    const w = mount(MediaGrid, { props: { items } })
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(20)
    const img = w.find('.tile img')
    await img.trigger('error')
    vi.advanceTimersByTime(2000)
    expect(img.element.getAttribute('src')).toBe('/thumb/0?retry=1')
    await img.trigger('error')
    expect(w.findAll('.tile')[0].find('.no-thumb').exists()).toBe(true)
    delete globalThis.IntersectionObserver
    vi.useRealTimers()
    w.unmount()
  })
})

describe('MediaView', () => {
  async function mountView(query = {}, blocked = { moderated: 2, black: 1 }) {
    const calls = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      calls.push([opts.method || 'GET', String(url)])
      const u = String(url)
      const body = u.includes('/api/media/blocked/clear') ? { cleared: 3 }
        : u.includes('/api/media/blocked') ? blocked
        : u.includes('/api/characters') ? []
        : { items: ITEMS }
      return { ok: true, status: 200, json: async () => body }
    })
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const MediaView = (await import('../views/MediaView.vue')).default
    const r = createRouter({ history: createMemoryHistory(), routes: [{ path: '/media', name: 'media', component: MediaView }] })
    r.push({ name: 'media', query })
    await r.isReady()
    const w = mount({ template: '<router-view />' }, { global: { plugins: [r], provide: { showToast: () => {} } } })
    await flushPromises()
    return { w, calls }
  }

  it('opens filtered to chats from the chat sidebar link', async () => {
    const { w } = await mountView({ origin: 'chat' })
    expect(w.find('select[aria-label="Where from"]').element.value).toBe('chat')
    w.unmount()
  })

  it('clears blocked generations after confirming', async () => {
    const { w, calls } = await mountView()
    const btn = w.find('.clear-blocked')
    expect(btn.text()).toContain('Clear blocked (3)')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await btn.trigger('click')
    await flushPromises()
    expect(calls).toContainEqual(['POST', '/api/media/blocked/clear'])
    w.unmount()
  })

  it('hides the button when nothing was blocked', async () => {
    const { w } = await mountView({}, { moderated: 0, black: 0 })
    expect(w.find('.clear-blocked').exists()).toBe(false)
    w.unmount()
  })
})
