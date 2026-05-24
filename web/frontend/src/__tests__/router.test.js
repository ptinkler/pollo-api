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

