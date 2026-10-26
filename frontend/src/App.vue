<script setup>
import { RouterView } from 'vue-router'
import { AlertCircle, CheckCircle2, X } from 'lucide-vue-next'
import { provideWorkspace } from './stores/workspace'

const { toast } = provideWorkspace()
</script>

<template>
  <RouterView />
  <Transition name="toast">
    <div v-if="toast" class="toast-message" :class="toast.type" role="status">
      <CheckCircle2 v-if="toast.type === 'success'" :size="18" />
      <AlertCircle v-else :size="18" />
      {{ toast.message }}
      <button aria-label="关闭提示" @click="toast = null">
        <X :size="14" />
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.toast-message {
  position: fixed;
  z-index: 100;
  bottom: 27px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  max-width: calc(100vw - 40px);
  min-height: 47px;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: #fff;
  padding: 12px 16px;
  color: var(--ink);
  font-size: 14px;
  line-height: 1.7;
}
.toast-message > svg {
  flex-shrink: 0;
  color: var(--green);
}
.toast-message > button {
  margin-left: 10px;
  padding: 8px;
  color: var(--muted);
}
.toast-message.error {
  border-color: #f3d9d2;
  color: #af7868;
}
.toast-message.error > svg {
  color: #d8927e;
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s,
    bottom 0.2s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  bottom: 16px;
}
@media (max-width: 700px) {
  .toast-message {
    left: 50%;
    bottom: 20px;
    width: max-content;
    font-size: 14px;
    padding: 11px 13px;
  }
}
</style>
