<!-- Inspector section: speech / music options, shown in Audio mode by what the model takes. -->
<script setup>
import { inject, ref, computed, watch } from 'vue'
import { fetchAudioVoices } from '../../composables/useChat'

const { audioOpts, audioInfo, showAudioOpts } = inject('composerSettings')
const has = opt => !!audioInfo.value?.options?.includes(opt)

// Pollo's voice list, loaded once the first time a voice-picking model is shown
const voices = ref([])
const voicesError = ref('')
const wantVoices = computed(() => showAudioOpts.value && has('voice'))
watch(
  wantVoices,
  async want => {
    if (!want || voices.value.length) return
    try {
      voices.value = (await fetchAudioVoices('?page_size=100')).voices
      voicesError.value = ''
    } catch (e) {
      voicesError.value = e.message || 'Could not load voices'
    }
  },
  { immediate: true },
)
const voiceLabel = v => [v.voiceName, v.language, v.gender].filter(Boolean).join(' · ')
</script>

<template>
  <div v-if="showAudioOpts" class="isection">
    <div class="ilabel">Audio options</div>

    <div v-if="has('voice')" class="orow">
      <select v-model="audioOpts.voice" class="msel" title="Voice">
        <option value="">Voice: pick one…</option>
        <option v-for="v in voices" :key="v.voiceId" :value="v.voiceId">{{ voiceLabel(v) }}</option>
      </select>
    </div>
    <div v-if="voicesError" class="aerr">{{ voicesError }}</div>

    <div v-if="has('tuning')" class="orow">
      <input
        v-model.number="audioOpts.speed"
        class="msel"
        type="number"
        min="0.5"
        max="2"
        step="0.1"
        placeholder="Speed ×"
        title="Speed (0.5–2×)"
      />
      <input
        v-model.number="audioOpts.volume"
        class="msel"
        type="number"
        min="0.5"
        max="2"
        step="0.1"
        placeholder="Volume ×"
        title="Volume (0.5–2×)"
      />
      <input
        v-model.number="audioOpts.pitch"
        class="msel"
        type="number"
        min="-12"
        max="12"
        step="1"
        placeholder="Pitch ±"
        title="Pitch shift in semitones (−12…12)"
      />
    </div>

    <template v-if="has('instrumental')">
      <div class="orow">
        <label class="audio"><input v-model="audioOpts.instrumental" type="checkbox" /> Instrumental</label>
        <select v-if="!audioOpts.instrumental" v-model="audioOpts.vocal_gender" class="msel" title="Preferred vocals">
          <option value="">Vocals: any</option>
          <option value="f">Female</option>
          <option value="m">Male</option>
        </select>
      </div>
      <div v-if="has('lyrics')" class="orow">
        <input v-model="audioOpts.style" class="msel" placeholder="Style (with title = lyrics mode)" />
        <input v-model="audioOpts.title" class="msel" placeholder="Title" maxlength="80" />
      </div>
      <div class="orow">
        <input v-model="audioOpts.negative_prompt" class="msel" placeholder="Avoid (styles to exclude)" />
        <input
          v-if="has('duration')"
          v-model.number="audioOpts.duration"
          class="msel"
          type="number"
          min="1"
          placeholder="Seconds"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.orow + .orow,
.aerr {
  margin-top: 8px;
}
.aerr {
  color: var(--sdanger);
  font-size: 12px;
}
</style>
