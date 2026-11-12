/**
 * Navigation must be real links.
 *
 * Anything that takes you to a URL has to be an <a href>, so right-click
 * "open in new tab", middle-click and ctrl-click all work. A <button> with a
 * click handler looks the same and silently loses all three.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StudioSidebar from '../components/studio/StudioSidebar.vue'
import StudioBalances from '../components/studio/StudioBalances.vue'

const sidebar = (threads = [{ id: 't1', title: 'A thread', kind: 'chat' }]) =>
  mount(StudioSidebar, {
    props: {
      threads,
      spaces: [{ id: 3, name: 'Novel' }],
      activeId: null,
      collapsed: false,
      search: '',
      filter: 'all',
    },
  })

const hrefOf = (w, text) =>
  w
    .findAll('a')
    .find(a => a.text().trim() === text || a.attributes('title') === text)
    ?.attributes('href')

describe('sidebar navigation is linkable', () => {
  it('uses the entire collapsed rail as one expandable button', async () => {
    const w = mount(StudioSidebar, {
      props: { threads: [], spaces: [], collapsed: true, search: '', filter: 'all' },
    })

    expect(w.find('button.rail').attributes('aria-label')).toBe('Expand sidebar')
    expect(w.findAll('button.rail svg use').map(use => use.attributes('href'))).toEqual([
      '#s-chev',
      '#s-plus',
      '#s-chat',
    ])
    await w.find('button.rail').trigger('click')
    expect(w.emitted('update:collapsed')).toEqual([[false]])
  })

  it.each([
    ['New chat', '/'],
    ['New gallery', '/?new=gallery'],
    ['Media', '/media'],
    ['Tools & library', '/tools'],
    ['Settings', '/settings'],
    ['Favourites', '/favourites'],
  ])('%s points at %s', (label, href) => {
    expect(hrefOf(sidebar(), label)).toBe(href)
  })

  it('a space row links to that space', () => {
    const w = sidebar()
    expect(w.find('a.fmain').attributes('href')).toBe('/space/3')
    expect(w.findAll('.folder .nact').map(button => button.attributes('title'))).toEqual([
      'Rename',
      'Space defaults',
      'Delete',
    ])
  })

  it('a thread row links to that thread', () => {
    expect(sidebar().find('a.nitem').attributes('href')).toBe('/t1')
  })

  it('lets a chat be pinned and unpinned from its row actions', async () => {
    const thread = { id: 't1', title: 'A thread', kind: 'chat' }
    const w = sidebar([thread])

    expect(w.findAll('.nrow .nact').map(button => button.attributes('title'))).toEqual(['Rename', 'Pin', 'Delete'])
    expect(w.find('button[aria-label="Pin chat"]').exists()).toBe(true)
    expect(w.find('button[aria-label="Delete chat"]').exists()).toBe(true)
    await w.find('button[aria-label="Pin chat"]').trigger('click')
    expect(w.emitted('pin')).toEqual([[thread]])
    await w.find('button[aria-label="Delete chat"]').trigger('click')
    expect(w.emitted('delete')).toEqual([[thread]])

    const pinned = sidebar([{ ...thread, pinned: true }])
    const unpin = pinned.find('button[aria-label="Unpin chat"]')
    expect(unpin.attributes('aria-pressed')).toBe('true')
  })

  it('shows explicit confirm and cancel actions while renaming a chat', async () => {
    const w = sidebar()
    await w.find('.nrow button[title="Rename"]').trigger('click')

    await w.find('input.nrename').setValue('Renamed')
    await w.find('button[aria-label="Confirm rename"]').trigger('click')
    expect(w.emitted('rename')).toEqual([[{ id: 't1', title: 'A thread', kind: 'chat' }, 'Renamed']])
  })

  it('collapses the Spaces and Recent sections', async () => {
    const w = sidebar()
    expect(w.find('a.fmain').exists()).toBe(true)
    expect(w.find('a.nitem').exists()).toBe(true)

    await w
      .findAll('.section-toggle')
      .find(button => button.text().includes('Spaces'))
      .trigger('click')
    expect(w.find('a.fmain').isVisible()).toBe(false)
    expect(w.find('a.nitem').exists()).toBe(true)

    await w
      .findAll('.section-toggle')
      .find(button => button.text().includes('Recent'))
      .trigger('click')
    expect(w.find('a.nitem').isVisible()).toBe(false)
  })

  it('collapses the Pinned section', async () => {
    const w = sidebar([{ id: 't1', title: 'A thread', kind: 'chat', pinned: true }])
    expect(w.find('button[aria-label="Unpin chat"]').exists()).toBe(true)

    await w.find('.section-toggle').trigger('click')
    expect(w.find('button[aria-label="Unpin chat"]').isVisible()).toBe(false)
  })

  it('still navigates in-app, without a full page load', async () => {
    const w = sidebar()
    const link = w.findAll('a').find(a => a.text().trim() === 'Media')
    await link.trigger('click')
    expect(w.emitted('media')).toHaveLength(1) // handled, and .prevent stops the browser
  })
})

describe('balance tiles are linkable', () => {
  it('open the usage page', () => {
    const w = mount(StudioBalances, {
      props: { balances: { openrouter: 1, venice: null, veniceCredits: null, pollo: 10 }, spend: null, messages: [] },
    })
    const tile = w.find('a.bseg')
    expect(tile.attributes('href')).toBe('/usage')
  })
})

/**
 * Buttons use the icon sprite, not emoji.
 *
 * Emoji render differently per platform and sit badly beside the stroke icons,
 * so an action button carries an <svg><use href="#s-…"> instead. Text (a
 * caption, a mode tag) may still use them.
 */
import ChatMessage from '../components/chat/ChatMessage.vue'

const EMOJI = /\p{Extended_Pictographic}/u

describe('action buttons use the icon sprite', () => {
  it('no emoji on a generated image card or its overlay', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 5,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'a.png', prompt: 'a fox' }],
        },
      },
    })
    const labels = w.findAll('button, a.media-btn').map(b => b.text())
    expect(labels.filter(l => EMOJI.test(l))).toEqual([])
  })

  it('the picture/video/download overlay is all sprite icons', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 6,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ id: 'm2', kind: 'image', source: 'generated', status: 'done', file: 'b.png' }],
        },
      },
    })
    const used = w.findAll('.media-overlay use').map(u => u.attributes('href'))
    expect(used).toEqual(['#s-image', '#s-film', '#s-download'])
  })
})

describe('a failed card suggests one action, not three', () => {
  const failed = {
    props: {
      convId: 'c1',
      message: {
        id: 70,
        role: 'assistant',
        content: '',
        status: 'done',
        media: [{ id: 'm1', kind: 'image', source: 'generated', status: 'error', error: 'nope', prompt: 'a fox' }],
      },
    },
  }

  it('reads as one set of three ways out', () => {
    const w = mount(ChatMessage, failed)
    const labels = w.findAll('.error-actions button').map(b => b.text())
    expect(labels).toEqual(['Try again', 'Try a new prompt…', 'Try another model…'])
    // none carries an icon: the picker trigger can't take one, so none does
    expect(w.findAll('.error-actions svg')).toHaveLength(0)
  })

  it('only the first is primary; the alternatives are plain', () => {
    const w = mount(ChatMessage, failed)
    const primary = w.findAll('.retry-btn.primary')
    expect(primary).toHaveLength(1)
    expect(primary[0].text()).toBe('Try again')
    expect(w.find('button[title="Edit the prompt, then run it again"]').classes()).not.toContain('primary')
  })
})
