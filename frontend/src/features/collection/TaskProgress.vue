<script setup>
import { computed } from 'vue'
import {
  ArrowRight,
  Clock3,
  LoaderCircle,
  Monitor,
  Square,
} from 'lucide-vue-next'
import { useWorkspace } from '../../stores/workspace'
import { statusName, taskFailedCount, taskStatus, taskUnconfirmed } from '../../constants/tasks'
import { time } from '../../utils/format'
import { platformName } from '../../constants/platforms'

const {
  selectedTask,
  taskRunning,
  waitingForLogin,
  busy,
  browserState,
  resumeCollection,
  interruptCollection,
} = useWorkspace()
const isDelivery = computed(() => selectedTask.value?.config.mode === 'delivery')
const isMessage = computed(() => selectedTask.value?.config.delivery_action === 'message')
const displayStatus = computed(() => taskStatus(selectedTask.value))
const failedCount = computed(() => taskFailedCount(selectedTask.value))
const unconfirmedCount = computed(() => taskUnconfirmed(selectedTask.value))
const progress = computed(() => {
  if (!selectedTask.value) return 0
  const task = selectedTask.value
  return Math.min(
    100,
    Math.round(
      ((isDelivery.value ? (task.scanned || 0) : ((task.scanned || 0) + (task.failed || 0))) / task.config.max_jobs) * 100,
    ),
  )
})
</script>

<template>
  <section
    v-if="selectedTask"
    class="panel task-panel"
    :class="{ 'task-waiting': selectedTask.status === 'waiting', 'task-failed': displayStatus === 'failed', 'task-partial': displayStatus === 'partial', 'task-unconfirmed': displayStatus === 'unknown' }"
    aria-label="当前任务进度"
  >
    <div class="task-top">
      <div class="task-caption">
        <span class="task-status" :class="displayStatus">
          <LoaderCircle v-if="selectedTask.status === 'running' || selectedTask.status === 'queued'" :size="14" class="spin" />
          <span v-else class="task-status-dot"></span>
          {{ waitingForLogin ? '等待登录' : statusName(displayStatus, selectedTask.config.mode, selectedTask.config.delivery_action) }}
        </span>
        <h2 :title="selectedTask.name">{{ selectedTask.name }}</h2>
        <span class="task-platform">{{ platformName(selectedTask.config.platform) }}</span>
      </div>
      <div class="task-actions">
        <button
          v-if="taskRunning"
          class="interrupt-action"
          :disabled="busy.interrupt"
          @click="interruptCollection(selectedTask)"
        >
          <LoaderCircle v-if="busy.interrupt" :size="14" class="spin" />
          <Square v-else :size="13" />
          {{ busy.interrupt ? '正在中断' : '中断任务' }}
        </button>
        <span v-else class="task-complete-time">
          <Clock3 :size="14" />{{ time(selectedTask.finished_at || selectedTask.created_at) }}
        </span>
      </div>
    </div>

    <div class="task-summary">
      <p class="task-message">{{ selectedTask.message }}</p>
      <div class="task-numbers">
        <span>{{ isDelivery ? '已处理' : '已读取' }} <strong>{{ selectedTask.scanned }}</strong></span>
        <span>{{ isMessage ? '新发送' : isDelivery ? '确认完成' : '新增' }} <strong>{{ selectedTask.saved }}</strong></span>
        <span>{{ isDelivery ? '跳过' : '更新' }} <strong>{{ selectedTask.duplicates }}</strong></span>
        <span v-if="unconfirmedCount" class="has-unconfirmed">待核对 <strong>{{ unconfirmedCount }}</strong></span>
        <span :class="{ 'has-failures': failedCount > 0 }">失败 <strong>{{ failedCount }}</strong></span>
      </div>
    </div>

    <div v-if="selectedTask.status === 'waiting'" class="login-waiting" role="status" aria-live="polite">
      <div class="login-instruction">
        <Monitor :size="21" class="login-icon" />
        <div>
          <strong>{{ waitingForLogin ? '登录后即可开始' : '处理官网提示后继续' }}</strong>
          <p v-if="waitingForLogin">在浏览器中登录 {{ platformName(selectedTask.config.platform) }}，再点击确认，开始{{ isMessage ? '发送已确认的消息' : isDelivery ? '投递所选岗位' : '采集岗位' }}。</p>
          <p v-else>请在浏览器中完成登录、验证或页面提示，再继续任务。</p>
          <span v-if="waitingForLogin && !browserState.login_ready" class="login-preparing">登录窗口正在准备中…</span>
        </div>
      </div>
      <button
        class="button button-primary resume-main-button"
        :disabled="busy.resume || busy.interrupt || (waitingForLogin && !browserState.login_ready)"
        @click="resumeCollection"
      >
        <LoaderCircle v-if="busy.resume || (waitingForLogin && !browserState.login_ready)" :size="17" class="spin" />
        <ArrowRight v-else :size="17" />
        {{ busy.resume ? '正在确认登录状态…' : waitingForLogin
          ? (browserState.login_ready ? (isMessage ? '我已登录，继续发送' : isDelivery ? '我已登录，继续投递' : '我已登录，继续采集') : '正在打开登录窗口…')
          : (isMessage ? '继续发送' : isDelivery ? '继续投递' : '继续采集') }}
      </button>
    </div>

    <div class="capture-track" role="progressbar" :aria-valuenow="progress" :aria-valuemin="0" :aria-valuemax="100" aria-label="任务处理进度">
      <div class="capture-track-fill" :style="{ width: `${progress}%` }"></div>
    </div>
  </section>
</template>

<style scoped>
.task-panel {
  padding: 16px 20px;
  border: 1px solid #e0e0e0;
  border-radius: 18px;
  background: #fff;
  color: #1d1d1f;
  box-shadow: none;
}
.task-top, .task-caption, .task-actions, .task-status, .task-complete-time, .interrupt-action {
  display: flex;
  align-items: center;
}
.task-top { justify-content: space-between; gap: 20px; }
.task-caption { flex: 1; min-width: 0; gap: 12px; }
.task-caption h2 { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 16px; line-height: 1.5; font-weight: 600; letter-spacing: -.22px; }
.task-status { flex-shrink: 0; gap: 6px; color: #6e6e73; font-size: 14px; white-space: nowrap; }
.task-status-dot { width: 6px; height: 6px; background: currentColor; border-radius: 50%; }
.task-status.running, .task-status.queued { color: var(--accent); }
.task-status.completed { color: #237a45; }
.task-status.waiting { color: #95631b; }
.task-status.partial { color: #95631b; }
.task-status.unknown { color: #95631b; }
.task-status.failed { color: #b42318; }
.task-platform { flex-shrink: 0; color: #6e6e73; font-size: 14px; }
.task-actions { flex-shrink: 0; }
.interrupt-action { gap: 6px; min-height: 36px; padding: 4px 0 4px 8px; color: var(--accent); font-size: 14px; line-height: 1.5; }
.interrupt-action:disabled { color: #86868b; }
.task-complete-time { gap: 6px; color: #6e6e73; font-size: 14px; white-space: nowrap; }
.task-summary { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px 24px; margin-top: 6px; }
.task-message { min-width: 0; color: #6e6e73; font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }
.task-failed .task-message { color: #b42318; }
.task-numbers { flex-shrink: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; color: #6e6e73; font-size: 14px; line-height: 1.5; }
.task-numbers > span { white-space: nowrap; }
.task-numbers strong { margin-left: 3px; color: #1d1d1f; font-weight: 600; font-variant-numeric: tabular-nums; }
.task-numbers .has-failures, .task-numbers .has-failures strong { color: #b42318; }
.capture-track { height: 3px; margin-top: 14px; border-radius: 999px; overflow: hidden; background: #f5f5f7; }
.capture-track-fill { height: 100%; border-radius: inherit; background: var(--accent); transition: width .3s ease; }
.task-waiting { border-color: #e8d5b6; }
.task-waiting .capture-track-fill { background: #b88731; }
.task-failed .capture-track-fill { background: #b42318; }
.task-partial .capture-track-fill { background: #b88731; }
.task-unconfirmed .capture-track-fill { background: #b88731; }
.task-unconfirmed .task-message, .task-numbers .has-unconfirmed, .task-numbers .has-unconfirmed strong { color: #95631b; }
.login-waiting { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-top: 14px; padding: 16px; border-radius: 12px; background: #fff8eb; }
.login-instruction { display: flex; align-items: flex-start; min-width: 0; gap: 10px; }
.login-icon { flex-shrink: 0; margin-top: 2px; color: #95631b; }
.login-instruction strong { display: block; color: #754b0d; font-size: 15px; font-weight: 600; line-height: 1.5; }
.login-instruction p, .login-preparing { color: #815f2c; font-size: 14px; line-height: 1.5; margin-top: 4px; }
.login-preparing { display: block; }
.resume-main-button { flex-shrink: 0; min-height: 44px; padding: 11px 22px; border-radius: 999px; background: var(--accent); border-color: var(--accent); color: #fff; font-size: 15px; font-weight: 400; line-height: 1.5; white-space: normal; text-align: center; box-shadow: none; }
.resume-main-button:disabled { opacity: 1; background: #e5e5ea; border-color: #e5e5ea; color: #6e6e73; box-shadow: none; }
.resume-main-button:active:not(:disabled), .interrupt-action:active:not(:disabled) { transform: scale(.95); }
.resume-main-button:focus-visible, .interrupt-action:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
@media (max-width: 1100px) {
  .task-summary { flex-direction: column; gap: 8px; }
}
@media (max-width: 760px) {
  .task-panel { padding: 16px; }
  .task-top { align-items: flex-start; gap: 12px; }
  .task-caption { flex-wrap: wrap; gap: 4px 10px; }
  .task-caption h2 { flex-basis: 100%; order: 1; font-size: 15px; }
  .task-complete-time { white-space: normal; justify-content: flex-end; text-align: right; }
  .task-complete-time svg { flex-shrink: 0; }
  .task-actions { max-width: 40%; }
  .interrupt-action { min-height: 44px; padding-top: 0; padding-bottom: 0; }
  .login-waiting { align-items: stretch; flex-direction: column; gap: 14px; padding: 14px; }
  .resume-main-button { width: 100%; }
}
@media (prefers-reduced-motion: reduce) {
  .capture-track-fill { transition: none; }
  .task-panel .spin { animation: none; }
  .resume-main-button:active:not(:disabled), .interrupt-action:active:not(:disabled) { transform: none; }
}
</style>
