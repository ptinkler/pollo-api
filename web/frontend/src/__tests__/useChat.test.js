import { describe, it, expect } from 'vitest'
import { readSSE, chatMediaUrl } from '../composables/useChat'

function streamOf(chunks) {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c))
      controller.close()
    },
  })
}

describe('readSSE', () => {
  it('parses events split across arbitrary chunk boundaries', async () => {
    const events = []
    await readSSE(streamOf([
      'data: {"type":"st',
      'art"}\n\ndata: {"type":"delta","text":"hi"}\n',
      '\n: keep-alive\n\ndata: {"type":"done"}\n\n',
    ]), e => events.push(e))
    expect(events).toEqual([{ type: 'start' }, { type: 'delta', text: 'hi' }, { type: 'done' }])
  })

  it('ignores comment-only blocks', async () => {
    const events = []
    await readSSE(streamOf([': keep-alive\n\n']), e => events.push(e))
    expect(events).toEqual([])
  })
})

describe('chatMediaUrl', () => {
  it('encodes path segments', () => {
    expect(chatMediaUrl('abc', 'img 1.png')).toBe('/api/chat/media/abc/img%201.png')
  })
})
