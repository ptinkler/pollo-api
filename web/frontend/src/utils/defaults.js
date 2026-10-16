// Small shared helpers for the chat defaults (global and per space)

// Where an inherited default comes from ('All chats' or a space's name): its icon and tooltip
export const ALL_CHATS = 'All chats'
export const defaultIcon = from => (from === ALL_CHATS ? '🌐' : '🗂')
export const defaultTitle = from =>
  from === ALL_CHATS ? 'From the defaults for all chats' : `From the ${from} defaults`

// The same ids, in any order
export const sameIds = (a, b) => a.length === b.length && a.every(x => b.includes(x))
