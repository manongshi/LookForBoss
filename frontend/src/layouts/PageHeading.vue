<script setup>
import { useRoute } from 'vue-router'
import { LoaderCircle, Square } from 'lucide-vue-next'
import { useWorkspace } from '../stores/workspace'

const route = useRoute()
const { isActive, busy, interruptCollection } = useWorkspace()
</script>

<template>
  <div class="page-heading">
    <div>
      <h1>{{ route.meta.title }}</h1>
      <p v-if="route.meta.description">{{ route.meta.description }}</p>
    </div>
    <div class="heading-actions">
      <button v-if="isActive && route.name !== 'workbench'" class="button button-white" :disabled="busy.interrupt" @click="interruptCollection()">
        <LoaderCircle v-if="busy.interrupt" :size="15" class="spin" /><Square v-else :size="13" />{{ busy.interrupt ? '正在中断' : '中断任务' }}
      </button>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 28px; }
.page-heading h1 { font-family: var(--font-display); font-size: 34px; font-weight: 600; line-height: 1.25; letter-spacing: -.374px; }
.page-heading p { margin-top: 10px; color: var(--muted); font-size: 17px; line-height: 1.47; }
.heading-actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 10px; }
.heading-actions :deep(.heading-export) { margin-top: 0; }
@media (max-width: 640px) {
  .page-heading { gap: 16px; align-items: flex-start; margin-bottom: 24px; }
  .page-heading h1 { font-size: 28px; }
  .page-heading p { font-size: 14px; max-width: 240px; }
  .heading-actions { gap: 8px; }
  .heading-actions :deep(.button) { font-size: 12px; min-height: 40px; padding: 0 12px; }
}
</style>
