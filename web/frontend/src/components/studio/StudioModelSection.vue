<!-- Inspector section: the three searchable model pickers. -->
<script setup>
import { inject } from 'vue'
import ModelPicker from '../chat/ModelPicker.vue'

defineProps({
  models: { type: Object, required: true },
  loading: { type: Boolean, default: false },
})
// Shared composer settings (not a prop) — binding to its slice is intended
const { selected } = inject('composerSettings')
</script>

<template>
  <div class="isection">
    <div class="ilabel">Models</div>
    <div class="pickers">
      <ModelPicker
        v-model="selected.text"
        :models="models.text"
        label="Chat"
        kind="text"
        :loading="loading"
        :allow-none="false"
      />
      <ModelPicker v-model="selected.image" :models="models.image" label="Image" kind="image" :loading="loading" />
      <ModelPicker v-model="selected.video" :models="models.video" label="Video" kind="video" :loading="loading" />
    </div>
  </div>
</template>
