/**
 * Tests for live Vue components — ToastContainer and the form components
 * (LengthSlider, RatioPicker, ToggleSwitch).
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

// ── ToastContainer ──────────────────────────────────────────────────

import ToastContainer from '../components/ToastContainer.vue'

describe('ToastContainer', () => {
  it('renders toasts', () => {
    const wrapper = mount(ToastContainer, {
      props: {
        toasts: [
          { id: 1, message: 'Success!', type: 'success' },
          { id: 2, message: 'Oops!', type: 'error' },
        ],
      },
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
        toasts: [{ id: 1, message: 'Click me', type: 'success' }],
      },
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
        ],
      },
    })
    const icons = wrapper.findAll('.toast-icon')
    expect(icons[0].text()).toBe('✓')
    expect(icons[1].text()).toBe('✗')
    expect(icons[2].text()).toBe('ℹ')
  })
})

// ── LengthSlider ────────────────────────────────────────────────────

import LengthSlider from '../components/form/LengthSlider.vue'

describe('LengthSlider', () => {
  it('renders a stop per valid length', () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    const opts = wrapper.findAll('datalist option')
    expect(opts).toHaveLength(3)
    expect(opts.map(o => o.attributes('label'))).toEqual(['5s', '10s', '15s'])
  })

  it('positions the slider at the index of the current value', () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    const input = wrapper.find('input[type=range]')
    expect(input.element.value).toBe('1')
    expect(input.attributes('max')).toBe('2')
  })

  it('shows the current value', () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    expect(wrapper.find('.length-value').text()).toBe('10s')
  })

  it('emits the mapped length on slide, not the raw index', async () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 10, lengths: [5, 10, 15] },
    })
    const input = wrapper.find('input[type=range]')
    await input.setValue('0')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([5])
  })

  it('only ever exposes valid stops, even for a gappy list', async () => {
    const wrapper = mount(LengthSlider, {
      props: { modelValue: 12, lengths: [4, 5, 6, 7, 8, 9, 10, 11, 12, 15] },
    })
    const input = wrapper.find('input[type=range]')
    expect(input.attributes('max')).toBe('9')
    await input.setValue('9')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual([15])
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
