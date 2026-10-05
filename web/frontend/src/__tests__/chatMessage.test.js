import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../components/chat/ChatMessage.vue'

const image = { id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'img_a.png', prompt: 'a fox' }
const video = { id: 'm2', kind: 'video', source: 'generated', status: 'done', file: 'vid_a.mp4' }

describe('ChatMessage "make a video from this image"', () => {
  it('is offered on generated images, not videos', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 1, role: 'assistant', content: '', status: 'done', media: [image, video] } } })
    const buttons = w.findAll('button[title="Make a video from this image"]')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(w.emitted('animate')).toEqual([['img_a.png']])
  })

  it('is offered on the user\'s own attachments', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 2, role: 'user', content: 'look', status: 'done',
      media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }] } } })
    await w.find('button[title="Make a video from this image"]').trigger('click')
    expect(w.emitted('animate')).toEqual([['up_b.png']])
  })

  it('passes the file to the image viewer so it can offer it too', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 3, role: 'assistant', content: '', status: 'done', media: [image] } } })
    await w.find('.media-item img').trigger('click')
    expect(w.emitted('open-media')[0][0]).toMatchObject({ kind: 'image', file: 'img_a.png' })
  })
})
