<!-- The app's own confirm / prompt dialog (see composables/useDialog.js). -->
<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { dialog, settleDialog } from '../composables/useDialog'

const input = ref(null)
const okBtn = ref(null)

const cancel = () => settleDialog(null)
function ok() {
  settleDialog(dialog.kind === 'prompt' ? dialog.value.trim() || null : true)
}
function onKey(e) {
  if (!dialog.open) return
  if (e.key === 'Escape') cancel()
  else if (e.key === 'Enter' && e.target?.tagName !== 'TEXTAREA') {
    e.preventDefault()
    ok()
  }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

watch(
  () => dialog.open,
  async open => {
    if (!open) return
    await nextTick()
    ;(dialog.kind === 'prompt' ? input.value : okBtn.value)?.focus()
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="dialog.open" class="ad-back" @click.self="cancel">
      <div class="ad" role="dialog" aria-modal="true" :aria-label="dialog.title">
        <h3 v-if="dialog.title">{{ dialog.title }}</h3>
        <p v-if="dialog.message" class="ad-msg">{{ dialog.message }}</p>
        <label v-if="dialog.kind === 'prompt'" class="ad-field">
          <span v-if="dialog.label">{{ dialog.label }}</span>
          <input ref="input" v-model="dialog.value" type="text" />
        </label>
        <label v-if="dialog.checkbox" class="ad-check">
          <input v-model="dialog.checkbox.checked" type="checkbox" />
          <span>{{ dialog.checkbox.label }}</span>
        </label>
        <div class="ad-actions">
          <button class="btn btn-secondary" @click="cancel">Cancel</button>
          <button ref="okBtn" class="btn" :class="dialog.danger ? 'btn-danger' : 'btn-primary'" @click="ok">
            {{ dialog.confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ad-back {
  position: fixed;
  inset: 0;
  z-index: 1400;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.6);
}
.ad {
  width: min(400px, 100%);
  padding: 14px 18px 16px;
  border: 1px solid var(--sborder);
  border-radius: var(--r-xl);
  box-shadow: var(--shadow-modal);
  background: var(--sbg);
  color: var(--sfg);
}
.ad h3 {
  margin: 0 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.ad-msg {
  margin: 0 0 14px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--smuted);
  white-space: pre-line;
}
.ad-field {
  display: block;
  margin-bottom: 14px;
}
.ad-field span {
  display: block;
}
.ad-field input {
  width: 100%;
  margin-top: 6px;
}
.ad-check {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 13px;
  font-weight: 400;
  color: var(--sfg);
  text-transform: none;
  letter-spacing: normal;
  cursor: pointer;
}
.ad-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
