import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InstructionEditor from '../components/chat/InstructionEditor.vue'
import InstructionPicker from '../components/chat/InstructionPicker.vue'
import InstructionsView from '../views/InstructionsView.vue'
import { useChatDefaults } from '../composables/useChatDefaults'

const resp = j => ({ ok: true, status: 200, json: async () => j })
const snippets = [
  { id: 1, name: 'Terse tone', content: 'Be brief.' },
  { id: 2, name: 'British spelling', content: 'Use British spelling.' },
  { id: 3, name: 'No emoji', content: 'Never use emoji.' },
]
const groups = [{ id: 7, name: 'House style', snippet_ids: [1] }]
const EMPTY = { default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] }
const spaces = [{ id: 4, name: 'Novel', ...EMPTY }]

let calls
beforeEach(() => {
  calls = []
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    url = String(url)
    calls.push([opts.method || 'GET', url, opts.body ? JSON.parse(opts.body) : null])
    if (url.includes('/settings')) return resp(opts.method === 'PUT' ? JSON.parse(opts.body) : { ...EMPTY })
    if (url.includes('/spaces/')) return resp({ id: 4, ...JSON.parse(opts.body) })
    if (url.includes('/spaces')) return resp({ spaces })
    if (url.endsWith('/instructions')) return resp({ instructions: snippets, groups })
    if (opts.method === 'PUT') return resp({ id: Number(url.split('/').pop()), ...JSON.parse(opts.body) })
    if (opts.method === 'POST') return resp({ id: 99, ...JSON.parse(opts.body) })
    return resp({})
  })
})

describe('InstructionEditor', () => {
  let w
  afterEach(() => w?.unmount())

  async function open(target) {
    w = mount(InstructionEditor, { props: { target: null, instructions: snippets, groups }, attachTo: document.body })
    await w.setProps({ target })
    await flushPromises()
    return document.body.querySelector('.dialog[role="dialog"]')
  }

  it("adds snippets to a group by searching, saves the group's snippets and closes", async () => {
    const dialog = await open({ kind: 'group', id: 7 })
    expect(dialog.querySelector('input[aria-label="Name"]').value).toBe('House style')
    const adder = dialog.querySelector('input[aria-label="Add a snippet"]')
    adder.value = 'emoji'
    adder.dispatchEvent(new Event('input'))
    await flushPromises()
    const options = [...dialog.querySelectorAll('.adder-menu .item')]
    expect(options.map(o => o.textContent.trim())).toEqual(['No emoji']) // members aren't offered again
    options[0].click()
    await flushPromises()
    dialog.querySelector('.btn-primary').click()
    await flushPromises()
    const put = calls.find(c => c[0] === 'PUT' && c[1].endsWith('/instruction-groups/7'))
    expect(put[2]).toEqual({ name: 'House style', snippet_ids: [1, 3] })
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('saves "Default for" picks with the Save button, for any space', async () => {
    useChatDefaults().setCurrentSpace(null)
    await useChatDefaults().loadDefaults()
    const dialog = await open({ kind: 'snippet', id: 1 })
    const save = dialog.querySelector('.btn-primary')
    expect(save.disabled).toBe(true) // nothing changed yet
    dialog.querySelector('.def-toggles .trigger').click()
    await flushPromises()
    const option = name => [...dialog.querySelectorAll('.option')].find(o => o.textContent.includes(name))
    option('All chats').click()
    option('Novel').click()
    await flushPromises()
    expect(dialog.querySelector('.trigger').textContent).toContain('All chats, Novel')
    expect(save.disabled).toBe(false) // picks alone are a change to save
    expect(calls.some(c => c[0] === 'PUT')).toBe(false) // nothing written before Save
    save.click()
    await flushPromises()
    expect(calls.find(c => c[0] === 'PUT' && c[1].includes('/settings'))[2].default_instruction_ids).toEqual([1])
    expect(calls.find(c => c[0] === 'PUT' && c[1].endsWith('/spaces/4'))[2].default_instruction_ids).toEqual([1])
  })
})

describe('InstructionsView', () => {
  it('lists groups and snippets and opens one in the editor', async () => {
    const w = mount(InstructionsView, { attachTo: document.body })
    await flushPromises()
    expect(w.findAll('.card h3').map(h => h.text())).toEqual([
      '📦 House style',
      'Terse tone',
      'British spelling',
      'No emoji',
    ])
    await w.find('.search').setValue('brit')
    expect(w.findAll('.card h3').map(h => h.text())).toEqual(['British spelling'])
    await w.find('.card').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.dialog input[aria-label="Name"]').value).toBe('British spelling')
    w.unmount()
  })
})

describe('InstructionPicker', () => {
  it('opens an attached snippet or group when its chip is clicked', async () => {
    const w = mount(InstructionPicker, {
      props: { instructions: snippets, groups, snippetIds: [2], groupIds: [7] },
    })
    const chips = w.findAll('.chip-main')
    await chips[0].trigger('click')
    await chips[1].trigger('click')
    expect(w.emitted('edit')).toEqual([[{ kind: 'group', id: 7 }], [{ kind: 'snippet', id: 2 }]])
  })

  it('shows what the defaults attach, which can be hidden in this chat and brought back', async () => {
    const w = mount(InstructionPicker, {
      props: {
        instructions: snippets,
        groups,
        snippetIds: [2],
        groupIds: [],
        inheritedSnippets: [{ id: 1, from: 'Novel' }],
        inheritedGroups: [{ id: 7, from: 'All chats' }],
        hiddenSnippets: [{ id: 3, from: 'All chats' }],
      },
    })
    const inherited = w.findAll('.chip.inherited')
    expect(inherited.map(c => c.find('.chip-name').text())).toEqual(['📦 House style', 'Terse tone'])
    expect(inherited[1].attributes('title')).toContain('From the Novel defaults')
    await inherited[1].find('.chip-x').trigger('click')
    expect(w.emitted('hide')).toEqual([[{ kind: 'snippet', id: 1 }]])
    // The hidden one is offered to switch back on, not to attach as the chat's own
    await w.find('.add').trigger('click')
    expect(w.findAll('.menu .item').map(i => i.text())).toEqual(['No emoji🌐', '⚙ All instructions…'])
    await w.find('.menu .item.hidden-default').trigger('click')
    expect(w.emitted('unhide')).toEqual([[{ kind: 'snippet', id: 3 }]])
    w.unmount()
  })

  it('searches the add menu once there is a lot to pick from', async () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, name: `Snippet ${i}`, content: '' }))
    const w = mount(InstructionPicker, { props: { instructions: many, groups: [], snippetIds: [], groupIds: [] } })
    await w.find('.add').trigger('click')
    await w.find('.menu-search').setValue('7')
    expect(w.findAll('.menu .item').map(i => i.text())).toEqual(['Snippet 7', '⚙ All instructions…'])
    w.unmount()
  })
})
