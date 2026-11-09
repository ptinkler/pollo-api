// Display formatting shared by the chat views

/** "openai/gpt-image-1" → "gpt-image-1" (Pollo's "pollo/<key>" likewise). */
export const shortModel = id => (id || '').split('/').pop()

/** OpenRouter dollar cost; sub-cent amounts keep 4 decimals. '' for none. */
export const fmtCost = c => (!c ? '' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`)

/** Pollo bills in credits; its API converts them to USD at this fixed rate. */
export const POLLO_USD_PER_CREDIT = 0.06
export const creditsToUsd = c => (c || 0) * POLLO_USD_PER_CREDIT

// A steady colour for an instruction snippet, from its name: the dot that
// tells snippets apart when their chips are cut short
export function instructionColor(name) {
  let h = 0
  for (const ch of name || '') h = (h * 31 + ch.codePointAt(0)) % 360
  return `hsl(${h} 70% 62%)`
}

// Seconds as m:ss ("0:05", "1:12")
export const fmtDuration = sec => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`
