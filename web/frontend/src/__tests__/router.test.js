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


// ── Chat: "New chat" from the Library ────────────────────────────────
import { mount as mountChat, flushPromises as flushChat } from '@vue/test-utils'
import { createRouter as createChatRouter, createMemoryHistory } from 'vue-router'

describe('ChatView New chat button', () => {
  it('leaves the Library for a blank chat', async () => {
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true, status: 200,
      json: async () => (String(url).includes('/models') ? { text: [], image: [], video: [], errors: {} }
        : String(url).includes('/library') ? { items: [] }
        : String(url).includes('/conversations') ? { conversations: [] }
        : { configured: true }),
    }))
    const ChatView = (await import('../views/ChatView.vue')).default
    const r = createChatRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', name: 'chat', component: ChatView },
        { path: '/chat/library', name: 'chat-library', component: ChatView },
        { path: '/chat/:id', name: 'chat-conversation', component: ChatView },
      ],
    })
    r.push('/chat/library')
    await r.isReady()
    const w = mountChat({ template: '<router-view />' }, { global: { plugins: [r] } })
    await flushChat()
    expect(w.find('.library').exists()).toBe(true)
    await w.find('.new-chat').trigger('click')
    await flushChat()
    expect(r.currentRoute.value.name).toBe('chat')
    expect(w.find('.library').exists()).toBe(false)
    expect(w.find('.welcome').exists()).toBe(true)
    w.unmount()
  })
})
