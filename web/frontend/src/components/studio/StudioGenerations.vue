<!-- A thread's Generations gallery: flattens the thread's message media into
     cards (newest first) and hands them to GenerationGrid. Includes in-progress
     (pending) and failed tiles too, so it doubles as the live generation queue. -->
<script setup>
import { computed } from 'vue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../../composables/useChat'
import GenerationGrid from './GenerationGrid.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  convId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['open', 'favourite'])

function toCard(m, item, originals) {
  const hasFile = !!item.file
  const url = f => chatMediaUrl(props.convId, f)
  const thumb = f => (item.kind === 'image' ? chatMediaPreviewUrl(props.convId, f) : url(f))
  return {
    ...item,
    message_id: m.id,
    conversation_id: props.convId,
    model: item.model || m.model,
    // What the user typed (the parent message), vs the prompt the model ended up with
    original_prompt: originals.get(m.parent_id)?.content || '',
    cost: m.cost,
    created_at: m.created_at,
    url: hasFile ? url(item.file) : '',
    preview: hasFile ? thumb(item.file) : '',
  }
}

// Only generations — uploads on user messages aren't shown here
const isGeneration = item =>
  (item.kind === 'image' || item.kind === 'video') && (item.source || 'generated') === 'generated'

const items = computed(() => {
  const originals = new Map(props.messages.map(m => [m.id, m]))
  const out = props.messages.flatMap(m => (m.media || []).filter(isGeneration).map(i => toCard(m, i, originals)))
  return out.reverse()
})
</script>

<template>
  <GenerationGrid
    :items="items"
    empty="No generations in this thread yet."
    @open="emit('open', $event)"
    @favourite="emit('favourite', $event)"
  />
</template>
