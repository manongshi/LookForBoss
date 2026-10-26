import { computed, onScopeDispose, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { apiHeaders, apiUrl, request } from '../api'
import { useWorkspace } from '../stores/workspace'

export function useJobList(viewName) {
  const route = useRoute()
  const router = useRouter()
  const {
    dbConnected,
    loginPending,
    system,
    selectedTask,
    refreshVersion,
    activeTask,
    apiError,
    notify,
  } = useWorkspace()
  const jobs = ref([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = 15
  const query = reactive({
    platform: route.name === viewName ? String(route.query.platform || '') : '',
    q: route.name === viewName ? String(route.query.q || '') : '',
    city: route.name === viewName ? String(route.query.city || '') : '',
    task_id: route.name === viewName ? String(route.query.task || '') : '',
    keyword: route.name === viewName ? String(route.query.keyword || '') : '',
  })
  const busy = reactive({ jobs: false, export: false })
  const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
  let jobsVersion = 0
  let searchTimer = null
  let disposed = false

  async function loadJobs() {
    if (route.name !== viewName || disposed) return
    const version = ++jobsVersion
    if (viewName === 'workbench' && query.task_id && loginPending.value) {
      busy.jobs = false
      return
    }
    if (!dbConnected.value) {
      busy.jobs = false
      return
    }
    busy.jobs = true
    try {
      const params = new URLSearchParams({
        ...query,
        page: page.value,
        page_size: pageSize,
      })
      const result = await request(`/jobs?${params}`)
      if (
        version !== jobsVersion ||
        (viewName === 'workbench' && query.task_id && loginPending.value)
      )
        return
      jobs.value = result.items
      total.value = result.total
      if (page.value > Math.max(1, Math.ceil(result.total / pageSize))) {
        page.value = Math.max(1, Math.ceil(result.total / pageSize))
        await loadJobs()
      }
    } catch (error) {
      if (version === jobsVersion) apiError.value = error.message
    } finally {
      if (version === jobsVersion) busy.jobs = false
    }
  }

  async function exportJobs() {
    if (busy.export) return
    busy.export = true
    try {
      const response = await fetch(
        apiUrl(`/jobs/export?${new URLSearchParams(query)}`),
        { headers: apiHeaders() },
      )
      if (!response.ok) {
        const body = await response.json()
        throw new Error(body.detail || '导出失败')
      }
      const blob = await response.blob()
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.href = url
      link.download =
        response.headers
          .get('content-disposition')
          ?.match(/filename="([^"]+)"/)?.[1] || 'jobs.csv'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      notify('当前筛选结果已导出')
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.export = false
    }
  }

  watch(
    query,
    () => {
      if (route.name !== viewName) return
      jobsVersion += 1
      jobs.value = []
      total.value = 0
      busy.jobs = false
      page.value = 1
      clearTimeout(searchTimer)
      searchTimer = setTimeout(loadJobs, 350)
    },
    { deep: true },
  )
  watch(page, loadJobs)
  watch(
    () => [query.task_id, query.keyword, query.q, query.city, query.platform],
    () => {
      if (route.name !== viewName) return
      const values = { task: query.task_id, keyword: query.keyword }
      if (viewName === 'jobs') Object.assign(values, { q: query.q, city: query.city, platform: query.platform })
      if (Object.entries(values).every(([key, value]) => value === String(route.query[key] || ''))) return
      router.replace({ query: { ...route.query, ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value || undefined])) } })
    },
  )
  watch(
    () => route.fullPath,
    () => {
      clearTimeout(searchTimer)
      jobsVersion += 1
      busy.jobs = false
      if (route.name !== viewName) return
      query.task_id = String(route.query.task || '')
      query.keyword = String(route.query.keyword || '')
      for (const key of ['q', 'city', 'platform']) {
        if (viewName === 'jobs' || route.query[key] !== undefined) query[key] = String(route.query[key] || '')
      }
      loadJobs()
    },
    { immediate: true },
  )
  watch(dbConnected, (connected) => {
    if (connected) loadJobs()
    else {
      jobsVersion += 1
      jobs.value = []
      total.value = 0
      busy.jobs = false
    }
  })
  watch(refreshVersion, loadJobs)
  watch(system, () => {
    if (activeTask.value?.status === 'running' && !loginPending.value)
      loadJobs()
  })
  watch(
    () => selectedTask.value?.status,
    (status, previous) => {
      if (status !== previous) loadJobs()
    },
  )
  watch(loginPending, (pending) => {
    if (viewName !== 'workbench') return
    if (pending && query.task_id) {
      jobsVersion += 1
      jobs.value = []
      total.value = 0
      busy.jobs = false
    } else loadJobs()
  })
  onScopeDispose(() => {
    disposed = true
    jobsVersion += 1
    clearTimeout(searchTimer)
  })

  return {
    jobs,
    total,
    page,
    pageSize,
    query,
    busy,
    pages,
    loadJobs,
    exportJobs,
  }
}
