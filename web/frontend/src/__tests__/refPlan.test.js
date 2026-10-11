import { describe, it, expect } from 'vitest'
import { charRef, planRefs } from '../utils/refPlan'

const A = { id: 1, images: ['a0', 'a1', 'a2'] }
const B = { id: 2, images: ['b0', 'b1', 'b2'] }
const a = i => charRef(1, `a${i}`)
const b = i => charRef(2, `b${i}`)

describe('planRefs (mirrors _plan_refs in web/chat.py)', () => {
  it('sends everything in priority order when the maximum is unknown', () => {
    const plan = planRefs({ lead: ['att'], chat: ['p0'], characters: [A, B] })
    expect(plan.sent).toEqual(['att', a(0), b(0), 'p0', a(1), b(1), a(2), b(2)])
    expect(plan.dropped).toEqual([])
  })

  it("keeps room for chat images: each character's main image, then pins, then the rest", () => {
    const plan = planRefs({ chat: ['p0', 'p1'], characters: [A, B], maxRefs: 6 })
    expect(plan.sent).toEqual([a(0), b(0), 'p0', 'p1', a(1), b(1)])
    expect(plan.dropped).toEqual([a(2), b(2)])
  })

  it('puts switched-on images first and never sends switched-off ones', () => {
    const plan = planRefs({
      chat: ['p0', 'p1'],
      characters: [A],
      maxRefs: 2,
      choices: { on: [a(2), 'elsewhere.png'], off: [a(0), 'p1'] },
    })
    expect(plan.sent).toEqual([a(2), a(1)])
    expect(plan.dropped).toEqual(['p0'])
    expect(plan.off).toEqual(['p1', a(0)])
  })

  it('caps chat images at the image slider, not character images', () => {
    const plan = planRefs({ chat: ['p0', 'p1', 'p2'], characters: [A], imageLimit: 1 })
    expect(plan.sent).toEqual([a(0), 'p0', a(1), a(2)])
    const forced = planRefs({ chat: ['p0', 'p1'], characters: [A], imageLimit: 1, choices: { on: ['p1'] } })
    expect(forced.sent).toEqual(['p1', a(0), 'p0', a(1), a(2)])
  })

  it('keeps attachments ahead even when one is switched off', () => {
    const plan = planRefs({ lead: ['x', 'y'], chat: ['p0'], characters: [A], choices: { off: ['x'] } })
    expect(plan.sent.slice(0, 2)).toEqual(['y', a(0)])
  })
})
