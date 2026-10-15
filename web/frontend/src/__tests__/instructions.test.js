import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import InstructionsDialog from '../components/chat/InstructionsDialog.vue'
import InstructionPicker from '../components/chat/InstructionPicker.vue'

const resp = j => ({ ok: true, status: 200, json: async () => j })
const snippets = [
  { id: 1, name: 'Terse tone', content: 'Be brief.' },
  { id: 2, name: 'British spelling', content: 'Use British spelling.' },
  { id: 3, name: 'No emoji', content: 'Never use emoji.' },
]
const groups = [{ id: 7, name: 'House style', snippet_ids: [1] }]
const EMPTY = { default_character_ids: [], default_instruction_ids: [], default_instruction_group_ids: [] }

describe('InstructionsDialog', () => {
  let calls, w
  beforeEach(() => {
    calls = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      calls.push([opts.method || 'GET', String(url), opts.body ? JSON.parse(opts.body) : null])
      if (String(url).includes('/settings')) return resp({ ...EMPTY })
      if (String(url).includes('/spaces')) return resp({ spaces: [] })
      if (opts.method === 'PUT') return resp({ id: 7, ...JSON.parse(opts.body) })
      return resp({})
    })
  })
  afterEach(() => w?.unmount())

  async function open(focus) {
    w = mount(InstructionsDialog, {
      props: { open: false, instructions: snippets, groups, focus },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await flushPromises()
    return document.body.querySelector('[aria-label="Instructions"]')
  }

  it('opens on the snippet or group it was asked for', async () => {
    const dialog = await open({ kind: 'group', id: 7 })
    expect(dialog.querySelector('input[aria-label="Name"]').value).toBe('House style')
    expect([...dialog.querySelectorAll('.members .chip')].map(c => c.textContent.replace('✕', '').trim())).toEqual([
      'Terse tone',
    ])
  })

  it('searches one list of groups and snippets', async () => {
    const dialog = await open(null)
    const search = dialog.querySelector('input[aria-label="Search instructions"]')
    search.value = 'brit'
    search.dispatchEvent(new Event('input'))
    await flushPromises()
    expect([...dialog.querySelectorAll('.items .item')].map(i => i.textContent.trim())).toEqual(['British spelling'])
  })

  it("adds snippets to a group by searching, and saves the group's snippets", async () => {
    const dialog = await open({ kind: 'group', id: 7 })
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
  })
})

describe('InstructionsDialog defaults', () => {
  it('saves a "Default for" pick with the Save button', async () => {
    const calls = []
    globalThis.fetch = vi.fn(async (url, opts = {}) => {
      calls.push([opts.method || 'GET', String(url), opts.body ? JSON.parse(opts.body) : null])
      if (String(url).includes('/settings')) return resp(opts.method === 'PUT' ? JSON.parse(opts.body) : { ...EMPTY })
      if (String(url).includes('/spaces')) return resp({ spaces: [] })
      if (opts.method === 'PUT') return resp({ id: 1, ...JSON.parse(opts.body) })
      return resp({})
    })
    const { useChatDefaults } = await import('../composables/useChatDefaults')
    useChatDefaults().setCurrentSpace(null)
    const w = mount(InstructionsDialog, {
      props: { open: false, instructions: snippets, groups, focus: { kind: 'snippet', id: 1 } },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await flushPromises()
    const dialog = document.body.querySelector('[aria-label="Instructions"]')
    const save = dialog.querySelector('.btn-primary')
    expect(save.disabled).toBe(true) // nothing changed yet
    dialog.querySelector('.pill').click()
    await flushPromises()
    expect(save.disabled).toBe(false) // a pick alone is a change to save
    save.click()
    await flushPromises()
    const put = calls.find(c => c[0] === 'PUT' && c[1].includes('/settings'))
    expect(put[2].default_instruction_ids).toEqual([1])
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

  it('searches the add menu once there is a lot to pick from', async () => {
    const many = Array.from({ length: 10 }, (_, i) => ({ id: 100 + i, name: `Snippet ${i}`, content: '' }))
    const w = mount(InstructionPicker, { props: { instructions: many, groups: [], snippetIds: [], groupIds: [] } })
    await w.find('.add').trigger('click')
    await w.find('.menu-search').setValue('7')
    expect(w.findAll('.menu .item').map(i => i.text())).toEqual(['Snippet 7', '＋ New or edit…'])
    w.unmount()
  })
})
