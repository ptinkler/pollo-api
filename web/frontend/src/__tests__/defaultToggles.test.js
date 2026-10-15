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
      if (String(url).includes('/settings')) return resp(opts.method === 'PUT' ? JSON.parse(opts.body) : { ...EMPTY })
      if (String(url).includes('/spaces')) return resp({ spaces: [space] })
      return resp({})
    })
  })

  it('keeps a pick as an unsaved change until the editor saves it', async () => {
    useChatDefaults().setCurrentSpace(null)
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: 5 } })
    await flushPromises()
    const pills = w.findAll('.pill')
    expect(pills).toHaveLength(1) // no space in context: just "All chats"
    await pills[0].trigger('click')
    expect(w.find('.pill').attributes('aria-pressed')).toBe('true')
    expect(w.emitted('update:dirty').at(-1)).toEqual([true]) // the editor's Save lights up
    expect(calls.some(c => c[0] === 'PUT')).toBe(false) // nothing written yet

    await w.vm.commit(5)
    await flushPromises()
    const put = calls.find(c => c[0] === 'PUT' && c[1].includes('/settings'))
    expect(put[2].default_instruction_ids).toEqual([5])
    expect(w.emitted('update:dirty').at(-1)).toEqual([false])
  })

  it('adds a space pill when a chat in a space is in context', async () => {
    const d = useChatDefaults()
    await d.loadDefaults()
    d.setCurrentSpace(3)
    const w = mount(DefaultToggles, { props: { kind: 'character', itemId: 9 } })
    await flushPromises()
    expect(w.findAll('.pill')).toHaveLength(2)
    expect(w.text()).toContain('Novel')
  })

  it('works for an item that is saved for the first time', async () => {
    useChatDefaults().setCurrentSpace(null)
    const w = mount(DefaultToggles, { props: { kind: 'instruction_group', itemId: null } })
    await flushPromises()
    await w.find('.pill').trigger('click')
    await w.vm.commit(42) // the id it was created under
    await flushPromises()
    const put = calls.findLast(c => c[0] === 'PUT' && c[1].includes('/settings'))
    expect(put[2].default_instruction_group_ids).toContain(42)
  })
})
