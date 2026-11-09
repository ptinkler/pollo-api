<!-- Inspector section: image/video media options, shown by mode + model. -->
<script setup>
import { inject } from 'vue'
import LengthSlider from '../form/LengthSlider.vue'

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
        <label class="autochk">
          <input
            type="checkbox"
            :checked="videoOpts.duration === '' || videoOpts.duration == null"
            @change="
              videoOpts.duration = $event.target.checked ? '' : durationOptions[Math.floor(durationOptions.length / 2)]
            "
          />
          Auto
        </label>
        <LengthSlider
          v-if="videoOpts.duration !== '' && videoOpts.duration != null"
          :model-value="Number(videoOpts.duration)"
          :lengths="durationOptions"
          @update:model-value="videoOpts.duration = $event"
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
  gap: 14px;
  flex: 1;
}
.dur :deep(.length-picker-group) {
  flex: 1;
  min-width: 0;
}
.autochk {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--smuted);
  white-space: nowrap;
}
</style>
