<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { useCopy } from '../../composables/useClipboard'

// What an image/video card sent to its provider and what came back, as
// JSON. Images in them are cut down to their type and size by the server.
const props = defineProps({
  request: { type: Object, required: true },
  response: { type: [Object, String, Array], default: null },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close'])
const { copiedKey, copy } = useCopy()

const fmt = v => (typeof v === 'string' ? v : JSON.stringify(v, null, 2))
const requestJson = computed(() => fmt(props.request))
const responseJson = computed(() => (props.response == null ? '' : fmt(props.response)))
const both = computed(() => JSON.stringify({ request: props.request, response: props.response }, null, 2))

const onKey = e => e.key === 'Escape' && emit('close')
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div class="req-backdrop" @click.self="emit('close')">
      <div class="req-dialog" role="dialog" aria-label="Request and response">
        <div class="req-head">
          <h3>Request and response</h3>
          <button class="req-btn" @click="copy(both, 'req')">
            {{ copiedKey === 'req' ? '✓ Copied' : '⧉ Copy JSON' }}
          </button>
          <RouterLink class="req-btn" :to="{ name: 'request-log' }" @click="emit('close')">All requests</RouterLink>
          <button class="req-btn" title="Close" @click="emit('close')">✕</button>
        </div>
        <p v-if="error" class="req-error">{{ error }}</p>
        <div class="req-body">
          <h4>Sent</h4>
          <pre class="req-json">{{ requestJson }}</pre>
          <h4>Response</h4>
          <pre v-if="responseJson" class="req-json">{{ responseJson }}</pre>
          <p v-else class="req-none">
            Nothing recorded (the connection failed, or this was made before responses were logged).
          </p>
        </div>
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

.req-body {
  overflow: auto;
  min-height: 0;
}

.req-body h4 {
  margin-top: 12px;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.req-none {
  margin-top: 6px;
  font-size: 0.8rem;
  color: var(--text2);
}

.req-error {
  margin-top: 10px;
  font-size: 0.82rem;
  color: var(--red);
}

.req-json {
  margin-top: 6px;
  padding: 12px;
  border-radius: 10px;
  background: var(--bg);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
