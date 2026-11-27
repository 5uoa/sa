﻿
<script setup lang="ts">
import {
  callShortcutKeyLabel,
  isCallShortcutKeyEvent,
  normalizeCallShortcutKey
} from '~/utils/callShortcut'

/** 会话输入区：附件、语音通话、推理强度；发送内容交由父级处理 */
const props = withDefaults(
  defineProps<{
    placeholder?: string
    /** 变化时清空输入与待发送附件（如切换任务） */
    resetKey?: string
    /** 总管正在运行时不发送新语音，避免任务被静默丢弃 */
    busy?: boolean
    /** 项目会话由专家 Agent 自行决定推理参数时可隐藏强度选择 */
    showDepth?: boolean
    /** 通话中停止播音使用的 KeyboardEvent.code */
    stopSpeechKey?: string
  }>(),
  {
    placeholder: '输入消息...',
    resetKey: '',
    busy: false,
    showDepth: true,
    stopSpeechKey: 'Escape'
  }
)

/** 编辑器选区引用：行范围 + 选中内容 */
interface QuoteRef {
  text: string
  range: string
}

const emit = defineEmits<{
  send: [
    payload: {
      text: string
      files: string[]
      rawFiles: File[]
      depth: string
      quote: QuoteRef | null
      source: 'text' | 'voice'
    }
  ]
  'barge-in': []
}>()

const draft = ref('')
const pendingFiles = ref<string[]>([])
const pendingRawFiles = ref<File[]>([])
/** 从文档编辑器「引用到 AI」带过来的选中文本 */
const quote = ref<QuoteRef | null>(null)
const thinkingDepth = ref('标准')
const inCall = ref(false)
const callSeconds = ref(0)
const muted = ref(false)
const speakerOn = ref(true)
const callError = ref('')
const speaking = ref(false)
const transcribing = ref(false)
let callTimer: ReturnType<typeof setInterval> | null = null
const speechQueue: string[] = []
let microphoneStream: MediaStream | null = null
let audioContext: AudioContext | null = null
let audioSource: MediaStreamAudioSourceNode | null = null
let audioProcessor: ScriptProcessorNode | null = null
let audioPlayer: HTMLAudioElement | null = null
let audioUrl = ''
let playbackGeneration = 0
let audioPlayerResolve: (() => void) | null = null
let capturing = false
let speechStarted = false
let bargeInFrames = 0
let silenceStartedAt = 0
let recordingStartedAt = 0
let recordingFrames: Float32Array[] = []
let preRollFrames: Float32Array[] = []
const callTime = computed(() => {
  const minutes = String(Math.floor(callSeconds.value / 60)).padStart(2, '0')
  const seconds = String(callSeconds.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})
const stopSpeechKeyLabel = computed(() => {
  return callShortcutKeyLabel(props.stopSpeechKey)
})
const callPhase = computed(() => {
  if (speaking.value) return `正在播报，按 ${stopSpeechKeyLabel.value} 停止`
  if (transcribing.value) return 'DeepSeek 正在识别'
  if (props.busy) return 'AI 正在处理'
  if (muted.value) return '已静音'
  return '正在聆听'
})
const filePicker = ref<{ inputRef?: HTMLInputElement } | null>(null)
const form = ref<HTMLFormElement | null>(null)

watch(
  () => props.resetKey,
  () => {
    draft.value = ''
    pendingFiles.value = []
    pendingRawFiles.value = []
    quote.value = null
  }
)

/** 写入引用并聚焦输入框 */
function setQuote(payload: QuoteRef) {
  quote.value = payload
  focus()
}

function focus() {
  form.value?.querySelector<HTMLInputElement>('input[type="text"]')?.focus()
}

defineExpose({ setQuote, focus, speak, speakStream, endCall })

/** 文件选择框选择后只记录文件名（不自动上传） */
function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files ?? [])
  if (files.length > 0) {
    pendingFiles.value = [...pendingFiles.value, ...files.map((file) => file.name)]
    pendingRawFiles.value = [...pendingRawFiles.value, ...files]
  }
  target.value = ''
}

function removeFile(index: number) {
  pendingFiles.value.splice(index, 1)
  pendingRawFiles.value.splice(index, 1)
}

/** 开始通话：重置静音/扬声器与计时 */
async function startCall() {
  callError.value = ''
  try {
    if (!window.isSecureContext) {
      throw new Error('语音通话需要 HTTPS 或 localhost 安全环境')
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持麦克风录音')
    }
    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    })
    audioContext = new AudioContext({ sampleRate: 16000 })
    audioSource = audioContext.createMediaStreamSource(microphoneStream)
    audioProcessor = audioContext.createScriptProcessor(4096, 1, 1)
    const silentGain = audioContext.createGain()
    silentGain.gain.value = 0
    audioProcessor.onaudioprocess = onAudioFrame
    audioSource.connect(audioProcessor)
    audioProcessor.connect(silentGain)
    silentGain.connect(audioContext.destination)
    resetRecording()
    inCall.value = true
    muted.value = false
    speakerOn.value = true
    callSeconds.value = 0
    if (callTimer) clearInterval(callTimer)
    callTimer = setInterval(() => {
      callSeconds.value += 1
    }, 1000)
    speak('您好，我是总管。请直接说出您要处理的任务。')
  } catch (error) {
    callError.value = speechErrorMessage(error)
    endCall()
  }
}

/** 挂断：停止计时并恢复输入区 */
function endCall() {
  inCall.value = false
  transcribing.value = false
  capturing = false
  stopAudioPlayback()
  audioProcessor?.disconnect()
  audioProcessor = null
  audioSource?.disconnect()
  audioSource = null
  microphoneStream?.getTracks().forEach((track) => track.stop())
  microphoneStream = null
  void audioContext?.close()
  audioContext = null
  resetRecording()
  if (callTimer) {
    clearInterval(callTimer)
    callTimer = null
  }
}

function toggleMute() {
  muted.value = !muted.value
  if (muted.value) pauseCapture()
  else resumeCapture()
}

function speechErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? `${error.name} ${error.message}` : String(error || '')
  const value = raw.toLowerCase()
  if (
    value.includes('notfound') ||
    value.includes('not-found') ||
    value.includes('device not found') ||
    value.includes('audio-capture') ||
    value.includes('requested device') ||
    value.includes('no microphone')
  ) {
    return '未检测到可用麦克风，请连接或启用系统麦克风后重新通话；也可以继续使用文字输入。'
  }
  if (
    value.includes('notallowed') ||
    value.includes('service-not-allowed') ||
    value.includes('permission')
  ) {
    return '麦克风权限未开启，请在浏览器地址栏允许本站使用麦克风。'
  }
  if (value.includes('notreadable') || value.includes('device in use')) {
    return '麦克风正被其他应用占用，请关闭占用程序后重试。'
  }
  if (value.includes('network')) {
    return 'DeepSeek ASR/TTS 网络服务不可用，请检查网络或改用文字输入。'
  }
  return error instanceof Error && error.message
    ? `DeepSeek 语音通话启动失败：${error.message}`
    : '未检测到可用麦克风或 DeepSeek 语音服务不可用，请检查麦克风连接和浏览器权限，或继续使用文字输入。'
}

function pauseCapture() {
  capturing = false
}

function resumeCapture() {
  if (!inCall.value || muted.value || speaking.value || props.busy || transcribing.value) return
  resetRecording()
  recordingStartedAt = Date.now()
  capturing = true
}

function resetRecording() {
  recordingFrames = []
  preRollFrames = []
  speechStarted = false
  silenceStartedAt = 0
  bargeInFrames = 0
}

function stopAudioPlayback() {
  playbackGeneration += 1
  speechQueue.splice(0)
  audioPlayer?.pause()
  audioPlayer = null
  if (audioUrl) URL.revokeObjectURL(audioUrl)
  audioUrl = ''
  audioPlayerResolve?.()
  audioPlayerResolve = null
  speaking.value = false
  bargeInFrames = 0
}

function isEditableTarget(event: KeyboardEvent) {
  const target = event.target
  return (
    target instanceof HTMLElement &&
    Boolean(target.closest('input, textarea, [contenteditable="true"]'))
  )
}

function shouldIgnoreShortcutInEditor(event: KeyboardEvent) {
  const key = normalizeCallShortcutKey(props.stopSpeechKey)
  return isEditableTarget(event) && ['Space', 'KeyV', 'KeyQ'].includes(key)
}

function handleStopSpeechKeydown(event: KeyboardEvent) {
  if (
    !inCall.value ||
    !isCallShortcutKeyEvent(event, props.stopSpeechKey) ||
    event.repeat ||
    shouldIgnoreShortcutInEditor(event)
  ) {
    return
  }
  event.preventDefault()
  // 通话中优先把快捷键用于停止播报，避免同时触发页面的 Esc 退出全屏等动作。
  event.stopImmediatePropagation()
  emit('barge-in')
  stopAudioPlayback()
  resumeCapture()
}

function onAudioFrame(event: AudioProcessingEvent) {
  if (!inCall.value || muted.value || props.busy || transcribing.value) {
    return
  }
  const samples = new Float32Array(event.inputBuffer.getChannelData(0))
  let energy = 0
  for (const sample of samples) energy += sample * sample
  const rms = Math.sqrt(energy / samples.length)
  const now = Date.now()

  if (speaking.value) {
    // 通话中允许用户随时插话；连续两帧（约 0.5 秒）超过阈值才中断，
    // 避免偶发噪声或回声误触发。
    if (rms > 0.025) bargeInFrames += 1
    else bargeInFrames = 0
    if (bargeInFrames < 2) return
    emit('barge-in')
    stopAudioPlayback()
    resetRecording()
    capturing = true
    speechStarted = true
    recordingFrames = [samples]
    recordingStartedAt = now
    return
  }

  if (!capturing) return
  if (!speechStarted) {
    preRollFrames.push(samples)
    if (preRollFrames.length > 4) preRollFrames.shift()
    if (rms > 0.018) {
      speechStarted = true
      recordingFrames = [...preRollFrames]
      recordingStartedAt = now
      preRollFrames = []
      silenceStartedAt = 0
    }
    return
  }
  recordingFrames.push(samples)
  if (rms < 0.009) {
    if (!silenceStartedAt) silenceStartedAt = now
    if (now - silenceStartedAt >= 750) void finishDeepSeekTurn()
  } else {
    silenceStartedAt = 0
  }
  if (recordingStartedAt && now - recordingStartedAt >= 105000) {
    void finishDeepSeekTurn()
  }
}

async function finishDeepSeekTurn() {
  if (!speechStarted || transcribing.value || !recordingFrames.length) return
  transcribing.value = true
  capturing = false
  const frames = recordingFrames
  resetRecording()
  try {
    const wav = encodeWav(frames, audioContext?.sampleRate || 16000)
    const formData = new FormData()
    formData.append('file', new Blob([wav], { type: 'audio/wav' }), 'speech.wav')
    const config = useRuntimeConfig()
    const response = await $fetch<{
      code: number
      message: string
      data: { text: string; durationMs: number }
    }>('/front/chief/voice/transcribe', {
      baseURL: config.public.apiBase as string,
      method: 'POST',
      headers: { Authorization: `Bearer ${getAdminToken()}` },
      body: formData
    })
    if (response.code !== 200 || !response.data.text.trim()) {
      throw new Error(response.message || 'DeepSeek ASR 未返回文本')
    }
    draft.value = response.data.text.trim()
    submit('voice')
  } catch (error) {
    callError.value = speechErrorMessage(error)
  } finally {
    transcribing.value = false
    if (inCall.value && !speaking.value && !props.busy) resumeCapture()
  }
}

function encodeWav(frames: Float32Array[], sampleRate: number): ArrayBuffer {
  const sampleCount = frames.reduce((total, frame) => total + frame.length, 0)
  const buffer = new ArrayBuffer(44 + sampleCount * 2)
  const view = new DataView(buffer)
  const write = (offset: number, value: string) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index))
    }
  }
  write(0, 'RIFF')
  view.setUint32(4, 36 + sampleCount * 2, true)
  write(8, 'WAVE')
  write(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  write(36, 'data')
  view.setUint32(40, sampleCount * 2, true)
  let offset = 44
  for (const frame of frames) {
    for (const sample of frame) {
      const value = Math.max(-1, Math.min(1, sample))
      view.setInt16(offset, value < 0 ? value * 32768 : value * 32767, true)
      offset += 2
    }
  }
  return buffer
}

function speak(text: string) {
  if (!inCall.value || !speakerOn.value || !text.trim()) return
  const speechText = markdownToSpeech(text)
  if (!speechText) return
  pauseCapture()
  stopAudioPlayback()
  const generation = playbackGeneration
  speechQueue.splice(0, speechQueue.length, ...splitSpeechText(speechText))
  speaking.value = true
  void playSpeechChunk(generation)
}

function speakStream(text: string) {
  if (!inCall.value || !speakerOn.value) return
  const speechText = markdownToSpeech(text)
  if (!speechText) return
  const chunks = splitSpeechText(speechText)
  if (!chunks.length) return
  speechQueue.push(...chunks)
  if (!speaking.value) {
    pauseCapture()
    speaking.value = true
    void playSpeechChunk(playbackGeneration)
  }
}

async function playSpeechChunk(generation = playbackGeneration) {
  if (!inCall.value || !speakerOn.value || !speechQueue.length) {
    speaking.value = false
    resumeCapture()
    return
  }
  const chunk = speechQueue.shift() || ''
  try {
    const config = useRuntimeConfig()
    const response = await fetch(`${config.public.apiBase}/front/chief/voice/synthesize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAdminToken()}`
      },
      body: JSON.stringify({ text: chunk, voice_id: 'stella' })
    })
    if (!response.ok) {
      throw new Error(`DeepSeek TTS 失败（HTTP ${response.status}）`)
    }
    if (generation !== playbackGeneration) return
    const blob = await response.blob()
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    audioUrl = URL.createObjectURL(blob)
    audioPlayer = new Audio(audioUrl)
    await new Promise<void>((resolve, reject) => {
      if (!audioPlayer) return reject(new Error('音频播放器初始化失败'))
      audioPlayerResolve = resolve
      audioPlayer.onended = () => {
        audioPlayerResolve = null
        resolve()
      }
      audioPlayer.onerror = () => {
        audioPlayerResolve = null
        reject(new Error('音频播放失败'))
      }
      void audioPlayer.play().catch(reject)
    })
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    audioUrl = ''
    audioPlayer = null
    if (generation === playbackGeneration) void playSpeechChunk(generation)
  } catch (error) {
    callError.value = speechErrorMessage(error)
    speaking.value = false
    resumeCapture()
  }
}

function splitSpeechText(text: string): string[] {
  const sentences = text
    .split(/(?<=[。！？!?；;])\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
  const chunks: string[] = []
  let current = ''
  for (const sentence of sentences) {
    if ((current + sentence).length > 120 && current) {
      chunks.push(current)
      current = sentence
    } else {
      current += sentence
    }
  }
  if (current) chunks.push(current)
  return chunks.length ? chunks : [text]
}

function markdownToSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, '，代码块，')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/[*_~]{1,3}([^*_~]+)[*_~]{1,3}/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleStopSpeechKeydown)
  endCall()
  if (callTimer) clearInterval(callTimer)
})

onMounted(() => {
  window.addEventListener('keydown', handleStopSpeechKeydown)
})

function submit(source: 'text' | 'voice' = 'text') {
  if (props.busy) return
  if (source === 'voice') {
    pauseCapture()
  }
  const text = draft.value.trim()
  const files = [...pendingFiles.value]
  const rawFiles = [...pendingRawFiles.value]
  if (!text && files.length === 0 && !quote.value) return
  emit('send', {
    text,
    files,
    rawFiles,
    depth: thinkingDepth.value,
    quote: quote.value,
    source
  })
  draft.value = ''
  pendingFiles.value = []
  pendingRawFiles.value = []
  quote.value = null
}

watch(
  () => props.busy,
  (busy) => {
    if (busy) {
      pauseCapture()
    } else resumeCapture()
  }
)

watch(speakerOn, (enabled) => {
  if (!inCall.value) return
  if (!enabled) {
    stopAudioPlayback()
    resumeCapture()
  }
})
</script>

<template>
  <form
    ref="form"
    class="flex flex-none flex-col gap-2 border-t border-default bg-default px-4 pb-3 pt-2.5"
    @submit.prevent="submit('text')"
  >
    <div
      v-if="quote"
      class="relative flex flex-col gap-0.5 rounded-md bg-primary/10 py-1.5 pe-9 ps-3 text-xs leading-snug text-primary"
    >
      <span class="font-semibold">引用 {{ quote.range }}</span>
      <span class="truncate">{{ quote.text }}</span>
      <UButton
        class="absolute end-1 top-1"
        color="neutral"
        variant="ghost"
        square
        aria-label="移除引用"
        @click="quote = null"
      >
        ×
      </UButton>
    </div>

    <ul v-if="pendingFiles.length" role="list" class="flex flex-wrap gap-1.5">
      <li v-for="(file, index) in pendingFiles" :key="`${file}-${index}`">
        <span
          class="inline-flex max-w-full items-center gap-1 rounded-md bg-elevated/60 py-0.5 pe-1 ps-2.5 text-xs leading-snug text-muted"
        >
          <span class="truncate">{{ file }}</span>
          <UButton
            color="neutral"
            variant="ghost"
            square
            :aria-label="`移除附件 ${file}`"
            @click="removeFile(index)"
          >
            ×
          </UButton>
        </span>
      </li>
    </ul>

    <div class="flex flex-wrap items-center gap-1.5">
      <template v-if="inCall">
        <div
          class="flex min-w-0 flex-1 items-center gap-2.5 rounded-md bg-primary/10 px-2.5 py-2 text-sm text-primary"
          role="group"
          :aria-label="`正在与 AI 通话，已通话 ${callTime}`"
        >
          <span class="size-2 shrink-0 animate-pulse rounded-full bg-primary" aria-hidden="true" />
          <span class="shrink-0 font-medium tabular-nums">{{ callTime }}</span>
          <span class="truncate text-muted">{{ callPhase }}</span>
          <span class="ms-auto hidden shrink-0 text-xs text-dimmed sm:inline">
            按 {{ stopSpeechKeyLabel }} 停止播报
          </span>
        </div>

        <div class="flex shrink-0 items-center gap-1">
          <UButton
            color="neutral"
            :variant="muted ? 'soft' : 'ghost'"
            :aria-pressed="muted"
            :aria-label="muted ? '取消静音' : '静音'"
            @click="toggleMute"
          >
            {{ muted ? '取消静音' : '静音' }}
          </UButton>
          <UButton
            color="neutral"
            :variant="speakerOn ? 'soft' : 'ghost'"
            :aria-pressed="speakerOn"
            :aria-label="speakerOn ? '关闭扬声器' : '打开扬声器'"
            @click="speakerOn = !speakerOn"
          >
            {{ speakerOn ? '关闭扬声器' : '打开扬声器' }}
          </UButton>
          <UButton color="error" aria-label="结束通话" @click="endCall">挂断</UButton>
        </div>
      </template>

      <UAlert
        v-if="callError"
        color="error"
        variant="subtle"
        :description="callError"
        class="w-full"
      />

      <template v-if="!inCall">
        <USelect
          v-if="showDepth"
          v-model="thinkingDepth"
          :items="['快速', '标准', '深度']"
          class="w-20 shrink-0"
          aria-label="推理强度"
        />

        <div class="min-w-0 flex-1">
          <UInput ref="filePicker" type="file" class="hidden" multiple @change="onFileChange" />
          <UInput
            v-model="draft"
            class="w-full"
            :disabled="busy"
            :placeholder="placeholder"
            aria-label="输入消息"
            @keydown.enter.prevent="submit('text')"
          >
            <template #leading>
              <UButton
                color="neutral"
                variant="ghost"
                square
                class="size-6 p-0"
                aria-label="添加附件"
                @click="filePicker?.inputRef?.click()"
              >
                <svg class="size-4" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M10.5 5.5 6 10a1.9 1.9 0 0 0 2.7 2.7l4.6-4.6a3.2 3.2 0 0 0-4.5-4.5L3.5 8.5a4.5 4.5 0 0 0 6.4 6.4"
                    stroke="currentColor"
                    stroke-width="1.3"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </UButton>
            </template>
          </UInput>
        </div>

        <UButton
          color="neutral"
          variant="ghost"
          class="shrink-0"
          aria-label="语音通话"
          @click="startCall"
        >
          通话
        </UButton>
      </template>
    </div>
  </form>
</template>
