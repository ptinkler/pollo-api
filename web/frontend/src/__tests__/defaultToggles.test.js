import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DefaultToggles from '../components/chat/DefaultToggles.vue'
import { useChatDefaults } from '../composables/useChatDefaults'

const resp = j => ({ ok: true, status: 200, json: async () => j })
const EMPTY = { default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] }
const space = { id: 3, name: 'Novel', ...EMPTY }

describe('DefaultToggles', () => {
  let calls
  beforeEach(() => {
    calls = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      calls.push([opts.method || 'GET', String(url), opts.body ? JSON.parse(opts.body) : null])
      if (String(url).includes('/settings')) return resp({ ...EMPTY })
      if (String(url).includes('/spaces')) return resp({ spaces: [space] })
      return resp({})
    })
  })

  it('shows only the global toggle with no space in context and PUTs settings when toggled', async () => {
    useChatDefaults().setCurrentSpace(null)
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: 5 } })
    await flushPromises()
    const checks = w.findAll('label.check')
    expect(checks).toHaveLength(1)
    await checks[0].find('input').trigger('change')
    await flushPromises()
    const put = calls.find(c => c[0] === 'PUT' && c[1].includes('/settings'))
    expect(put[2].default_instruction_ids).toEqual([5])
  })

  it('adds a space toggle when a chat in a space is in context', async () => {
    const d = useChatDefaults()
    await d.loadDefaults()
    d.setCurrentSpace(3)
    const w = mount(DefaultToggles, { props: { kind: 'character', itemId: 9 } })
    await flushPromises()
    expect(w.findAll('label.check')).toHaveLength(2)
    expect(w.text()).toContain('Novel')
  })

  it('disables the toggles for an unsaved item', async () => {
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: null } })
    await flushPromises()
    expect(w.find('input').element.disabled).toBe(true)
    expect(w.text()).toContain('Save it first')
  })
})
