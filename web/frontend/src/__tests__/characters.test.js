import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CharacterPicker from '../components/characters/CharacterPicker.vue'
import CharacterEditor from '../components/characters/CharacterEditor.vue'

const linh = { id: 1, name: 'Linh', description: 'red scarf', images: ['a.png'], adhoc: false }
const bao = { id: 2, name: 'Bao', description: '', images: [], adhoc: true }

describe('CharacterPicker', () => {
  it('shows attached characters and attaches / detaches', async () => {
    const w = mount(CharacterPicker, { props: { modelValue: [1], characters: [linh, bao] } })
    expect(w.findAll('.chip').map(c => c.text())).toEqual([expect.stringContaining('Linh')])
    expect(w.find('.chip img').attributes('src')).toBe('/api/characters/1/images/a.png')

    await w.find('.add').trigger('click')
    const items = w.findAll('.menu .item:not(.create)')
    expect(items.map(i => i.text())).toEqual([expect.stringContaining('Bao')])
    await items[0].trigger('click')
    expect(w.emitted('update:modelValue')[0][0]).toEqual([1, 2])

    await w.find('.chip-x').trigger('click')
    expect(w.emitted('update:modelValue')[1][0]).toEqual([])
  })

  it('emits edit and create', async () => {
    const w = mount(CharacterPicker, { props: { modelValue: [1], characters: [linh] } })
    await w.find('.chip-main').trigger('click')
    expect(w.emitted('edit')[0][0]).toEqual(linh)
    await w.find('.add').trigger('click')
    await w.find('.item.create').trigger('click')
    expect(w.emitted('create')).toHaveLength(1)
  })
})

describe('CharacterEditor', () => {
  let requests
  beforeEach(() => {
    requests = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      const body = opts.body && typeof opts.body === 'string' ? JSON.parse(opts.body) : null
      requests.push([opts.method || 'GET', String(url), body])
      const char = { id: 7, name: 'Linh', description: 'red scarf', images: [], adhoc: true, conversation_id: 'c1' }
      if (String(url).endsWith('/from-chat')) char.images = ['img_x.png']
      return { ok: true, status: 200, json: async () => char }
    })
  })

  it('creates an ad-hoc character and copies the seed image from the chat', async () => {
    const w = mount(CharacterEditor, {
      props: {
        open: false,
        conversationId: 'c1',
        seed: [{ kind: 'chat', conversationId: 'c1', file: 'g.png', preview: '/p' }],
      },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    const dialog = document.body.querySelector('.dialog')
    expect(dialog.querySelectorAll('.img.pending')).toHaveLength(1)

    const name = dialog.querySelector('#char-name')
    name.value = 'Linh'
    name.dispatchEvent(new Event('input'))
    const desc = dialog.querySelector('#char-desc')
    desc.value = 'red scarf'
    desc.dispatchEvent(new Event('input'))
    await flushPromises()
    dialog.querySelector('.btn-primary').click()
    await flushPromises()

    expect(requests[0]).toEqual([
      'POST',
      '/api/characters',
      { name: 'Linh', description: 'red scarf', conversation_id: 'c1' },
    ])
    expect(requests[1]).toEqual([
      'POST',
      '/api/characters/7/images/from-chat',
      { conversation_id: 'c1', file: 'g.png' },
    ])
    expect(w.emitted('saved')[0][0].images).toEqual(['img_x.png'])
    w.unmount()
  })
})

describe('which models can use characters', () => {
  it('chat image models: reference images or conversational', async () => {
    const { chatImageModelTakesCharacters: ok } = await import('../composables/useCharacters')
    expect(ok({ input_modalities: ['text', 'image'] })).toBe(true)
    expect(ok({ input_modalities: ['text'], conversational: true })).toBe(true)
    expect(ok({ input_modalities: ['text'] })).toBe(false)
    expect(ok(null)).toBe(false)
  })

  it('Generate models: image models with "images", ref models, v1 models in Ref mode', async () => {
    const { generateModelTakesCharacters: ok } = await import('../composables/useCharacters')
    expect(ok({ type: 'image', options: ['images'] })).toBe(true)
    expect(ok({ type: 'image', options: [] })).toBe(false)
    expect(ok({ type: 'ref' })).toBe(true)
    const v1 = { type: 'img2vid', ref_mode: { types: ['image'], max: 9 } }
    expect(ok(v1, false)).toBe(false)
    expect(ok(v1, true)).toBe(true)
    expect(ok({ type: 'img2vid' }, true)).toBe(false)
  })

  it('the chat model picker badges image models that can', async () => {
    const { nextTick } = await import('vue')
    const ModelPicker = (await import('../components/chat/ModelPicker.vue')).default
    const w = mount(ModelPicker, {
      props: {
        kind: 'image',
        label: 'Image',
        modelValue: '',
        models: [
          { id: 'a/refs', name: 'Refs', input_modalities: ['text', 'image'] },
          { id: 'b/prompt', name: 'Prompt only', input_modalities: ['text'] },
        ],
      },
      attachTo: document.body,
    })
    await w.find('.picker-btn').trigger('click')
    await nextTick()
    const badged = w.findAll('.picker-item').filter(i => i.findAll('.item-badge').some(b => b.text() === '👤'))
    expect(badged.map(i => i.find('.item-name').text())).toEqual(['Refs'])
    w.unmount()
  })
})
