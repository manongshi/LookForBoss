<script setup>
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { MessagesSquare, Plus } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import JobsPanel from '../features/jobs/JobsPanel.vue'
import ExportJobsButton from '../features/jobs/ExportJobsButton.vue'
import { useJobList } from '../composables/useJobList'
import { useWorkspace } from '../stores/workspace'
import { request } from '../api'
import { number } from '../utils/format'

const list = useJobList('jobs')
const { total, busy, exportJobs, query } = list
const { dbConnected, refreshVersion, system } = useWorkspace()
const groups = ref([])
const loading = ref(false)
const error = ref('')
const active = ref(false)
let version = 0
const keywordOptions = computed(() => query.keyword && !groups.value.some(item => item.keyword === query.keyword)
  ? [{ keyword: query.keyword }, ...groups.value]
  : groups.value)

async function loadGroups() {
  if (!active.value || !dbConnected.value) return
  const current = ++version
  loading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({ task_id: query.task_id, platform: query.platform, city: query.city, q: query.q })
    const result = await request(`/jobs/keywords?${params}`)
    if (current === version && active.value) groups.value = result
  } catch (e) {
    if (current === version) error.value = e.message
  } finally {
    if (current === version) loading.value = false
  }
}
onActivated(() => { active.value = true; loadGroups() })
onDeactivated(() => { active.value = false; version++; loading.value = false })
watch(dbConnected, connected => {
  if (connected) loadGroups()
  else { version++; groups.value = []; loading.value = false }
})
watch(refreshVersion, loadGroups)
watch(system, () => { if (system.value?.active_task_id) loadGroups() })
watch(() => [query.task_id, query.platform, query.city, query.q], loadGroups)
</script>

<template>
  <div class="saved-jobs-page">
    <PageHeading>
      <ExportJobsButton :disabled="!dbConnected || !total" :busy="busy.export" @export="exportJobs" />
      <RouterLink class="button button-white" :to="{ name: 'interview', query: query.keyword ? { keyword: query.keyword } : query.q ? { q: query.q } : {} }"><MessagesSquare :size="16" />{{ query.keyword ? '练习这类岗位' : '模拟面试' }}</RouterLink>
      <RouterLink class="button button-primary" :to="{ name: 'workbench' }"><Plus :size="16" />采集职位</RouterLink>
    </PageHeading>
    <JobsPanel :list="list">
      <template #filters>
        <div class="keyword-filter-row saved-keyword-filter">
          <label class="keyword-select-label" for="saved-keyword">采集关键词</label>
          <select id="saved-keyword" v-model="query.keyword" :disabled="!dbConnected" aria-label="按采集关键词筛选职位">
            <option value="">全部关键词</option>
            <option v-for="item in keywordOptions" :key="item.keyword" :value="item.keyword">{{ item.keyword }}{{ item.total === undefined ? '' : ` · ${number(item.total)}` }}</option>
          </select>
          <span v-if="loading" class="filter-loading" role="status">正在加载关键词…</span>
          <div v-if="error" class="keyword-load-error" role="status"><span>关键词加载失败</span><button :title="error" @click="loadGroups">重试</button></div>
        </div>
      </template>
    </JobsPanel>
  </div>
</template>

<style scoped>
.saved-jobs-page { min-width: 0; }
.saved-keyword-filter { justify-content: flex-start; }
.keyword-select-label, .filter-loading, .keyword-load-error { font-size: 14px; color: var(--muted); }
.saved-keyword-filter select { width: 240px; min-height: 44px; }
.keyword-load-error { display: flex; align-items: center; gap: 8px; }
.keyword-load-error button { color: var(--accent); min-height: 44px; }
@media (max-width: 640px) {
  .keyword-select-label { display: none; }
  .saved-keyword-filter select { width: 100%; }
}
</style>
