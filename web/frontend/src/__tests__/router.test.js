/**
 * Tests for router/index.js
 */
import { describe, it, expect } from 'vitest'
import router from '../router/index.js'

describe('Router', () => {
  it('has home route', () => {
    const home = router.getRoutes().find(r => r.name === 'home')
    expect(home).toBeDefined()
    expect(home.path).toBe('/')
  })

  it('has project generate route', () => {
    const route = router.getRoutes().find(r => r.name === 'project-generate')
    expect(route).toBeDefined()
    expect(route.meta.tab).toBe('generate')
  })

  it('has project gallery route', () => {
    const route = router.getRoutes().find(r => r.name === 'project-gallery')
    expect(route).toBeDefined()
    expect(route.meta.tab).toBe('gallery')
  })

  it('has project video route', () => {
    const route = router.getRoutes().find(r => r.name === 'project-video')
    expect(route).toBeDefined()
    expect(route.meta.tab).toBe('gallery')
  })

  it('has project history route', () => {
    const route = router.getRoutes().find(r => r.name === 'project-history')
    expect(route).toBeDefined()
    expect(route.meta.tab).toBe('history')
  })

  it('has project archive route', () => {
    const route = router.getRoutes().find(r => r.name === 'project-archive')
    expect(route).toBeDefined()
    expect(route.meta.tab).toBe('archive')
  })

  it('has catch-all route', () => {
    const catchAll = router.getRoutes().find(r => r.path === '/:pathMatch(.*)*')
    expect(catchAll).toBeDefined()
  })
})

import { mount as mountChat, flushPromises as flushChat } from '@vue/test-utils'
import { createRouter as createChatRouter, createMemoryHistory } from 'vue-router'

describe('ChatView balances', () => {
  it('shows the OpenRouter and Pollo balances at the top', async () => {
    globalThis.fetch = vi.fn(async url => ({
      ok: true,
      status: 200,
      json: async () =>
        String(url).includes('/api/chat/credits')
          ? { total_credits: 60, total_usage: 52.79, remaining: 7.21 }
          : String(url).includes('/api/usage/balance')
            ? { availableCredits: 12345, totalCredits: 20000 }
            : String(url).includes('/models')
              ? { text: [], image: [], video: [], errors: {} }
              : String(url).includes('/instructions')
                ? { instructions: [] }
                : String(url).includes('/conversations')
                  ? { conversations: [] }
                  : { configured: true },
    }))
    const ChatView = (await import('../views/ChatView.vue')).default
    const r = createChatRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', name: 'chat', component: ChatView },
        { path: '/usage', name: 'usage', component: { template: '<div />' } },
      ],
    })
    r.push('/chat')
    await r.isReady()
    const w = mountChat({ template: '<router-view />' }, { global: { plugins: [r] } })
    await flushChat()
    const chips = w.findAll('.balance').map(b => b.text())
    expect(chips).toEqual(['OpenRouter $7.21', 'Pollo 12,345'])
    w.unmount()
  })
})

describe('ChatView sidebar sections', () => {
  it('fold away, show a summary and stay folded', async () => {
    localStorage.removeItem('chat.folded')
    globalThis.fetch = vi.fn(async url => ({
      ok: true,
      status: 200,
      json: async () =>
        String(url).includes('/models')
          ? { text: [], image: [], video: [], errors: {} }
          : String(url).includes('/instructions')
            ? { instructions: [] }
            : String(url).includes('/conversations')
              ? { conversations: [] }
              : { configured: true },
    }))
    const ChatView = (await import('../views/ChatView.vue')).default
    const mountView = async () => {
      const r = createChatRouter({
        history: createMemoryHistory(),
        routes: [{ path: '/chat', name: 'chat', component: ChatView }],
      })
      r.push('/chat')
      await r.isReady()
      const w = mountChat({ template: '<router-view />' }, { global: { plugins: [r] }, attachTo: document.body })
      await flushChat()
      return w
    }
    let w = await mountView()
    const modeFold = () => w.findAll('button.fold').find(b => b.text() === 'Mode')
    expect(w.find('.modes').isVisible()).toBe(true)
    await modeFold().trigger('click')
    expect(w.find('.modes').isVisible()).toBe(false)
    expect(modeFold().element.parentElement.textContent).toContain('Auto')
    w.unmount()

    w = await mountView()
    expect(w.find('.modes').isVisible()).toBe(false)
    await modeFold().trigger('click')
    expect(w.find('.modes').isVisible()).toBe(true)
    w.unmount()
  })
})

describe('ChatView chat list and per-chat state', () => {
  const day = 24 * 60 * 60 * 1000
  const iso = msAgo => new Date(Date.now() - msAgo).toISOString()
  const convs = [
    { id: 'p', title: 'Pinned one', pinned: true, updated_at: iso(40 * day) },
    { id: 't', title: 'Fresh', pinned: false, updated_at: iso(0) },
    { id: 'b', title: 'Story (branch)', pinned: false, forked_from_id: 'x', updated_at: iso(3 * day) },
    { id: 'o', title: 'Ancient', pinned: false, updated_at: iso(90 * day) },
  ]
  const conversation = {
    id: 'b',
    title: 'Story (branch)',
    text_model: null,
    image_model: null,
    video_model: null,
    character_ids: [],
    instruction_id: null,
    settings: {
      mode: 'image',
      history_limit: 10,
      image_limit: 2,
      image_options: { aspect_ratio: '16:9' },
      video_options: {},
    },
    forked_from: { id: 'x', title: 'Story', message_id: 1, exists: true },
    spend: { usd: 0.42, credits: 300, inherited_usd: 0.4, inherited_credits: 0 },
  }
  const calls = []

  async function mountView(path) {
    localStorage.removeItem('chat.folded')
    localStorage.removeItem('chat.prefs')
    globalThis.fetch = vi.fn(async (url, opts) => {
      url = String(url)
      calls.push([url, opts?.method || 'GET', opts?.body])
      return {
        ok: true,
        status: 200,
        json: async () =>
          url.includes('/models')
            ? { text: [], image: [], video: [], errors: {} }
            : url.includes('/instructions')
              ? { instructions: [] }
              : url.includes('/conversations?q=')
                ? { conversations: [{ ...convs[3], snippet: '…a fox appears…' }], more: false }
                : url.includes('/conversations/b') && opts?.method === 'PATCH'
                  ? { ...convs[2], pinned: true }
                  : url.includes('/conversations/b')
                    ? {
                        conversation,
                        messages: [{ id: 1, role: 'user', content: 'hi', status: 'done', media: [], siblings: [1] }],
                      }
                    : url.includes('/conversations')
                      ? { conversations: convs, more: true }
                      : url.includes('/characters')
                        ? { characters: [] }
                        : { configured: true },
      }
    })
    const ChatView = (await import('../views/ChatView.vue')).default
    const r = createChatRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', name: 'chat', component: ChatView },
        { path: '/chat/c/:id', name: 'chat-conversation', component: ChatView },
      ],
    })
    r.push(path)
    await r.isReady()
    const w = mountChat({ template: '<router-view />' }, { global: { plugins: [r] }, attachTo: document.body })
    await flushChat()
    return w
  }

  it('groups chats by pin and date, and says when older ones are left out', async () => {
    const w = await mountView('/chat')
    const rows = w
      .findAll('.conv-group, .conv-item')
      .map(e => (e.classes('conv-group') ? `# ${e.text()}` : e.find('.conv-title').text()))
    expect(rows).toEqual([
      '# Pinned',
      'Pinned one',
      '# Today',
      'Fresh',
      '# Previous 7 days',
      '⑂ Story (branch)',
      '# Older',
      'Ancient',
    ])
    expect(w.text()).toContain("Older chats aren't listed")
    w.unmount()
  })

  it('searches chats and shows the matching text', async () => {
    vi.useFakeTimers()
    const w = await mountView('/chat')
    await w.find('.conv-search input').setValue('fox')
    await vi.advanceTimersByTimeAsync(300)
    vi.useRealTimers()
    await flushChat()
    expect(w.findAll('.conv-title').map(e => e.text())).toEqual(['Ancient'])
    expect(w.find('.conv-snippet').text()).toBe('…a fox appears…')
    expect(w.findAll('.conv-group')).toHaveLength(0)
    w.unmount()
  })

  it('pins a chat', async () => {
    const w = await mountView('/chat')
    const row = w.findAll('.conv-item').find(e => e.text().includes('Story'))
    await row.find('button[title="Pin to the top"]').trigger('click')
    await flushChat()
    expect(
      calls.some(([u, m, b]) => u.includes('/conversations/b') && m === 'PATCH' && JSON.parse(b).pinned === true),
    ).toBe(true)
    expect(w.findAll('.conv-group, .conv-item')[2].find('.conv-title').text()).toBe('⑂ Story (branch)')
    w.unmount()
  })

  it("restores the chat's own settings and shows its origin and spend", async () => {
    const w = await mountView('/chat/c/b')
    expect(w.find('.mode.active').text()).toContain('Image')
    expect(w.find('.fork-origin').text()).toContain('Branched from Story')
    const chip = w.find('.balance.spend')
    expect(chip.text()).toBe('This chat $0.42 + 300 cr')
    expect(chip.attributes('title')).toContain('$0.40 of it was spent before it was branched')
    w.unmount()
  })
})
