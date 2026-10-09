import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'

export default [
  { ignores: ['coverage/**'] },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: globals.browser,
    },
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrors: 'none' }],
      complexity: ['error', 12],
    },
  },
  {
    files: ['src/__tests__/**', 'vite.config.js', 'eslint.config.js'],
    // vite.config.js runs Vitest with `globals: true`
    languageOptions: { globals: { ...globals.browser, ...globals.node, ...globals.vitest } },
  },
  // Layout is Prettier's job: turn off the stylistic rules that would fight it
  prettier,
]
