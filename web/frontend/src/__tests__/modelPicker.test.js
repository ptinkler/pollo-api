import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { copyText } from '../composables/useClipboard'
import { nextTick } from 'vue'
import ModelPicker from '../components/chat/ModelPicker.vue'
import { useModelFavourites } from '../composables/useModelFavourites'

const MODELS = [
  { id: 'a/alpha', name: 'Alpha' },
  { id: 'b/beta', name: 'Beta' },
  { id: 'c/gamma', name: 'Gamma' },
]

async function openPicker(props = {}) {
  const wrapper = mount(ModelPicker, {
    props: { models: MODELS, label: 'Image', kind: 'image', modelValue: '', ...props },
    attachTo: document.body,
  })
  await wrapper.find('.picker-btn').trigger('click')
  await nextTick()
  return wrapper
}

const names = (w) => w.findAll('.picker-item .item-name').map(n => n.text())
const sections = (w) => w.findAll('.picker-section').map(n => n.text())

describe('ModelPicker favourites', () => {
  beforeEach(() => {
    const { favourites } = useModelFavourites()
    favourites.text.splice(0); favourites.image.splice(0); favourites.video.splice(0)
    localStorage.clear()
  })

  it('shows no section headings until something is starred', async () => {
    const w = await openPicker()
    expect(sections(w)).toEqual([])
    expect(names(w)).toEqual(['None', 'Alpha', 'Beta', 'Gamma'])
    w.unmount()
  })

  it('starring pins a model into a Favourites section above the rest', async () => {
    const w = await openPicker()
    await w.findAll('.star')[2].trigger('click')   // Gamma
    expect(sections(w)).toEqual(['★ Favourites', 'All models'])
    expect(names(w)).toEqual(['Gamma', 'None', 'Alpha', 'Beta'])
    expect(JSON.parse(localStorage.getItem('chat.favourites')).image).toEqual(['c/gamma'])
    // starring doesn't select the model or close the picker
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(w.find('.picker-pop').exists()).toBe(true)
    w.unmount()
  })

  it('unstarring moves it back', async () => {
    useModelFavourites().toggleFavourite('image', 'b/beta')
    const w = await openPicker()
    expect(names(w)[0]).toBe('Beta')
    await w.find('.star.on').trigger('click')
    expect(names(w)).toEqual(['None', 'Alpha', 'Beta', 'Gamma'])
    w.unmount()
  })

  it('favourites are per kind and search filters them too', async () => {
    const { toggleFavourite } = useModelFavourites()
    toggleFavourite('image', 'a/alpha')
    toggleFavourite('text', 'b/beta')
    const w = await openPicker()
    expect(names(w)[0]).toBe('Alpha')
    await w.find('.picker-search').setValue('gam')
    expect(sections(w)).toEqual([])
    expect(names(w)).toEqual(['Gamma'])
    w.unmount()
  })

  it('skips favourites no longer in the catalogue', async () => {
    useModelFavourites().toggleFavourite('image', 'gone/model')
    const w = await openPicker()
    expect(sections(w)).toEqual([])
    w.unmount()
  })
})

// ── ChatMessage user actions ────────────────────────────────────────
import ChatMessage from '../components/chat/ChatMessage.vue'

describe('ChatMessage user actions', () => {
  const msg = { id: 5, role: 'user', content: 'hello', media: [], status: 'done' }

  it('Retry emits resend without opening the editor', async () => {
    const w = mount(ChatMessage, { props: { message: msg, convId: 'c1', canEdit: true } })
    await w.find('button[title^="Resend"]').trigger('click')
    expect(w.emitted('resend')).toHaveLength(1)
    expect(w.find('.edit-box').exists()).toBe(false)
  })

  it('hides Edit and Retry while a reply is streaming, but keeps Copy', () => {
    const w = mount(ChatMessage, { props: { message: msg, convId: 'c1', canEdit: false } })
    const labels = w.findAll('.user-actions button').map(b => b.text())
    expect(labels).toEqual(['⧉ Copy'])
  })

  it('Copy puts the prompt on the clipboard and shows feedback', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(ChatMessage, { props: { message: msg, convId: 'c1', canEdit: true } })
    await w.find('button[title="Copy prompt"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('hello')
    expect(w.find('button[title="Copy prompt"]').text()).toBe('✓ Copied')
  })

  it('media caption copies the prompt sent to the image model', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const reply = {
      id: 6, role: 'assistant', content: 'Here', status: 'done',
      media: [{ id: 'm1', kind: 'image', status: 'done', file: 'a.png', model: 'x/seedream', prompt: 'a red fox, dusk' }],
    }
    const w = mount(ChatMessage, { props: { message: reply, convId: 'c1' } })
    await w.find('.caption-btn').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('a red fox, dusk')
    expect(w.find('.caption-btn').text()).toBe('✓ Copied')
  })
})

describe('copyText fallback', () => {
  it('uses execCommand when the Clipboard API is unavailable (plain HTTP)', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    document.execCommand = vi.fn().mockReturnValue(true)
    expect(await copyText('hi')).toBe(true)
    expect(document.execCommand).toHaveBeenCalledWith('copy')
    expect(document.querySelectorAll('textarea').length).toBe(0)  // cleaned up
  })
})

describe('Failed media card', () => {
  const failed = {
    id: 7, role: 'assistant', content: 'Here goes.', status: 'done',
    media: [{ id: 'm1', kind: 'image', source: 'generated', status: 'error', moderated: true,
              error: 'flagged', prompt: 'a lighthouse', model: 'x/strict' }],
  }
  const provide = { chatModels: { image: [{ id: 'x/strict', name: 'Strict' }, { id: 'y/lenient', name: 'Lenient' }], video: [] } }

  it('labels moderation blocks and offers Retry / another model', async () => {
    const w = mount(ChatMessage, { props: { message: failed, convId: 'c1' }, global: { provide }, attachTo: document.body })
    expect(w.find('.media-error strong').text()).toContain('blocked by moderation')
    await w.find('.retry-btn').trigger('click')
    expect(w.emitted('regenerate')[0]).toEqual([{ mediaId: 'm1', model: null }])

    await w.find('.picker-trigger').trigger('click')
    const items = w.findAll('.picker-item')
    expect(items.map(i => i.find('.item-name').text())).toEqual(['Strict', 'Lenient'])  // no "None"
    await items[1].trigger('click')
    expect(w.emitted('regenerate')[1]).toEqual([{ mediaId: 'm1', model: 'y/lenient' }])
    w.unmount()
  })

  it('hides the actions while the reply is still streaming', () => {
    const w = mount(ChatMessage, { props: { message: { ...failed, status: 'streaming' }, convId: 'c1' }, global: { provide } })
    expect(w.find('.error-actions').exists()).toBe(false)
  })
})

describe('Media note lines in replies', () => {
  const reply = (content, media = []) => ({ id: 9, role: 'assistant', content, status: 'done', media })
  const img = [{ id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'a.png', model: 'x/y', prompt: 'p' }]

  it('hides a reply that is only a [generated image: …] line, leaving the image', () => {
    const w = mount(ChatMessage, { props: { message: reply('[generated image: Photorealistic gym scene, long prompt…]', img), convId: 'c' } })
    expect(w.find('.markdown').exists()).toBe(false)
    expect(w.find('.media-item img').exists()).toBe(true)
    expect(w.find('.msg-meta').text()).not.toContain('Copy')
  })

  it('keeps the story and drops only the note lines', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(ChatMessage, { props: { message: reply('She laughed.\n\n[generated image: a gym]\n\nThe end.', img), convId: 'c' } })
    expect(w.find('.markdown').text()).toBe('She laughed.\nThe end.')
    await w.find('.msg-meta .meta-btn').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('She laughed.\n\nThe end.')
  })

  it('leaves ordinary bracketed text alone', () => {
    const w = mount(ChatMessage, { props: { message: reply('[Chapter 2] She smiled.'), convId: 'c' } })
    expect(w.find('.markdown').text()).toBe('[Chapter 2] She smiled.')
  })
})
