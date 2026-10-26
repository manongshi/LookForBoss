<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowUpRight } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import JobsPanel from '../features/jobs/JobsPanel.vue'
import ExportJobsButton from '../features/jobs/ExportJobsButton.vue'
import CollectionForm from '../features/collection/CollectionForm.vue'
import TaskProgress from '../features/collection/TaskProgress.vue'
import CollectionLogs from '../features/collection/CollectionLogs.vue'
import { useJobList } from '../composables/useJobList'
import { useWorkspace } from '../stores/workspace'

const list = useJobList('workbench')
const { total, busy, exportJobs, query } = list
const { dbConnected, selectedTask, waitingForLogin, collectionConfig } = useWorkspace()
const resultKeywords = computed(() => [...new Set([
  ...(query.task_id && selectedTask.value?.id === query.task_id
    ? selectedTask.value.config.keywords || []
    : collectionConfig.config.keywords),
  ...(query.keyword ? [query.keyword] : []),
])])
const route = useRoute()
const taskSection = ref(null)
watch(
  [() => route.name, () => selectedTask.value?.id, () => selectedTask.value?.status, waitingForLogin],
  async () => {
    if (route.name !== 'workbench' || selectedTask.value?.status !== 'waiting') return
    await nextTick()
    if (route.name === 'workbench') taskSection.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
  },
  { immediate: true },
)
</script>

<template>
  <div class="workbench-page">
    <PageHeading><ExportJobsButton :disabled="!dbConnected || !total" :busy="busy.export" @export="exportJobs" /></PageHeading>
    <CollectionForm />
    <div v-if="selectedTask" ref="taskSection" class="task-section"><TaskProgress /></div>
    <JobsPanel :list="list" workbench>
      <template #filters>
        <div v-if="resultKeywords.length" class="keyword-filter-row">
          <div class="keyword-filter-options" aria-label="按采集关键词筛选职位">
            <button class="keyword-filter" :class="{ selected: !query.keyword }" :aria-pressed="!query.keyword" @click="query.keyword = ''">全部职位</button>
            <button v-for="keyword in resultKeywords" :key="keyword" class="keyword-filter" :class="{ selected: query.keyword === keyword }" :aria-pressed="query.keyword === keyword" @click="query.keyword = query.keyword === keyword ? '' : keyword">{{ keyword }}</button>
          </div>
          <RouterLink class="all-jobs-link" :to="{ name: 'jobs' }">我的职位<ArrowUpRight :size="15" /></RouterLink>
        </div>
      </template>
    </JobsPanel>
    <details v-if="selectedTask" class="collection-log-details">
      <summary>采集日志</summary>
      <CollectionLogs />
    </details>
  </div>
</template>

<style scoped>
.workbench-page { display: flex; flex-direction: column; min-width: 0; gap: 24px; }
.workbench-page > :deep(.page-heading) { margin-bottom: 0; }
.task-section { scroll-margin-top: 84px; }
.collection-log-details { border-top: 1px solid var(--line); padding-top: 8px; color: var(--muted); }
.collection-log-details summary { cursor: pointer; padding: 16px 0; font-size: 14px; }
.collection-log-details summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
@media (max-width: 640px) { .workbench-page { gap: 20px; } }
</style>
