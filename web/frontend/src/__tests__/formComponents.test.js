/**
 * Tests for form components — SleekInput, SleekSelect, SleekTextarea
 * and the form/index.js barrel export
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'

// ── SleekInput ──────────────────────────────────────────────────────

import SleekInput from '../components/form/SleekInput.vue'

describe('SleekInput', () => {
  it('renders label', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'Image URL', modelValue: '' },
    })
    expect(wrapper.text()).toContain('Image URL')
  })

  it('renders hint when provided', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '', hint: 'Optional' },
    })
    expect(wrapper.text()).toContain('Optional')
  })

  it('does not render hint when empty', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '' },
    })
    expect(wrapper.find('.field-hint').exists()).toBe(false)
  })

  it('emits update on input', async () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '' },
    })
    await wrapper.find('input').setValue('https://example.com')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['https://example.com'])
  })

  it('renders placeholder', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '', placeholder: 'Enter URL...' },
    })
    expect(wrapper.find('input').attributes('placeholder')).toBe('Enter URL...')
  })

  it('adds focused class on focus', async () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '' },
    })
    await wrapper.find('input').trigger('focus')
    expect(wrapper.find('.sleek-input').classes()).toContain('focused')
  })

  it('removes focused class on blur', async () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '' },
    })
    await wrapper.find('input').trigger('focus')
    await wrapper.find('input').trigger('blur')
    expect(wrapper.find('.sleek-input').classes()).not.toContain('focused')
  })

  it('has has-value class when value present', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: 'something' },
    })
    expect(wrapper.find('.sleek-input').classes()).toContain('has-value')
  })

  it('no has-value class when empty', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '' },
    })
    expect(wrapper.find('.sleek-input').classes()).not.toContain('has-value')
  })

  it('respects type prop', () => {
    const wrapper = mount(SleekInput, {
      props: { label: 'URL', modelValue: '', type: 'url' },
    })
    expect(wrapper.find('input').attributes('type')).toBe('url')
  })
})

// ── SleekSelect ─────────────────────────────────────────────────────

import SleekSelect from '../components/form/SleekSelect.vue'

describe('SleekSelect', () => {
  const stringOptions = ['480p', '720p']
  const objectOptions = [
    { value: 'pollodance20', label: 'Sora 2' },
    { value: 'pollo20', label: 'Pollo 2.0' },
  ]

  it('renders label', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Resolution', modelValue: '480p', options: stringOptions },
    })
    expect(wrapper.text()).toContain('Resolution')
  })

  it('renders string options', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '', options: stringOptions },
    })
    const opts = wrapper.findAll('option')
    expect(opts).toHaveLength(2)
    expect(opts[0].text()).toBe('480p')
  })

  it('renders object options with label/value', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Model', modelValue: 'pollodance20', options: objectOptions },
    })
    const opts = wrapper.findAll('option')
    expect(opts[0].text()).toBe('Sora 2')
    expect(opts[0].attributes('value')).toBe('pollodance20')
  })

  it('emits on change', async () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '480p', options: stringOptions },
    })
    await wrapper.find('select').setValue('720p')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['720p'])
  })

  it('renders hint', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '', options: stringOptions, hint: 'Pick one' },
    })
    expect(wrapper.text()).toContain('Pick one')
  })

  it('adds focused class on focus', async () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '', options: stringOptions },
    })
    await wrapper.find('select').trigger('focus')
    expect(wrapper.find('.sleek-select').classes()).toContain('focused')
  })

  it('has has-value class when value present', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '720p', options: stringOptions },
    })
    expect(wrapper.find('.sleek-select').classes()).toContain('has-value')
  })

  it('no has-value class when empty', () => {
    const wrapper = mount(SleekSelect, {
      props: { label: 'Res', modelValue: '', options: stringOptions },
    })
    expect(wrapper.find('.sleek-select').classes()).not.toContain('has-value')
  })
})

// ── SleekTextarea ───────────────────────────────────────────────────

import SleekTextarea from '../components/form/SleekTextarea.vue'

describe('SleekTextarea', () => {
  it('renders label', () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '' },
    })
    expect(wrapper.text()).toContain('Prompt')
  })

  it('emits update on input', async () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '' },
    })
    await wrapper.find('textarea').setValue('Hello world')
    expect(wrapper.emitted('update:modelValue')[0]).toEqual(['Hello world'])
  })

  it('renders placeholder', () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '', placeholder: 'Type here...' },
    })
    expect(wrapper.find('textarea').attributes('placeholder')).toBe('Type here...')
  })

  it('renders hint', () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '', hint: 'Required' },
    })
    expect(wrapper.text()).toContain('Required')
  })

  it('respects rows prop', () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '', rows: 6 },
    })
    expect(wrapper.find('textarea').attributes('rows')).toBe('6')
  })

  it('adds focused class on focus', async () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: '' },
    })
    await wrapper.find('textarea').trigger('focus')
    expect(wrapper.find('.sleek-textarea').classes()).toContain('focused')
  })

  it('has has-value class when value present', () => {
    const wrapper = mount(SleekTextarea, {
      props: { label: 'Prompt', modelValue: 'content' },
    })
    expect(wrapper.find('.sleek-textarea').classes()).toContain('has-value')
  })
})

// ── form/index.js barrel export ─────────────────────────────────────

describe('form/index.js exports', () => {
  it('exports all form components', async () => {
    const exports = await import('../components/form/index.js')
    expect(exports.SleekInput).toBeDefined()
    expect(exports.SleekTextarea).toBeDefined()
    expect(exports.SleekSelect).toBeDefined()
    expect(exports.ToggleSwitch).toBeDefined()
    expect(exports.RatioPicker).toBeDefined()
    expect(exports.LengthSlider).toBeDefined()
  })
})

