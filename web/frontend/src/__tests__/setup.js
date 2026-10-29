// Test setup for Vitest
// Mock localStorage
const localStorageMock = (() => {
  let store = {}
  return {
    getItem: key => store[key] || null,
    setItem: (key, value) => {
      store[key] = String(value)
    },
    removeItem: key => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
    get length() {
      return Object.keys(store).length
    },
    key: index => Object.keys(store)[index] || null,
  }
})()

// vi.stubGlobal installs reliably whether or not jsdom already defined
// localStorage as a non-configurable property (a plain defineProperty threw
// there, aborting setup and leaving tests with no localStorage).
vi.stubGlobal('localStorage', localStorageMock)

// Mock import.meta.env
globalThis.import = globalThis.import || {}

// jsdom has no ResizeObserver (the chat follows new content with one)
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
