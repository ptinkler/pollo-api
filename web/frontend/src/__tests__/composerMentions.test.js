/**
 * StudioComposer reference mentions: the @-picker lists attachments as
 * image1 / video1… handles (matching the backend's web/chat/turn.py _ref_items),
 * clicking one inserts a [@name] mention, and the [@name] text round-trips
 * through the contenteditable as inline pills.
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import StudioComposer from '../components/studio/StudioComposer.vue'

const REF_MODE = { types: ['image', 'video', 'audio'], max: 15, limits: { image: 10, video: 5, audio: 3 } }

function make(attachments, draft = '') {
  return mount(StudioComposer, {
    props: { mode: 'video', refMode: REF_MODE, attachments, draft, 'onUpdate:draft': () => {} },
  })
}

const atts = [
  { key: 'k1', video: true, preview: 'v1.jpg' },
  { key: 'k2', preview: 'i1.png' },
  { key: 'k3', preview: 'i2.png' },
]

describe('StudioComposer mentions', () => {
  it('focuses the prompt when clicking empty space in the composer bar', async () => {
    const w = make(atts)
    const focus = vi.spyOn(w.find('.ed').element, 'focus')
    await w.find('.cbox').trigger('click')
    expect(focus).toHaveBeenCalled()
  })

  it('labels refs by type and order in the @ picker', async () => {
    const w = make(atts)
    await w.find('.clip.at').trigger('click')
    const labels = w.findAll('.atmenu button').map(b => b.text().replace(/[🎞🔊]/gu, '').trim())
    expect(labels).toEqual(['Video 1', 'Image 1', 'Image 2'])
  })

  it('opens the reference picker when typing @, then inserts the selected pill', async () => {
    const w = make(atts)
    await w.find('.ed').trigger('keydown', { key: '@' })
    expect(w.find('.atmenu').exists()).toBe(true)

    await w.findAll('.atmenu button')[0].trigger('click')
    expect(w.find('.ed .pill').attributes('data-name')).toBe('video1')
    expect(w.emitted('update:draft').at(-1)[0]).toContain('[@video1]')
  })

  it('uses a placeholder that does not require typing reference syntax', () => {
    const w = make(atts)
    expect(w.find('.ed').attributes('data-placeholder')).toContain('Type @')
    expect(w.find('.ed').attributes('data-placeholder')).not.toMatch(/\[@|\]/)
    expect(w.find('.ed').attributes('data-empty')).toBe('true')
  })

  it('keeps mode buttons on the bottom action row and tracks empty prompt state', async () => {
    const w = mount(StudioComposer, {
      props: {
        mode: 'image',
        modes: [
          { id: 'image', label: 'Image' },
          { id: 'video', label: 'Video' },
        ],
      },
    })
    expect(w.find('.cbar .modes').exists()).toBe(true)
    expect(w.find('.cbar').element.previousElementSibling).toBe(w.find('.ed').element)

    await w.setProps({ draft: 'A prompt' })
    expect(w.find('.ed').attributes('data-empty')).toBe('false')
  })

  it('inserts a [@name] mention when a picker item is clicked', async () => {
    const w = make(atts)
    await w.find('.clip.at').trigger('click')
    await w.findAll('.atmenu button')[0].trigger('click') // Video 1
    const emits = w.emitted('update:draft')
    expect(emits.at(-1)[0]).toContain('[@video1]')
  })

  it('renders existing [@name] tokens as inline pills', async () => {
    const w = make(atts, 'replace [@video1] with [@image1]')
    const pills = w.find('.ed').findAll('.pill')
    expect(pills.map(p => p.attributes('data-name'))).toEqual(['video1', 'image1'])
    // Serializing the pills (on input) round-trips back to the [@name] text form.
    await w.find('.ed').trigger('input')
    expect(w.emitted('update:draft').at(-1)[0]).toBe('replace [@video1] with [@image1]')
  })

  it('has no @ picker for a non-ref model', () => {
    const w = mount(StudioComposer, { props: { mode: 'video', refMode: null, attachments: atts } })
    expect(w.find('.clip.at').exists()).toBe(false)
  })

  it('respects per-type caps (max 1 video drops the second)', async () => {
    const w = make([
      { key: 'a', video: true, preview: 'v1' },
      { key: 'b', video: true, preview: 'v2' },
      { key: 'c', preview: 'i1' },
    ])
    // Omni-style: only 1 video allowed.
    await w.setProps({ refMode: { types: ['image', 'video'], max: 7, limits: { image: 4, video: 1 } } })
    await w.find('.clip.at').trigger('click')
    const labels = w.findAll('.atmenu button').map(b => b.text().replace(/[🎞🔊]/gu, '').trim())
    expect(labels).toEqual(['Video 1', 'Image 1']) // 2nd video over the cap
  })
})
