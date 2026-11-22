<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import still from '@/assets/phase-ring.webp'
import { drawGlass } from './glass'

// The moving glass ring at the top of the home page; the still picture where the browser cannot draw it.
const canvas = ref<HTMLCanvasElement>()
const drawn = ref(true)
let stop: (() => void) | undefined
onMounted(() => {
  stop = drawGlass(canvas.value!, () => (drawn.value = false))
  drawn.value = !!stop
})
onBeforeUnmount(() => stop?.())
</script>

<template>
  <div class="stage" aria-hidden="true">
    <canvas v-if="drawn" ref="canvas" />
    <img v-else class="still" :src="still" alt="" />
  </div>
</template>

<style scoped>
.stage {
  position: relative;
  width: min(560px, 100%);
  height: min(400px, 74vw);
  margin: 0 auto;
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: pointer;
}
.still {
  position: absolute;
  inset: 8% 16%;
  width: 68%;
  margin: auto;
}
</style>
