import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import GenerationModal from '../components/studio/GenerationModal.vue'
import { useChatAttachments, MAX_ATTACHMENTS } from '../composables/useChatAttachments'

describe('GenerationModal: the big view, also used for chat images', () => {
  const chatImage = {
    url: '/x.png',
    file: 'x.png',
    kind: 'image',
    status: 'done',
    prompt: 'a fox',
    message_id: 7,
    conversation_id: 'c1',
  }
  const open = () => mount(GenerationModal, { props: { item: chatImage }, attachTo: document.body })
  const btn = label => [...document.querySelectorAll('.gm-btn')].find(b => b.textContent.trim() === label)

  it('offers Edit, Animate and Character on a picture', async () => {
    const w = open()
    btn('Edit').click()
    expect(w.emitted('use-image')).toEqual([[{ file: 'x.png', mode: 'image', conversation_id: 'c1' }]])
    btn('Animate').click()
    expect(w.emitted('use-image')[1][0].mode).toBe('video')
    btn('Character').click()
    expect(w.emitted('make-character')).toEqual([[chatImage]])
    w.unmount()
  })

  it('uses icons, not emoji, for those actions', () => {
    const w = open()
    expect(btn('Edit').querySelector('svg use').getAttribute('href')).toBe('#s-image')
    expect(btn('Animate').querySelector('svg use').getAttribute('href')).toBe('#s-film')
    w.unmount()
  })

  it('closes on Escape', () => {
    const w = open()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(1)
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

  it('uploads pasted, dropped or picked images to this chat', async () => {
    const calls = []
    globalThis.fetch = vi.fn(async (url, opts) => {
      calls.push([String(url), opts?.method])
      return { ok: true, status: 200, json: async () => ({ file: 'up_1.png' }) }
    })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    const a = useChatAttachments({ convId: ref('c1'), ensureConversation: async () => 'c1', showToast: vi.fn() })
    a.addFiles([new File(['x'], 'a.png', { type: 'image/png' })])
    await vi.waitFor(() => expect(a.files.value).toEqual(['up_1.png']))
    expect(calls).toEqual([['/api/chat/conversations/c1/attachments', 'POST']])
  })
})
