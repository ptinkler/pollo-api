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
      <label class="ifield">
        <span class="fcap">Voice</span>
        <select v-model="audioOpts.voice">
          <option value="">Pick one…</option>
          <option v-for="v in voices" :key="v.voiceId" :value="v.voiceId">{{ voiceLabel(v) }}</option>
        </select>
      </label>
    </div>
    <div v-if="voicesError" class="aerr">{{ voicesError }}</div>

    <div v-if="has('tuning')" class="orow">
      <label class="ifield" title="Speed (0.5–2×)">
        <span class="fcap">Speed</span>
        <input v-model.number="audioOpts.speed" type="number" min="0.5" max="2" step="0.1" placeholder="1×" />
      </label>
      <label class="ifield" title="Volume (0.5–2×)">
        <span class="fcap">Volume</span>
        <input v-model.number="audioOpts.volume" type="number" min="0.5" max="2" step="0.1" placeholder="1×" />
      </label>
      <label class="ifield" title="Pitch shift in semitones (−12…12)">
        <span class="fcap">Pitch</span>
        <input v-model.number="audioOpts.pitch" type="number" min="-12" max="12" step="1" placeholder="0" />
      </label>
    </div>

    <template v-if="has('instrumental')">
      <div class="orow">
        <label class="audio"><input v-model="audioOpts.instrumental" type="checkbox" /> Instrumental</label>
        <label v-if="!audioOpts.instrumental" class="ifield">
          <span class="fcap">Vocals</span>
          <select v-model="audioOpts.vocal_gender">
            <option value="">Any</option>
            <option value="f">Female</option>
            <option value="m">Male</option>
          </select>
        </label>
      </div>
      <div v-if="has('lyrics')" class="orow">
        <label class="ifield" title="A style and a title together switch the model into lyrics mode">
          <span class="fcap">Style</span>
          <input v-model="audioOpts.style" placeholder="e.g. synthwave" />
        </label>
        <label class="ifield">
          <span class="fcap">Title</span>
          <input v-model="audioOpts.title" placeholder="Untitled" maxlength="80" />
        </label>
      </div>
      <div class="orow">
        <label class="ifield">
          <span class="fcap">Avoid</span>
          <input v-model="audioOpts.negative_prompt" placeholder="Styles to exclude" />
        </label>
        <label v-if="has('duration')" class="ifield">
          <span class="fcap">Length</span>
          <input v-model.number="audioOpts.duration" type="number" min="1" placeholder="Seconds" />
        </label>
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
