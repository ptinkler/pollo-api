// Display formatting shared by the chat views

/** "openai/gpt-image-1" → "gpt-image-1" (Pollo's "pollo/<key>" likewise). */
export const shortModel = id => (id || '').split('/').pop()

/** OpenRouter dollar cost; sub-cent amounts keep 4 decimals. '' for none. */
export const fmtCost = c => (!c ? '' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`)

// A steady colour for an instruction snippet, from its name: the dot that
// tells snippets apart when their chips are cut short
export function instructionColor(name) {
  let h = 0
  for (const ch of name || '') h = (h * 31 + ch.codePointAt(0)) % 360
  return `hsl(${h} 70% 62%)`
}
