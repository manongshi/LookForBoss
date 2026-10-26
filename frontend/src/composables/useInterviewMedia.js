import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { apiHeaders, apiUrl, post, request } from '../api'

const API = '/interviews'
const REQUEST_TIMEOUT = 90000
const SPEECH_TIMEOUT = 160000
const PREVIEW_TIMEOUT = 110000
const MAX_RECORDING_SECONDS = 90
const CANCELLED = Symbol('interview-media-cancelled')

export function useInterviewMedia() {
  const videoRef = ref(null)
  const status = ref({ installed: false, running: false, ready: false, note: '', asr_installed: false })
  const connecting = ref(false)
  const connected = ref(false)
  const soundEnabled = ref(false)
  const preparingSpeech = ref(false)
  const playing = ref(false)
  const recording = ref(false)
  const recognizing = ref(false)
  const error = ref('')
  const transcript = ref(null)
  const speechActivity = ref({ id: 0, text: '', phase: 'idle' })
  const speechNote = ref('')

  let active = true
  let destroyed = false
  let connectionVersion = 0
  let playbackVersion = 0
  let statusVersion = 0
  let recordingVersion = 0
  let previewVersion = 0
  let cancelConnection = null
  let peer = null
  let remoteStream = null
  let sessionId = null
  let speechQueue = Promise.resolve()
  let speakingTimer = null
  let disconnectedTimer = null
  let previewAudio = null
  let previewUrl = null
  let previewController = null
  let microphone = null
  let audioContext = null
  let audioSource = null
  let processor = null
  let silentOutput = null
  let recordingTimer = null
  let recordingStarting = false
  let recordingChunks = []
  let recordedSamples = 0
  let recordingSampleRate = 16000
  let recognitionPromise = null
  let reportedSpeechError = ''
  let utteranceVersion = 0
  let utterance = null
  let speechDeadline = null
  let recordingOptions = null

  function updateStatus(value) {
    if (value && typeof value === 'object') status.value = { ...status.value, ...value }
    return status.value
  }

  function notifyDisconnect(id) {
    if (id === null || id === undefined) return Promise.resolve()
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT)
    return fetch(apiUrl(`${API}/avatar/disconnect`), {
      method: 'POST', headers: apiHeaders(), body: JSON.stringify({ sessionid: id }),
      keepalive: true, signal: controller.signal,
    }).catch(() => {}).finally(() => clearTimeout(timer))
  }

  function finishSpeech(phase) {
    clearTimeout(speechDeadline)
    speechDeadline = null
    if (utterance) speechActivity.value = { id: utterance.id, text: utterance.text, phase }
  }

  function releaseConnection() {
    utteranceVersion += 1
    finishSpeech('cancelled')
    utterance = null
    playbackVersion += 1
    speechQueue = Promise.resolve()
    clearTimeout(speakingTimer)
    clearTimeout(disconnectedTimer)
    speakingTimer = null
    disconnectedTimer = null
    const oldSession = sessionId
    sessionId = null
    if (peer) {
      peer.ontrack = null
      peer.onconnectionstatechange = null
      peer.close()
      peer = null
    }
    remoteStream?.getTracks().forEach(track => track.stop())
    remoteStream = null
    if (videoRef.value) {
      videoRef.value.pause()
      videoRef.value.srcObject = null
    }
    connecting.value = false
    connected.value = false
    soundEnabled.value = false
    preparingSpeech.value = false
    playing.value = false
    speechNote.value = ''
    reportedSpeechError = ''
    return oldSession
  }

  async function playVideo() {
    const video = videoRef.value
    if (!video || !remoteStream || !active) return false
    const stream = remoteStream
    const version = ++playbackVersion
    video.srcObject = stream
    video.autoplay = true
    video.playsInline = true
    video.muted = false
    try {
      await video.play()
      if (!active || version !== playbackVersion || remoteStream !== stream || videoRef.value !== video) return false
      soundEnabled.value = true
      if (/播放声音|开启声音/.test(error.value)) error.value = ''
      return true
    } catch (cause) {
      if (active && version === playbackVersion && remoteStream === stream && videoRef.value === video && cause.name !== 'AbortError') {
        soundEnabled.value = false
        error.value = '浏览器暂未允许播放声音，请点击“开启声音”。'
        // Keep the connected avatar visible while waiting for a sound gesture.
        if (cause.name === 'NotAllowedError') {
          video.muted = true
          await video.play().catch(() => {})
        }
      }
      return false
    }
  }

  watch(videoRef, () => { if (remoteStream) void playVideo() })

  async function refreshStatus() {
    const version = ++statusVersion
    try {
      const result = await request(`${API}/avatar/status`, { timeout: REQUEST_TIMEOUT })
      if (active && version === statusVersion) updateStatus(result)
      return result
    } catch (cause) {
      if (active && version === statusVersion) error.value = cause.message
      return null
    }
  }

  function pollSpeaking(version) {
    let failures = 0
    const poll = async () => {
      if (!active || version !== connectionVersion || !connected.value || sessionId === null) return
      const speechVersion = utteranceVersion
      const pollStartedAt = Date.now()
      try {
        const result = await request(`${API}/avatar/speaking?sessionid=${encodeURIComponent(sessionId)}`, { timeout: REQUEST_TIMEOUT })
        if (version !== connectionVersion || !active) return
        if (!result || result.connected === false || result.session_exists === false) {
          throw new Error('数字人会话已断开，请重新连接。')
        }
        if (speechVersion === utteranceVersion) {
          const speechError = typeof result.speech_error === 'string' ? result.speech_error.trim() : ''
          speechNote.value = typeof result.speech_note === 'string' ? result.speech_note.trim() : ''
          preparingSpeech.value = !speechError && Boolean(result.speech_pending)
          playing.value = !speechError && Boolean(result.speaking)
          if (speechError) error.value = speechError
          else if (reportedSpeechError && error.value === reportedSpeechError) error.value = ''
          reportedSpeechError = speechError
          if (utterance?.acknowledgedAt && pollStartedAt >= utterance.acknowledgedAt && ['pending', 'speaking'].includes(speechActivity.value.phase)) {
            if (speechError) finishSpeech('failed')
            else if (result.speaking) {
              utterance.heard = true
              utterance.quietPolls = 0
              speechActivity.value = { id: utterance.id, text: utterance.text, phase: 'speaking' }
            } else if (utterance.heard && !result.speech_pending) {
              utterance.quietPolls += 1
              if (utterance.quietPolls >= 2) finishSpeech('finished')
            } else utterance.quietPolls = 0
          }
        }
        failures = 0
      } catch (cause) {
        if (version !== connectionVersion || !active) return
        failures += 1
        if (failures >= 3 || /不存在|已断开|会话.*失效|session.*(missing|not found)/i.test(cause.message)) {
          error.value = cause.message || '数字人连接已断开，请重新连接。'
          const id = releaseConnection()
          void notifyDisconnect(id)
          return
        }
      }
      if (active && version === connectionVersion && connected.value) speakingTimer = setTimeout(poll, 900)
    }
    void poll()
  }

  async function connect({ avatar_id, voice_id } = {}) {
    if (!active || connecting.value) return false
    error.value = ''
    statusVersion += 1
    const oldSession = releaseConnection()
    cancelConnection?.()
    const version = ++connectionVersion
    connecting.value = true
    let operationCancelled = false
    let cancel
    const cancellation = new Promise((_, reject) => { cancel = () => reject(CANCELLED) })
    cancelConnection = cancel
    const current = () => active && version === connectionVersion && !operationCancelled
    const wait = async (promise, milliseconds) => {
      let timer
      try {
        const options = [promise, cancellation]
        if (milliseconds !== undefined) options.push(new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('数字人启动或连接等待超时，请稍后重新连接。')), Math.max(1, milliseconds))
        }))
        const result = await Promise.race(options)
        if (!current()) throw CANCELLED
        return result
      } finally { clearTimeout(timer) }
    }
    try {
      if (typeof window.RTCPeerConnection !== 'function') throw new Error('当前浏览器不支持数字人视频，请使用新版 Chrome 或 Edge。')
      if (oldSession !== null) await wait(notifyDisconnect(oldSession), 10000)
      const deadline = Date.now() + 75000
      updateStatus(await wait(post(`${API}/avatar/start`, {}, { timeout: REQUEST_TIMEOUT }), deadline - Date.now()))
      while (!status.value.ready) {
        if (status.value.installed === false) throw new Error(status.value.note || '数字人运行环境尚未安装。')
        await wait(new Promise(resolve => setTimeout(resolve, 1200)), deadline - Date.now())
        updateStatus(await wait(request(`${API}/avatar/status`, { timeout: REQUEST_TIMEOUT }), deadline - Date.now()))
      }
      const connection = new RTCPeerConnection({ iceServers: [] })
      peer = connection
      remoteStream = new MediaStream()
      let resolveConnected
      let rejectConnected
      const established = new Promise((resolve, reject) => { resolveConnected = resolve; rejectConnected = reject })
      // Connection errors can arrive while the SDP request is still pending.
      established.catch(() => {})
      connection.ontrack = (event) => {
        if (!current()) return
        const tracks = event.streams[0]?.getTracks() || [event.track]
        tracks.forEach(track => {
          if (!remoteStream.getTracks().some(existing => existing.id === track.id)) remoteStream.addTrack(track)
        })
        void playVideo()
      }
      connection.onconnectionstatechange = () => {
        if (!current()) return
        if (connection.connectionState === 'connected') {
          clearTimeout(disconnectedTimer)
          connected.value = true
          resolveConnected()
        } else if (['closed', 'failed'].includes(connection.connectionState)) {
          rejectConnected(new Error('数字人视频连接失败，请重新连接。'))
          if (connected.value) {
            error.value = '数字人连接已断开，请重新连接。'
            void notifyDisconnect(releaseConnection())
          }
        } else if (connection.connectionState === 'disconnected') {
          clearTimeout(disconnectedTimer)
          disconnectedTimer = setTimeout(() => {
            if (!current() || connection.connectionState !== 'disconnected') return
            rejectConnected(new Error('数字人视频连接中断，请重新连接。'))
            error.value = '数字人视频连接中断，请重新连接。'
            void notifyDisconnect(releaseConnection())
          }, 5000)
        }
      }
      connection.addTransceiver('audio', { direction: 'recvonly' })
      connection.addTransceiver('video', { direction: 'recvonly' })
      await wait(connection.setLocalDescription(await connection.createOffer()), 15000)
      if (connection.iceGatheringState !== 'complete') {
        await wait(new Promise(resolve => {
          const gathered = () => {
            if (connection.iceGatheringState === 'complete') {
              connection.removeEventListener('icegatheringstatechange', gathered)
              resolve()
            }
          }
          connection.addEventListener('icegatheringstatechange', gathered)
        }), 15000)
      }
      const offered = post(`${API}/avatar/offer`, {
        type: connection.localDescription.type, sdp: connection.localDescription.sdp, avatar_id, voice_id,
      }, { timeout: REQUEST_TIMEOUT })
      offered.then(answer => {
        if (!current() && answer?.sessionid !== undefined) void notifyDisconnect(answer.sessionid)
      }, () => {})
      const answer = await wait(offered, 70000)
      if (!answer?.sdp || answer.sessionid === null || answer.sessionid === undefined) throw new Error('数字人没有返回有效的视频会话，请重新连接。')
      sessionId = answer.sessionid
      await wait(connection.setRemoteDescription({ type: answer.type, sdp: answer.sdp }), 15000)
      await wait(established, 20000)
      if (!current()) throw CANCELLED
      connected.value = true
      pollSpeaking(version)
      return true
    } catch (cause) {
      if (current()) {
        if (cause !== CANCELLED) error.value = cause.message || '数字人连接失败，请稍后重试。'
        void notifyDisconnect(releaseConnection())
      }
      operationCancelled = true
      return false
    } finally {
      if (version === connectionVersion) {
        connecting.value = false
        cancelConnection = null
      }
    }
  }

  async function disconnect() {
    cancelConnection?.()
    cancelConnection = null
    connectionVersion += 1
    await notifyDisconnect(releaseConnection())
  }

  function queueSpeechCommand(action, payload = {}) {
    const version = connectionVersion
    const id = sessionId
    const current = () => active && connected.value && version === connectionVersion && id !== null && id === sessionId
    const execute = async () => {
      if (!current()) return false
      try {
        if (action === 'speak') {
          speechNote.value = ''
          preparingSpeech.value = true
          clearTimeout(speechDeadline)
          utterance = { id: ++utteranceVersion, text: payload.text, heard: false, quietPolls: 0, acknowledgedAt: 0 }
          speechActivity.value = { id: utterance.id, text: utterance.text, phase: 'pending' }
          if (reportedSpeechError && error.value === reportedSpeechError) error.value = ''
        }
        await post(`${API}/avatar/${action}`, { sessionid: id, ...payload }, { timeout: REQUEST_TIMEOUT })
        if (!current()) return false
        playing.value = action === 'speak'
        if (action === 'speak' && utterance) {
          const speakingTurn = utterance
          speakingTurn.acknowledgedAt = Date.now()
          speechDeadline = setTimeout(async () => {
            if (!current() || utterance !== speakingTurn || utteranceVersion !== speakingTurn.id || speakingTurn.heard) return
            // Cancel a slow synthesis before allowing the microphone to listen.
            const interrupted = await queueSpeechCommand('interrupt')
            if (!current() || utterance !== speakingTurn || utteranceVersion !== speakingTurn.id) return
            preparingSpeech.value = false
            if (!interrupted) {
              error.value = '无法确认播报已停止，请先断开数字人再重新连接。'
              finishSpeech('blocked')
              return
            }
            error.value = '语音播报等待超时，已暂停播报，可以直接回答。'
            finishSpeech('failed')
          }, 65000)
        }
        return true
      } catch (cause) {
        if (current()) {
          preparingSpeech.value = false
          finishSpeech('blocked')
          error.value = cause?.message || '数字人语音操作失败，请稍后重试。'
        }
        return false
      }
    }
    const result = speechQueue.then(execute, execute)
    speechQueue = result.then(() => {}, () => {})
    return result
  }

  async function speak(text) {
    const value = String(text || '').trim()
    if (!active || !connected.value || sessionId === null || !value) return false
    return queueSpeechCommand('speak', { text: value })
  }

  function stopPreview() {
    previewVersion += 1
    previewController?.abort()
    previewController = null
    if (previewAudio) {
      previewAudio.onended = null
      previewAudio.onerror = null
      previewAudio.pause()
      previewAudio.removeAttribute('src')
      previewAudio.load()
      previewAudio = null
    }
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    previewUrl = null
  }

  async function interrupt() {
    utteranceVersion += 1
    const interrupted = utterance
    finishSpeech('cancelling')
    stopPreview()
    playing.value = false
    preparingSpeech.value = false
    if (!active || !connected.value || sessionId === null) { finishSpeech('cancelled'); return true }
    const result = await queueSpeechCommand('interrupt')
    if (utterance === interrupted) finishSpeech(result ? 'cancelled' : 'blocked')
    return result
  }

  async function playVoicePreview(voice_id) {
    if (!active) return false
    if (recording.value || recordingStarting) {
      error.value = '请先结束录音，再试听面试官音色。'
      return false
    }
    stopPreview()
    const version = previewVersion
    error.value = ''
    const controller = new AbortController()
    previewController = controller
    let timedOut = false
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, PREVIEW_TIMEOUT)
    try {
      const response = await fetch(apiUrl(`${API}/speech/preview`), {
        method: 'POST', headers: apiHeaders(), body: JSON.stringify({ voice_id }), signal: controller.signal,
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        const detail = Array.isArray(body?.detail) ? body.detail.map(item => item.msg).join('；') : body?.detail
        throw new Error(typeof detail === 'string' ? detail : '音色试听失败，请稍后重试。')
      }
      const blob = await response.blob()
      if (!active || version !== previewVersion) return false
      if (!blob.size) throw new Error('没有收到试听音频，请稍后重试。')
      const speechNotice = response.headers.get('X-Speech-Notice')
      if (speechNotice) {
        try { speechNote.value = decodeURIComponent(speechNotice) }
        catch { speechNote.value = speechNotice }
      } else speechNote.value = response.headers.get('X-Speech-Fallback') === 'local' ? '在线语音暂不可用，已改用本机离线语音。' : ''
      previewUrl = URL.createObjectURL(blob)
      previewAudio = new Audio(previewUrl)
      previewAudio.onended = () => { if (version === previewVersion) stopPreview() }
      previewAudio.onerror = () => {
        if (active && version === previewVersion) { error.value = '试听音频播放失败，请重新试听。'; stopPreview() }
      }
      try { await previewAudio.play() } catch (cause) {
        if (cause.name === 'NotAllowedError') throw new Error('浏览器暂未允许播放声音，请点击“开启声音”。')
        throw cause
      }
      return true
    } catch (cause) {
      if (active && version === previewVersion && (cause.name !== 'AbortError' || timedOut)) {
        error.value = timedOut ? '音色试听等待超时，请稍后重试。' : cause.message || '音色试听失败。'
      }
      return false
    } finally {
      clearTimeout(timer)
      if (previewController === controller) previewController = null
    }
  }

  async function enableSound() {
    error.value = ''
    try {
      if (previewAudio) await previewAudio.play()
      if (remoteStream) return await playVideo()
      return Boolean(previewAudio)
    } catch {
      error.value = '声音播放被浏览器阻止，请允许此页面播放声音后重试。'
      return false
    }
  }

  function releaseMicrophone() {
    clearTimeout(recordingTimer)
    recordingTimer = null
    if (processor) { processor.onaudioprocess = null; processor.disconnect(); processor = null }
    audioSource?.disconnect()
    silentOutput?.disconnect()
    audioSource = null
    silentOutput = null
    microphone?.getTracks().forEach(track => track.stop())
    microphone = null
    const context = audioContext
    audioContext = null
    if (context && context.state !== 'closed') void context.close().catch(() => {})
  }

  async function startRecording(options = {}) {
    if (!active || recording.value || recordingStarting) return false
    if (recognizing.value) { error.value = '上一段回答正在识别，请稍候。'; return false }
    if (!navigator.mediaDevices?.getUserMedia || !(window.AudioContext || window.webkitAudioContext)) {
      error.value = '当前浏览器不支持麦克风录音，请使用新版 Chrome 或 Edge，并允许麦克风权限。'
      return false
    }
    stopPreview()
    error.value = ''
    transcript.value = null
    recordingOptions = options
    recognitionPromise = null
    const version = ++recordingVersion
    recordingStarting = true
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext
      try { audioContext = new AudioContextClass({ sampleRate: 16000 }) } catch { audioContext = new AudioContextClass() }
      const context = audioContext
      await context.resume()
      if (!active || version !== recordingVersion) return false
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }, video: false,
      })
      if (!active || version !== recordingVersion) { stream.getTracks().forEach(track => track.stop()); return false }
      microphone = stream
      recordingSampleRate = context.sampleRate
      recordingChunks = []
      recordedSamples = 0
      audioSource = context.createMediaStreamSource(stream)
      processor = context.createScriptProcessor(4096, 1, 1)
      silentOutput = context.createGain()
      silentOutput.gain.value = 0
      let speechSamples = 0
      let lastSpeechSample = 0
      let noiseFloor = 0.002
      processor.onaudioprocess = ({ inputBuffer }) => {
        if (!recording.value || version !== recordingVersion) return
        const length = Math.min(inputBuffer.length, Math.ceil(recordingSampleRate * MAX_RECORDING_SECONDS) - recordedSamples)
        if (length <= 0) { void stopRecording(); return }
        const mono = new Float32Array(length)
        for (let channel = 0; channel < inputBuffer.numberOfChannels; channel += 1) {
          const values = inputBuffer.getChannelData(channel)
          for (let i = 0; i < length; i += 1) mono[i] += values[i] / inputBuffer.numberOfChannels
        }
        recordingChunks.push(mono)
        recordedSamples += length
        if (options.autoStop) {
          let energy = 0
          for (const value of mono) energy += value * value
          const rms = Math.sqrt(energy / Math.max(1, mono.length))
          if (rms < 0.008 && !speechSamples) noiseFloor = noiseFloor * 0.9 + rms * 0.1
          if (rms > Math.max(0.008, noiseFloor * 3)) {
            speechSamples += length
            lastSpeechSample = recordedSamples
          }
          const hasSpeech = speechSamples >= recordingSampleRate * 0.15
          if (hasSpeech && recordedSamples - lastSpeechSample >= recordingSampleRate * 1.8) {
            void stopRecording()
            return
          }
          if (!hasSpeech && recordedSamples >= recordingSampleRate * 15) {
            void stopRecording({ noSpeech: true })
            return
          }
        }
        if (recordedSamples >= Math.ceil(recordingSampleRate * MAX_RECORDING_SECONDS)) void stopRecording()
      }
      audioSource.connect(processor)
      processor.connect(silentOutput)
      silentOutput.connect(context.destination)
      recording.value = true
      if (connected.value && !options.keepSpeech) void interrupt()
      recordingTimer = setTimeout(() => { void stopRecording() }, MAX_RECORDING_SECONDS * 1000)
      return true
    } catch (cause) {
      if (active && version === recordingVersion) {
        error.value = ['NotAllowedError', 'SecurityError'].includes(cause.name)
          ? '麦克风权限未开启，请在浏览器中允许此页面使用麦克风。'
          : cause.name === 'NotFoundError' ? '没有找到可用的麦克风，请连接设备后重试。' : '无法开启录音，请检查麦克风是否被其他应用占用。'
        releaseMicrophone()
      }
      return false
    } finally { if (version === recordingVersion) recordingStarting = false }
  }

  async function encodeWav(chunks, total, sourceRate) {
    const samples = new Float32Array(total)
    let offset = 0
    chunks.forEach(chunk => { samples.set(chunk, offset); offset += chunk.length })
    const length = Math.max(1, Math.ceil(total * 16000 / sourceRate))
    let mono = samples
    if (sourceRate !== 16000) {
      const OfflineContext = window.OfflineAudioContext || window.webkitOfflineAudioContext
      if (OfflineContext) {
        const context = new OfflineContext(1, length, 16000)
        const buffer = context.createBuffer(1, total, sourceRate)
        buffer.copyToChannel(samples, 0)
        const source = context.createBufferSource()
        source.buffer = buffer
        source.connect(context.destination)
        source.start()
        mono = (await context.startRendering()).getChannelData(0)
      } else {
        mono = new Float32Array(length)
        const ratio = sourceRate / 16000
        for (let i = 0; i < length; i += 1) {
          const start = Math.floor(i * ratio)
          const end = Math.min(total, Math.max(start + 1, Math.floor((i + 1) * ratio)))
          for (let j = start; j < end; j += 1) mono[i] += samples[j] / (end - start)
        }
      }
    }
    const bytes = new ArrayBuffer(44 + mono.length * 2)
    const view = new DataView(bytes)
    const text = (position, value) => { for (let i = 0; i < value.length; i += 1) view.setUint8(position + i, value.charCodeAt(i)) }
    text(0, 'RIFF'); view.setUint32(4, 36 + mono.length * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
    view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
    text(36, 'data'); view.setUint32(40, mono.length * 2, true)
    for (let i = 0; i < mono.length; i += 1) {
      const value = Math.max(-1, Math.min(1, mono[i]))
      view.setInt16(44 + i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true)
    }
    const binary = []
    const array = new Uint8Array(bytes)
    for (let i = 0; i < array.length; i += 32768) binary.push(String.fromCharCode(...array.subarray(i, i + 32768)))
    return `data:audio/wav;base64,${btoa(binary.join(''))}`
  }

  function cancelRecording() {
    recordingVersion += 1
    recordingStarting = false
    recording.value = false
    recognizing.value = false
    recordingOptions = null
    recordingChunks = []
    recordedSamples = 0
    recognitionPromise = null
    releaseMicrophone()
  }

  function stopRecording({ noSpeech = false } = {}) {
    if (recognitionPromise) return recognitionPromise
    if (!recording.value) return Promise.resolve('')
    const version = recordingVersion
    const chunks = recordingChunks
    const total = recordedSamples
    const sourceRate = recordingSampleRate
    const options = recordingOptions
    recordingChunks = []
    recordedSamples = 0
    recording.value = false
    releaseMicrophone()
    recognizing.value = true
    recognitionPromise = (async () => {
      let outcome = null
      try {
        if (noSpeech) throw new Error('还没有听到回答，已暂停语音对话。准备好后可以重新开启。')
        if (total < sourceRate * 0.2) throw new Error('录音太短，请说完一句话后再结束。')
        const audio = await encodeWav(chunks, total, sourceRate)
        if (!active || version !== recordingVersion) return ''
        const result = await post(`${API}/speech/transcribe`, { audio }, { timeout: SPEECH_TIMEOUT })
        if (!active || version !== recordingVersion) return ''
        const value = typeof result?.text === 'string' ? result.text.trim() : ''
        if (!value) throw new Error('没有识别出文字，请靠近麦克风重新录音。')
        outcome = { id: version, text: value, context: options?.context, autoSubmit: Boolean(options?.autoSubmit) }
        return value
      } catch (cause) {
        if (active && version === recordingVersion) {
          error.value = cause.message || '语音识别失败，请重新录音或输入文字。'
          outcome = { id: version, text: '', context: options?.context, autoSubmit: Boolean(options?.autoSubmit), error: error.value }
        }
        return ''
      } finally {
        if (active && version === recordingVersion) {
          recognizing.value = false
          // Publish after clearing recognition so an automatic answer can submit.
          if (outcome) transcript.value = outcome
        }
      }
    })()
    return recognitionPromise
  }

  function dispose() {
    active = false
    statusVersion += 1
    recordingVersion += 1
    previewVersion += 1
    recordingStarting = false
    recording.value = false
    recognizing.value = false
    recordingChunks = []
    recordedSamples = 0
    recognitionPromise = null
    releaseMicrophone()
    stopPreview()
    void disconnect()
  }

  onActivated(() => { if (!destroyed) active = true })
  onDeactivated(dispose)
  onBeforeUnmount(() => { destroyed = true; dispose() })

  return {
    videoRef, status, connecting, connected, soundEnabled, preparingSpeech, playing, recording, recognizing, error, transcript, speechNote, speechActivity,
    refreshStatus, connect, disconnect, speak, interrupt, startRecording, stopRecording, cancelRecording,
    playVoicePreview, enableSound, dispose,
  }
}
