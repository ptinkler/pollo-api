import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import ChatComposer from '../components/chat/ChatComposer.vue'
import MediaLightbox from '../components/chat/MediaLightbox.vue'
import SidebarSection from '../components/chat/SidebarSection.vue'
import { provideFolded } from '../composables/useFolded'
import { useChatAttachments, MAX_ATTACHMENTS } from '../composables/useChatAttachments'

const MODE = { id: 'auto', label: 'Auto', icon: '✦' }

describe('ChatComposer', () => {
  const mountComposer = (props = {}) =>
    mount(ChatComposer, { props: { modelValue: 'hi', mode: MODE, attachments: [], canSend: true, ...props } })

  it('sends on Enter but not Shift+Enter', async () => {
    const w = mountComposer()
    await w.find('textarea').trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(w.emitted('send')).toBeUndefined()
    await w.find('textarea').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('send')).toHaveLength(1)
  })

  it('hands pasted images over as files', async () => {
    const w = mountComposer()
    const img = new File(['x'], 'a.png', { type: 'image/png' })
    await w.find('textarea').trigger('paste', { clipboardData: { files: [img] } })
    expect(w.emitted('files')).toEqual([[[img]]])
  })

  it('shows a stop button while sending, and what goes with the message', () => {
    const w = mountComposer({ sending: true, characterNames: ['Linh'], pinnedCount: 2 })
    expect(w.find('.send.stop').exists()).toBe(true)
    expect(w.find('.ctx-chip').text()).toContain('👤 Linh')
    expect(w.find('.ctx-chip.pins').text()).toContain('📌 2')
    expect(
      mountComposer({ mode: { id: 'text', label: 'Chat', icon: '💬' }, pinnedCount: 2 })
        .find('.pins')
        .exists(),
    ).toBe(false)
  })

  it('keeps characters and pins in the one row: change characters, or unpin all', async () => {
    const w = mountComposer({ characterNames: ['Young Linh', 'Bao'], pinnedCount: 3 })
    expect(w.findAll('.composer-row .ctx-chip')).toHaveLength(2)
    await w.find('.ctx-chip').trigger('click')
    expect(w.emitted('show-sidebar')).toHaveLength(1)
    await w.find('.ctx-x').trigger('click')
    expect(w.emitted('unpin-all')).toHaveLength(1)
  })
})

describe('MediaLightbox', () => {
  it('offers uses for a chat image and closes on Escape', async () => {
    const w = mount(MediaLightbox, { props: { item: { url: '/x.png', file: 'x.png' } }, attachTo: document.body })
    document.querySelector('.lightbox-animate').click()
    expect(w.emitted('use-image')).toEqual([[{ file: 'x.png', mode: 'image' }]])
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})

describe('SidebarSection', () => {
  it('folds its body away and shows the summary instead', async () => {
    localStorage.removeItem('chat.folded')
    const Host = defineComponent({
      setup() {
        provideFolded()
        return () => h(SidebarSection, { id: 's', title: 'Things', summary: 'two' }, () => h('p', 'body'))
      },
    })
    const w = mount(Host, { attachTo: document.body })
    expect(w.find('.heading-value').exists()).toBe(false)
    await w.find('button.fold').trigger('click')
    expect(w.find('.heading-value').text()).toBe('two')
    expect(w.find('.side-body').isVisible()).toBe(false)
    w.unmount()
  })
})

describe('useChatAttachments', () => {
  it('takes chat images up to the limit, once each', () => {
    const showToast = vi.fn()
    const a = useChatAttachments({ convId: ref('c1'), ensureConversation: async () => 'c1', showToast })
    expect(a.addChatImage('one.png')).toBe(true)
    expect(a.addChatImage('one.png')).toBe(true)
    expect(a.attachments.value).toHaveLength(1)
    for (let i = 1; i < MAX_ATTACHMENTS; i++) a.addChatImage(`${i}.png`)
    expect(a.addChatImage('extra.png')).toBe(false)
    expect(showToast).toHaveBeenCalledWith(`Up to ${MAX_ATTACHMENTS} attachments per message`, 'error')
    expect(a.files.value).toHaveLength(MAX_ATTACHMENTS)
  })
})
