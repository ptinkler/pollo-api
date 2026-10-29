<!-- Studio center feed: the thread's messages via the shared ChatMessage
     component (all per-message actions bubble up as events). -->
<script setup>
import { ref, watch, nextTick } from 'vue'
import ChatMessage from '../chat/ChatMessage.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  active: { type: String, default: null },
  sending: { type: Boolean, default: false },
  lastAssistantId: { type: [Number, String], default: null },
})
defineEmits([
  'retry',
  'edit',
  'resend',
  'branch',
  'use-image',
  'use-text',
  'regenerate',
  'pin',
  'delete',
  'fork',
  'open-chat',
  'stop',
  'open-media',
])

const scroller = ref(null)
function scrollToBottom(force = false) {
  nextTick(() => {
    const el = scroller.value
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 200
    if (force || near) el.scrollTop = el.scrollHeight
  })
}
// Follow new messages, and streaming text on the last one
watch(
  () => props.messages.length,
  () => scrollToBottom(true),
)
watch(
  () => props.messages[props.messages.length - 1]?.content,
  () => scrollToBottom(),
)
watch(
  () => props.active,
  () => scrollToBottom(true),
)
</script>

<template>
  <div ref="scroller" class="feed">
    <div v-if="!messages.length" class="empty">
      {{ active ? 'No messages yet.' : 'Start a new thread — type below.' }}
    </div>
    <div v-else class="finner">
      <ChatMessage
        v-for="m in messages"
        :key="m.id"
        :message="m"
        :conv-id="active || ''"
        :can-retry="m.id === lastAssistantId && !sending"
        :can-edit="m.role === 'user' && typeof m.id === 'number' && !sending"
        :can-switch="!sending"
        :can-branch="typeof m.id === 'number' && !sending && m.status !== 'streaming'"
        @retry="$emit('retry', m)"
        @edit="content => $emit('edit', m, content)"
        @resend="$emit('resend', m)"
        @branch="$emit('branch', $event)"
        @use-image="$emit('use-image', $event)"
        @use-text="$emit('use-text', $event)"
        @regenerate="payload => $emit('regenerate', m, payload)"
        @pin="payload => $emit('pin', m, payload)"
        @delete="$emit('delete', m)"
        @fork="$emit('fork', m)"
        @open-chat="$emit('open-chat', $event)"
        @stop="$emit('stop')"
        @open-media="$emit('open-media', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.feed {
  flex: 1;
  overflow-y: auto;
  padding: 22px;
}
.empty {
  color: var(--sfaint);
  text-align: center;
  margin-top: 60px;
}
.finner {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
