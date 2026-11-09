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
    <div class="card">
      <div class="crow">
        <span class="clabel" :title="videoInfo?.generate_audio ? '' : 'This model decides its own audio'">Audio</span>
        <div v-if="videoInfo?.generate_audio" class="seg" role="group" aria-label="Generate audio">
          <button :class="{ on: videoOpts.generate_audio }" @click="videoOpts.generate_audio = true">On</button>
          <button :class="{ on: !videoOpts.generate_audio }" @click="videoOpts.generate_audio = false">Off</button>
        </div>
        <span v-else class="dval hint end">model default</span>
      </div>
      <template v-if="videoShowsDuration && durationOptions.length">
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
            class="drange"
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
      </template>
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
  min-height: 32px;
  padding: 0 10px;
}
.crow + .crow {
  margin-top: 0;
}
.crow + .crow:not(.slide) {
  border-top: 1px solid var(--sborder2);
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
.drange {
  flex: 1;
  min-width: 0;
  height: 18px;
  margin: 0;
  background: none;
  appearance: none;
  cursor: pointer;
}
.drange:disabled {
  cursor: default;
}
.drange::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(to right, var(--saccent) var(--fill), var(--sborder) var(--fill));
}
.drange::-moz-range-track {
  height: 4px;
  border-radius: 2px;
  background: linear-gradient(to right, var(--saccent) var(--fill), var(--sborder) var(--fill));
}
.drange::-webkit-slider-thumb {
  appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 50%;
  border: 0;
  background: var(--sfg);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
}
.drange::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 0;
  background: var(--sfg);
}
.dval {
  min-width: 0;
  text-align: right;
  font-size: 12px;
  font-weight: 600;
  color: var(--saccent);
  font-variant-numeric: tabular-nums;
}
.crow .crow .dval.hint.end {
  margin: 0 0 0 auto;
  text-align: right;
}
.dval.hint {
  min-width: 0;
  margin-right: auto;
  text-align: left;
}
.dval.hint {
  white-space: nowrap;
  font-weight: 400;
  color: var(--smuted);
}
</style>
