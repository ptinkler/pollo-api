import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../composables/useApi', async importOriginal => ({
  ...(await importOriginal()),
  generateVideo: vi.fn(async () => ({ job_id: 'j1' })),
  generateImage: vi.fn(async () => ({ job_id: 'j2' })),
  fetchCreditEstimate: vi.fn(async () => ({ credits: 12, source: 'pollo' })),
}))
vi.mock('../composables/useCharacters', async importOriginal => ({
  ...(await importOriginal()),
  fetchCharacters: vi.fn(async () => []),
}))

import GeneratePanel from '../views/panels/GeneratePanel.vue'
import { fetchCreditEstimate, generateVideo } from '../composables/useApi'

const MODELS = {
  seedance25draftv1: {
    label: 'Seedance 2.5 Draft',
    type: 'img2vid',
    lengths: [4, 5, 6],
    resolutions: ['480p'],
    ratios: ['16:9', '9:16'],
    options: ['generate_audio', 'seed', 'image_tail'],
  },
  seedance25extendv1: {
    label: 'Seedance 2.5 Extend',
    type: 'extend',
    lengths: [4, 5, 6],
    resolutions: ['480p', '720p'],
    ratios: [],
    options: ['generate_audio', 'seed'],
  },
}

const toast = vi.fn()

function mountPanel(props = {}) {
  return mount(GeneratePanel, {
    props: { project: 'p1', models: MODELS, ...props },
    global: { provide: { showToast: toast }, stubs: { MediaPicker: true, CharacterEditor: true } },
  })
}

const settingsOf = w => w.vm.$.setupState.settings
const lastEstimate = () => fetchCreditEstimate.mock.calls.at(-1)[0]

describe('Generate: Extend and estimates', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  it('a video’s Extend switches to the extend model with that video', async () => {
    const w = mountPanel()
    await w.setProps({ extendVideo: { video_url: 'https://videocdn.pollo.ai/a.mp4' } })
    expect(w.emitted('extend-applied')).toHaveLength(1)
    expect(settingsOf(w).model).toBe('seedance25extendv1')
    expect(w.find('video.source-thumb').attributes('src')).toBe('https://videocdn.pollo.ai/a.mp4')
    expect(w.text()).toContain('What happens next')
    w.unmount()
  })

  it('a project video previews from the project and is sent as local:', async () => {
    const w = mountPanel()
    await w.setProps({ extendVideo: { video_url: 'local:v.mp4' } })
    expect(w.find('video.source-thumb').attributes('src')).toContain('/video/p1/v.mp4')
    await w.find('form').trigger('submit') // no prompt needed to extend
    await flushPromises()
    const body = generateVideo.mock.calls[0][0]
    expect(body).toMatchObject({ model: 'seedance25extendv1', video_url: 'local:v.mp4', prompt: '' })
    expect(body.image_url).toBeUndefined()
    expect(body.character_ids).toEqual([])
    w.unmount()
  })

  it('says so when Pollo hasn’t enabled extending for the key', async () => {
    const models = { ...MODELS, seedance25extendv1: { ...MODELS.seedance25extendv1, hidden: 'Not enabled (403)' } }
    const w = mountPanel({ models })
    await w.setProps({ extendVideo: { video_url: 'https://v.mp4' } })
    expect(settingsOf(w).model).toBe('seedance25extendv1')
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('Not enabled (403)'), 'error')
    w.unmount()
  })

  it('without the extend model (legacy mode) it says so', async () => {
    const w = mountPanel({ models: { seedance25draftv1: MODELS.seedance25draftv1 } })
    await w.setProps({ extendVideo: { video_url: 'https://v.mp4' } })
    expect(toast).toHaveBeenCalledWith(expect.stringContaining('Legacy mode'), 'error')
    w.unmount()
  })

  it('asks for a price with the kinds of media, not the media', async () => {
    const w = mountPanel()
    const s = settingsOf(w)
    Object.assign(s, { model: 'seedance25draftv1', image_url: 'local:src.png', image_tail: 'https://t.png', length: 5 })
    await vi.advanceTimersByTimeAsync(400)
    expect(lastEstimate()).toMatchObject({
      model: 'seedance25draftv1',
      image: true,
      image_tail: true,
      ref_types: [],
      length: 5,
      resolution: '480p',
      web_search: null,
    })
    expect(JSON.stringify(lastEstimate())).not.toContain('src.png')
    expect(w.text()).toContain('(12 credits)') // Pollo's price: no "~"
    w.unmount()
  })

  it('a price from past jobs is marked as a guess', async () => {
    fetchCreditEstimate.mockResolvedValue({ credits: 30, source: 'history' })
    const w = mountPanel()
    settingsOf(w).model = 'seedance25draftv1'
    await vi.advanceTimersByTimeAsync(400)
    expect(w.text()).toContain('(~30 credits)')
    w.unmount()
  })
})
