<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ArrowRight, Check, ChevronRight, CircleHelp, History, LoaderCircle, Mic, Pause, Play, Plus, RefreshCw, Send, Settings2, Square, Volume2, X } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import { request, post } from '../api'
import { useInterviewMedia } from '../composables/useInterviewMedia'

const defaultModelProviders = [
  { id: 'minimax', name: 'MiniMax', model: 'MiniMax-M3' },
  { id: 'deepseek', name: 'DeepSeek', model: 'deepseek-flash' },
  { id: 'qwen', name: '百炼', model: 'qwen-plus' },
]

const route = useRoute()
const router = useRouter()
const media = useInterviewMedia()
const { videoRef, status: mediaStatus, connecting, connected, soundEnabled, preparingSpeech, playing, recording, recognizing, transcript, error: mediaError, speechNote, speechActivity } = media
const active = ref(false)
const initialized = ref(false)
const sourceMode = ref('keyword')
const keyword = ref('')
const categorySearch = ref('')
const jobSearch = ref('')
const selectedJob = ref('')
const groups = ref([])
const jobs = ref([])
const context = ref(null)
const session = ref(null)
const history = ref([])
const answer = ref('')
const notice = ref('')
const sourceError = ref('')
const historyError = ref('')
const busy = reactive({ context: false, jobs: false, session: false, history: false, settings: false, restore: false })
const loadingAction = ref('')
const settingsOpen = ref(false)
const settingsFeedback = ref('')
const settingsFailed = ref(false)
const modelStatus = ref({ configured: false, provider: 'deepseek', model: 'deepseek-flash' })
const settingsForm = reactive({ provider: 'deepseek', model: 'deepseek-flash', api_key: '', clear_key: false })
const form = reactive({ title: '', requirements: '', level: '中级', question_count: 6 })
const avatarId = ref('hr-warm')
const voiceId = ref('zh-CN-XiaoxiaoNeural')
const dialogue = ref(null)
const conversation = ref(null)
const pendingOperation = ref(null)
const startAttempt = ref(null)
const lastSpoken = ref('')
const voiceConversation = ref(false)
let recordingTurn = null
let voiceListeningTimer = null
let lastTranscriptId = 0
let contextVersion = 0
let lastRoute = ''
let speakingQuestion = null

const avatars = [
  { id: 'hr-warm', name: '知夏', description: '亲和', image: '/interview/avatars/hr-warm.png' },
  { id: 'hr-calm', name: '明远', description: '沉稳', image: '/interview/avatars/hr-calm.png' },
  { id: 'hr-senior', name: '若宁', description: '资深', image: '/interview/avatars/hr-senior.png' },
]
const voices = [
  { id: 'zh-CN-XiaoxiaoNeural', name: '晓晓 · 女声' },
  { id: 'zh-CN-XiaoyiNeural', name: '晓伊 · 女声' },
  { id: 'zh-CN-YunxiNeural', name: '云希 · 男声' },
  { id: 'zh-CN-YunjianNeural', name: '云健 · 男声' },
]
const selectedAvatar = computed(() => avatars.find(item => item.id === avatarId.value) || avatars[0])
const modelProviders = computed(() => modelStatus.value.providers || defaultModelProviders)
const selectedModelProvider = computed(() => modelProviders.value.find(item => item.id === settingsForm.provider))
const modelProviderName = computed(() => modelStatus.value.provider_name || modelProviders.value.find(item => item.id === modelStatus.value.provider)?.name || '模型')
const selectedProviderConfigured = computed(() => Boolean(selectedModelProvider.value?.configured || (settingsForm.provider === modelStatus.value.provider && modelStatus.value.configured)))
const inProgress = computed(() => session.value?.status === 'active')
const pendingAnswer = computed(() => session.value?.pending_action === 'answer')
const hasAnswers = computed(() => Boolean(session.value?.messages?.some(item => item.role === 'candidate')))
const canAnswer = computed(() => inProgress.value && session.value.awaiting_answer && !pendingAnswer.value && !busy.restore)
const report = computed(() => session.value?.report)
const currentQuestion = computed(() => session.value?.current_question || '')
const progress = computed(() => session.value ? Math.min(100, Math.round((session.value.answered_count || 0) / Math.max(1, session.value.question_count) * 100)) : 0)
const keywordOptions = computed(() => keyword.value && !groups.value.some(item => item.keyword === keyword.value) ? [{ keyword: keyword.value }, ...groups.value] : groups.value)
const questionNumber = computed(() => Math.min((session.value?.current_index || 0) + 1, session.value?.question_count || form.question_count))
const roleLabel = computed(() => connected.value ? !soundEnabled.value ? '点击开启声音后提问' : preparingSpeech.value ? '正在准备提问语音' : playing.value ? '面试官正在提问' : '面试官已连接' : connecting.value ? '正在准备数字人' : '数字人待连接')
const profileSummary = computed(() => {
  const profile = context.value?.profile
  if (session.value) return ''
  if (!profile) return ''
  return [profile.roles?.join(' / '), profile.years == null ? '' : `${profile.years} 年经验`, profile.degree, profile.skills?.slice(0, 8).join('、')].filter(Boolean).join(' · ')
})

function storageGet(key) { try { return localStorage.getItem(key) } catch { return null } }
function storageSet(key, value) { try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value) } catch {} }
function operationKey(id) { return `findboss:interview:operation:${id}` }
function requestId() { return globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}` }
function valueOfQuery(value) { return String(Array.isArray(value) ? value[0] || '' : value || '') }
function score(value) { return Number.isFinite(Number(value)) ? Math.min(100, Math.max(0, Math.round(Number(value)))) : 0 }
function dateLabel(value) {
  if (!value) return ''
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? '' : parsed.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function operationFor(kind, submittedAnswer = '') {
  const current = pendingOperation.value
  if (current && current.session_id === session.value.id && current.kind === kind && (kind !== 'answer' || current.answer === submittedAnswer)) return current
  const value = { session_id: session.value.id, kind, answer: submittedAnswer, version: session.value.version, request_id: requestId() }
  pendingOperation.value = value
  storageSet(operationKey(value.session_id), JSON.stringify(value))
  return value
}
function clearOperation(id) {
  storageSet(operationKey(id), null)
  if (pendingOperation.value?.session_id === id) pendingOperation.value = null
}
async function scrollDialogue() {
  await nextTick()
  if (active.value && dialogue.value && conversation.value) {
    dialogue.value.scrollTop = dialogue.value.scrollHeight
  }
}
function acceptSession(value) {
  session.value = value
  storageSet('findboss:interview:last-session', value.id)
  scrollDialogue()
}
async function loadModelSettings() {
  const value = await request('/interviews/settings')
  modelStatus.value = value
  Object.assign(settingsForm, { provider: value.provider || 'deepseek', model: value.model || 'deepseek-flash', api_key: '', clear_key: false })
  if (!value.configured) settingsOpen.value = true
}
async function loadHistory() {
  busy.history = true
  historyError.value = ''
  try { history.value = (await request('/interviews/sessions')).items || [] }
  catch (error) { historyError.value = error.message }
  finally { busy.history = false }
}
async function loadGroups() {
  try { groups.value = await request('/jobs/keywords') }
  catch (error) { sourceError.value = error.message }
}
async function loadJobs() {
  busy.jobs = true
  try {
    const result = await request(`/jobs?${new URLSearchParams({ page: '1', page_size: '50', q: jobSearch.value.trim() })}`)
    jobs.value = result.items || []
  } catch (error) { sourceError.value = error.message }
  finally { busy.jobs = false }
}
function changeSource(mode) {
  if (inProgress.value || busy.context || busy.session || busy.restore) return
  sourceMode.value = mode
  sourceError.value = ''
  context.value = null
  contextVersion++
  if (mode === 'job' && !jobs.value.length) loadJobs()
}
async function loadContext() {
  if (busy.session || busy.restore || inProgress.value || sourceMode.value === 'manual') return
  if (sourceMode.value === 'job' && !selectedJob.value) { sourceError.value = '先选择一份已采集的职位。'; return }
  if (sourceMode.value === 'keyword' && !keyword.value && !categorySearch.value.trim()) { sourceError.value = '先选择采集关键词，或填写要练习的岗位方向。'; return }
  const version = ++contextVersion
  busy.context = true
  sourceError.value = ''
  const params = new URLSearchParams(sourceMode.value === 'job' ? { job_id: selectedJob.value } : { keyword: keyword.value, q: categorySearch.value.trim() })
  try {
    const value = await request(`/interviews/context?${params}`)
    if (version !== contextVersion) return
    context.value = value
    form.title = value.title || ''
    form.requirements = value.requirements || ''
    if (!value.requirements?.trim()) sourceError.value = '这组岗位还没有完整的职位描述，请在下方补充岗位要求。'
  } catch (error) { if (version === contextVersion) sourceError.value = error.message }
  finally { if (version === contextVersion) busy.context = false }
}
function changeProvider() {
  settingsForm.model = selectedModelProvider.value?.model || ''
  settingsForm.api_key = ''
  settingsForm.clear_key = false
  settingsFeedback.value = ''
  settingsFailed.value = false
}
async function saveSettings() {
  if (busy.settings) return
  busy.settings = true
  settingsFeedback.value = ''
  settingsFailed.value = false
  try {
    const value = await post('/interviews/settings', { ...settingsForm }, { timeout: 90000 })
    modelStatus.value = value
    settingsForm.model = value.model
    settingsForm.api_key = ''
    settingsForm.clear_key = false
    settingsFeedback.value = value.configured ? '已保存，下次打开可直接使用。' : '模型已保存，请填写 API Key 后使用。'
  } catch (error) {
    settingsFeedback.value = error.message
    settingsFailed.value = true
  }
  finally { busy.settings = false }
}
async function recoverSession(id, operation) {
  try {
    const value = await request(`/interviews/sessions/${encodeURIComponent(id)}`)
    acceptSession(value)
    if (operation.kind === 'finish' && value.report) { clearOperation(id); return true }
    if (operation.kind === 'answer' && !value.pending_action && value.version > operation.version) {
      const lastAnswer = [...(value.messages || [])].reverse().find(item => item.role === 'candidate')
      if (lastAnswer?.content === operation.answer) {
        answer.value = ''
        clearOperation(id)
        return true
      }
    }
  } catch {}
  return false
}
async function startInterview() {
  if (busy.session || busy.context || busy.restore) return
  if (!form.title.trim() || !form.requirements.trim()) { notice.value = '请填写岗位名称和岗位要求，再生成面试题。'; return }
  if (!modelStatus.value.configured) { settingsOpen.value = true; notice.value = '先在模型设置中配置可用的 API Key。'; return }
  notice.value = ''
  busy.session = true
  loadingAction.value = 'start'
  const body = {
    title: form.title.trim(), requirements: form.requirements.trim(), level: form.level, question_count: Number(form.question_count),
    ...(sourceMode.value === 'job' ? { job_id: selectedJob.value } : sourceMode.value === 'keyword' ? { keyword: keyword.value, q: categorySearch.value.trim() } : {}),
  }
  const fingerprint = JSON.stringify(body)
  if (!startAttempt.value || startAttempt.value.fingerprint !== fingerprint) startAttempt.value = { fingerprint, request_id: requestId() }
  try {
    const value = await post('/interviews/sessions', { ...body, request_id: startAttempt.value.request_id }, { timeout: 120000 })
    acceptSession(value)
    startAttempt.value = null
    pendingOperation.value = null
    answer.value = ''
    loadHistory()
  } catch (error) { notice.value = error.message; loadHistory() }
  finally { busy.session = false; loadingAction.value = '' }
}
async function submitAnswer(retry = false, { fromVoice = false } = {}) {
  if (busy.session || busy.restore || !session.value || recognizing.value || recording.value) return
  const submitted = retry ? String(session.value.retry_answer || pendingOperation.value?.answer || answer.value).trim() : answer.value.trim()
  if (!submitted) { notice.value = '先输入或录入你的回答。'; return }
  if (submitted.length > 4000) { notice.value = '回答超过 4000 字，请保留重点后再提交。'; return }
  if (!retry && !canAnswer.value) return
  if (!fromVoice) stopVoiceConversation()
  const operation = operationFor('answer', submitted)
  const id = session.value.id
  busy.session = true
  loadingAction.value = 'answer'
  notice.value = ''
  void media.interrupt()
  try {
    const value = await post(`/interviews/sessions/${encodeURIComponent(id)}/answer`, { answer: submitted, request_id: operation.request_id, version: operation.version }, { timeout: 120000 })
    acceptSession(value)
    clearOperation(id)
    answer.value = ''
    loadHistory()
    return true
  } catch (error) {
    const recovered = await recoverSession(id, operation)
    notice.value = recovered ? '本次回答已处理，已同步最新问题。' : error.message
    return recovered
  } finally { busy.session = false; loadingAction.value = '' }
}
async function finishInterview() {
  if (busy.session || busy.restore || !session.value || !hasAnswers.value) return
  stopVoiceConversation()
  const id = session.value.id
  const operation = operationFor('finish')
  busy.session = true
  loadingAction.value = 'finish'
  notice.value = ''
  void media.interrupt()
  try {
    const value = await post(`/interviews/sessions/${encodeURIComponent(id)}/finish`, { request_id: operation.request_id, version: operation.version }, { timeout: 120000 })
    acceptSession(value)
    clearOperation(id)
    loadHistory()
  } catch (error) {
    const recovered = await recoverSession(id, operation)
    notice.value = recovered ? '面试报告已生成，已同步最新记录。' : error.message
  } finally { busy.session = false; loadingAction.value = '' }
}
async function restoreSession(id) {
  if (busy.session || busy.restore || !id) return
  stopVoiceConversation()
  busy.restore = true
  notice.value = ''
  void media.interrupt()
  try {
    const value = await request(`/interviews/sessions/${encodeURIComponent(id)}`)
    acceptSession(value)
    answer.value = ''
    try { pendingOperation.value = JSON.parse(storageGet(operationKey(id)) || 'null') } catch { pendingOperation.value = null }
    if (value.report) clearOperation(id)
  } catch (error) {
    notice.value = error.message
    if (storageGet('findboss:interview:last-session') === id) storageSet('findboss:interview:last-session', null)
  } finally { busy.restore = false }
}
async function newInterview() {
  if (busy.session || busy.restore) return
  stopVoiceConversation()
  void media.interrupt()
  session.value = null
  pendingOperation.value = null
  startAttempt.value = null
  answer.value = ''
  notice.value = ''
  lastSpoken.value = ''
  storageSet('findboss:interview:last-session', null)
  if (route.query.session) router.replace({ name: 'interview', query: {} })
}
async function speakQuestion() {
  if (!active.value || !connected.value || !soundEnabled.value || !session.value || !currentQuestion.value || busy.restore || busy.session || recording.value || recognizing.value) return
  const id = session.value.id
  const question = currentQuestion.value
  const key = `${id}:${question}`
  if (speakingQuestion?.key === key) return
  const operation = { key }
  speakingQuestion = operation
  try {
    if (playing.value) await media.interrupt()
    if (!active.value || speakingQuestion !== operation || !connected.value || !soundEnabled.value || recording.value || recognizing.value || session.value?.id !== id || currentQuestion.value !== question) return
    const spoken = await media.speak(question)
    if (spoken !== false && speakingQuestion === operation && session.value?.id === id && currentQuestion.value === question) lastSpoken.value = key
  } finally {
    if (speakingQuestion === operation) speakingQuestion = null
  }
}
async function replayQuestion() {
  if (!connected.value || busy.session || busy.restore || recording.value || recognizing.value) return
  if (!soundEnabled.value && !await media.enableSound()) return
  await speakQuestion()
}
function answerContext() {
  return session.value ? { sessionId: session.value.id, version: session.value.version, question: currentQuestion.value } : null
}
function matchesAnswerContext(value) {
  return Boolean(value && active.value && session.value?.id === value.sessionId && session.value.version === value.version && currentQuestion.value === value.question)
}
function stopVoiceConversation() {
  voiceConversation.value = false
  clearTimeout(voiceListeningTimer)
  voiceListeningTimer = null
  recordingTurn = null
  media.cancelRecording()
}
async function beginVoiceAnswer() {
  if (!voiceConversation.value || !active.value || !canAnswer.value || busy.session || busy.restore || recording.value || recognizing.value || recordingTurn) return
  if (connected.value && soundEnabled.value && (playing.value || preparingSpeech.value || ['pending', 'speaking', 'cancelling', 'blocked'].includes(speechActivity.value.phase))) return
  const context = { ...answerContext(), token: requestId() }
  recordingTurn = context
  const started = await media.startRecording({ context, autoStop: true, autoSubmit: true, keepSpeech: true })
  if (recordingTurn !== context) return
  if (!started || !matchesAnswerContext(context) || !voiceConversation.value) {
    stopVoiceConversation()
    return
  }
  notice.value = ''
}
function queueVoiceListening() {
  clearTimeout(voiceListeningTimer)
  voiceListeningTimer = null
  if (!voiceConversation.value || !active.value || !canAnswer.value || busy.session || busy.restore || recording.value || recognizing.value || recordingTurn) return
  if (connected.value && soundEnabled.value) {
    const key = `${session.value.id}:${currentQuestion.value}`
    if (lastSpoken.value !== key || speakingQuestion || playing.value || preparingSpeech.value) return
    if (speechActivity.value.text !== currentQuestion.value || !['finished', 'failed', 'cancelled'].includes(speechActivity.value.phase)) return
  }
  const context = answerContext()
  voiceListeningTimer = setTimeout(() => {
    voiceListeningTimer = null
    if (matchesAnswerContext(context)) void beginVoiceAnswer()
  }, 600)
}
async function toggleVoiceConversation() {
  if (voiceConversation.value) { stopVoiceConversation(); return }
  if (!canAnswer.value || busy.session || busy.restore || recognizing.value || recording.value) return
  if (answer.value.trim()) { notice.value = '请先发送或清空输入框中的回答，再开启语音对话。'; return }
  voiceConversation.value = true
  notice.value = ''
  if (connected.value && soundEnabled.value) {
    const key = `${session.value.id}:${currentQuestion.value}`
    if (lastSpoken.value !== key) await speakQuestion()
    queueVoiceListening()
  } else await beginVoiceAnswer()
}
async function receiveTranscript(event) {
  if (!event || event.id === lastTranscriptId) return
  lastTranscriptId = event.id
  if (!matchesAnswerContext(event.context) || event.context.token !== recordingTurn?.token) return
  recordingTurn = null
  if (event.error) { if (event.autoSubmit) stopVoiceConversation(); return }
  if (!event.text?.trim()) return
  answer.value = [answer.value.trim(), event.text.trim()].filter(Boolean).join('\n')
  if (!event.autoSubmit || !voiceConversation.value) return
  if (answer.value.length > 4000) {
    stopVoiceConversation()
    notice.value = '识别内容超过 4000 字，已保留在输入框，请精简后发送。'
    return
  }
  const submitted = await submitAnswer(false, { fromVoice: true })
  if (!submitted) stopVoiceConversation()
  else queueVoiceListening()
}
async function toggleRecording() {
  notice.value = ''
  if (recording.value) { await media.stopRecording(); return }
  if (!canAnswer.value || busy.session || recognizing.value || voiceConversation.value || recordingTurn) return
  const context = { ...answerContext(), token: requestId() }
  recordingTurn = context
  const interrupted = await media.interrupt()
  if (!interrupted) {
    if (recordingTurn === context) recordingTurn = null
    notice.value = '请先断开数字人再重新连接，确认播报停止后再录音。'
    return
  }
  await new Promise(resolve => setTimeout(resolve, 300))
  if (!matchesAnswerContext(context) || !canAnswer.value || recordingTurn !== context) return
  if (!await media.startRecording({ context, keepSpeech: true }) && recordingTurn === context) recordingTurn = null
}
async function applyRoute() {
  const signature = JSON.stringify([route.query.job || '', route.query.keyword || '', route.query.q || '', route.query.session || ''])
  if (signature === lastRoute) return
  if (busy.session || busy.restore) { notice.value = '当前请求完成后，可点击“新一场面试”选择其他岗位。'; return }
  stopVoiceConversation()
  lastRoute = signature
  const id = valueOfQuery(route.query.session)
  if (id) { await restoreSession(id); return }
  const job = valueOfQuery(route.query.job)
  const group = valueOfQuery(route.query.keyword)
  const q = valueOfQuery(route.query.q)
  if (job || group || q) {
    await newInterview()
    selectedJob.value = job
    keyword.value = group
    categorySearch.value = q
    sourceMode.value = job ? 'job' : 'keyword'
    if (job) loadJobs()
    await loadContext()
  }
}
onActivated(async () => {
  active.value = true
  const first = !initialized.value
  initialized.value = true
  await Promise.allSettled([
    loadModelSettings().catch(error => { notice.value = error.message }),
    loadHistory(), loadGroups(), media.refreshStatus(),
  ])
  if (!active.value) return
  await applyRoute()
  if (first && !session.value && !route.query.job && !route.query.keyword && !route.query.q && !route.query.session) {
    const lastId = storageGet('findboss:interview:last-session')
    if (lastId) await restoreSession(lastId)
  }
  scrollDialogue()
})
onDeactivated(() => { active.value = false; stopVoiceConversation() })
onBeforeUnmount(stopVoiceConversation)
watch(() => [route.query.job, route.query.keyword, route.query.q, route.query.session], () => { if (active.value && route.name === 'interview') applyRoute() })
watch(() => [busy.session, busy.restore, recording.value, recognizing.value], () => {
  if (active.value && route.name === 'interview' && !busy.session && !busy.restore && !recording.value && !recognizing.value) applyRoute()
})
watch(transcript, event => { if (active.value) void receiveTranscript(event) })
watch(connected, value => { if (!value) { lastSpoken.value = ''; speakingQuestion = null } })
watch([currentQuestion, connected, soundEnabled, active, () => busy.restore, () => busy.session], () => {
  const key = session.value ? `${session.value.id}:${currentQuestion.value}` : ''
  if (active.value && connected.value && soundEnabled.value && !busy.restore && !busy.session && !recording.value && !recognizing.value && currentQuestion.value && key !== lastSpoken.value) speakQuestion()
})
watch([speechActivity, playing, preparingSpeech, soundEnabled, connected, () => busy.session, () => busy.restore, recognizing, lastSpoken], () => {
  if (voiceConversation.value && recordingTurn && (playing.value || preparingSpeech.value) && connected.value && soundEnabled.value) {
    recordingTurn = null
    media.cancelRecording()
  }
  queueVoiceListening()
})
watch(() => [session.value?.id, session.value?.version, currentQuestion.value], () => {
  if (recordingTurn && !matchesAnswerContext(recordingTurn)) { recordingTurn = null; media.cancelRecording() }
  if (session.value && (!inProgress.value || (!session.value.awaiting_answer && !busy.session))) stopVoiceConversation()
  else queueVoiceListening()
})
</script>

<template>
  <div class="interview-page">
    <PageHeading>
      <button class="button button-white" :disabled="busy.session || busy.restore" @click="newInterview"><Plus :size="16" />新一场面试</button>
    </PageHeading>

    <div v-if="notice" class="interview-notice" role="status"><CircleHelp :size="18" /><span>{{ notice }}</span><button class="icon-button" aria-label="关闭提示" @click="notice = ''"><X :size="16" /></button></div>

    <div class="interview-grid">
      <aside class="preparation-column">
        <section class="panel preparation-panel" aria-labelledby="preparation-title">
          <header class="section-heading"><div><span class="section-kicker">面试准备</span><h2 id="preparation-title">从真实岗位开始</h2></div><span class="model-state" :class="{ ready: modelStatus.configured }"><i></i>{{ modelStatus.configured ? '模型已配置' : '待配置模型' }}</span></header>
          <section class="model-settings" aria-label="面试模型设置">
            <button type="button" class="model-settings-toggle" :aria-expanded="settingsOpen" aria-controls="interview-model-form" :disabled="busy.settings" @click="settingsOpen = !settingsOpen">
              <Settings2 :size="16" />
              <span><strong>面试模型</strong><small>{{ modelProviderName }} · {{ modelStatus.model || '点击配置' }}</small></span>
              <ChevronRight :size="15" :class="{ expanded: settingsOpen }" />
            </button>
            <form v-if="settingsOpen" id="interview-model-form" @submit.prevent="saveSettings">
              <label>模型服务<select v-model="settingsForm.provider" :disabled="busy.settings" @change="changeProvider"><option v-for="provider in modelProviders" :key="provider.id" :value="provider.id">{{ provider.name }}{{ provider.configured ? ' · 已配置密钥' : '' }}</option></select></label>
              <label>模型名称<input v-model="settingsForm.model" maxlength="100" required :disabled="busy.settings" /></label>
              <label>API Key<span v-if="selectedProviderConfigured && !settingsForm.clear_key" class="saved-key-state"><Check :size="12" />已配置，可直接使用</span><input v-model="settingsForm.api_key" type="password" autocomplete="new-password" maxlength="2048" :disabled="busy.settings || settingsForm.clear_key" :placeholder="selectedProviderConfigured ? '留空保留密钥，输入可替换' : '填写当前服务商的 API Key'" /></label>
              <p class="model-settings-help">密钥按服务商保存在本机，下次无需重复输入。</p>
              <label v-if="selectedProviderConfigured" class="check-label"><input v-model="settingsForm.clear_key" type="checkbox" :disabled="busy.settings" />清除该服务商的密钥</label>
              <button class="button button-primary save-model-button" :disabled="busy.settings"><LoaderCircle v-if="busy.settings" :size="14" class="spin" /><Check v-else :size="14" />{{ busy.settings ? '正在保存…' : '保存并使用' }}</button>
              <p v-if="settingsFeedback" class="settings-feedback" :class="{ failed: settingsFailed }" role="status">{{ settingsFeedback }}</p>
            </form>
          </section>
          <div v-if="session" class="session-source"><strong>{{ session.title }}</strong><p>{{ session.level }} · {{ session.question_count }} 道主问题 · {{ session.job_context?.source_count || 0 }} 份岗位描述</p><span>本场使用生成时的岗位要求。重新选岗请开始新一场。</span><details class="session-requirements"><summary>查看本场岗位要求<ChevronRight :size="13" /></summary><p>{{ session.job_context?.requirements }}</p><ul v-if="session.job_context?.jobs?.length"><li v-for="job in session.job_context.jobs" :key="job.id">{{ job.title }} · {{ job.company || '公司未标注' }}</li></ul></details></div>
          <form v-else @submit.prevent="startInterview">
            <div class="source-tabs" aria-label="岗位要求来源">
              <button type="button" :class="{ active: sourceMode === 'keyword' }" :aria-pressed="sourceMode === 'keyword'" :disabled="busy.context || busy.session || busy.restore" @click="changeSource('keyword')">同类岗位</button>
              <button type="button" :class="{ active: sourceMode === 'job' }" :aria-pressed="sourceMode === 'job'" :disabled="busy.context || busy.session || busy.restore" @click="changeSource('job')">具体职位</button>
              <button type="button" :class="{ active: sourceMode === 'manual' }" :aria-pressed="sourceMode === 'manual'" :disabled="busy.context || busy.session || busy.restore" @click="changeSource('manual')">手动填写</button>
            </div>
            <fieldset :disabled="busy.session || busy.restore">
              <template v-if="sourceMode === 'keyword'">
                <label>采集关键词<select v-model="keyword" :disabled="busy.context" @change="loadContext"><option value="">选择已采集的岗位类别</option><option v-for="item in keywordOptions" :key="item.keyword" :value="item.keyword">{{ item.keyword }}{{ item.total == null ? '' : ` · ${item.total} 个职位` }}</option></select></label>
                <label>岗位方向<input v-model="categorySearch" maxlength="100" placeholder="也可搜索方向，例如 Java 后端" :disabled="busy.context" @keydown.enter.prevent="loadContext" /></label>
                <button type="button" class="source-load" :disabled="busy.context || (!keyword && !categorySearch.trim())" @click="loadContext"><RefreshCw :size="14" :class="{ spin: busy.context }" />{{ busy.context ? '正在整理要求…' : '整理这一类岗位要求' }}</button>
              </template>
              <template v-else-if="sourceMode === 'job'">
                <label>搜索已采集职位<div class="inline-search"><input v-model="jobSearch" maxlength="100" placeholder="职位或公司" @keydown.enter.prevent="loadJobs" /><button type="button" aria-label="搜索职位" :disabled="busy.jobs" @click="loadJobs"><LoaderCircle v-if="busy.jobs" :size="16" class="spin" /><ArrowRight v-else :size="17" /></button></div></label>
                <label>选择具体职位<select v-model="selectedJob" :disabled="busy.context" @change="loadContext"><option value="">选择一份职位</option><option v-if="selectedJob && !jobs.some(item => item.id === selectedJob)" :value="selectedJob">{{ context?.title || '从职位详情带入的岗位' }}</option><option v-for="item in jobs" :key="item.id" :value="item.id">{{ item.title }} · {{ item.company || '公司未标注' }}</option></select></label>
                <button type="button" class="source-load" :disabled="busy.context || !selectedJob" @click="loadContext"><RefreshCw :size="14" :class="{ spin: busy.context }" />{{ busy.context ? '正在读取职位…' : '读取这份职位要求' }}</button>
              </template>
              <p v-else class="field-help">粘贴招聘中的岗位职责、技能要求和经验要求，也可以补充希望重点练习的方向。</p>
              <p v-if="sourceError" class="field-error" role="status">{{ sourceError }}</p>
              <div v-if="context?.source_count" class="context-source"><Check :size="14" /><span>已整理 {{ context.source_count }} 份岗位描述，可在下方调整。</span></div>
              <label>岗位名称<input v-model="form.title" maxlength="120" required placeholder="例如：中级前端开发工程师" :disabled="busy.context" /></label>
              <label>交给 AI 的岗位要求<textarea v-model="form.requirements" rows="5" maxlength="24000" required placeholder="先从已采集职位读取，或粘贴岗位要求。内容越具体，问题越贴近目标岗位。" :disabled="busy.context" /></label>
              <div class="preparation-options"><label>面试级别<select v-model="form.level"><option>初级</option><option>中级</option><option>高级</option></select></label><label>主问题数<select v-model.number="form.question_count"><option v-for="count in 8" :key="count" :value="count + 2">{{ count + 2 }} 题</option></select></label></div>
              <p class="field-help">每题可根据回答追问一次。岗位要求和回答会发送给所选模型。</p>
              <button class="button button-primary start-button" :disabled="busy.context || busy.session || !form.title.trim() || !form.requirements.trim()"><LoaderCircle v-if="loadingAction === 'start'" :size="16" class="spin" /><Play v-else :size="16" />{{ loadingAction === 'start' ? '正在生成面试题…' : '生成题目，开始面试' }}</button>
            </fieldset>
          </form>
          <details v-if="context?.profile || session?.job_context" class="profile-note"><summary>会结合我的求职资料<ChevronRight :size="13" /></summary><p>{{ profileSummary || '使用“求职助手”中已保存的真实经历和技能，未填写的内容不会当作已有能力。' }}</p><RouterLink :to="{ name: 'assistant' }">管理求职资料<ArrowRight :size="12" /></RouterLink></details>
        </section>

        <section class="panel history-panel" aria-labelledby="interview-history-title">
          <header><h2 id="interview-history-title"><History :size="17" />我的面试记录</h2><button class="icon-button" aria-label="刷新面试记录" :disabled="busy.history" @click="loadHistory"><RefreshCw :size="15" :class="{ spin: busy.history }" /></button></header>
          <p v-if="historyError" class="field-error">{{ historyError }}</p>
          <p v-else-if="!history.length" class="history-empty">{{ busy.history ? '正在读取记录…' : '完成第一场练习后，在这里继续对话或查看反馈。' }}</p>
          <button v-for="item in history.slice(0, 12)" :key="item.id" class="history-row" :class="{ selected: session?.id === item.id }" :disabled="busy.session || busy.restore" @click="restoreSession(item.id)"><span><strong>{{ item.title }}</strong><small>{{ dateLabel(item.updated_at || item.created_at) }} · {{ item.answered_count || 0 }}/{{ item.question_count }} 题</small></span><em :class="{ done: item.status === 'completed' }">{{ item.status === 'completed' ? '已完成' : '继续' }}</em></button>
        </section>
      </aside>

      <section class="interview-room" aria-label="面试练习区">
        <aside class="presenter-column" aria-label="数字人及语音设置">
        <section class="panel stage-panel" aria-label="数字人面试官">
          <header class="presenter-heading"><span>数字人面试官</span><strong>{{ selectedAvatar.name }}<small>{{ selectedAvatar.description }}</small></strong></header>
          <div class="stage-media" :class="{ live: connected }">
            <img v-show="!connected" :src="selectedAvatar.image" :alt="`${selectedAvatar.name}，${selectedAvatar.description}面试官`" />
            <video ref="videoRef" v-show="connected" autoplay playsinline aria-label="数字人面试官画面"></video>
            <div class="stage-media-label"><span class="live-indicator" :class="{ online: connected }"></span><span>{{ roleLabel }}</span></div>
            <div v-if="connecting" class="stage-loading"><LoaderCircle :size="25" class="spin" /><span>正在准备面试官<br /><small>首次加载模型需要一些时间</small></span></div>
          </div>
          <div class="presenter-controls">
            <div class="stage-actions">
              <button v-if="!connected" class="button button-primary connect-button" :disabled="connecting" @click="media.connect({ avatar_id: avatarId, voice_id: voiceId })"><LoaderCircle v-if="connecting" :size="15" class="spin" /><Play v-else :size="15" />{{ connecting ? '正在连接…' : '连接数字人' }}</button>
              <template v-else><button v-if="!soundEnabled" class="stage-action" @click="media.enableSound"><Volume2 :size="16" />{{ currentQuestion ? '开启声音并提问' : '开启声音' }}</button><button v-if="currentQuestion" class="stage-action" :disabled="busy.session || busy.restore || recording || recognizing || !soundEnabled" @click="speakQuestion"><Play :size="15" />重播问题</button><button class="stage-action disconnect-action" @click="media.disconnect"><X :size="15" />断开</button></template>
              <button v-if="!connected && mediaError?.includes('声音')" class="stage-action" @click="media.enableSound"><Volume2 :size="16" />开启声音</button>
            </div>
            <div class="avatar-options" aria-label="选择数字人面试官"><button v-for="item in avatars" :key="item.id" :class="{ selected: avatarId === item.id }" :disabled="connected || connecting" :aria-pressed="avatarId === item.id" @click="avatarId = item.id"><img :src="item.image" alt="" /><span>{{ item.name }}<small>{{ item.description }}</small></span><Check v-if="avatarId === item.id" :size="13" /></button></div>
            <div class="voice-controls"><label for="interview-voice">面试官音色</label><select id="interview-voice" v-model="voiceId" :disabled="connected || connecting"><option v-for="item in voices" :key="item.id" :value="item.id">{{ item.name }}</option></select><button class="icon-button" aria-label="试听当前音色" :disabled="connected || connecting || recording || recognizing" @click="media.playVoicePreview(voiceId)"><Volume2 :size="17" /></button></div>
          </div>
        </section>
        <p v-if="mediaError" class="media-notice" role="status"><CircleHelp :size="16" /><span>{{ mediaError }}</span><button @click="media.refreshStatus">刷新状态</button></p>
        <p v-else-if="speechNote" class="media-caption" role="status">{{ speechNote }}</p>
        <p v-else-if="mediaStatus.note && !connected && !connecting" class="media-caption">{{ mediaStatus.note }}</p>

        </aside>

        <div ref="conversation" class="conversation-column" :class="{ 'active-conversation': session && !report && !busy.restore }">
          <section v-if="!session || busy.restore || report" class="panel stage-content" aria-labelledby="interview-stage-title">
            <div class="stage-overline"><span>岗位面试 · {{ selectedAvatar.name }}</span><span v-if="session">{{ session.status === 'completed' ? '面试结束' : `${questionNumber} / ${session.question_count}` }}</span><span v-else>准备就绪后开始</span></div>
            <template v-if="busy.restore"><h2 id="interview-stage-title">正在恢复面试记录</h2><p class="stage-description">问题、回答和反馈会一起恢复。</p></template>
            <template v-else-if="report"><h2 id="interview-stage-title">这一场，练得怎么样？</h2><p class="stage-description">往下查看逐题反馈和下一步练习建议，也可以开始新一场面试。</p></template>
            <template v-else><h2 id="interview-stage-title">把下一场面试，<br />先在这里练一遍。</h2><p class="stage-description">选一类岗位或带入具体职位，让 AI 围绕真实要求提问。你可以打字，也可以录音回答。</p></template>
            <p v-if="!session" class="stage-text-mode">在左侧准备岗位，即可开始文字或语音面试。</p>
          </section>

        <section v-if="session" class="panel dialogue-panel" aria-labelledby="dialogue-title">
          <header class="dialogue-heading"><div><h2 id="dialogue-title">本场对话</h2><span>{{ session.title }} · {{ session.answered_count || 0 }} / {{ session.question_count }} 道主问题已回答</span></div><div class="dialogue-tools"><button v-if="connected && playing" @click="media.interrupt"><Pause :size="14" />打断播报</button><span v-if="session.status === 'completed'" class="completed-label"><Check :size="14" />已完成</span><button v-else :disabled="busy.session || busy.restore || !hasAnswers" @click="finishInterview">{{ loadingAction === 'finish' ? '正在生成反馈…' : canAnswer ? '结束并生成反馈' : '生成面试反馈' }}<ArrowRight :size="14" /></button></div></header>
          <div class="interview-progress" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100" aria-label="主问题完成进度"><span :style="{ width: `${progress}%` }"></span></div>
          <div v-if="mediaError || speechNote || (connected && currentQuestion)" class="dialogue-speech-status" role="status"><span v-if="mediaError || speechNote"><CircleHelp :size="16" />{{ mediaError || speechNote }}</span><span v-else>{{ preparingSpeech ? '正在准备朗读…' : playing ? '面试官正在朗读问题' : '面试官会自动朗读当前问题' }}</span><button v-if="connected && currentQuestion" type="button" :disabled="busy.session || busy.restore || recording || recognizing || preparingSpeech" @click="replayQuestion"><Volume2 :size="16" />{{ soundEnabled ? '朗读问题' : '开启声音并朗读' }}</button></div>
          <div ref="dialogue" class="dialogue-messages" aria-live="polite" aria-relevant="additions">
            <article v-for="(message, index) in session.messages" :key="message.id || index" class="dialogue-message" :class="[message.role, { feedback: message.kind === 'feedback' }]"><span class="speaker-avatar"><img v-if="message.role === 'interviewer'" :src="selectedAvatar.image" alt="" /><span v-else>我</span></span><div class="message-body"><header><strong>{{ message.role === 'candidate' ? '我的回答' : message.kind === 'feedback' ? '本题反馈' : message.kind === 'follow_up' ? `${selectedAvatar.name} · 追问` : `${selectedAvatar.name} · 面试官` }}</strong></header><p>{{ message.content }}</p></div></article>
            <div v-if="loadingAction === 'answer'" class="thinking-row" role="status"><LoaderCircle :size="16" class="spin" />面试官正在阅读你的回答…</div>
          </div>
          <div v-if="pendingAnswer" class="retry-answer" role="status"><div><strong>回答已保存，面试官暂未完成回复</strong><p>{{ session.last_error || '可以重试处理本次回答，已有内容不会重复提交。' }}</p></div><button class="button button-white" :disabled="busy.session || busy.restore" @click="submitAnswer(true)"><RefreshCw :size="14" :class="{ spin: busy.session }" />重试本次回答</button></div>
          <form v-else-if="canAnswer" class="answer-composer" @submit.prevent="submitAnswer()">
            <div class="voice-conversation"><button type="button" class="button" :class="voiceConversation ? 'button-primary' : 'button-white'" :aria-pressed="voiceConversation" :disabled="!voiceConversation && (busy.session || recognizing || recording)" @click="toggleVoiceConversation"><Mic :size="16" />{{ voiceConversation ? '关闭语音对话' : '开启语音对话' }}</button><span role="status">{{ voiceConversation ? recording ? '正在听你说话，停顿后自动发送' : recognizing ? '正在转成文字…' : busy.session ? '面试官正在思考…' : '等面试官说完，就可以直接回答' : '开启后可连续对话，回答会自动转文字并发送' }}</span></div>
            <label for="interview-answer">你的回答<span>{{ recording ? voiceConversation ? '说完后停顿片刻即可发送' : '结束录音后可编辑文字' : recognizing ? '正在识别录音…' : '也可以直接输入文字回答' }}</span></label>
            <textarea id="interview-answer" v-model="answer" rows="3" maxlength="4000" :disabled="busy.session || recording || recognizing" placeholder="可以先说结论，再讲项目背景、处理过程和最终结果。只描述自己真实参与的经历。"></textarea>
            <p v-if="answer.length > 4000" class="field-error">识别内容超过 4000 字，请保留重点后提交。</p>
            <div class="answer-actions"><button type="button" class="record-button" :class="{ recording }" :disabled="busy.session || recognizing || (voiceConversation && !recording)" @click="toggleRecording"><Square v-if="recording" :size="13" /><LoaderCircle v-else-if="recognizing" :size="16" class="spin" /><Mic v-else :size="16" />{{ recording ? voiceConversation ? '说完了，立即发送' : '结束录音并识别' : recognizing ? '正在识别…' : '录音转文字' }}</button><span class="answer-length">{{ answer.length }} / 4000</span><button class="button button-primary" :disabled="busy.session || recording || recognizing || !answer.trim() || answer.length > 4000"><LoaderCircle v-if="busy.session" :size="15" class="spin" /><Send v-else :size="15" />{{ busy.session ? '正在提交…' : '提交回答' }}</button></div>
            <p v-if="!mediaStatus.asr_installed" class="field-help">本地语音模型尚未就绪时，仍可直接输入文字回答。</p>
          </form>
          <div v-else-if="!report && !busy.restore" class="dialogue-complete"><Check :size="20" /><div><strong>本场问答已记录</strong><p>现在生成面试反馈，梳理回答中有依据的优势和需要继续准备的内容。</p></div><button class="button button-primary" :disabled="busy.session || !hasAnswers" @click="finishInterview"><LoaderCircle v-if="busy.session" :size="15" class="spin" />{{ busy.session ? '正在生成…' : '生成面试反馈' }}</button></div>
        </section>

        <section v-if="report" class="panel report-panel" aria-labelledby="interview-report-title">
          <header class="report-heading"><div><span class="section-kicker">本场练习反馈</span><h2 id="interview-report-title">让下一次回答更有底气</h2><p>AI 评分仅用于练习参考，不代表真实录用结果。</p></div><div class="overall-score"><strong>{{ score(report.overall_score) }}</strong><span>/ 100</span></div></header>
          <p class="report-summary">{{ report.summary }}</p>
          <div v-if="report.dimensions?.length" class="dimension-grid"><div v-for="(item, index) in report.dimensions" :key="`${item.name}-${index}`" class="dimension"><div><strong>{{ item.name }}</strong><span>{{ score(item.score) }}</span></div><div class="dimension-track"><span :style="{ width: `${score(item.score)}%` }"></span></div><p>{{ item.comment }}</p></div></div>
          <div class="report-columns"><section><h3><Check :size="17" />这次做得好的地方</h3><ul><li v-for="(item, index) in report.strengths || []" :key="index">{{ item }}</li></ul><p v-if="!report.strengths?.length" class="field-help">回答信息还不足以总结优势，可以补充更具体的经历。</p></section><section><h3><ArrowRight :size="17" />下次可以补充</h3><ul><li v-for="(item, index) in report.improvements || []" :key="index">{{ item }}</li></ul></section></div>
          <section v-if="report.suggested_answers?.length" class="suggested-answers"><h3>逐题复盘与参考回答</h3><details v-for="(item, index) in report.suggested_answers" :key="index"><summary><span>{{ index + 1 }}.</span><strong>{{ item.question }}</strong><ChevronRight :size="16" /></summary><div><h4>回答反馈</h4><p>{{ item.feedback }}</p><h4>参考回答思路</h4><p>{{ item.answer }}</p><small>请用自己的真实经历补全细节，参考思路不等于个人经历。</small></div></details></section>
          <section v-if="report.next_steps?.length" class="next-steps"><h3>接下来，重点练习</h3><ol><li v-for="(item, index) in report.next_steps" :key="index">{{ item }}</li></ol></section>
        </section>

        <section v-if="!session && !busy.restore" class="practice-guide" aria-label="面试流程"><div><span>准备岗位</span><p>整理真实招聘要求<br />补充自己的求职资料</p></div><ChevronRight :size="18" /><div><span>逐题对答</span><p>从回答中继续追问<br />用项目经历解释思路</p></div><ChevronRight :size="18" /><div><span>复盘改进</span><p>回看逐题反馈<br />找到下一次的练习重点</p></div></section>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.voice-conversation { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 14px; margin-bottom: 18px; }.voice-conversation .button { min-height: 38px; padding: 0 12px; font-size: 12px; }.voice-conversation > span { color: var(--muted); font-size: 11px; line-height: 1.8; }
.interview-page { --interview-blue: #0066cc; --interview-tint: #eaf3fc; --interview-ink: #26374e; min-width: 0; }
.interview-grid { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 20px; align-items: start; }
.preparation-column, .conversation-column { display: grid; gap: 20px; min-width: 0; }
.interview-room { display: grid; grid-template-columns: minmax(240px, 36%) minmax(0, 1fr); gap: 20px; min-width: 0; align-items: start; }
.presenter-column { position: sticky; top: 88px; display: grid; gap: 16px; min-width: 0; align-self: start; }
.interview-room > .report-panel, .interview-room > .practice-guide { grid-column: 1 / -1; }
.preparation-panel, .history-panel { padding: 16px; }
.preparation-panel { background: #fbfcfd; }
.preparation-panel .section-heading h2 { font-size: 17px; }
.preparation-panel .field-help { font-size: 11px; }
.section-heading { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.section-kicker { display: block; color: var(--muted); font-size: 12px; margin-bottom: 8px; }
.section-heading h2, .report-heading h2 { font-size: 20px; line-height: 1.4; letter-spacing: -.3px; }
.model-state { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); white-space: nowrap; }
.model-state i { width: 5px; height: 5px; border-radius: 50%; background: #9b9ba1; }
.model-state.ready { color: var(--green); }.model-state.ready i { background: var(--green); }
.source-tabs { display: grid; grid-template-columns: repeat(3, 1fr); padding: 3px; background: var(--canvas); border-radius: 9px; margin-bottom: 20px; }
.source-tabs button { min-height: 36px; padding: 7px 2px; font-size: 12px; border-radius: 6px; color: var(--muted); }
.source-tabs button.active { background: var(--surface); color: var(--ink); box-shadow: 0 1px 4px rgb(0 0 0 / 8%); }
fieldset { display: grid; gap: 16px; border: 0; margin: 0; padding: 0; min-width: 0; }
label { display: grid; gap: 8px; font-size: 12px; line-height: 1.5; color: #515154; }
textarea { resize: vertical; line-height: 1.8; }
.preparation-panel input, .preparation-panel select, .preparation-panel textarea { min-width: 0; padding: 9px 10px; font-size: 12px; }
.source-load { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 38px; border: 1px solid #cce0f5; border-radius: 9px; color: var(--accent); font-size: 12px; background: #f6faff; }
.source-load:hover:not(:disabled) { background: var(--interview-tint); }
.inline-search { display: flex; align-items: center; gap: 8px; }.inline-search input { flex: 1; }.inline-search button { min-height: 40px; width: 34px; display: grid; place-items: center; color: var(--accent); }
.field-help { color: var(--muted); font-size: 12px; line-height: 1.8; }
.field-error { color: #a0442e; font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; }
.context-source { display: flex; align-items: flex-start; gap: 6px; color: var(--green); font-size: 11px; line-height: 1.6; }.context-source svg { margin-top: 2px; flex-shrink: 0; }
.preparation-options { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.start-button { width: 100%; justify-content: center; min-height: 45px; font-size: 13px; }
.profile-note { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line); font-size: 12px; }.profile-note summary { list-style: none; display: flex; align-items: center; justify-content: space-between; min-height: 30px; cursor: pointer; }.profile-note[open] summary svg { transform: rotate(90deg); }.profile-note p { margin-top: 8px; line-height: 1.8; color: var(--muted); }.profile-note a { display: inline-flex; align-items: center; gap: 6px; color: var(--accent); margin-top: 8px; min-height: 28px; }
.session-source { display: grid; gap: 8px; padding: 14px; background: var(--canvas); border-radius: 10px; }.session-source strong { font-size: 15px; line-height: 1.6; overflow-wrap: anywhere; }.session-source p, .session-source span { font-size: 11px; color: var(--muted); line-height: 1.8; }
.session-requirements { border-top: 1px solid var(--line); padding-top: 8px; }.session-requirements summary { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 11px; min-height: 32px; cursor: pointer; list-style: none; }.session-requirements[open] summary svg { transform: rotate(90deg); }.session-requirements p { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 320px; overflow-y: auto; font-size: 11px; }.session-requirements ul { margin: 12px 0 0; padding-left: 15px; color: var(--muted); font-size: 10px; line-height: 1.9; }
.history-panel header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 12px; }.history-panel h2 { display: flex; align-items: center; gap: 8px; font-size: 14px; }.history-empty { font-size: 12px; line-height: 1.8; color: var(--muted); }
.history-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; width: calc(100% + 16px); min-height: 66px; margin-left: -8px; padding: 10px 8px; border-radius: 8px; text-align: left; }.history-row:hover, .history-row.selected { background: var(--canvas); }.history-row > span { display: grid; gap: 6px; min-width: 0; }.history-row strong { color: var(--ink); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }.history-row small { color: var(--muted); font-size: 10px; }.history-row em { color: var(--accent); font-size: 10px; font-style: normal; white-space: nowrap; }.history-row em.done { color: var(--green); }
.stage-panel { display: grid; grid-template-columns: minmax(0, 1fr); overflow: hidden; min-width: 0; }
.presenter-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 16px; }
.presenter-heading > span { color: var(--muted); font-size: 11px; }
.presenter-heading strong { display: flex; align-items: center; gap: 9px; color: var(--interview-ink); font-size: 16px; font-weight: 600; }
.presenter-heading small { color: var(--muted); font-size: 10px; font-weight: 400; }
.stage-media { aspect-ratio: 4 / 5; min-height: 0; background: #dce3e8; position: relative; overflow: hidden; }.stage-media > img, .stage-media > video { position: absolute; width: 100%; height: 100%; object-fit: cover; object-position: center 31%; }.stage-media > video { object-fit: contain; object-position: center; background: #151c25; }.stage-media-label { position: absolute; left: 12px; right: 12px; bottom: 12px; display: flex; align-items: center; gap: 7px; padding: 9px 11px; border: 1px solid rgb(255 255 255 / 35%); background: rgb(22 31 43 / 70%); backdrop-filter: blur(14px); color: #fff; font-size: 11px; border-radius: 8px; }.live-indicator { width: 6px; height: 6px; background: #d4dce5; border-radius: 50%; }.live-indicator.online { background: #68d29b; }
.stage-loading { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 14px; background: rgb(21 28 37 / 75%); color: #fff; text-align: center; font-size: 13px; line-height: 1.8; }.stage-loading small { font-size: 10px; color: #d3dce5; }
.stage-content { display: flex; flex-direction: column; padding: 25px; min-width: 0; min-height: 285px; }.stage-overline { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; color: var(--muted); font-size: 10px; line-height: 1.6; margin-bottom: 25px; }.stage-content h2 { font-size: 25px; letter-spacing: -.5px; color: var(--interview-ink); line-height: 1.5; font-weight: 600; }.stage-content h2.current-question { font-size: 20px; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }.stage-description { color: var(--muted); font-size: 12px; line-height: 1.9; margin-top: 14px; }.question-topic { align-self: flex-start; color: var(--accent); background: var(--interview-tint); padding: 4px 8px; font-size: 10px; border-radius: 5px; margin-bottom: 12px; }
.stage-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; min-height: 38px; }.stage-actions .button { min-height: 38px; font-size: 12px; padding: 0 12px; }.connect-button { width: 100%; justify-content: center; }.stage-text-mode { margin-top: 22px; font-size: 11px; line-height: 1.8; color: var(--muted); }.stage-action { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; color: var(--accent); font-size: 11px; padding: 0; }.disconnect-action { margin-left: auto; color: var(--muted); }
.presenter-controls { display: grid; gap: 12px; padding: 12px; min-width: 0; border-top: 1px solid var(--line); }.avatar-options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; min-width: 0; }.avatar-options button { position: relative; display: flex; width: 100%; min-width: 0; text-align: left; align-items: center; gap: 5px; border: 1px solid var(--line); border-radius: 8px; padding: 7px 5px; min-height: 48px; color: var(--muted); }.avatar-options button.selected { background: var(--interview-tint); border-color: #cce0f5; color: var(--accent); }.avatar-options button > img { width: 25px; height: 34px; object-fit: cover; object-position: center 25%; border-radius: 5px; }.avatar-options button > span { display: grid; text-align: left; gap: 3px; font-size: 11px; }.avatar-options button > svg { position: absolute; top: 3px; right: 3px; width: 10px; height: 10px; }.avatar-options small { color: var(--muted); font-size: 9px; }.voice-controls { display: grid; grid-template-columns: minmax(0, 1fr) 30px; align-items: center; gap: 6px 8px; min-width: 0; }.voice-controls label { grid-column: 1 / -1; font-size: 10px; }.voice-controls select { width: 100%; min-width: 0; min-height: 34px; padding: 7px 28px 7px 9px; font-size: 11px; }.voice-controls .icon-button { width: 30px; min-height: 34px; }
.media-notice { display: flex; align-items: flex-start; gap: 9px; padding: 12px 16px; background: #fff8ec; border: 1px solid #ead9b5; border-radius: 10px; color: #82590e; font-size: 12px; line-height: 1.8; margin-top: -8px; }.media-notice svg { flex-shrink: 0; margin-top: 2px; }.media-notice span { flex: 1; overflow-wrap: anywhere; }.media-notice button { color: var(--accent); flex-shrink: 0; font-size: 11px; min-height: 25px; }.media-caption { font-size: 11px; color: var(--muted); line-height: 1.8; padding: 0 3px; margin-top: -8px; }
.dialogue-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 14px; padding: 21px 24px 18px; }.dialogue-heading > div:first-child { display: grid; gap: 6px; }.dialogue-heading h2 { font-size: 16px; }.dialogue-heading > div:first-child > span { color: var(--muted); font-size: 10px; }.dialogue-tools { display: flex; align-items: center; flex-wrap: wrap; gap: 14px; }.dialogue-tools button, .completed-label { display: inline-flex; align-items: center; gap: 5px; min-height: 32px; padding: 0; font-size: 11px; color: var(--accent); }.completed-label { color: var(--green); }.interview-progress { height: 3px; background: var(--canvas); }.interview-progress > span { display: block; height: 100%; background: var(--accent); transition: width .25s ease; }
.dialogue-messages { display: grid; gap: 24px; max-height: 470px; overflow-y: auto; overscroll-behavior: contain; padding: 26px 24px; }.dialogue-message { display: flex; gap: 11px; align-items: flex-start; min-width: 0; }.speaker-avatar { display: grid; place-items: center; flex-shrink: 0; overflow: hidden; width: 31px; height: 35px; border-radius: 8px; background: var(--canvas); color: var(--muted); font-size: 12px; }.speaker-avatar img { width: 100%; height: 100%; object-fit: cover; object-position: center 25%; }.message-body { min-width: 0; flex: 1; }.message-body header { font-size: 10px; color: var(--muted); margin: 1px 0 8px; }.message-body header strong { font-weight: 500; }.message-body p { font-size: 13px; line-height: 1.9; white-space: pre-wrap; overflow-wrap: anywhere; }.candidate .message-body { padding: 14px 16px; background: var(--canvas); border-radius: 0 12px 12px; }.candidate .speaker-avatar { color: var(--accent); background: var(--interview-tint); }.feedback .message-body p { color: var(--muted); font-size: 12px; }.thinking-row { display: flex; align-items: center; gap: 9px; color: var(--accent); font-size: 12px; padding-left: 42px; }
.answer-composer { padding: 20px 24px 24px; border-top: 1px solid var(--line); background: #fcfcfd; border-radius: 0 0 18px 18px; }.answer-composer > label { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; margin-bottom: 10px; }.answer-composer > label span { font-size: 10px; color: var(--muted); }.answer-composer textarea { min-height: 125px; font-size: 13px; padding: 14px; }.answer-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 12px; }.record-button { display: inline-flex; align-items: center; gap: 7px; min-height: 40px; padding: 0; color: var(--accent); font-size: 12px; }.record-button.recording { color: #ae332e; }.answer-length { margin-left: auto; color: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }.answer-actions .button { min-height: 40px; padding: 0 14px; font-size: 12px; }.answer-composer > .field-help { margin-top: 10px; font-size: 10px; }
.retry-answer, .dialogue-complete { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; padding: 22px 24px; border-top: 1px solid var(--line); background: #fcfcfd; border-radius: 0 0 18px 18px; }.retry-answer > div, .dialogue-complete > div { flex: 1; min-width: 160px; }.retry-answer strong, .dialogue-complete strong { font-size: 13px; font-weight: 600; }.retry-answer p, .dialogue-complete p { font-size: 11px; color: var(--muted); line-height: 1.9; margin-top: 6px; }.retry-answer .button, .dialogue-complete .button { min-height: 40px; font-size: 12px; }.dialogue-complete > svg { color: var(--green); }
.report-panel { padding: 28px; }.report-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; }.report-heading p { font-size: 10px; line-height: 1.8; color: var(--muted); margin-top: 10px; }.overall-score { display: flex; align-items: baseline; gap: 5px; flex-shrink: 0; color: var(--accent); font-variant-numeric: tabular-nums; }.overall-score strong { font-size: 46px; font-weight: 600; letter-spacing: -2px; }.overall-score span { font-size: 12px; color: var(--muted); }.report-summary { font-size: 13px; line-height: 1.9; color: #515154; margin-top: 24px; white-space: pre-wrap; overflow-wrap: anywhere; }
.dimension-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px 26px; margin-top: 28px; padding: 24px; background: var(--canvas); border-radius: 12px; }.dimension > div:first-child { display: flex; align-items: center; justify-content: space-between; gap: 12px; font-size: 12px; }.dimension strong { font-weight: 500; }.dimension > div:first-child > span { color: var(--accent); font-variant-numeric: tabular-nums; }.dimension-track { height: 4px; border-radius: 4px; background: #dfe5ec; overflow: hidden; margin-top: 11px; }.dimension-track > span { display: block; height: 100%; background: #458acf; border-radius: inherit; }.dimension p { margin-top: 9px; color: var(--muted); font-size: 10px; line-height: 1.8; }
.report-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 26px; margin-top: 30px; }.report-panel h3 { display: flex; align-items: center; gap: 8px; font-size: 14px; line-height: 1.6; }.report-columns section:first-child h3 svg { color: var(--green); }.report-columns section:last-child h3 svg { color: var(--accent); }.report-panel ul, .report-panel ol { margin: 14px 0 0; padding-left: 17px; display: grid; gap: 10px; color: #515154; font-size: 12px; line-height: 1.9; }.report-panel li { padding-left: 3px; overflow-wrap: anywhere; }.report-panel .report-columns .field-help { margin-top: 12px; }
.suggested-answers { margin-top: 30px; }.suggested-answers > h3 { margin-bottom: 16px; }.suggested-answers details { border-top: 1px solid var(--line); }.suggested-answers summary { list-style: none; display: flex; align-items: flex-start; gap: 12px; padding: 18px 0; min-height: 55px; cursor: pointer; font-size: 12px; line-height: 1.8; }.suggested-answers summary > span { color: var(--muted); flex-shrink: 0; }.suggested-answers summary strong { font-weight: 500; flex: 1; overflow-wrap: anywhere; }.suggested-answers summary svg { margin-top: 3px; flex-shrink: 0; }.suggested-answers details[open] summary svg { transform: rotate(90deg); }.suggested-answers details > div { padding: 0 0 20px 24px; }.suggested-answers h4 { font-size: 11px; color: var(--accent); font-weight: 500; margin: 8px 0; }.suggested-answers p { font-size: 12px; color: #515154; line-height: 2; white-space: pre-wrap; overflow-wrap: anywhere; }.suggested-answers small { display: block; color: var(--muted); font-size: 10px; line-height: 1.8; margin-top: 12px; }.next-steps { margin-top: 20px; border-top: 1px solid var(--line); padding-top: 24px; }
.practice-guide { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 18px 8px; }.practice-guide > div { min-width: 0; }.practice-guide span { font-size: 13px; font-weight: 600; }.practice-guide p { margin-top: 9px; color: var(--muted); font-size: 11px; line-height: 1.9; }.practice-guide > svg { color: #b5bdc8; flex-shrink: 0; }
.interview-notice { display: flex; align-items: center; gap: 12px; padding: 12px 16px; background: #edf5fd; border: 1px solid #cce0f5; border-radius: 11px; color: #225285; font-size: 13px; line-height: 1.8; margin-bottom: 20px; }.interview-notice > svg { flex-shrink: 0; }.interview-notice > span { flex: 1; overflow-wrap: anywhere; }.interview-notice .icon-button { width: 28px; min-height: 32px; }
.model-settings { padding-bottom: 16px; margin-bottom: 18px; border-bottom: 1px solid var(--line); }
.model-settings-toggle { display: flex; align-items: center; gap: 9px; width: 100%; min-width: 0; padding: 0; text-align: left; }
.model-settings-toggle > svg { flex-shrink: 0; color: var(--muted); }
.model-settings-toggle > span { display: grid; flex: 1; min-width: 0; gap: 5px; }
.model-settings-toggle strong { color: var(--interview-ink); font-size: 12px; font-weight: 500; }
.model-settings-toggle small { overflow: hidden; color: var(--muted); font-size: 10px; line-height: 1.6; text-overflow: ellipsis; white-space: nowrap; }
.model-settings-toggle .expanded { transform: rotate(90deg); }
.model-settings form { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; margin-top: 16px; }
.model-settings label { gap: 6px; font-size: 11px; }
.saved-key-state { display: inline-flex; align-items: center; gap: 4px; color: var(--green); font-size: 10px; }
.model-settings-help { color: var(--muted); font-size: 10px; line-height: 1.8; }
.model-settings .check-label { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 10px; }
.preparation-panel .check-label input { width: 14px; height: 14px; min-height: 0; padding: 0; }
.save-model-button { width: 100%; min-height: 36px; justify-content: center; font-size: 12px; }
.settings-feedback { color: var(--green); font-size: 11px; line-height: 1.8; overflow-wrap: anywhere; }
.settings-feedback.failed { color: #a0442e; }
@media (max-width: 960px) {
  .interview-grid { grid-template-columns: minmax(0, 1fr); gap: 20px; }.preparation-column { grid-template-columns: minmax(0, 1fr) minmax(220px, .7fr); align-items: start; }.interview-room { grid-template-columns: minmax(220px, 36%) minmax(0, 1fr); }.stage-content { padding: 20px; }.stage-content h2 { font-size: 22px; }.stage-content h2.current-question { font-size: 18px; }.avatar-options { gap: 3px; }
}
@media (max-width: 900px) {
  .interview-grid { grid-template-columns: 1fr; }.preparation-column { grid-template-columns: minmax(0, 1fr) minmax(220px, .7fr); align-items: start; }.interview-room { grid-template-columns: minmax(200px, 34%) minmax(0, 1fr); gap: 16px; }.stage-content { padding: 24px; }.stage-content h2 { font-size: 27px; }.stage-content h2.current-question { font-size: 21px; }
}
@media (max-width: 600px) {
  .preparation-column { grid-template-columns: 1fr; }.history-panel { order: 2; }.history-panel .history-row:nth-of-type(n + 5) { display: none; }.interview-room { grid-template-columns: minmax(100px, 30%) minmax(0, 1fr); gap: 10px; }.presenter-column { top: 116px; gap: 10px; }.conversation-column { gap: 12px; }.stage-content { padding: 18px 16px; }.stage-overline { margin-bottom: 17px; font-size: 9px; }.stage-content h2 { font-size: 20px; }.stage-content h2.current-question { font-size: 16px; line-height: 1.8; }.stage-description { font-size: 11px; margin-top: 11px; }.stage-media-label { left: 7px; right: 7px; bottom: 7px; gap: 5px; padding: 7px; font-size: 9px; }.stage-actions { gap: 8px 12px; padding-top: 15px; }.stage-text-mode { font-size: 9px; }.stage-action { font-size: 10px; }.presenter-controls { padding: 8px; gap: 12px; }.avatar-options { gap: 4px; }.avatar-options button { padding: 5px 3px; gap: 5px; }.avatar-options button > img { width: 22px; height: 28px; }.avatar-options button > span { font-size: 10px; }.avatar-options button > svg { display: none; }.voice-controls { grid-template-columns: minmax(0, 1fr); gap: 6px; }.voice-controls select { max-width: 100%; padding: 7px 18px 7px 5px; font-size: 10px; }.voice-controls .icon-button { width: 100%; min-height: 30px; border: 1px solid var(--line); border-radius: 6px; }.stage-media-label { flex-wrap: wrap; padding: 5px; font-size: 8px; }.stage-content { padding: 16px 12px; min-height: 235px; }.dialogue-heading, .answer-composer { padding: 14px 12px; }.dialogue-messages { padding: 18px 12px; }.dialogue-message { gap: 7px; }.speaker-avatar { width: 24px; height: 29px; }.candidate .message-body { padding: 10px; }.dialogue-heading { padding: 14px 12px; gap: 10px; }.dialogue-messages { padding: 18px 12px; gap: 22px; max-height: 420px; }.message-body p { font-size: 12px; }.answer-composer { padding: 14px 12px; }.answer-length { display: none; }.answer-actions .button { margin-left: auto; }.retry-answer, .dialogue-complete { padding: 18px 12px; }.retry-answer > div, .dialogue-complete > div { min-width: 0; }.presenter-column .media-notice { flex-wrap: wrap; padding: 10px 8px; gap: 6px; }.presenter-column .media-notice > span { flex: 1 1 calc(100% - 22px); min-width: 0; }.presenter-column .media-notice > button { flex-basis: 100%; text-align: left; }.report-panel { padding: 22px 18px; }.report-heading h2 { font-size: 18px; }.overall-score strong { font-size: 36px; }.dimension-grid { padding: 18px; gap: 20px; }.report-columns { grid-template-columns: 1fr; gap: 24px; }.report-summary { font-size: 12px; }.practice-guide { gap: 8px; padding: 14px 0; }.practice-guide span { font-size: 11px; }.practice-guide p { font-size: 10px; }.practice-guide > svg { width: 13px; }.model-settings { padding: 20px 18px; }.model-settings form { gap: 14px; }.interview-notice { font-size: 12px; }
}

/* The workspace supplies the viewport height; only the content panes scroll. */
.interview-page { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.interview-page :deep(.page-heading) { flex-shrink: 0; margin-bottom: 16px; }
.interview-notice { flex: 0 0 auto; max-height: 18%; overflow-y: auto; margin-bottom: 12px; }
.interview-grid { flex: 1; min-height: 0; grid-template-rows: minmax(0, 1fr); align-items: stretch; overflow: hidden; }
.interview-room { height: 100%; min-height: 0; grid-template-rows: minmax(0, 1fr); align-items: stretch; overflow: hidden; }
.preparation-column, .presenter-column, .conversation-column { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow-x: hidden; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; scrollbar-width: thin; scrollbar-color: #b5bdc8 transparent; }
.preparation-column > *, .presenter-column > *, .conversation-column > * { flex-shrink: 0; }
.presenter-column { position: static; align-self: stretch; }
.stage-content { min-height: 0; }
.stage-media { max-height: max(260px, calc(100dvh - 410px)); }
.dialogue-messages { max-height: none; overflow: visible; }
.answer-composer textarea { min-height: 82px; max-height: 160px; }
.active-conversation { overflow: hidden; }
.active-conversation .dialogue-panel { display: flex; flex: 1; flex-direction: column; min-height: 0; overflow: hidden; border-color: #d5dfeb; }
.active-conversation .dialogue-panel > * { flex-shrink: 0; }
.active-conversation .dialogue-messages { flex: 1 1 0; min-height: 80px; align-content: start; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; scrollbar-color: #b5bdc8 transparent; }
.dialogue-heading h2 { color: var(--interview-ink); font-size: 19px; }
.dialogue-heading > div:first-child > span { font-size: 11px; line-height: 1.7; overflow-wrap: anywhere; }
.message-body p { color: var(--interview-ink); font-size: 14px; line-height: 1.95; }
.answer-composer { padding: 16px 20px 18px; }
.answer-composer > label { margin-bottom: 8px; }
.answer-composer .voice-conversation { gap: 8px 12px; margin-bottom: 12px; }
.answer-composer .voice-conversation .button { min-height: 34px; }
.answer-composer .answer-actions { margin-top: 10px; }
.answer-composer .answer-actions .button, .answer-composer .record-button { min-height: 36px; }
.preparation-column::-webkit-scrollbar, .presenter-column::-webkit-scrollbar, .conversation-column::-webkit-scrollbar, .dialogue-messages::-webkit-scrollbar { width: 7px; }
.preparation-column::-webkit-scrollbar-thumb, .presenter-column::-webkit-scrollbar-thumb, .conversation-column::-webkit-scrollbar-thumb, .dialogue-messages::-webkit-scrollbar-thumb { background: #b5bdc8; border-radius: 8px; }
@media (max-width: 960px) {
  .interview-grid { grid-template-rows: minmax(0, 26%) minmax(0, 1fr); }
  .preparation-column { display: grid; grid-template-rows: minmax(0, 1fr); overflow: hidden; }
  .preparation-column > .panel { min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin; }
  .avatar-options button { justify-content: center; }
  .avatar-options button > img { display: none; }
  .active-conversation { overflow-y: auto; }
  .active-conversation .dialogue-panel { flex: 0 0 auto; min-height: 100%; overflow: visible; }
  .active-conversation .dialogue-messages { flex: 1 0 auto; max-height: 48dvh; }
}
@media (max-width: 600px) {
  .interview-page :deep(.page-heading) { margin-bottom: 12px; }
  .interview-grid { gap: 12px; grid-template-rows: minmax(0, 24%) minmax(0, 1fr); }
  .preparation-column { display: flex; overflow-y: auto; }
  .preparation-column > .panel { overflow: visible; }
  .stage-content { min-height: 0; }
  .dialogue-messages { max-height: none; }
  .dimension-grid { grid-template-columns: minmax(0, 1fr); }
  .presenter-heading { flex-wrap: wrap; gap: 7px; padding: 10px 8px; }
  .presenter-heading > span { font-size: 9px; }
  .presenter-heading strong { gap: 6px; font-size: 13px; }
  .presenter-heading small { font-size: 9px; }
  .stage-media { max-height: none; }
  .stage-actions { gap: 5px; padding-top: 0; }
  .stage-actions .button { padding: 0 6px; font-size: 10px; }
  .stage-actions .button svg { width: 12px; }
  .avatar-options { grid-template-columns: minmax(0, 1fr); }
  .avatar-options button { justify-content: flex-start; }
  .avatar-options button > img { display: block; }
  .model-settings { padding: 0 0 16px; }
  .dialogue-heading h2 { font-size: 17px; }
  .message-body p { font-size: 13px; }
  .answer-composer { padding: 14px 12px; }
}
.dialogue-speech-status { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px 16px; padding: 12px 24px; border-bottom: 1px solid var(--line); background: var(--canvas); color: var(--muted); font-size: 12px; line-height: 1.8; }
.dialogue-speech-status > span { display: flex; align-items: flex-start; gap: 7px; min-width: 0; flex: 1 1 240px; overflow-wrap: anywhere; }
.dialogue-speech-status > span > svg { flex-shrink: 0; margin-top: 3px; }
.dialogue-speech-status > button { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; color: var(--accent); white-space: nowrap; }
</style>
