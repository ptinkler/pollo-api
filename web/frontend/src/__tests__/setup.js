// Test setup for Vitest
// Mock localStorage
const localStorageMock = (() => {
  let store = {}
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = String(value) },
    removeItem: (key) => { delete store[key] },
    clear: () => { store = {} },
    get length() { return Object.keys(store).length },
    key: (index) => Object.keys(store)[index] || null,
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

// Mock import.meta.env
globalThis.import = globalThis.import || {}

