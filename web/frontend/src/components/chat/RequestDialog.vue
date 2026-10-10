<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { useCopy } from '../../composables/useClipboard'

// The body an image/video card sent to its provider, as JSON.
// Images in it are cut down to their type and size by the server.
const props = defineProps({
  request: { type: Object, required: true },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close'])
const { copiedKey, copy } = useCopy()

const json = computed(() => JSON.stringify(props.request, null, 2))

const onKey = e => e.key === 'Escape' && emit('close')
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="req-backdrop" @click.self="emit('close')">
      <div class="req-dialog" role="dialog" aria-label="Request sent">
        <div class="req-head">
          <h3>Request sent</h3>
          <button class="req-btn" @click="copy(json, 'req')">
            {{ copiedKey === 'req' ? '✓ Copied' : '⧉ Copy JSON' }}
          </button>
          <RouterLink class="req-btn" :to="{ name: 'request-log' }" @click="emit('close')">All requests</RouterLink>
          <button class="req-btn" title="Close" @click="emit('close')">✕</button>
        </div>
        <p v-if="error" class="req-error">{{ error }}</p>
        <pre class="req-json">{{ json }}</pre>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.req-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.6);
}

.req-dialog {
  width: min(760px, 100%);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
}

.req-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.req-head h3 {
  flex: 1;
  font-size: 0.95rem;
}

.req-btn {
  border: 1px solid var(--border);
  background: none;
  color: var(--text2);
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 0.78rem;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
}

.req-btn:hover {
  color: var(--text);
  background: var(--surface2);
}

.req-error {
  margin-top: 10px;
  font-size: 0.82rem;
  color: var(--red);
}

.req-json {
  margin-top: 10px;
  overflow: auto;
  padding: 12px;
  border-radius: 10px;
  background: var(--bg);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
