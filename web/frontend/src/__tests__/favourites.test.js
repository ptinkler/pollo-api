import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import VideoCard from '../components/VideoCard.vue'
import HomeView from '../views/HomeView.vue'

const video = (over = {}) => ({
  filename: 'vid_a.mp4',
  favourite: false,
  media_type: 'video',
  job: { job_id: 'job-a', model: 'seedance20fastv1', prompt: 'a fox', created_at: '2026-10-06T12:00:00+00:00' },
  ...over,
})

describe('VideoCard star', () => {
  it('toggles and reflects the favourite state', async () => {
    const w = mount(VideoCard, { props: { video: video(), project: 'p1' } })
    const star = w.find('.fav-btn')
    expect(star.text()).toBe('☆')
    await star.trigger('click')
    expect(w.emitted('toggle-favourite')[0][0].filename).toBe('vid_a.mp4')
    await w.setProps({ video: video({ favourite: true }) })
    expect(w.find('.fav-btn').text()).toBe('★')
  })

  it('in the Favourites tab: project label, no project-scoped actions', () => {
    const w = mount(VideoCard, {
      props: { video: video({ favourite: true }), project: 'p1', projectName: 'Trailer', manage: false },
    })
    expect(w.find('.video-project').text()).toContain('Trailer')
    expect(w.find('[title="Regenerate"]').exists()).toBe(false)
    expect(w.find('[title="Delete"]').exists()).toBe(false)
    expect(w.find('.fav-btn').exists()).toBe(true)
  })
})

describe('HomeView Favourites tab', () => {
  let requests
  beforeEach(() => {
    requests = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      requests.push([opts.method || 'GET', String(url)])
      const body =
        String(url).includes('/api/favourites') && (opts.method || 'GET') === 'GET'
          ? {
              items: [
                { ...video({ favourite: true }), project: 'p1', project_name: 'Trailer' },
                {
                  ...video({ filename: 'img_b.png', favourite: true, media_type: 'image' }),
                  project: 'p2',
                  project_name: 'Posters',
                },
              ],
            }
          : String(url).includes('/api/projects')
            ? []
            : {}
      return { ok: true, status: 200, json: async () => body }
    })
  })

  async function mountHome() {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: HomeView },
        { path: '/project/:project/gallery/:videoFilename', name: 'project-video', component: { template: '<div/>' } },
        { path: '/project/:project/archive', name: 'project-archive', component: { template: '<div/>' } },
      ],
    })
    router.push('/')
    await router.isReady()
    const w = mount(HomeView, { global: { plugins: [router], provide: { showToast: vi.fn() } } })
    await flushPromises()
    await w
      .findAll('.tab-btn')
      .find(b => b.text().includes('Favourites'))
      .trigger('click')
    await flushPromises()
    return { w, router }
  }

  it('lists starred generations from every project, filterable', async () => {
    const { w } = await mountHome()
    expect(w.findAll('.video-project').map(e => e.text())).toEqual(['📁 Trailer', '📁 Posters'])
    await w
      .findAll('.fav-filter')
      .find(b => b.text() === 'Images')
      .trigger('click')
    expect(w.findAll('.video-project').map(e => e.text())).toEqual(['📁 Posters'])
  })

  it('opens a favourite in its project and drops it when unstarred', async () => {
    const { w, router } = await mountHome()
    await w.findAll('.card-clickable')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/project/p1/gallery/vid_a.mp4')
    await w.findAll('.fav-btn')[0].trigger('click')
    await flushPromises()
    expect(requests).toContainEqual(['DELETE', '/api/favourites/vid_a.mp4'])
    expect(w.findAll('.video-project').map(e => e.text())).toEqual(['📁 Posters'])
  })
})

describe('GalleryPanel favourites filter', () => {
  it('shows only starred generations, and drops one when unstarred', async () => {
    const { default: GalleryPanel } = await import('../views/panels/GalleryPanel.vue')
    globalThis.fetch = vi.fn(async (url, opts = {}) => ({
      ok: true,
      status: 200,
      json: async () =>
        String(url).includes('/api/projects/p1') && (opts.method || 'GET') === 'GET'
          ? { videos: [video(), video({ filename: 'vid_b.mp4', favourite: true })] }
          : {},
    }))
    const w = mount(GalleryPanel, {
      props: { project: 'p1', active: true },
      global: { provide: { showToast: vi.fn() } },
    })
    await flushPromises()
    expect(w.findAll('.fav-btn')).toHaveLength(2)
    await w.findAll('.filter-check input')[2].setValue(true)
    expect(w.findAll('.fav-btn')).toHaveLength(1)
    await w.find('.fav-btn').trigger('click')
    await flushPromises()
    expect(w.findAll('.fav-btn')).toHaveLength(0)
    expect(w.text()).toContain('Nothing matches these filters')
  })
})
