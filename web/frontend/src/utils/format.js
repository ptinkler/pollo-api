// Display formatting shared by the chat views

/** "openai/gpt-image-1" → "gpt-image-1" (Pollo's "pollo/<key>" likewise). */
export const shortModel = (id) => (id || '').split('/').pop()

/** OpenRouter dollar cost; sub-cent amounts keep 4 decimals. '' for none. */
export const fmtCost = (c) => (!c ? '' : c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`)
