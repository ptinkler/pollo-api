import { describe, it, expect, beforeEach } from 'vitest'
import { reactive } from 'vue'
import { useComposerSettings } from '../composables/useComposerSettings'

const STORE_KEY = 'chat.prefs'

// A catalogue in the shape /api/chat/models returns
const catalogue = () =>
  reactive({
    text: [{ id: 'anthropic/claude-sonnet', supports_tools: true }, { id: 'openai/gpt-5' }],
    image: [{ id: 'pollo/seedream' }, { id: 'pollo/flux2max' }],
    video: [{ id: 'pollo/seedance20fast' }],
    audio: [{ id: 'pollo/elevenv3' }],
  })

describe('useComposerSettings: remembered models that no longer exist', () => {
  beforeEach(() => localStorage.clear())

  it('replaces a renamed or retired pick with a default', () => {
    // what this browser remembered before the Pollo keys lost their v1 suffix
    localStorage.setItem(STORE_KEY, JSON.stringify({ image: 'pollo/seedreamv1', video: 'pollo/seedance20fastv1' }))
    const s = useComposerSettings(catalogue())
    s.applyDefaults()
    expect(s.selected.image).toBe('pollo/seedream')
    expect(s.selected.video).toBe('pollo/seedance20fast')
  })

  it('keeps a remembered pick the catalogue still has', () => {
    localStorage.setItem(STORE_KEY, JSON.stringify({ image: 'pollo/flux2max' }))
    const s = useComposerSettings(catalogue())
    s.applyDefaults()
    expect(s.selected.image).toBe('pollo/flux2max')
  })

  it('keeps a deliberate "None" for image and video', () => {
    localStorage.setItem(STORE_KEY, JSON.stringify({ image: '', video: '' }))
    const s = useComposerSettings(catalogue())
    s.applyDefaults()
    expect(s.selected.image).toBe('')
    expect(s.selected.video).toBe('')
  })

  it("does not discard a pick while that provider's catalogue is empty", () => {
    // A provider outage (or no key yet) must not wipe what the user chose
    localStorage.setItem(STORE_KEY, JSON.stringify({ image: 'pollo/seedream' }))
    const models = catalogue()
    models.image = []
    const s = useComposerSettings(models)
    s.applyDefaults()
    expect(s.selected.image).toBe('pollo/seedream')
  })

  it('ignores a thread model the catalogue no longer has, keeping the current pick', () => {
    const s = useComposerSettings(catalogue())
    s.applyDefaults()
    const before = s.selected.image
    s.applyChat({ image_model: 'pollo/polloimage2', settings: null })
    expect(s.selected.image).toBe(before)
  })

  it('adopts a thread model the catalogue has', () => {
    const s = useComposerSettings(catalogue())
    s.applyChat({ image_model: 'pollo/flux2max', settings: { audio_model: 'pollo/elevenv3' } })
    expect(s.selected.image).toBe('pollo/flux2max')
    expect(s.selected.audio).toBe('pollo/elevenv3')
  })
})
