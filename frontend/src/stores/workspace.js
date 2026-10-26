import {
  computed,
  inject,
  onBeforeUnmount,
  onMounted,
  provide,
  reactive,
  ref,
  watch,
} from 'vue'
import { useRouter } from 'vue-router'
import { eventUrl, post, request } from '../api'
import { activeStatuses } from '../constants/tasks'
import { useCollectionConfig } from '../composables/useCollectionConfig'
import { platformName } from '../constants/platforms'

const workspaceKey = Symbol('workspace')

export function provideWorkspace() {
  const router = useRouter()
  const collectionConfig = useCollectionConfig()
  const { config, selectedCities } = collectionConfig
  const system = ref(null)
  const history = ref([])
  const selectedTask = ref(null)
  const logs = ref([])
  const logConnected = ref(false)
  const apiError = ref('')
  const toast = ref(null)
  const refreshVersion = ref(0)
  const busy = reactive({
    start: false,
    interrupt: false,
    resume: false,
    browser: false,
    database: false,
  })
  let polling = null
  let pollBusy = false
  let eventSource = null
  let toastTimer = null
  let disposed = false

  const activeTask = computed(
    () =>
      history.value.find((task) => task.id === system.value?.active_task_id) ||
      history.value.find((task) => activeStatuses.includes(task.status)),
  )
  const isActive = computed(() =>
    Boolean(system.value?.active_task_id || activeTask.value),
  )
  const taskRunning = computed(
    () =>
      selectedTask.value && activeStatuses.includes(selectedTask.value.status),
  )
  const dbConnected = computed(() => Boolean(system.value?.database?.connected))
  const browserState = computed(
    () => system.value?.browser || { open: false, logged_in: false },
  )
  const waitingForLogin = computed(
    () =>
      selectedTask.value?.status === 'waiting' &&
      (selectedTask.value.message?.startsWith('等待登录完成') ||
        (selectedTask.value.id === system.value?.active_task_id &&
          browserState.value.waiting_for_login)),
  )
  const loginPending = computed(() =>
    Boolean(
      (browserState.value.waiting_for_login ||
        waitingForLogin.value ||
        activeTask.value?.status === 'queued') &&
      !(activeTask.value?.scanned > 0),
    ),
  )
  const stats = computed(() => system.value?.stats)
  function notify(message, type = 'success') {
    clearTimeout(toastTimer)
    toast.value = { message, type }
    toastTimer = setTimeout(() => {
      toast.value = null
    }, 4500)
  }

  async function refreshSystem() {
    try {
      system.value = await request('/system', { timeout: 22000 })
      apiError.value = ''
    } catch (error) {
      apiError.value = error.message
    }
  }
  async function refreshTasks() {
    if (!dbConnected.value) return
    try {
      history.value = await request('/tasks')
      if (selectedTask.value) {
        const task = history.value.find(
          (item) => item.id === selectedTask.value.id,
        )
        if (task) selectedTask.value = task
      }
    } catch (error) {
      apiError.value = error.message
    }
  }

  async function refreshAll() {
    await refreshSystem()
    await refreshTasks()
    refreshVersion.value += 1
  }

  function connectEvents(taskId) {
    eventSource?.close()
    logs.value = []
    logConnected.value = false
    eventSource = new EventSource(
      eventUrl(`/tasks/${encodeURIComponent(taskId)}/events`),
    )
    eventSource.onopen = () => {
      logConnected.value = true
    }
    eventSource.onerror = () => {
      logConnected.value = false
    }
    eventSource.addEventListener('service-error', (event) => {
      apiError.value = JSON.parse(event.data).message
      eventSource?.close()
      logConnected.value = false
    })
    eventSource.addEventListener('snapshot', (event) => {
      if (selectedTask.value?.id !== taskId) return
      const data = JSON.parse(event.data)
      if (
        data.task &&
        !activeStatuses.includes(selectedTask.value.status) &&
        activeStatuses.includes(data.task.status)
      )
        return
      const previousStatus = selectedTask.value?.status
      selectedTask.value = data.task
      const bySequence = new Map(logs.value.map((log) => [log.seq, log]))
      data.logs.forEach((log) => bySequence.set(log.seq, log))
      logs.value = [...bySequence.values()]
        .sort((a, b) => a.seq - b.seq)
        .slice(-200)
      if (data.task && !activeStatuses.includes(data.task.status)) {
        if (data.logs.length < 200) {
          eventSource?.close()
          logConnected.value = false
        }
        if (previousStatus && activeStatuses.includes(previousStatus))
          refreshAll()
      }
    })
  }
  function selectTask(task, showResults = true) {
    selectedTask.value = task
    if (showResults)
      router.push({ name: 'workbench', query: { task: task.id } })
    connectEvents(task.id)
  }

  async function startCollection() {
    if (busy.start || isActive.value) return
    if (!config.keywords.length || !selectedCities.value.length) {
      notify('请至少填写一个关键词并选择一个城市', 'error')
      return
    }
    if (Number(config.delay_max) < Number(config.delay_min)) {
      notify('最大间隔不能小于最小间隔', 'error')
      return
    }
    busy.start = true
    try {
      const payload = { ...config, cities: selectedCities.value }
      delete payload.cityCodes
      const task = await post('/tasks', payload)
      system.value.active_task_id = task.id
      system.value.browser = {
        ...browserState.value,
        waiting_for_login: true,
        login_ready: false,
      }
      history.value.unshift(task)
      selectTask(task)
      notify('任务已创建，请登录后点击“我已登录，继续采集”')
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.start = false
    }
  }
  async function interruptCollection(task = null) {
    const taskId =
      task?.id || system.value?.active_task_id || activeTask.value?.id
    if (!taskId || busy.interrupt) return
    busy.interrupt = true
    try {
      const result = await post(`/tasks/${taskId}/interrupt`)
      const position = history.value.findIndex((item) => item.id === taskId)
      if (position !== -1) history.value[position] = result
      if (selectedTask.value?.id === taskId) selectedTask.value = result
      if (
        !activeStatuses.includes(result.status) &&
        system.value?.active_task_id === taskId
      )
        system.value.active_task_id = null
      await refreshAll()
      notify(
        activeStatuses.includes(result.status)
          ? '正在中断，等待当前入库操作结束'
          : result.status === 'interrupted'
            ? '任务已中断，已采集岗位已保留'
            : '任务已结束，已采集岗位已保留',
      )
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.interrupt = false
    }
  }
  async function resumeCollection() {
    if (busy.resume || busy.interrupt) return
    busy.resume = true
    try {
      const action = waitingForLogin.value ? 'confirm-login' : 'resume'
      await post(`/tasks/${selectedTask.value.id}/${action}`)
      notify(
        waitingForLogin.value
          ? '正在确认登录状态，通过后开始采集'
          : '已请求继续采集',
      )
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.resume = false
    }
  }
  async function openBrowser() {
    if (busy.browser) return
    busy.browser = true
    try {
      await post(`/browser/open?platform=${encodeURIComponent(activeTask.value?.config.platform || config.platform)}`)
      await refreshSystem()
      notify(`请在打开的浏览器中登录${platformName(activeTask.value?.config.platform || config.platform)}`)
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.browser = false
    }
  }
  async function closeBrowser() {
    busy.browser = true
    try {
      await post('/browser/close')
      await refreshSystem()
      notify('采集浏览器已关闭，登录状态已保留')
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.browser = false
    }
  }
  async function reconnectDatabase() {
    busy.database = true
    try {
      const result = await post('/database/reconnect')
      notify(result.message, result.connected ? 'success' : 'error')
      await refreshAll()
    } catch (error) {
      notify(error.message, 'error')
    } finally {
      busy.database = false
    }
  }
  async function startDelivery(jobIds, action, messages = {}, allowRepeat = false) {
    if (busy.start || isActive.value) throw new Error('请先结束当前任务')
    busy.start = true
    try {
      const task = await post('/deliveries', { job_ids: jobIds, action, messages, allow_repeat: allowRepeat, confirmed: true })
      system.value.active_task_id = task.id
      system.value.browser = { ...browserState.value, waiting_for_login: true, login_ready: false }
      history.value.unshift(task)
      selectTask(task)
      notify(action === 'message' ? '消息任务已创建，请确认浏览器登录后继续发送' : '投递任务已创建，请确认浏览器登录后继续')
      return task
    } finally { busy.start = false }
  }
  function reuseTask(task) {
    if (task.config.mode === 'delivery') {
      notify('投递任务请在岗位列表重新勾选，避免重复投递', 'error')
      return
    }
    collectionConfig.reuseConfig(task.config)
    router.push({ name: 'workbench' })
    notify('已填入该任务的采集配置')
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text)
      notify('已复制')
    } catch {
      notify('复制失败，请手动选中文本复制', 'error')
    }
  }

  onMounted(async () => {
    await refreshAll()
    if (disposed) return
    if (activeTask.value && !selectedTask.value)
      selectTask(activeTask.value, false)
    polling = setInterval(async () => {
      if (pollBusy || document.hidden) return
      pollBusy = true
      try {
        await refreshSystem()
        await refreshTasks()
        if (system.value?.active_task_id && !selectedTask.value) {
          const task = history.value.find(
            (item) => item.id === system.value.active_task_id,
          )
          if (task) selectTask(task, false)
        }
      } catch {
        /* 连接状态由页面顶部呈现，轮询不重复弹窗。 */
      } finally {
        pollBusy = false
      }
    }, 4000)
  })

  onBeforeUnmount(() => {
    disposed = true
    clearInterval(polling)
    clearTimeout(toastTimer)
    eventSource?.close()
  })

  watch(
    () => [
      router.currentRoute.value.name,
      router.currentRoute.value.query.task,
      history.value,
    ],
    () => {
      const route = router.currentRoute.value
      if (route.name !== 'workbench' || !route.query.task) return
      const task = history.value.find(
        (item) => item.id === String(route.query.task),
      )
      if (task && selectedTask.value?.id !== task.id) selectTask(task, false)
    },
  )

  const workspace = {
    collectionConfig,
    system,
    history,
    selectedTask,
    logs,
    logConnected,
    apiError,
    toast,
    busy,
    refreshVersion,
    activeTask,
    isActive,
    taskRunning,
    dbConnected,
    browserState,
    waitingForLogin,
    loginPending,
    stats,
    notify,
    refreshAll,
    selectTask,
    startCollection,
    startDelivery,
    interruptCollection,
    resumeCollection,
    openBrowser,
    closeBrowser,
    reconnectDatabase,
    reuseTask,
    copyText,
  }
  provide(workspaceKey, workspace)
  return workspace
}

export function useWorkspace() {
  const workspace = inject(workspaceKey)
  if (!workspace) throw new Error('工作台状态尚未初始化')
  return workspace
}
