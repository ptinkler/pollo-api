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
  clipDuration,
} = inject('composerSettings')

// Duration: Auto ('' — the clip's length for reference-to-video, else the
// model's default) or a hand-picked length on the slider. The slider row is
// always there (dimmed on Auto) so the panel never changes height.
const isAuto = computed(() => videoOpts.duration === '' || videoOpts.duration == null)
const lastIndex = computed(() => durationOptions.value.length - 1)
const durIndex = computed(() => Math.max(durationOptions.value.indexOf(Number(videoOpts.duration)), 0))
const fillPct = computed(() => (lastIndex.value > 0 ? (durIndex.value / lastIndex.value) * 100 : 0))
const durText = computed(() => {
  if (!isAuto.value) return `${videoOpts.duration}s`
  return clipDuration.value ? `${clipDuration.value}s from clip` : 'default'
})
function setAuto(auto) {
  if (auto === isAuto.value) return
  videoOpts.duration = auto ? '' : (clipDuration.value ?? durationOptions.value[0])
}
function onDuration(e) {
  videoOpts.duration = durationOptions.value[Number(e.target.value)]
}
</script>

<template>
  <div v-if="showImageOpts" class="isection">
    <div class="ilabel">Image options</div>
    <div class="orow">
      <label v-if="imageShowsRatio" class="ifield">
        <span class="fcap">Ratio</span>
        <select v-model="imageOpts.aspect_ratio">
          <option value="">Auto</option>
          <option v-for="r in imageRatioOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <label class="ifield">
        <span class="fcap">Resolution</span>
        <select v-model="imageOpts.resolution">
          <option value="">Model default</option>
          <option v-for="r in imageResOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
    </div>
  </div>

  <div v-if="showVideoOpts" class="isection">
    <div class="ilabel">Video options</div>
    <div class="orow">
      <label v-if="videoShowsRatio" class="ifield">
        <span class="fcap">Ratio</span>
        <select v-model="videoOpts.aspect_ratio">
          <option value="">Auto</option>
          <option v-for="r in videoRatioOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
      <label class="ifield">
        <span class="fcap">Resolution</span>
        <select v-model="videoOpts.resolution">
          <option value="">Model default</option>
          <option v-for="r in videoResOptions" :key="r" :value="r">{{ r }}</option>
        </select>
      </label>
    </div>
    <!-- A card each: a hairline between rows is invisible against the card's
         own fill, and these are two unrelated settings. -->
    <div class="card">
      <div class="crow">
        <span class="clabel" :title="videoInfo?.generate_audio ? '' : 'This model decides its own audio'">Audio</span>
        <div v-if="videoInfo?.generate_audio" class="seg" role="group" aria-label="Generate audio">
          <button :class="{ on: videoOpts.generate_audio }" @click="videoOpts.generate_audio = true">On</button>
          <button :class="{ on: !videoOpts.generate_audio }" @click="videoOpts.generate_audio = false">Off</button>
        </div>
        <span v-else class="dval hint end">model default</span>
      </div>
    </div>
    <div v-if="videoShowsDuration && durationOptions.length" class="card">
      <div class="crow">
        <span class="clabel">Length</span>
        <span v-if="isAuto" class="dval hint">{{ durText }}</span>
        <div class="seg" role="group" aria-label="Length mode">
          <button :class="{ on: isAuto }" @click="setAuto(true)">Auto</button>
          <button :class="{ on: !isAuto }" @click="setAuto(false)">Custom</button>
        </div>
      </div>
      <div v-if="!isAuto" class="crow slide">
        <input
          type="range"
          class="srange"
          min="0"
          :max="lastIndex"
          step="1"
          :value="durIndex"
          :style="{ '--fill': fillPct + '%' }"
          aria-label="Length in seconds"
          @input="onDuration"
        />
        <span class="dval">{{ durText }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card {
  margin-top: 6px;
  border: 1px solid var(--sborder);
  border-radius: var(--r);
  background: var(--spanel2);
}
.crow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 38px;
  padding: 0 10px;
}
.crow + .crow {
  margin-top: 0;
}
.clabel {
  font-size: 12px;
  color: var(--smuted);
}

/* Slider row: always present, dimmed on Auto, so nothing shifts */
.slide {
  min-height: 24px;
  padding-bottom: 4px;
}
.dval {
  min-width: 0;
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: var(--saccent);
  font-variant-numeric: tabular-nums;
}
.dval.hint {
  margin-right: auto;
  text-align: left;
  white-space: nowrap;
  font-weight: 400;
  color: var(--smuted);
}
.dval.hint.end {
  margin: 0 0 0 auto;
  text-align: right;
}
</style>
