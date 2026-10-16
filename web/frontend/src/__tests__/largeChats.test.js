import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useChatList } from '../composables/useChatList'

const EMPTY = { default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] }

function mockApi({ messages = [], fork } = {}) {
  const conv = { id: 'a', title: 'Big chat', pinned: false, space_id: null, updated_at: new Date().toISOString() }
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    url = String(url)
    let json
    if (url.includes('/fork')) json = await fork()
    else if (url.includes('/models')) json = { text: [], image: [], video: [], errors: {} }
    else if (url.includes('/settings')) json = { ...EMPTY }
    else if (url.includes('/instructions')) json = { instructions: [], groups: [] }
    else if (url.includes('/spaces')) json = { spaces: [] }
    else if (/\/conversations\/\w+$/.test(url)) json = { conversation: conv, messages }
    else if (url.includes('/conversations')) json = { conversations: [conv], more: false }
    else if (url.includes('/characters')) json = { characters: [] }
    else json = { configured: true }
    return { ok: true, status: 200, json: async () => json, opts }
  })
}

async function mountChat(path) {
  const ChatView = (await import('../views/ChatView.vue')).default
  const r = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/chat', name: 'chat', component: ChatView },
      { path: '/chat/c/:id', name: 'chat-conversation', component: ChatView },
    ],
  })
  r.push(path)
  await r.isReady()
  const w = mount({ template: '<router-view />' }, { global: { plugins: [r] }, attachTo: document.body })
  await flushPromises()
  return w
}

const msgs = n =>
  Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    role: i % 2 ? 'assistant' : 'user',
    content: `message ${i + 1}`,
    media: [],
    status: 'done',
    siblings: [i + 1],
    forks: [],
  }))

describe('large chats', () => {
  it('draws the latest messages first, and earlier ones on request', async () => {
    mockApi({ messages: msgs(90) })
    const w = await mountChat('/chat/c/a')
    const button = () => w.find('.show-earlier')
    expect(button().text()).toContain('(50)')
    expect(w.text()).toContain('message 90')
    expect(w.text()).not.toContain('message 50 ')
    await button().trigger('click')
    expect(button().text()).toContain('(10)')
    await button().trigger('click')
    expect(button().exists()).toBe(false)
    expect(w.text()).toContain('message 1')
    w.unmount()
  })

  it('a second click while branching does nothing', async () => {
    let finish
    mockApi({
      messages: msgs(2),
      fork: () => new Promise(resolve => (finish = resolve)),
    })
    const w = await mountChat('/chat/c/a')
    const forkButton = w.findAll('button').find(b => b.attributes('title')?.startsWith('Start a new chat from here'))
    await forkButton.trigger('click')
    await forkButton.trigger('click')
    const forks = () => globalThis.fetch.mock.calls.filter(([u]) => String(u).includes('/fork'))
    expect(forks()).toHaveLength(1)
    finish({ id: 'b', title: 'Big chat (branch)', space_id: null, updated_at: new Date().toISOString() })
    await flushPromises()
    w.unmount()
  })
})

describe('deleting a chat', () => {
  it('marks it as being deleted, and ignores another click meanwhile', async () => {
    let finish
    globalThis.fetch = vi.fn(() => new Promise(resolve => (finish = resolve)))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const list = useChatList(() => {})
    const c = { id: 'x', title: 'Big' }
    list.conversations = [c]
    const first = list.remove(c)
    expect(list.deleting.has('x')).toBe(true)
    expect(await list.remove(c)).toBe(false) // already going
    expect(globalThis.fetch).toHaveBeenCalledTimes(1)
    finish({ ok: true, status: 200, json: async () => ({ deleted: 'x' }) })
    expect(await first).toBe(true)
    expect(list.deleting.has('x')).toBe(false)
    expect(list.conversations).toEqual([])
  })
})
