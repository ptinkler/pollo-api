<!-- Inspector section: image/video media options, shown by mode + model. -->
<script setup>
import { computed, inject } from 'vue'

const {
  imageOpts,
  videoOpts,
  imageRatioOptions,
  imageResOptions,
  videoRatioOptions,
  videoResOptions,
  durationOptions,
  showImageOpts,
  showVideoOpts,
  videoInfo,
  imageShowsRatio,
  videoShowsRatio,
  videoShowsDuration,
} = inject('composerSettings')

// Duration is one slider: position 0 = Auto, then each allowed length.
const isAuto = d => d === '' || d == null
const durText = computed(() => (isAuto(videoOpts.duration) ? 'Auto' : `${videoOpts.duration}s`))
const durIndex = computed(() => {
  if (isAuto(videoOpts.duration)) return 0
  const i = durationOptions.value.indexOf(Number(videoOpts.duration))
  return i === -1 ? 0 : i + 1
})
function onDuration(e) {
  const i = Number(e.target.value)
  videoOpts.duration = i === 0 ? '' : durationOptions.value[i - 1]
}
</script>

<template>
  <div v-if="showImageOpts" class="isection">
    <div class="ilabel">Image options</div>
    <div class="orow">
      <select v-if="imageShowsRatio" v-model="imageOpts.aspect_ratio" class="msel">
        <option value="">Ratio: auto</option>
        <option v-for="r in imageRatioOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="imageOpts.resolution" class="msel">
        <option value="">Res: default</option>
        <option v-for="r in imageResOptions" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>
  </div>

  <div v-if="showVideoOpts" class="isection">
    <div class="ilabel">Video options</div>
    <div class="orow">
      <select v-if="videoShowsRatio" v-model="videoOpts.aspect_ratio" class="msel">
        <option value="">Ratio: auto</option>
        <option v-for="r in videoRatioOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="videoOpts.resolution" class="msel">
        <option value="">Res: default</option>
        <option v-for="r in videoResOptions" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>
    <div class="orow">
      <div v-if="videoShowsDuration && durationOptions.length" class="dur">
        <label class="dlabel"
          >Duration <span class="dval">{{ durText }}</span></label
        >
        <input
          type="range"
          class="drange"
          min="0"
          :max="durationOptions.length"
          step="1"
          :value="durIndex"
          :title="durText"
          @input="onDuration"
        />
      </div>
      <label v-if="videoInfo?.generate_audio" class="audio"
        ><input v-model="videoOpts.generate_audio" type="checkbox" /> Audio</label
      >
    </div>
  </div>
</template>

<style scoped>
/* second option row in a section sits below the first */
.orow + .orow {
  margin-top: 8px;
}
.dur {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.dlabel {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  color: var(--smuted);
  white-space: nowrap;
}
.dval {
  color: var(--saccent);
  font-weight: 600;
  min-width: 34px;
}
.drange {
  flex: 1;
  min-width: 0;
  accent-color: var(--saccent);
  cursor: pointer;
}
</style>
