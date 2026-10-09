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
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true, status: 200,
      json: async () => (String(url).includes('/api/chat/credits') ? { total_credits: 60, total_usage: 52.79, remaining: 7.21 }
        : String(url).includes('/api/usage/balance') ? { availableCredits: 12345, totalCredits: 20000 }
        : String(url).includes('/models') ? { text: [], image: [], video: [], errors: {} }
        : String(url).includes('/instructions') ? { instructions: [] }
        : String(url).includes('/conversations') ? { conversations: [] }
        : { configured: true }),
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
