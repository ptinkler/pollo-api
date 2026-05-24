/**
 * Tests for Vue components — AppHeader, ToastContainer, ProjectCard,
 * VideoCard, JobCard, form components (LengthSlider, RatioPicker, ToggleSwitch)
 */
import { describe, it, expect } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

// ── Minimal router for components that use RouterLink ───────────────
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', name: 'home', component: { template: '<div />' } },
    { path: '/project/:project/gallery', name: 'project-gallery', component: { template: '<div />' } },
  ],
})

// ── AppHeader ───────────────────────────────────────────────────────

import AppHeader from '../components/AppHeader.vue'

describe('AppHeader', () => {
  it('renders the title', async () => {
    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    await router.isReady()
    expect(wrapper.text()).toContain('Pollo')
    expect(wrapper.text()).toContain('Video Generator')
  })

  it('has a link to home', async () => {
    const wrapper = mount(AppHeader, { global: { plugins: [router] } })
    await router.isReady()
    const link = wrapper.find('a')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/')
  })
})

// ── ToastContainer ──────────────────────────────────────────────────

import ToastContainer from '../components/ToastContainer.vue'

describe('ToastContainer', () => {
  it('renders toasts', () => {
    const wrapper = mount(ToastContainer, {
      props: {
        toasts: [
          { id: 1, message: 'Success!', type: 'success' },
          { id: 2, message: 'Oops!', type: 'error' },
        ]
      }
    })
    expect(wrapper.text()).toContain('Success!')
    expect(wrapper.text()).toContain('Oops!')
  })

  it('renders empty when no toasts', () => {
    const wrapper = mount(ToastContainer, { props: { toasts: [] } })
    expect(wrapper.findAll('.toast')).toHaveLength(0)
  })

  it('emits remove on click', async () => {
    const wrapper = mount(ToastContainer, {
      props: {
        toasts: [{ id: 1, message: 'Click me', type: 'success' }]
      }
    })
    await wrapper.find('.toast').trigger('click')
    expect(wrapper.emitted('remove')).toBeTruthy()
    expect(wrapper.emitted('remove')[0]).toEqual([1])
  })

  it('shows correct icons for types', () => {
    const wrapper = mount(ToastContainer, {
      props: {
        toasts: [
          { id: 1, message: 'ok', type: 'success' },
          { id: 2, message: 'bad', type: 'error' },
          { id: 3, message: 'info', type: 'info' },
        ]
      }
    })
    const icons = wrapper.findAll('.toast-icon')
    expect(icons[0].text()).toBe('✓')
    expect(icons[1].text()).toBe('✗')
    expect(icons[2].text()).toBe('ℹ')
  })
})

// ── ProjectCard ─────────────────────────────────────────────────────

import ProjectCard from '../components/ProjectCard.vue'

describe('ProjectCard', () => {
  const baseProject = {
    slug: 'test-project',
    name: 'Test Project',
    prompt: 'A lovely scene',
    image_url: '',
    video_count: 3,
    has_image: false,
    thumb_ts: '',
  }

  it('renders project name', async () => {
    const wrapper = mount(ProjectCard, {
      props: { project: baseProject },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.text()).toContain('Test Project')
  })

  it('renders video count', async () => {
    const wrapper = mount(ProjectCard, {
      props: { project: baseProject },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.text()).toContain('3 videos')
  })

  it('renders singular video count', async () => {
    const proj = { ...baseProject, video_count: 1 }
    const wrapper = mount(ProjectCard, {
      props: { project: proj },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.text()).toContain('1 video')
    expect(wrapper.text()).not.toContain('1 videos')
  })

  it('shows placeholder when no image', async () => {
    const wrapper = mount(ProjectCard, {
      props: { project: baseProject },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.find('.project-thumb-placeholder').exists()).toBe(true)
  })

  it('shows prompt in placeholder', async () => {
    const wrapper = mount(ProjectCard, {
      props: { project: baseProject },
      global: { plugins: [router] },
    })
    await router.isReady()
    expect(wrapper.text()).toContain('A lovely scene')
  })
})

// ── VideoCard ───────────────────────────────────────────────────────

import VideoCard from '../components/VideoCard.vue'

describe('VideoCard', () => {
  const baseVideo = {
    filename: 'video.mp4',
    mtime: Date.now(),
    job: {
      model: 'pollodance20',
      prompt: 'A cat dancing',
      aspect_ratio: '16:9',
      length: 10,
      created_at: '2025-01-01T00:00:00',
    }
  }

  it('renders model name', () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    expect(wrapper.text()).toContain('pollodance20')
  })

  it('renders prompt', () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    expect(wrapper.text()).toContain('A cat dancing')
  })

  it('renders metadata', () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    expect(wrapper.text()).toContain('16:9')
    expect(wrapper.text()).toContain('10s')
  })

  it('emits click on card click', async () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    await wrapper.find('.card-clickable').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')[0]).toEqual([baseVideo])
  })

  it('emits regenerate', async () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    const btns = wrapper.findAll('.action-btn')
    await btns[0].trigger('click')
    expect(wrapper.emitted('regenerate')).toBeTruthy()
  })

  it('emits delete', async () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    await wrapper.find('.action-btn-danger').trigger('click')
    expect(wrapper.emitted('delete')).toBeTruthy()
  })

  it('shows archive button by default', () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test' },
    })
    // Should have archive button (2nd action btn)
    const btns = wrapper.findAll('.action-btn')
    expect(btns.length).toBeGreaterThanOrEqual(2)
  })

  it('shows unarchive button when showUnarchive true', () => {
    const wrapper = shallowMount(VideoCard, {
      props: { video: baseVideo, project: 'test', showArchive: false, showUnarchive: true },
    })
    expect(wrapper.html()).toContain('Unarchive')
  })

  it('handles missing job gracefully', () => {
    const video = { filename: 'test.mp4', mtime: Date.now() }
    const wrapper = shallowMount(VideoCard, {
      props: { video, project: 'test' },
    })
    expect(wrapper.text()).toContain('Unknown')
  })
})

// ── JobCard ─────────────────────────────────────────────────────────

import JobCard from '../components/JobCard.vue'

describe('JobCard', () => {
  const baseJob = {
    job_id: 'j1',
    model: 'pollodance20',
    status: 'done',
    message: 'Video ready!',
    video_path: '/assets/proj/video.mp4',
    video_exists: true,
    video_url: 'https://vid.com/v.mp4',
    created_at: '2025-01-01T00:00:00',
  }

  it('renders model name', () => {
    const wrapper = shallowMount(JobCard, {
      props: { job: baseJob, project: 'test' },
    })
    expect(wrapper.text()).toContain('pollodance20')
  })

  it('renders status badge', () => {
    const wrapper = shallowMount(JobCard, {
      props: { job: baseJob, project: 'test' },
    })
    expect(wrapper.find('.badge').text()).toBe('done')
  })

  it('renders message', () => {
    const wrapper = shallowMount(JobCard, {
      props: { job: baseJob, project: 'test' },
    })
    expect(wrapper.text()).toContain('Video ready!')
  })

  it('shows download button when video_url but no local file', () => {
    const job = { ...baseJob, video_exists: false }
    const wrapper = shallowMount(JobCard, {
      props: { job, project: 'test' },
    })
    expect(wrapper.text()).toContain('Download')
  })

  it('emits download on button click', async () => {
    const job = { ...baseJob, video_exists: false }
    const wrapper = shallowMount(JobCard, {
      props: { job, project: 'test' },
    })
    await wrapper.find('.btn-secondary').trigger('click')
    expect(wrapper.emitted('download')).toBeTruthy()
    expect(wrapper.emitted('download')[0]).toEqual(['j1'])
  })

  it('emits delete on trash click', async () => {
    const wrapper = shallowMount(JobCard, {
      props: { job: baseJob, project: 'test' },
    })
    await wrapper.find('.btn-delete').trigger('click')
    expect(wrapper.emitted('delete')).toBeTruthy()
  })

  it('shows processing spinner for active jobs', () => {
    const job = { ...baseJob, status: 'processing', video_path: null, video_exists: false, video_url: null }
    const wrapper = shallowMount(JobCard, {
      props: { job, project: 'test' },
    })
    expect(wrapper.find('.processing-spinner').exists()).toBe(true)
  })

  it('renders filename link when video exists', () => {
    const wrapper = shallowMount(JobCard, {
      props: { job: baseJob, project: 'test' },
    })
    expect(wrapper.text()).toContain('video.mp4')
  })
})

// ── LengthSlider ────────────────────────────────────────────────────

import LengthSlider from '../components/form/LengthSlider.vue'

describe('LengthSlider', () => {
  it('renders all length options', () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    const btns = wrapper.findAll('.length-btn')
    expect(btns).toHaveLength(3)
    expect(btns[0].text()).toBe('5s')
    expect(btns[1].text()).toBe('10s')
  })

  it('marks active length', () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    const active = wrapper.find('.length-btn.active')
    expect(active.text()).toBe('10s')
  })

  it('emits on click', async () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    await wrapper.findAll('.length-btn')[0].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([5])
  })
})

// ── RatioPicker ─────────────────────────────────────────────────────

import RatioPicker from '../components/form/RatioPicker.vue'

describe('RatioPicker', () => {
  it('renders all ratio options', () => {
    const wrapper = mount(RatioPicker, {
      props: { modelValue: '16:9', ratios: ['16:9', '9:16', '1:1'] },
    })
    const btns = wrapper.findAll('.ratio-btn')
    expect(btns).toHaveLength(3)
  })

  it('marks active ratio', () => {
    const wrapper = mount(RatioPicker, {
      props: { modelValue: '16:9', ratios: ['16:9', '9:16', '1:1'] },
    })
    const active = wrapper.find('.ratio-btn.active')
    expect(active.attributes('title')).toBe('16:9')
  })

  it('emits on click', async () => {
    const wrapper = mount(RatioPicker, {
      props: { modelValue: '16:9', ratios: ['16:9', '9:16', '1:1'] },
    })
    await wrapper.findAll('.ratio-btn')[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['9:16'])
  })

  it('renders ratio labels', () => {
    const wrapper = mount(RatioPicker, {
      props: { modelValue: '', ratios: ['16:9'] },
    })
    expect(wrapper.text()).toContain('16:9')
  })
})

// ── ToggleSwitch ────────────────────────────────────────────────────

import ToggleSwitch from '../components/form/ToggleSwitch.vue'

describe('ToggleSwitch', () => {
  it('renders label', () => {
    const wrapper = mount(ToggleSwitch, {
      props: { modelValue: false, label: 'Audio', id: 'audio' },
    })
    expect(wrapper.text()).toContain('Audio')
  })

  it('checkbox reflects modelValue', () => {
    const wrapper = mount(ToggleSwitch, {
      props: { modelValue: true, label: 'Audio', id: 'audio' },
    })
    expect(wrapper.find('input').element.checked).toBe(true)
  })

  it('emits on toggle', async () => {
    const wrapper = mount(ToggleSwitch, {
      props: { modelValue: false, label: 'Audio', id: 'audio' },
    })
    await wrapper.find('input').setValue(true)
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([true])
  })

  it('checkbox unchecked by default', () => {
    const wrapper = mount(ToggleSwitch, {
      props: { modelValue: false, label: 'Test', id: 'test' },
    })
    expect(wrapper.find('input').element.checked).toBe(false)
  })
})

