import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../components/chat/ChatMessage.vue'

const image = { id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'img_a.png', prompt: 'a fox' }
const video = { id: 'm2', kind: 'video', source: 'generated', status: 'done', file: 'vid_a.mp4' }

describe('ChatMessage "make a video from this image"', () => {
  it('is offered on generated images, not videos', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 1,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image, video],
        },
      },
    })
    const buttons = w.findAll('button[title="Attach this picture and switch to Video mode"]')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'video' }]])
  })

  it("is offered on the user's own attachments", async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 2,
          role: 'user',
          content: 'look',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    await w.find('button[title="Attach this picture and switch to Video mode"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'up_b.png', mode: 'video' }]])
  })

  it('passes the file to the image viewer so it can offer it too', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 3,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image],
        },
      },
    })
    await w.find('.media-item img').trigger('click')
    expect(w.emitted('open-media')[0][0]).toMatchObject({ kind: 'image', file: 'img_a.png' })
  })
})

describe('ChatMessage media settings', () => {
  it('shows the settings a video was made with, while rendering and when done', async () => {
    const params = {
      duration: 5,
      resolution: '480p',
      aspect_ratio: null,
      first_frame: 'img_a.png',
      generate_audio: true,
    }
    const pending = { id: 'v1', kind: 'video', source: 'generated', status: 'pending', prompt: 'waves', params }
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 4,
          role: 'assistant',
          content: '',
          status: 'done',
          created_at: new Date().toISOString(),
          media: [pending],
        },
      },
    })
    expect(w.find('.pending-specs').text()).toBe('from image · 5s · 480p · audio')
    await w.setProps({
      message: {
        id: 4,
        role: 'assistant',
        content: '',
        status: 'done',
        media: [{ ...pending, status: 'done', file: 'vid.mp4' }],
      },
    })
    expect(w.find('.caption-specs').text()).toBe('from image · 5s · 480p · audio')
  })

  it('shows ratio and resolution for images', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 5,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ ...image, model: 'pollo/seedream', params: { aspect_ratio: '16:9', resolution: '2K', refs: [] } }],
        },
      },
    })
    expect(w.find('.caption-specs').text()).toBe('2K · 16:9')
  })
})

describe('ChatMessage mode tag', () => {
  const user = mode =>
    mount(ChatMessage, {
      props: { convId: 'c1', canEdit: true, message: { id: 6, role: 'user', content: 'waves', status: 'done', mode } },
    })

  it('marks prompts sent outside Auto mode', () => {
    expect(user('video').find('.mode-tag').text()).toBe('🎬 Video')
    expect(user('image').find('.mode-tag').text()).toBe('🖼 Image')
  })

  it('stays quiet for Auto and older messages', () => {
    expect(user('auto').find('.mode-tag').exists()).toBe(false)
    expect(user(null).find('.mode-tag').exists()).toBe(false)
  })
})

describe('ChatMessage "make a picture" and text-to-media', () => {
  it('offers a picture-from-image button beside the video one', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 7,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image],
        },
      },
    })
    await w.find('button[title="Attach this picture and switch to Image mode"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'image' }]])
  })

  it('no longer offers the reply-text-to-prompt buttons', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: { id: 9, role: 'assistant', content: 'Some words.', status: 'done', media: [] },
      },
    })
    expect(w.find('button[title$="as an Image-mode prompt"]').exists()).toBe(false)
    expect(w.find('button[title$="as a Video-mode prompt"]').exists()).toBe(false)
  })
})

describe('ChatMessage pin as reference', () => {
  it('is offered on generated images and uploads, not videos, and toggles', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 5,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image, video],
        },
      },
    })
    const pins = w.findAll('.pin-btn')
    expect(pins).toHaveLength(1)
    await pins[0].trigger('click')
    expect(w.emitted('pin')).toEqual([[{ mediaId: 'm1', pinned: true }]])
    await w.setProps({
      message: { id: 5, role: 'assistant', content: '', status: 'done', media: [{ ...image, pinned: true }, video] },
    })
    expect(w.find('.pin-btn').classes()).toContain('on')
    await w.find('.pin-btn').trigger('click')
    expect(w.emitted('pin')[1]).toEqual([{ mediaId: 'm1', pinned: false }])

    const u = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 6,
          role: 'user',
          content: 'this is Linh',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    expect(u.findAll('.pin-btn')).toHaveLength(1)
  })

  it('is not offered before the message is saved', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 'tmp-1',
          role: 'user',
          content: 'x',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    expect(w.find('.pin-btn').exists()).toBe(false)
  })
})

describe('ChatMessage delete', () => {
  it('is offered on saved prompts, not replies', async () => {
    const user = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: true,
        message: {
          id: 7,
          role: 'user',
          content: 'draw a cat',
          status: 'done',
          media: [],
        },
      },
    })
    await user.find('button[title^="Delete this prompt"]').trigger('click')
    expect(user.emitted('delete')).toHaveLength(1)
    const reply = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: false,
        message: {
          id: 8,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    expect(reply.find('button[title^="Delete this prompt"]').exists()).toBe(false)
  })
})

describe('ChatMessage branch to a new chat', () => {
  it('is offered on saved prompts, not replies', async () => {
    const user = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: true,
        message: {
          id: 7,
          role: 'user',
          content: 'draw a cat',
          status: 'done',
          media: [],
        },
      },
    })
    await user.find('button[title^="Start a new chat from here"]').trigger('click')
    expect(user.emitted('fork')).toHaveLength(1)
    const reply = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 8,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    expect(reply.find('button[title^="Start a new chat from here"]').exists()).toBe(false)
  })
})

describe('ChatMessage branches', () => {
  it('offers Branch on replies too', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canBranch: true,
        message: {
          id: 9,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    await w.find('button[title^="Start a new chat from here: everything up to this reply"]').trigger('click')
    expect(w.emitted('fork')).toHaveLength(1)
  })

  it('lists the chats branched off a message and opens one', async () => {
    const forks = [
      { id: 'b1', title: 'Fox (branch)' },
      { id: 'b2', title: 'Other' },
    ]
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 7,
          role: 'user',
          content: 'draw a fox',
          status: 'done',
          media: [],
          forks,
        },
      },
    })
    expect(w.find('.fork-toggle').text()).toBe('⑂ 2 branches')
    await w.find('.fork-toggle').trigger('click')
    const items = w.findAll('.fork-item')
    expect(items.map(i => i.text())).toEqual(['Fox (branch)', 'Other'])
    await items[1].trigger('click')
    expect(w.emitted('open-chat')).toEqual([['b2']])
    expect(w.find('.fork-menu').exists()).toBe(false)
  })
})

describe('ChatMessage refs sent', () => {
  it('says when a model took fewer reference images than were picked', () => {
    const item = { ...image, params: { refs: ['a.png', 'b.png', 'c.png'], refs_used: 1 } }
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 9,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [item],
        },
      },
    })
    expect(w.find('.media-caption').text()).toContain('🔗 1 of 3 refs')
    const all = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 10,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ ...image, params: { refs: ['a.png', 'b.png'] } }],
        },
      },
    })
    expect(all.find('.media-caption').text()).toContain('🔗 2 refs')
  })

  it('shows thumbnails of the refs on hover, dimming the ones not sent', async () => {
    const item = { ...image, params: { refs: ['a.png', 'char:7/b.png'], refs_used: 1 } }
    const w = mount(ChatMessage, {
      attachTo: document.body,
      props: { convId: 'c1', message: { id: 11, role: 'assistant', content: '', status: 'done', media: [item] } },
    })
    await w.find('.caption-refs').trigger('mouseenter')
    const imgs = document.querySelectorAll('.refs-peek img')
    expect([...imgs].map(i => i.getAttribute('src'))).toEqual([
      '/api/chat/media/c1/a.png',
      '/api/characters/7/images/b.png',
    ])
    expect([...imgs].map(i => i.classList.contains('unused'))).toEqual([false, true])
    await w.find('.caption-refs').trigger('mouseleave')
    expect(document.querySelector('.refs-peek')).toBeNull()
    w.unmount()
  })
})

describe('ChatMessage request view', () => {
  it('shows what a card sent to the provider', async () => {
    const request = { model: 'seedream-v5-pro-edit', prompt: 'a fox', images: ['data:image/png;base64,… (90 KB)'] }
    const w = mount(ChatMessage, {
      attachTo: document.body,
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
      props: {
        convId: 'c1',
        message: {
          id: 3,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [
            {
              id: 'm',
              kind: 'image',
              source: 'generated',
              status: 'error',
              error: 'Venice: blocked',
              prompt: 'a fox',
              model: 'venice/seedream-v5-pro',
              request,
              response: { error: 'Your prompt violates the content policy' },
            },
          ],
        },
      },
    })
    await w.find('button[title="Show exactly what was sent to the provider"]').trigger('click')
    const dialog = document.querySelector('.req-dialog')
    expect(dialog.textContent).toContain('"model": "seedream-v5-pro-edit"')
    expect(dialog.textContent).toContain('Venice: blocked')
    expect(dialog.textContent).toContain('"error": "Your prompt violates the content policy"')
    w.unmount()
  })

  it('has no request button for media without one', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 4,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [
            { id: 'n', kind: 'image', source: 'generated', status: 'done', file: 'x.png', prompt: 'p', model: 'a/b' },
          ],
        },
      },
    })
    expect(w.find('button[title="Show exactly what was sent to the provider"]').exists()).toBe(false)
  })
})

const reply = (media, extra = {}) => ({
  props: {
    convId: 'c1',
    message: { id: 42, role: 'assistant', content: 'Here you go.', status: 'done', media, ...extra },
  },
})

describe('ChatMessage edit and redo a picture in place', () => {
  it('offers Edit only on a picture, Redo on anything it can make again', () => {
    const img = mount(ChatMessage, reply([image]))
    expect(img.find('button[title^="Edit this picture"]').exists()).toBe(true)
    expect(img.find('button[title^="Make it again"]').exists()).toBe(true)
    const vid = mount(ChatMessage, reply([{ ...video, prompt: 'waves' }]))
    expect(vid.find('button[title^="Edit this picture"]').exists()).toBe(false)
    expect(vid.find('button[title^="Make it again"]').exists()).toBe(true)
  })

  it('Edit opens an empty box and asks to edit this picture', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Edit this picture"]').trigger('click')
    const box = w.find('.prompt-box textarea')
    expect(box.element.value).toBe('')
    expect(box.attributes('placeholder')).toBe('Describe the change…')
    await box.setValue('give it a hat')
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')[0][0]).toEqual({
      mediaId: 'm1',
      model: null,
      prompt: 'give it a hat',
      edit: true,
      replace: true,
    })
  })

  it('Redo pre-fills the prompt it was made with and does not edit', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Make it again"]').trigger('click')
    expect(w.find('.prompt-box textarea').element.value).toBe('a fox')
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')[0][0]).toMatchObject({ prompt: 'a fox', edit: false, replace: true })
  })

  it('will not send an empty prompt', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Edit this picture"]').trigger('click')
    expect(w.find('.prompt-box .edit-send').attributes('disabled')).toBeDefined()
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')).toBeUndefined()
  })

  it('Cancel closes the box without regenerating', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Make it again"]').trigger('click')
    await w.find('.prompt-box .meta-btn').trigger('click')
    expect(w.find('.prompt-box').exists()).toBe(false)
    expect(w.emitted('regenerate')).toBeUndefined()
  })

  it('neither is offered while the reply is still streaming', () => {
    const w = mount(ChatMessage, reply([image], { status: 'streaming' }))
    expect(w.find('button[title^="Edit this picture"]').exists()).toBe(false)
    expect(w.find('button[title^="Make it again"]').exists()).toBe(false)
  })
})

describe('ChatMessage earlier versions of a picture', () => {
  const versioned = {
    ...image,
    file: 'img_new.png',
    prompt: 'a fox in a hat',
    versions: [{ file: 'img_a.png', prompt: 'a fox' }],
  }

  it('shows no arrows until a picture has been replaced', () => {
    expect(
      mount(ChatMessage, reply([image]))
        .find('.ver-nav')
        .exists(),
    ).toBe(false)
  })

  it('counts the live picture as the last version', () => {
    const w = mount(ChatMessage, reply([versioned]))
    expect(w.find('.ver-nav span').text()).toBe('2/2')
  })

  it('asks for the picture it replaced to become the real one', async () => {
    const w = mount(ChatMessage, { props: { ...reply([versioned]).props, canSwitch: true } })
    const [back, forward] = w.findAll('.ver-nav button')
    expect(forward.attributes('disabled')).toBeDefined() // already on the newest
    await back.trigger('click')
    expect(w.emitted('media-version')).toEqual([[{ mediaId: versioned.id, index: 0 }]])
  })

  it('shows where the live picture sits once an earlier one was chosen', () => {
    const chosen = { ...versioned, file: 'img_a.png', versions: [{ file: 'img_new.png' }], version_shown: 0 }
    const w = mount(ChatMessage, { props: { ...reply([chosen]).props, canSwitch: true } })
    expect(w.find('.ver-nav span').text()).toBe('1/2')
    expect(w.find('img').attributes('src')).toContain('img_a.png')
    const [back, forward] = w.findAll('.ver-nav button')
    expect(back.attributes('disabled')).toBeDefined()
    expect(forward.attributes('disabled')).toBeUndefined()
  })

  it('cannot switch mid-reply', () => {
    const w = mount(ChatMessage, reply([versioned]))
    for (const b of w.findAll('.ver-nav button')) expect(b.attributes('disabled')).toBeDefined()
  })

  it('offers the previous picture back after a failed redo', async () => {
    const failed = { ...versioned, status: 'error', file: null, error: 'nope' }
    const w = mount(ChatMessage, { props: { ...reply([failed]).props, canSwitch: true } })
    await w.find('button[title^="Keep the picture this card had"]').trigger('click')
    expect(w.emitted('media-version')).toEqual([[{ mediaId: failed.id, index: 0 }]])
  })
})

describe('ChatMessage edit and redo the text in place', () => {
  // Offered on any finished reply (the feed passes canReword); the pictures stay
  const rewordable = (media, extra = {}) => {
    const r = reply(media, extra)
    return { props: { ...r.props, canReword: true, canSwitch: true } }
  }

  it('Redo text is offered on a reply that made media, and emits reword with no instruction', async () => {
    const w = mount(ChatMessage, rewordable([image]))
    await w.find('button[title^="Redo text"]').trigger('click')
    expect(w.emitted('reword')).toEqual([['']])
  })

  it('Redo text is not offered on a reply with no media to keep (Retry covers it)', () => {
    expect(mount(ChatMessage, rewordable([])).find('button[title^="Redo text"]').exists()).toBe(false)
  })

  it('Edit text sends the instruction', async () => {
    const w = mount(ChatMessage, rewordable([image]))
    await w.find('button[title^="Edit text"]').trigger('click')
    await w.find('.text-box textarea').setValue('make it shorter')
    await w.find('.text-box .edit-send').trigger('click')
    expect(w.emitted('reword')).toEqual([['make it shorter']])
    expect(w.find('.text-box').exists()).toBe(false)
  })

  it('is not offered while the reply cannot be reworded', () => {
    const w = mount(ChatMessage, reply([image]))
    expect(w.find('button[title^="Redo text"]').exists()).toBe(false)
    expect(w.find('button[title^="Edit text"]').exists()).toBe(false)
  })

  it('is not offered while a picture is still being made', () => {
    const w = mount(ChatMessage, rewordable([{ ...image, status: 'pending', file: null }]))
    expect(w.find('button[title^="Redo text"]').exists()).toBe(false)
  })
})

describe('ChatMessage earlier wordings of the text', () => {
  const worded = (shown, extra = {}) => ({
    props: { ...reply([image]).props, canSwitch: true, ...extra },
  })
  const withVersions = (shown, props = {}) => {
    const w = worded(shown, props)
    w.props.message = { ...w.props.message, text_versions: 3, text_shown: shown }
    return w
  }

  it('has no text arrows until the text has been rewritten', () => {
    expect(mount(ChatMessage, worded()).find('.text-ver').exists()).toBe(false)
  })

  it('shows which wording is up, apart from the picture versions', () => {
    const w = mount(ChatMessage, withVersions(1))
    expect(w.find('.text-ver span').text()).toBe('text 2/3')
    expect(w.find('.ver-nav').exists()).toBe(false) // the picture has no versions of its own
  })

  it('asks for the neighbouring wording', async () => {
    const w = mount(ChatMessage, withVersions(1))
    const [back, forward] = w.findAll('.text-ver button')
    await back.trigger('click')
    await forward.trigger('click')
    expect(w.emitted('text-version')).toEqual([[0], [2]])
  })

  it('cannot switch mid-reply', () => {
    const w = mount(ChatMessage, withVersions(1, { canSwitch: false }))
    for (const b of w.findAll('.text-ver button')) expect(b.attributes('disabled')).toBeDefined()
  })
})

describe('ChatMessage renders one element per media kind', () => {
  // Regression: the version arrows were inserted between the <img v-if> and
  // its <video v-else>, which breaks Vue's conditional chain — the <video>
  // then rendered for images too, putting a play control on a picture.
  const media = extra => ({
    props: {
      convId: 'c1',
      message: {
        id: 50,
        role: 'assistant',
        content: '',
        status: 'done',
        media: [{ id: 'm1', source: 'generated', status: 'done', prompt: 'a fox', ...extra }],
      },
    },
  })

  it('an image is an <img> and nothing else', () => {
    const w = mount(ChatMessage, media({ kind: 'image', file: 'a.png' }))
    expect(w.findAll('img')).toHaveLength(1)
    expect(w.find('video').exists()).toBe(false)
    expect(w.find('audio').exists()).toBe(false)
  })

  it('an image with earlier versions is still only an <img>', () => {
    const w = mount(ChatMessage, media({ kind: 'image', file: 'b.png', versions: [{ file: 'a.png' }] }))
    expect(w.find('.ver-nav').exists()).toBe(true)
    expect(w.find('video').exists()).toBe(false)
  })

  it('a video is a <video> and not an <img>', () => {
    const w = mount(ChatMessage, media({ kind: 'video', file: 'a.mp4' }))
    expect(w.findAll('video')).toHaveLength(1)
    expect(w.find('img').exists()).toBe(false)
  })

  it('audio is an <audio> and not a <video>', () => {
    const w = mount(ChatMessage, media({ kind: 'audio', file: 'a.mp3' }))
    expect(w.findAll('audio')).toHaveLength(1)
    expect(w.find('video').exists()).toBe(false)
  })
})

describe('ChatMessage a failed picture can be changed and retried', () => {
  const failed = {
    props: {
      convId: 'c1',
      message: {
        id: 60,
        role: 'assistant',
        content: '',
        status: 'done',
        media: [
          {
            id: 'm1',
            kind: 'image',
            source: 'generated',
            status: 'error',
            error: 'flagged',
            prompt: 'a fox',
            model: 'i/model',
          },
        ],
      },
    },
  }

  it('offers Change prompt beside Retry', async () => {
    const w = mount(ChatMessage, failed)
    expect(w.find('button[title^="Run the same prompt again"]').exists()).toBe(true)
    await w.find('button[title="Edit the prompt, then run it again"]').trigger('click')
    const box = w.find('.prompt-box textarea')
    expect(box.element.value).toBe('a fox') // pre-filled with what failed
    await box.setValue('a fox, softer lighting')
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')[0][0]).toMatchObject({
      mediaId: 'm1',
      prompt: 'a fox, softer lighting',
      edit: false,
      replace: true,
    })
  })
})
