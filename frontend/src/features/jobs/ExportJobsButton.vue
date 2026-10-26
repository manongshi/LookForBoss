<script setup>
import { Download, LoaderCircle } from 'lucide-vue-next'
defineProps({ disabled: Boolean, busy: Boolean })
defineEmits(['export'])
</script>

<template>
  <button
    class="button button-white heading-export"
    :disabled="disabled || busy"
    @click="$emit('export')"
  >
    <LoaderCircle v-if="busy" :size="16" class="spin" /><Download
      v-else
      :size="16"
    />导出 CSV
  </button>
</template>

<style scoped>
.heading-export {
  align-self: center;
  margin-top: 12px;
}
@media (max-width: 600px) {
  .heading-export {
    padding: 0 10px;
    font-size: 10px;
    min-height: 33px;
  }
}
</style>
