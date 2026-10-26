<script setup>
import { Terminal } from 'lucide-vue-next'
import { useWorkspace } from '../../stores/workspace'
import { time } from '../../utils/format'

const { logs, logConnected, selectedTask } = useWorkspace()
</script>

<template>
  <section class="panel logs-panel">
    <div class="logs-heading">
      <h2><Terminal :size="15" />任务日志</h2>
      <span
        ><span class="status-dot" :class="{ online: logConnected }"></span
        >{{
          logConnected ? '实时更新' : selectedTask ? '任务日志' : '等待任务'
        }}</span
      >
    </div>
    <div class="logs-body" role="log" aria-label="任务日志">
      <div
        v-for="log in logs"
        :key="log.seq"
        class="log-line"
        :class="log.level"
      >
        <time>{{ time(log.created_at) }}</time
        ><span class="log-level">{{
          log.level === 'warning'
            ? '注意'
            : log.level === 'error'
              ? '错误'
              : log.level === 'success'
                ? '完成'
                : '信息'
        }}</span
        ><span>{{ log.message }}</span>
      </div>
      <div v-if="!logs.length" class="log-placeholder">
        <span class="terminal-prompt">›</span
        >{{
          selectedTask
            ? '正在读取任务日志…'
            : '任务开始后，采集过程会记录在这里。'
        }}<span v-if="!selectedTask" class="terminal-cursor"></span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.logs-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 20px;
  border-bottom: 1px solid var(--line);
}
.logs-heading h2 {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #728098;
}
.logs-heading > span {
  font-size: 9px;
  display: flex;
  align-items: center;
  gap: 6px;
  color: #a0a9b9;
}
.logs-body {
  padding: 14px 20px;
  background: #fcfdff;
  min-height: 122px;
  overflow: visible;
}
.log-line {
  display: grid;
  grid-template-columns: 56px 29px minmax(0, 1fr);
  gap: 11px;
  font-size: 12px;
  line-height: 1.9;
  margin-bottom: 6px;
}
.log-line time {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  color: #b3bbca;
  font-size: 9px;
}
.log-level {
  color: #9b94c9;
}
.log-line > span:last-child {
  color: #8a96ab;
  overflow-wrap: anywhere;
}
.log-line.warning .log-level {
  color: #cbab72;
}
.log-line.warning > span:last-child {
  color: #b89760;
}
.log-line.error .log-level,
.log-line.error > span:last-child {
  color: #c98074;
}
.log-line.success .log-level,
.log-line.success > span:last-child {
  color: #6ba28d;
}
.log-placeholder {
  color: #acb5c5;
  font-size: 10px;
  line-height: 1.8;
  padding-top: 7px;
}
.terminal-prompt {
  font-family: ui-monospace, monospace;
  color: #9386c7;
  font-size: 16px;
  margin-right: 9px;
}
.terminal-cursor {
  display: inline-block;
  width: 5px;
  height: 11px;
  margin-left: 7px;
  background: #c7c1db;
  vertical-align: -2px;
  animation: cursor-blink 1.4s steps(1) infinite;
}
@keyframes cursor-blink {
  50% {
    opacity: 0;
  }
}
@media (max-width: 600px) {
  .logs-heading {
    padding-left: 17px;
    padding-right: 17px;
  }
  .logs-body {
    padding: 13px 15px;
  }
  .log-line {
    gap: 7px;
    grid-template-columns: 51px 23px minmax(0, 1fr);
  }
}
</style>
