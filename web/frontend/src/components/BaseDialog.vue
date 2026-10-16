<script setup>
import { onBeforeUnmount, watch } from 'vue'

// A modal's shell: the backdrop, the card with its title and ✕, Esc and
// backdrop clicks to close. Slots: `head` (beside the title), the body, and
// `actions` (the button row). `form`: the card is a <form> (Enter submits;
// `submit` is emitted). Emits `close` — the parent decides whether to.
const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  label: { type: String, default: '' }, // for screen readers; the title by default
  width: { type: String, default: '480px' },
  form: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'submit'])

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
watch(
  () => props.open,
  open => (open ? window.addEventListener('keydown', onKey) : window.removeEventListener('keydown', onKey)),
  { immediate: true },
)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="backdrop" @click.self="emit('close')">
      <component
        :is="form ? 'form' : 'div'"
        class="dialog"
        role="dialog"
        aria-modal="true"
        :aria-label="label || title"
        :style="{ width: `min(${width}, 100%)` }"
        @submit.prevent="emit('submit')"
      >
        <div class="head">
          <h3>{{ title }}</h3>
          <slot name="head" />
          <button type="button" class="x" title="Close" @click="emit('close')">✕</button>
        </div>
        <div class="body"><slot /></div>
        <div v-if="$slots.actions" class="actions"><slot name="actions" /></div>
      </component>
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.7);
  display: grid;
  place-items: center;
  padding: 16px;
}

.dialog {
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 20px 18px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.head h3 {
  flex: 1;
  min-width: 0;
  font-size: 1.05rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.x {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}

.x:hover {
  background: var(--surface2);
  color: var(--text);
}

.body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 16px;
}

.actions :slotted(.btn) {
  padding: 8px 16px;
}

.actions :slotted(.spacer) {
  flex: 1;
}
</style>
