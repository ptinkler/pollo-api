<!-- Inspector section: image/video media options, shown by mode + model. -->
<script setup>
import { inject } from 'vue'

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
} = inject('composerSettings')
</script>

<template>
  <div v-if="showImageOpts" class="isection">
    <div class="ilabel">Image options</div>
    <div class="orow">
      <select v-model="imageOpts.aspect_ratio" class="msel">
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
      <select v-model="videoOpts.aspect_ratio" class="msel">
        <option value="">Ratio: auto</option>
        <option v-for="r in videoRatioOptions" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="videoOpts.resolution" class="msel">
        <option value="">Res: default</option>
        <option v-for="r in videoResOptions" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>
    <div class="orow">
      <select v-model="videoOpts.duration" class="msel">
        <option value="">Duration: auto</option>
        <option v-for="d in durationOptions" :key="d" :value="d">{{ d }}s</option>
      </select>
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
</style>
