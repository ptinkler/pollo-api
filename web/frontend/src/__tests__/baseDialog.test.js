import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import BaseDialog from '../components/BaseDialog.vue'

describe('BaseDialog', () => {
  it('Esc closes only the dialog on top (a picker opened from inside another)', () => {
    const outer = mount(BaseDialog, { props: { open: true, title: 'Space' }, attachTo: document.body })
    const inner = mount(BaseDialog, { props: { open: true, title: 'Characters' }, attachTo: document.body })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(inner.emitted('close')).toHaveLength(1)
    expect(outer.emitted('close')).toBeUndefined()
    inner.unmount()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(outer.emitted('close')).toHaveLength(1)
    outer.unmount()
  })
})
