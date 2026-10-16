import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DefaultToggles from '../components/chat/DefaultToggles.vue'
import { useChatDefaults } from '../composables/useChatDefaults'

const resp = j => ({ ok: true, status: 200, json: async () => j })
const EMPTY = { default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] }

describe('DefaultToggles', () => {
  let calls, spaces
  beforeEach(async () => {
    calls = []
    spaces = [{ id: 3, name: 'Novel', ...EMPTY }]
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      url = String(url)
      calls.push([opts.method || 'GET', url, opts.body ? JSON.parse(opts.body) : null])
      if (url.includes('/settings')) return resp(opts.method === 'PUT' ? JSON.parse(opts.body) : { ...EMPTY })
      if (url.includes('/spaces/')) return resp({ id: Number(url.split('/').pop()), ...JSON.parse(opts.body) })
      if (url.includes('/spaces')) return resp({ spaces })
      return resp({})
    })
    await useChatDefaults().loadDefaults()
  })

  const option = (w, name) => w.findAll('.option').find(o => o.text().includes(name))

  it('picks from all chats and every space, saved only when the editor commits', async () => {
    useChatDefaults().setCurrentSpace(null) // every space is offered, not just the chat's
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: 5 } })
    await flushPromises()
    expect(w.findAll('.pill')).toHaveLength(0)
    await w.find('.add').trigger('click')
    expect(w.find('.search').exists()).toBe(true) // always searchable
    expect(w.findAll('.option').map(o => o.find('.name').text())).toEqual(['All chats', 'Novel'])
    await option(w, 'Novel').trigger('click')
    await option(w, 'All chats').trigger('click')
    expect(option(w, 'Novel').attributes('aria-selected')).toBe('true')
    expect(w.findAll('.pill .pill-name').map(p => p.text())).toEqual(['🌐 All chats', '🗂 Novel'])
    expect(w.emitted('update:dirty').at(-1)).toEqual([true]) // the editor's Save lights up
    expect(calls.some(c => c[0] === 'PUT')).toBe(false) // nothing written yet

    await w.vm.commit(5)
    await flushPromises()
    expect(calls.find(c => c[1].includes('/settings') && c[0] === 'PUT')[2].default_instruction_ids).toEqual([5])
    expect(calls.find(c => c[1].endsWith('/spaces/3'))[2].default_instruction_ids).toEqual([5])
    expect(w.emitted('update:dirty').at(-1)).toEqual([false])
  })

  it('clicking a ticked one unticks it', async () => {
    const w = mount(DefaultToggles, { props: { kind: 'character', itemId: 9 } })
    await flushPromises()
    await w.find('.add').trigger('click')
    await option(w, 'Novel').trigger('click')
    await option(w, 'Novel').trigger('click')
    expect(option(w, 'Novel').attributes('aria-selected')).toBe('false')
    expect(w.emitted('update:dirty').at(-1)).toEqual([false])
  })

  it('a pill’s ✕ takes it off', async () => {
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: 5 } })
    await flushPromises()
    await w.find('.add').trigger('click')
    await option(w, 'Novel').trigger('click')
    await w.find('.pill .pill-x').trigger('click')
    expect(w.findAll('.pill')).toHaveLength(0)
    expect(w.emitted('update:dirty').at(-1)).toEqual([false])
  })

  it('searches the list', async () => {
    spaces = Array.from({ length: 8 }, (_, i) => ({ id: 10 + i, name: `Space ${i}`, ...EMPTY }))
    await useChatDefaults().loadDefaults()
    const w = mount(DefaultToggles, { props: { kind: 'instruction', itemId: 5 } })
    await flushPromises()
    await w.find('.add').trigger('click')
    await w.find('.search').setValue('5')
    expect(w.findAll('.option').map(o => o.find('.name').text())).toEqual(['Space 5'])
  })

  it('works for an item that is saved for the first time', async () => {
    const w = mount(DefaultToggles, { props: { kind: 'instruction_group', itemId: null } })
    await flushPromises()
    await w.find('.add').trigger('click')
    await option(w, 'All chats').trigger('click')
    await w.vm.commit(42) // the id it was created under
    await flushPromises()
    const put = calls.findLast(c => c[0] === 'PUT' && c[1].includes('/settings'))
    expect(put[2].default_instruction_group_ids).toContain(42)
  })
})
