import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { copyText } from '../composables/useClipboard'
import { nextTick } from 'vue'
import { useUncensoredOnly } from '../composables/useUncensoredOnly'
import ModelPicker from '../components/chat/ModelPicker.vue'
import { useModelFavourites } from '../composables/useModelFavourites'
import { useModelFilters } from '../composables/useModelFilters'
import { useShowHidden } from '../composables/useShowHidden'

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

const names = w => w.findAll('.picker-item .item-name').map(n => n.text())
// The filter menu opens from the Filters button (when the list has anything to filter by)
async function openFilters(w) {
  if (!w.find('.fpanel').exists() && w.find('.filters-btn').exists()) await w.find('.filters-btn').trigger('click')
  return w
}
const sections = w => w.findAll('.picker-section').map(n => n.text())

describe('ModelPicker favourites', () => {
  beforeEach(() => {
    const { favourites } = useModelFavourites()
    favourites.text.splice(0)
    favourites.image.splice(0)
    favourites.video.splice(0)
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
    await w.findAll('.star')[2].trigger('click') // Gamma
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
    const labels = w.findAll('.user-actions button').map(b => b.attributes('title'))
    expect(labels).toEqual(['Copy prompt'])
  })

  it('Copy puts the prompt on the clipboard and shows feedback', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(ChatMessage, { props: { message: msg, convId: 'c1', canEdit: true } })
    await w.find('button[title="Copy prompt"]').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('hello')
    expect(w.find('button[title="Copy prompt"]').text()).toBe('✓')
  })

  it('media caption copies the prompt sent to the image model', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const reply = {
      id: 6,
      role: 'assistant',
      content: 'Here',
      status: 'done',
      media: [
        { id: 'm1', kind: 'image', status: 'done', file: 'a.png', model: 'x/seedream', prompt: 'a red fox, dusk' },
      ],
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
    expect(document.querySelectorAll('textarea').length).toBe(0) // cleaned up
  })
})

describe('Failed media card', () => {
  const failed = {
    id: 7,
    role: 'assistant',
    content: 'Here goes.',
    status: 'done',
    media: [
      {
        id: 'm1',
        kind: 'image',
        source: 'generated',
        status: 'error',
        moderated: true,
        error: 'flagged',
        prompt: 'a lighthouse',
        model: 'x/strict',
      },
    ],
  }
  const provide = {
    chatModels: {
      image: [
        { id: 'x/strict', name: 'Strict' },
        { id: 'y/lenient', name: 'Lenient' },
      ],
      video: [],
    },
  }

  it('labels moderation blocks and offers Retry / another model', async () => {
    const w = mount(ChatMessage, {
      props: { message: failed, convId: 'c1' },
      global: { provide },
      attachTo: document.body,
    })
    expect(w.find('.media-error strong').text()).toContain('blocked by moderation')
    await w.find('.retry-btn').trigger('click')
    expect(w.emitted('regenerate')[0]).toEqual([{ mediaId: 'm1', model: null }])

    await w.find('.picker-trigger').trigger('click')
    const items = w.findAll('.picker-item')
    expect(items.map(i => i.find('.item-name').text())).toEqual(['Strict', 'Lenient']) // no "None"
    await items[1].trigger('click')
    expect(w.emitted('regenerate')[1]).toEqual([{ mediaId: 'm1', model: 'y/lenient' }])
    w.unmount()
  })

  it('hides the actions while the reply is still streaming', () => {
    const w = mount(ChatMessage, {
      props: { message: { ...failed, status: 'streaming' }, convId: 'c1' },
      global: { provide },
    })
    expect(w.find('.error-actions').exists()).toBe(false)
  })
})

describe('Media note lines in replies', () => {
  const reply = (content, media = []) => ({ id: 9, role: 'assistant', content, status: 'done', media })
  const img = [
    { id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'a.png', model: 'x/y', prompt: 'p' },
  ]

  it('hides a reply that is only a [generated image: …] line, leaving the image', () => {
    const w = mount(ChatMessage, {
      props: { message: reply('[generated image: Photorealistic gym scene, long prompt…]', img), convId: 'c' },
    })
    expect(w.find('.markdown').exists()).toBe(false)
    expect(w.find('.media-item img').exists()).toBe(true)
    expect(w.find('.msg-meta button[title="Copy reply"]').exists()).toBe(false)
  })

  it('keeps the story and drops only the note lines', async () => {
    const writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    const w = mount(ChatMessage, {
      props: { message: reply('She laughed.\n\n[generated image: a gym]\n\nThe end.', img), convId: 'c' },
    })
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

describe('ModelPicker provider & tag filters', () => {
  const MIXED = [
    { id: 'pollo/a', name: 'Pollo A', tags: ['img2vid', 'audio'] },
    { id: 'pollo/b', name: 'Pollo B', tags: ['img2vid'] },
    { id: 'google/g', name: 'Gemini', tags: ['text2vid'] },
    { id: 'qwen/q', name: 'Qwen OR', tags: ['img2vid'] },
  ]
  const providerChips = w => w.findAll('.frow.provider').map(c => `${c.find('.fpill').text()} ${c.find('.fn').text()}`)
  const tagChips = w => w.findAll('.frow.tag').map(c => `${c.find('.fpill').text()} ${c.find('.fn').text()}`)
  const modelNames = w => names(w).filter(n => n !== 'None')
  const openVid = async (props = {}) => openFilters(await openPicker({ kind: 'video', models: MIXED, ...props }))

  beforeEach(() => {
    const { favourites } = useModelFavourites()
    favourites.image.splice(0)
    favourites.video.splice(0)
    useModelFilters().clear('video')
    useModelFilters().clear('image')
    localStorage.clear()
  })

  it('shows no provider chips when every model is from one provider', async () => {
    const w = await openPicker() // default MODELS are all OpenRouter
    expect(providerChips(w)).toEqual([])
    w.unmount()
  })

  it('has a Filters button that opens the menu (and counts what is ticked)', async () => {
    const w = await openPicker({ kind: 'video', models: MIXED })
    expect(w.find('.fpanel').exists()).toBe(false)
    await w.find('.filters-btn').trigger('click')
    expect(w.find('.fpanel').exists()).toBe(true)
    await w.findAll('.frow.provider input')[0].setValue(true)
    await w.findAll('.frow.tag input')[0].setValue(true)
    expect(w.find('.filters-n').text()).toBe('2')
    expect(w.findAll('.achip').map(c => c.text().replace(/\s+/g, ' '))).toEqual(['Pollo ✕', 'Image→Video ✕'])
    await w.find('.achip').trigger('click') // remove a pick from its chip
    expect(w.find('.filters-n').text()).toBe('1')
    w.unmount()
  })

  it('shows all providers in one list, with provider chips and per-row provider tags', async () => {
    const w = await openVid()
    expect(providerChips(w)).toEqual(['Pollo 2', 'OpenRouter 2'])
    expect(modelNames(w)).toEqual(['Pollo A', 'Pollo B', 'Gemini', 'Qwen OR'])
    expect(w.findAll('.row-provider').map(r => r.text())).toEqual(['Pollo', 'Pollo', 'OpenRouter', 'OpenRouter'])
    w.unmount()
  })

  it('a provider chip narrows the list to that provider, and persists', async () => {
    const w = await openVid()
    await w.findAll('.frow.provider input')[0].setValue(true) // Pollo
    expect(modelNames(w)).toEqual(['Pollo A', 'Pollo B'])
    expect(JSON.parse(localStorage.getItem('models.filters')).video.providers).toEqual(['pollo'])
    w.unmount()
    // a freshly mounted picker remembers the filter
    const again = await openVid()
    expect(modelNames(again)).toEqual(['Pollo A', 'Pollo B'])
    again.unmount()
  })

  it('tag chips come from the models and narrow the list (OR within tags, AND across facets)', async () => {
    const w = await openVid()
    expect(tagChips(w)).toEqual(['Image→Video 3', 'Text→Video 1', 'Makes audio 1'])
    await w.findAll('.frow.tag input')[2].setValue(true) // "Makes audio"
    expect(modelNames(w)).toEqual(['Pollo A'])
    // add Text→Video: OR within the tag facet
    await w.findAll('.frow.tag input')[1].setValue(true)
    expect(modelNames(w)).toEqual(['Pollo A', 'Gemini'])
    // narrow by provider too: AND across facets (Gemini is OpenRouter, drops out)
    await w.findAll('.frow.provider input')[0].setValue(true) // Pollo
    expect(modelNames(w)).toEqual(['Pollo A'])
    w.unmount()
  })

  it('Clear resets provider, tag and uncensored filters (keeping the search box)', async () => {
    const w = await openVid()
    await w.findAll('.frow.provider input')[0].setValue(true)
    await w.findAll('.frow.tag input')[0].setValue(true)
    expect(w.find('.fclear').exists()).toBe(true)
    await w.find('.fclear').trigger('click')
    expect(modelNames(w)).toEqual(['Pollo A', 'Pollo B', 'Gemini', 'Qwen OR'])
    expect(w.find('.fclear').exists()).toBe(false)
    expect(useModelFilters().hasActive('video')).toBe(false)
    w.unmount()
  })

  it('always keeps the current pick visible even when filtered out', async () => {
    const w = await openVid({ modelValue: 'google/g' }) // Gemini: OpenRouter + text2vid
    await w.findAll('.frow.provider input')[0].setValue(true) // Pollo only
    expect(modelNames(w)).toContain('Gemini')
    w.unmount()
  })

  it('shows the selected provider on the closed picker', () => {
    const w = mount(ModelPicker, {
      props: { models: MIXED, label: 'Video', kind: 'video', modelValue: 'pollo/a' },
    })
    expect(w.find('.picker-label').text()).toBe('Video · Pollo')
    w.unmount()
  })

  it('adds a Venice chip, and only shows chips for providers that have models', async () => {
    const withVenice = [...MIXED, { id: 'venice/v', name: 'Venice V', tags: ['img2vid'] }]
    const w = await openVid({ models: withVenice })
    expect(providerChips(w)).toEqual(['Pollo 2', 'Venice 1', 'OpenRouter 2'])
    w.unmount()
    const noPollo = await openVid({ models: withVenice.filter(m => !m.id.startsWith('pollo/')) })
    expect(providerChips(noPollo)).toEqual(['Venice 1', 'OpenRouter 2'])
    noPollo.unmount()
  })

  it('marks uncensored models in the list and on the closed picker', async () => {
    const models = [
      { id: 'venice/lustify-v8', name: 'Venice: Lustify', uncensored: true },
      { id: 'venice/flux-2-pro', name: 'Venice: Flux 2 Pro' },
    ]
    const w = await openPicker({ models })
    const badgesOf = name =>
      w
        .findAll('.picker-item')
        .find(i => i.text().includes(name))
        .findAll('.item-badge.uncensored')
    expect(badgesOf('Lustify')).toHaveLength(1)
    expect(badgesOf('Flux 2 Pro')).toHaveLength(0)
    w.unmount()
    const closed = mount(ModelPicker, {
      props: { models, label: 'Image', kind: 'image', modelValue: 'venice/lustify-v8' },
    })
    expect(closed.find('.picker-value .uncensored').text()).toContain('uncensored')
    closed.unmount()
  })

  it('shows Venice privacy levels in the list and on the closed picker', async () => {
    const models = [
      { id: 'venice/lustify-v8', name: 'Venice: Lustify', privacy: 'private' },
      { id: 'venice/flux-2-pro', name: 'Venice: Flux 2 Pro', privacy: 'anonymized' },
      { id: 'venice/other', name: 'Venice: Other' },
    ]
    const w = await openPicker({ models })
    const item = name => w.findAll('.picker-item').find(i => i.text().includes(name))
    expect(item('Lustify').find('.item-badge.private').text()).toBe('private')
    expect(item('Flux 2 Pro').find('.item-badge.anonymized').text()).toBe('anonymized')
    expect(item('Other').find('.item-badge.private').exists()).toBe(false)
    expect(item('Other').find('.item-badge.anonymized').exists()).toBe(false)
    w.unmount()
    const closed = mount(ModelPicker, {
      props: { models, label: 'Image', kind: 'image', modelValue: 'venice/lustify-v8' },
    })
    expect(closed.find('.picker-value .private').text()).toContain('private')
    closed.unmount()
  })
})

describe('ModelPicker row badges', () => {
  it('shows capability tags on the row, folding more than two into coloured dots', async () => {
    const models = [
      { id: 'pollo/few', name: 'Few', tags: ['img2vid', 'motion'] },
      { id: 'pollo/many', name: 'Many', tags: ['img2vid', 'text2vid', 'motion', 'audio'] },
    ]
    const w = await openPicker({ kind: 'video', models })
    const row = name => w.findAll('.picker-item').find(i => i.find('.item-name').text() === name)
    expect(row('Few').find('.item-badges.collapsed').exists()).toBe(false)
    expect(
      row('Few')
        .findAll('.item-badge')
        .map(b => b.text()),
    ).toEqual(['Image→Video', 'Motion / recast'])
    const many = row('Many')
    expect(many.find('.item-badges.collapsed').exists()).toBe(true)
    expect(many.findAll('.dot')).toHaveLength(4)
    // every tag has its own colour, and each dot matches its label
    const colours = many.findAll('.badge-list .item-badge').map(b => b.attributes('style'))
    expect(new Set(colours).size).toBe(4)
    expect(many.findAll('.dot').map(d => d.attributes('style'))).toEqual(colours)
    expect(many.findAll('.badge-list .item-badge')).toHaveLength(4) // the labels, shown on hover
    w.unmount()
  })
})

describe('ModelPicker uncensored filter', () => {
  const MODELS = [
    { id: 'venice/lustify-v8', name: 'Venice: Lustify', uncensored: true },
    { id: 'venice/flux-2-pro', name: 'Venice: Flux 2 Pro' },
    { id: 'or/img', name: 'OpenRouter Img' },
  ]
  beforeEach(() => {
    localStorage.clear()
    useModelFilters().clear('image')
    useUncensoredOnly().uncensoredOnly.value = false
  })

  it('narrows the list to uncensored models, dropping providers left empty', async () => {
    const w = mount(ModelPicker, { attachTo: document.body, props: { models: MODELS, label: 'Image', kind: 'image' } })
    await w.find('.picker-btn').trigger('click')
    await openFilters(w)
    // Venice (uncensored + plain) and OpenRouter → two providers before filtering
    expect(w.findAll('.frow.provider')).toHaveLength(2)
    const toggle = w.find('.uncensored-only input')
    expect(w.find('.uncensored-only .fn').text()).toBe('1')
    await toggle.setValue(true)
    expect(w.findAll('.frow.provider')).toHaveLength(0) // only Venice is left
    expect(
      w
        .findAll('.item-name')
        .map(n => n.text())
        .filter(n => n !== 'None'),
    ).toEqual(['Venice: Lustify'])
    w.unmount()
  })

  it('is only offered when the list has uncensored models', async () => {
    const w = mount(ModelPicker, {
      attachTo: document.body,
      props: { models: MODELS.slice(1), label: 'Image', kind: 'image' },
    })
    await w.find('.picker-btn').trigger('click')
    await openFilters(w)
    expect(w.find('.uncensored-only').exists()).toBe(false)
    w.unmount()
  })
})

describe('ModelPicker prices', () => {
  it('shows Venice per-image and quoted video prices', async () => {
    const img = mount(ModelPicker, {
      attachTo: document.body,
      props: {
        label: 'Image',
        kind: 'image',
        models: [
          { id: 'venice/a', name: 'A', price: { usd: 0.05, basis: '' } },
          { id: 'venice/b', name: 'B', price: { usd: 0.1, basis: '1K' } },
        ],
      },
    })
    await img.find('.picker-btn').trigger('click')
    expect(img.findAll('.item-badge').map(b => b.text())).toEqual(['$0.05', '$0.10'])
    img.unmount()
    const vid = mount(ModelPicker, {
      attachTo: document.body,
      props: {
        label: 'Video',
        kind: 'video',
        models: [{ id: 'venice/v', name: 'V', price: { usd: 0.65, basis: '5s · 720p' } }],
      },
    })
    await vid.find('.picker-btn').trigger('click')
    const badge = vid.findAll('.item-badge').find(b => b.text() === '$0.65')
    expect(badge.attributes('title')).toContain('5s · 720p')
    vid.unmount()
  })
})

describe('ModelPicker pop-up placement', () => {
  it("floats next to its button and fits the window, so a scrolling sidebar can't clip it", async () => {
    const w = mount(ModelPicker, {
      attachTo: document.body,
      props: {
        models: [{ id: 'a/b', name: 'A' }],
        label: 'Chat',
        kind: 'text',
      },
    })
    w.element.getBoundingClientRect = () => ({ left: 900, right: 1180, top: 100, bottom: 140, width: 280, height: 40 })
    Object.assign(window, { innerWidth: 1200, innerHeight: 800 })
    await w.find('.picker-btn').trigger('click')
    const style = w.find('.picker-pop').attributes('style')
    expect(style).toContain('top: 146px')
    expect(style).toContain('left: 772px') // pulled in so the 420px pop-up stays on screen
    w.unmount()
  })
})

describe('ModelPicker hidden models', () => {
  const WITH_HIDDEN = [
    { id: 'pollo/seedream', name: 'Pollo: Seedream 5.0 Lite' },
    {
      id: 'pollo/seedreampro',
      name: 'Pollo: Seedream 5.0 Pro',
      hidden: 'Not enabled for API access on this key (403)',
    },
  ]
  const modelNames = w => names(w).filter(n => n !== 'None')

  beforeEach(() => {
    localStorage.clear()
    useShowHidden().showHidden.value = false
  })

  it('hides them until "Show hidden" is ticked, then badges them', async () => {
    const w = await openFilters(await openPicker({ models: WITH_HIDDEN, modelValue: 'pollo/seedream' }))
    expect(modelNames(w)).toEqual(['Pollo: Seedream 5.0 Lite'])
    expect(w.find('.show-hidden .fn').text()).toBe('1')
    await w.find('.show-hidden input').setValue(true)
    expect(modelNames(w)).toEqual(['Pollo: Seedream 5.0 Lite', 'Pollo: Seedream 5.0 Pro'])
    const badge = w.findAll('.item-badge').find(b => b.text() === 'hidden')
    expect(badge.attributes('title')).toContain('403')
    w.unmount()
  })

  it('keeps a hidden model that is already selected', async () => {
    const w = await openPicker({ models: WITH_HIDDEN, modelValue: 'pollo/seedreampro' })
    expect(modelNames(w)).toEqual(['Pollo: Seedream 5.0 Lite', 'Pollo: Seedream 5.0 Pro'])
    w.unmount()
  })

  it('has no checkbox when nothing is hidden', async () => {
    const w = await openPicker()
    expect(w.find('.show-hidden').exists()).toBe(false)
    w.unmount()
  })
})
