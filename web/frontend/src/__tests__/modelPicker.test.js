import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
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

  it('hides Edit and Retry while a reply is streaming (canEdit false)', () => {
    const w = mount(ChatMessage, { props: { message: msg, convId: 'c1', canEdit: false } })
    expect(w.find('.user-actions').exists()).toBe(false)
  })
})
