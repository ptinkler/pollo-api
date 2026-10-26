import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import MediaPicker from '../components/media/MediaPicker.vue'
import { useMediaFilters, mediaOrigin } from '../composables/useMedia'

const ITEMS = [
  {
    id: 'lib:a.png',
    kind: 'image',
    source: 'upload',
    origin: 'library',
    name: 'a.png',
    url: '/a',
    created_at: '2026-10-07',
  },
  {
    id: 'proj:p:v.mp4',
    kind: 'video',
    source: 'generated',
    origin: 'project',
    name: 'v.mp4',
    url: '/v',
    project: 'p',
    project_name: 'Trailer',
    prompt: 'a fox runs',
  },
  {
    id: 'chat:c:g.png',
    kind: 'image',
    source: 'generated',
    origin: 'chat',
    name: 'g.png',
    url: '/g',
    conversation_title: 'Fox chat',
    prompt: 'fox in snow',
  },
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
    filters.q = 'trailer' // matches where it's from
    expect(filtered.value.map(i => i.id)).toEqual(['proj:p:v.mp4'])
  })

  it('names where an item is from', () => {
    expect(ITEMS.map(mediaOrigin)).toEqual(['Library', 'Trailer', 'Fox chat'])
    expect(mediaOrigin({ origin: 'orphan', conversation_title: 'Old chat' })).toBe('Old chat (orphaned)')
    expect(mediaOrigin({ origin: 'orphan' })).toBe('Orphaned')
  })
})

describe('MediaPicker', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async url => {
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
    expect(tiles).toHaveLength(2) // the video isn't offered
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

  it('opens on the origin it was given, widening it for an upload', async () => {
    const w = await open({ origin: 'chat' })
    expect(document.body.querySelector('select[aria-label="Where from"]').value).toBe('chat')
    expect(document.body.querySelectorAll('.tile')).toHaveLength(1)
    const input = document.body.querySelector('input[type=file]')
    Object.defineProperty(input, 'files', { value: [new File(['x'], 'n.png', { type: 'image/png' })] })
    input.dispatchEvent(new Event('change'))
    await flushPromises()
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
      constructor(cb) {
        trigger = cb
      }
      observe(el) {
        observed.push(el)
      }
      unobserve() {}
      disconnect() {}
    }
    const items = Array.from({ length: 130 }, (_, n) => ({
      id: `lib:${n}.png`,
      kind: 'image',
      source: 'upload',
      origin: 'library',
      name: `${n}.png`,
      url: `/full/${n}`,
      thumb_url: `/thumb/${n}`,
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

  it('asks the caller for more once every loaded tile is shown (server paging)', async () => {
    const { default: MediaGrid } = await import('../components/media/MediaGrid.vue')
    let trigger
    globalThis.IntersectionObserver = class {
      constructor(cb) {
        trigger = cb
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    // A full server page already loaded, with more rows waiting on the server
    const all = Array.from({ length: 80 }, (_, i) => ({ id: `lib:${i}.png`, kind: 'image', name: `${i}.png` }))
    const w = mount(MediaGrid, { props: { items: all.slice(0, 50), pageSize: 50, hasMore: true } })
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(50)
    trigger([{ isIntersecting: true }]) // reaching the end of the loaded page asks for the next
    await flushPromises()
    expect(w.emitted('more')).toHaveLength(1)
    // The parent appends the next page to the end — the window isn't reset to the top
    await w.setProps({ items: all, hasMore: false })
    trigger([{ isIntersecting: true }])
    await flushPromises()
    expect(w.findAll('.tile')).toHaveLength(80)
    expect(w.find('.sentinel').exists()).toBe(false) // nothing more to load
    delete globalThis.IntersectionObserver
    w.unmount()
  })
})

describe('MediaGrid thumbnails', () => {
  it('defaults to batches of 20, retries a failed thumbnail once, then shows a placeholder', async () => {
    vi.useFakeTimers()
    const { default: MediaGrid } = await import('../components/media/MediaGrid.vue')
    globalThis.IntersectionObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    const items = Array.from({ length: 30 }, (_, n) => ({
      id: `lib:${n}.png`,
      kind: 'image',
      source: 'upload',
      origin: 'library',
      name: `${n}.png`,
      thumb_url: `/thumb/${n}`,
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
      const body = u.includes('/api/media/blocked/clear')
        ? { cleared: 3 }
        : u.includes('/api/media/blocked')
          ? blocked
          : u.includes('/api/characters')
            ? { characters: [] }
            : { items: ITEMS }
      return { ok: true, status: 200, json: async () => body }
    })
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const MediaView = (await import('../views/MediaView.vue')).default
    const r = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/media', name: 'media', component: MediaView }],
    })
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

  const tiles = w => w.findAll('.tile')
  const ticked = w => tiles(w).map(t => t.classes().includes('selected'))

  it('ticking a tile’s circle starts selecting; then clicks toggle', async () => {
    const { w } = await mountView()
    expect(w.find('.selection-bar').exists()).toBe(false)
    await tiles(w)[1].find('.check').trigger('click')
    expect(ticked(w)).toEqual([false, true, false])
    expect(w.find('.selection-bar').text()).toContain('1 selected')
    await tiles(w)[0].trigger('click') // selecting now: a click toggles rather than opens
    expect(ticked(w)).toEqual([true, true, false])
    expect(document.querySelector('.preview')).toBeNull()
    w.unmount()
  })

  it('shift-click selects a range; select all and clear', async () => {
    const { w } = await mountView()
    await tiles(w)[0].find('.check').trigger('click')
    await tiles(w)[2].trigger('click', { shiftKey: true })
    expect(ticked(w)).toEqual([true, true, true])
    await w.find('.selection-bar button.btn-secondary').trigger('click') // Clear (all are selected)
    expect(w.find('.selection-bar').exists()).toBe(false)
    await w.find('.bar .btn-secondary:last-child').trigger('click') // Select (touch screens)
    const selectAll = w.findAll('.selection-bar button').find(b => b.text().startsWith('Select all'))
    await selectAll.trigger('click')
    expect(ticked(w)).toEqual([true, true, true])
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(ticked(w)).toEqual([false, false, false])
    w.unmount()
  })

  it('deletes the selection in one go', async () => {
    const { w, calls } = await mountView()
    await tiles(w)[0].find('.check').trigger('click')
    await tiles(w)[2].trigger('click')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    await w.find('.selection-bar .btn-danger').trigger('click')
    await flushPromises()
    expect(calls.filter(([m]) => m === 'DELETE')).toHaveLength(2)
    expect(tiles(w)).toHaveLength(1)
    w.unmount()
  })

  it('hides the button when nothing was blocked', async () => {
    const { w } = await mountView({}, { moderated: 0, black: 0 })
    expect(w.find('.clear-blocked').exists()).toBe(false)
    w.unmount()
  })
})
