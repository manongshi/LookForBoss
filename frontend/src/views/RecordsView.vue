<script setup>
import { RouterLink, useRouter } from 'vue-router'
import { History, Plus, RefreshCw } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import { useWorkspace } from '../stores/workspace'
import { statusName, taskFailedCount, taskStatus, taskUnconfirmed } from '../constants/tasks'
import { time } from '../utils/format'
import { platformName } from '../constants/platforms'

const router = useRouter()
const { history, isActive, refreshAll, selectTask, reuseTask } = useWorkspace()
</script>

<template>
  <div>
    <PageHeading
      ><button
        class="button button-primary"
        @click="router.push({ name: 'workbench' })"
      >
        <Plus :size="16" />新建采集任务
      </button></PageHeading
    >
    <section class="panel records-panel">
      <div class="records-heading">
        <h2>
          全部任务<span>{{ history.length }}</span>
        </h2>
        <button class="button button-white compact" @click="refreshAll">
          <RefreshCw :size="14" />刷新
        </button>
      </div>
      <div class="table-scroll">
        <table v-if="history.length">
          <thead>
            <tr>
              <th>任务 / 搜索范围</th>
              <th>状态</th>
              <th>执行结果</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="task in history" :key="task.id">
              <td>
                <strong class="record-title">{{ task.name }}</strong
                ><small
                  >{{
                    task.config.mode === 'delivery' ? `已选 ${task.config.job_ids.length} 个岗位` : task.config.cities.map((city) => city.name).join('、')
                  }}
                  · {{ platformName(task.config.platform) }}</small
                >
              </td>
              <td>
                <span class="status-pill" :class="taskStatus(task)"
                  ><span></span>{{ statusName(taskStatus(task), task.config.mode, task.config.delivery_action) }}</span
                >
              </td>
              <td>
                <span
                  >{{ task.config.delivery_action === 'message' ? '新发送' : task.config.mode === 'delivery' ? '确认完成' : '新增' }} <strong class="green-text">{{ task.saved }}</strong> /
                  {{ task.config.mode === 'delivery' ? '跳过' : '更新' }} {{ task.duplicates }}</span
                ><small
                  >{{ task.config.mode === 'delivery' ? '已处理' : '已读取' }} {{ task.scanned }} · 失败 {{ taskFailedCount(task) }}<span v-if="taskUnconfirmed(task)"> · 待核对 {{ taskUnconfirmed(task) }}</span></small
                >
              </td>
              <td>
                <span class="table-time">{{
                  time(task.created_at, true)
                }}</span>
              </td>
              <td>
                <div class="record-actions">
                  <RouterLink v-if="task.config.delivery_action === 'message'" :to="{ name: 'messages', query: { task: task.id, status: 'all' } }">查看消息</RouterLink>
                  <button @click="selectTask(task)">查看结果</button
                  ><button v-if="task.config.mode !== 'delivery'" :disabled="isActive" @click="reuseTask(task)">
                    复用配置
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="empty-state">
          <span class="empty-record"><History :size="32" /></span>
          <h3>还没有采集记录</h3>
          <p>每次任务的搜索范围、日志和执行结果都会保留。</p>
          <button
            class="button button-primary"
            @click="router.push({ name: 'workbench' })"
          >
            <Plus :size="15" />创建第一个任务
          </button>
        </div>
      </div>
      <div class="records-note">
        显示最近 100 次任务，历史岗位仍保留在数据库中。
      </div>
    </section>
  </div>
</template>

<style scoped>
.records-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 19px 21px 17px;
}
.records-heading h2 {
  display: flex;
  align-items: center;
  gap: 9px;
}
.records-heading h2 > span {
  font-size: 10px;
  font-weight: 500;
  background: #f2f1fd;
  color: #8b80cf;
  padding: 3px 7px;
  border-radius: 5px;
  font-variant-numeric: tabular-nums;
}
.records-heading {
  border-bottom: 1px solid var(--line);
}
.records-panel table {
  min-width: 740px;
}
.record-title {
  display: block;
  max-width: 290px;
  font-size: 12px;
  font-weight: 550;
  color: #626e87;
  overflow: hidden;
  text-overflow: ellipsis;
}
.records-panel td {
  padding-top: 19px;
  padding-bottom: 19px;
}
.record-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: 10px;
}
.record-actions button {
  padding: 0;
  color: #8172d8;
}
.record-actions button:last-child {
  color: #a0a8b8;
}
.record-actions button:hover:not(:disabled) {
  color: var(--accent-dark);
}
.record-actions a { color: var(--accent); font-size: 14px; white-space: nowrap; }
.records-note {
  padding: 16px 21px;
  color: #a9b1c1;
  font-size: 10px;
  border-top: 1px solid var(--line);
}
.empty-record {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  background: #f4f1ff;
  color: #b1a7d8;
  display: grid;
  place-items: center;
}
@media (max-width: 600px) {
  .records-heading {
    padding-left: 17px;
    padding-right: 17px;
  }
}
</style>
