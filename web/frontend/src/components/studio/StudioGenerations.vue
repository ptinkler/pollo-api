<!-- A thread's Generations gallery: flattens the thread's message media into
     cards (newest first) and hands them to GenerationGrid. -->
<script setup>
import { computed } from 'vue'
import { chatMediaUrl, chatMediaPreviewUrl } from '../../composables/useChat'
import GenerationGrid from './GenerationGrid.vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  convId: { type: [String, Number], default: '' },
})
const emit = defineEmits(['open', 'favourite'])

const items = computed(() => {
  const out = []
  for (const m of props.messages) {
    for (const item of m.media || []) {
      if (item.file && (item.kind === 'image' || item.kind === 'video') && item.status !== 'error') {
        out.push({
          ...item,
          message_id: m.id,
          conversation_id: props.convId,
          model: item.model || m.model,
          cost: m.cost,
          created_at: m.created_at,
          url: chatMediaUrl(props.convId, item.file),
          preview:
            item.kind === 'image'
              ? chatMediaPreviewUrl(props.convId, item.file)
              : chatMediaUrl(props.convId, item.file),
        })
      }
    }
  }
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
