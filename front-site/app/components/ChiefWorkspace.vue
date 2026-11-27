<script setup lang="ts">
import { getAdminToken } from '~/composables/useAdminSession'
import { escapeMarkdown, renderMarkdown } from '~/utils/markdown'
import type { DropdownMenuItem } from '@nuxt/ui'

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

interface ChiefAttachment {
  id: string
  uuid: string
  name: string
  ext: string
  size: number
  mimeType: string
  role: 'user' | 'assistant'
  kind?: string
  documentId?: string
}

interface ChiefDocument {
  id: string
  sessionId: string
  projectId?: string | null
  sourceMessageId?: string | null
  title: string
  kind: 'custom' | ProjectArtifactKind
  status: 'draft' | 'confirmed' | 'stale'
  contentHtml: string
  contentText: string
  attached: boolean
  createTime: string
  updateTime: string
}

interface ChiefMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  meta: Record<string, unknown>
  attachments: ChiefAttachment[]
  runId?: string
  createTime?: string
}

interface ChiefSession {
  id: string
  title: string
  domain: string
  riskTier: string
  projectId?: string
  projectName?: string
  messageCount?: number
  preview?: string
  updateTime?: string
  messages?: ChiefMessage[]
  runs?: ChiefRunSummary[]
  documents?: ChiefDocument[]
}

interface ChiefProject {
  id: string
  name: string
  description: string
  status: string
  context: Record<string, unknown>
  used: number
  limit: number
  sourceSessionId?: string | null
  expertId?: string | null
  expertName?: string | null
  expertRole?: string | null
}

interface ChiefExpertOption {
  id: string
  name: string
  role: string
  enabled: boolean
}

type ProjectArtifactKind = 'requirements' | 'solution' | 'task_plan'

interface ChiefProjectArtifactVersion {
  id: string
  versionNo: number
  contentText: string
  confirmedAt: string
  sourceVersionNo?: number
}

interface ChiefProjectArtifact {
  id: string
  kind: 'requirements' | 'solution' | 'task_plan'
  title: string
  status: 'draft' | 'confirmed' | 'stale'
  latestVersionNo: number
  draftHtml: string
  draftText: string
  sourceVersionNo?: number
  versions: ChiefProjectArtifactVersion[]
}

interface ChiefProjectDetail extends ChiefProject {
  phase:
    | 'requirements'
    | 'requirements_confirmed'
    | 'solution'
    | 'solution_confirmed'
    | 'task_planning'
    | 'tasks_confirmed'
    | 'executing'
    | 'reviewing'
    | 'completed'
  executionStatus: 'idle' | 'running' | 'completed' | 'failed'
  requirementHtml?: string
  requirementText?: string
  solutionHtml?: string
  solutionText?: string
  taskPlan?: {
    packages?: Array<{
      name?: string
      tasks?: Array<{
        key?: string
        title?: string
        description?: string
        acceptanceCriteria?: string
        priority?: string
        dependsOn?: string[]
      }>
    }>
  }
  documents?: Partial<Record<'requirements' | 'solution' | 'task_plan', ChiefProjectArtifact>>
}

interface ChiefRunSummary {
  id: string
  status: string
  domain: string
  riskTier: string
  recursionMode?: string
  recursionK?: number
  selectedHarnessId?: string
  answer?: string
  error?: string
  requiresApproval?: boolean
  inputTokens?: number
  outputTokens?: number
  estimatedCost?: number
  regressionPassed?: boolean | null
  autoAdoptReason?: string
}

interface HarnessCandidate {
  id: string
  label: string
  scope: string
  answer: string
  score: number
  latencyMs: number
  step?: number
  inputTokens?: number
  outputTokens?: number
  estimatedCost?: number
  harnessId: string
  harness: Record<string, unknown>
  trace: {
    ok?: boolean
    message?: string
    assessment?: { reasons?: string[] }
    diff?: Array<{ component: string }>
  }
}

interface RunEvent {
  seq: number
  stage: string
  status: string
  message: string
  payload: Record<string, unknown>
}

interface ChiefRun extends ChiefRunSummary {
  sessionId: string
  answer: string
  modelName: string
  candidates: HarnessCandidate[]
  events: RunEvent[]
}

const sessions = ref<ChiefSession[]>([])
const projects = ref<ChiefProject[]>([])
const projectExperts = ref<ChiefExpertOption[]>([])
const projectCreatorOpen = ref(false)
const projectCreatorBusy = ref(false)
const projectCreatorError = ref('')
const projectCreatorForm = reactive({
  name: '',
  description: '',
  expertId: 'none'
})
const activeSessionId = ref('')
const activeSession = ref<ChiefSession | null>(null)
const messages = ref<ChiefMessage[]>([])
const currentRun = ref<ChiefRun | null>(null)
const recursionMode = ref<'sequential' | 'parallel'>('sequential')
const recursionK = ref(1)
const stopSpeechKey = ref('Escape')
const loading = ref(true)
const sending = ref(false)
const liveEvents = ref<RunEvent[]>([])
const error = ref('')
const documentVisible = ref(true)
const attachmentVisible = ref(true)
const harnessVisible = ref(true)
const rightPanel = ref<'harness' | 'document'>('harness')
let suppressSidebarWatch = false
const sidebarMode = ref<'sessions' | 'projects'>('sessions')
const showArchived = ref(false)
const edited = ref(false)
const documentHtml = ref('')
const sessionDocuments = ref<ChiefDocument[]>([])
const generatedDocumentOpen = ref(false)
const activeGeneratedDocumentId = ref('')
const generatedDocumentTitle = ref('')
const generatedDocumentHtml = ref('')
const generatedDocumentBusy = ref(false)
const generatedDocumentError = ref('')
const pendingDeleteDocumentId = ref('')
const body = ref<HTMLElement | null>(null)
const previewOpen = ref(false)
const previewFile = ref<{ title: string; ext: string; meta: string } | null>(null)
const messageActionId = ref('')
const copiedMessageId = ref('')
const convertedMessageId = ref('')
const convertingMessageId = ref('')
const playingMessageId = ref('')
const messageActionError = ref('')
const projectDetail = ref<ChiefProjectDetail | null>(null)
const viewedProjectArtifactKind = ref<ProjectArtifactKind | null>(null)
const projectArtifactDraft = ref('')
const projectArtifactHtml = ref('')
const projectArtifactLoading = ref(false)
const projectArtifactError = ref('')
const projectArtifactBusy = ref(false)
const projectArtifactFullscreen = ref(false)
let messageAudio: HTMLAudioElement | null = null
let messageAudioUrl = ''
let messageSpeechQueue: string[] = []
let messagePlaybackGeneration = 0
const composerRef = ref<{
  setQuote: (payload: { text: string; range: string }) => void
  speak: (text: string) => void
  speakStream: (text: string) => void
  endCall: () => void
} | null>(null)

async function request<T>(path: string, payload: Record<string, unknown> = {}) {
  const response = await useApi<ApiEnvelope<T>>(path, payload)
  if (response.code !== 200) throw new Error(response.message)
  return response.data
}

function stopMessageAudio() {
  messagePlaybackGeneration += 1
  messageAudio?.pause()
  messageAudio = null
  if (messageAudioUrl) URL.revokeObjectURL(messageAudioUrl)
  messageAudioUrl = ''
  messageSpeechQueue = []
  playingMessageId.value = ''
}

async function copyMessage(message: ChiefMessage) {
  if (messageActionId.value) return
  messageActionId.value = message.id
  messageActionError.value = ''
  try {
    await navigator.clipboard.writeText(message.content)
    copiedMessageId.value = message.id
    window.setTimeout(() => {
      if (copiedMessageId.value === message.id) copiedMessageId.value = ''
    }, 1500)
  } catch (err) {
    messageActionError.value = `复制失败：${normalizeApiError(err).message}`
  } finally {
    messageActionId.value = ''
  }
}

async function playMessage(message: ChiefMessage) {
  if (playingMessageId.value === message.id) {
    stopMessageAudio()
    return
  }
  if (messageActionId.value) return
  messageActionId.value = message.id
  messageActionError.value = ''
  try {
    stopMessageAudio()
    messageSpeechQueue = splitSpeechText(
      message.content.replace(/```[\s\S]*?```/g, '代码块').replace(/[#*_>`~]/g, '')
    )
    playingMessageId.value = message.id
    await playNextMessageChunk(message.id, messagePlaybackGeneration)
  } catch (err) {
    messageActionError.value = `播放失败：${normalizeApiError(err).message}`
    stopMessageAudio()
  } finally {
    messageActionId.value = ''
  }
}

async function playNextMessageChunk(messageId: string, generation: number) {
  if (
    generation !== messagePlaybackGeneration ||
    !messageSpeechQueue.length ||
    playingMessageId.value !== messageId
  ) {
    stopMessageAudio()
    return
  }
  const chunk = messageSpeechQueue.shift() || ''
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
    if (!response.ok) throw new Error(`DeepSeek TTS 失败（HTTP ${response.status}）`)
    if (generation !== messagePlaybackGeneration) return
    messageAudioUrl = URL.createObjectURL(await response.blob())
    messageAudio = new Audio(messageAudioUrl)
    messageAudio.onended = () => {
      if (messageAudioUrl) URL.revokeObjectURL(messageAudioUrl)
      messageAudioUrl = ''
      messageAudio = null
      void playNextMessageChunk(messageId, generation)
    }
    messageAudio.onerror = () => {
      messageActionError.value = 'DeepSeek 音频播放失败'
      stopMessageAudio()
    }
    await messageAudio.play()
  } catch (err) {
    messageActionError.value = `播放失败：${normalizeApiError(err).message}`
    stopMessageAudio()
  }
}

function markMessageConverted(messageId: string) {
  convertedMessageId.value = messageId
  window.setTimeout(() => {
    if (convertedMessageId.value === messageId) convertedMessageId.value = ''
  }, 1800)
}

async function convertMessageToDocument(message: ChiefMessage) {
  if (convertingMessageId.value || !activeSession.value) return
  convertingMessageId.value = message.id
  messageActionError.value = ''
  try {
    const document = await request<ChiefDocument>('/front/chief/workspace/documents/create', {
      sessionId: activeSession.value.id,
      sourceMessageId: message.id,
      title: `${activeSession.value.title} · 文档 ${
        sessionDocuments.value.filter((item) => item.kind === 'custom').length + 1
      }`,
      contentText: message.content.trim(),
      contentHtml: renderMarkdown(message.content)
    })
    sessionDocuments.value = [
      { ...document, attached: false },
      ...sessionDocuments.value.filter((item) => item.id !== document.id)
    ]
    markMessageConverted(message.id)
    openGeneratedDocument(document)
  } catch (err) {
    messageActionError.value = `生成文档失败：${normalizeApiError(err).message}`
  } finally {
    convertingMessageId.value = ''
  }
}

function openGeneratedDocument(document: ChiefDocument) {
  activeGeneratedDocumentId.value = document.id
  generatedDocumentTitle.value = document.title
  generatedDocumentHtml.value = document.contentHtml
  generatedDocumentError.value = ''
  generatedDocumentOpen.value = true
}

async function saveGeneratedDocument() {
  if (!activeSession.value || !activeGeneratedDocumentId.value || generatedDocumentBusy.value) {
    return
  }
  const contentText = htmlToPlainText(generatedDocumentHtml.value)
  if (!generatedDocumentTitle.value.trim() || !contentText) {
    generatedDocumentError.value = '文档标题和正文不能为空。'
    return
  }
  generatedDocumentBusy.value = true
  generatedDocumentError.value = ''
  try {
    const updated = await request<ChiefDocument>('/front/chief/workspace/documents/update', {
      sessionId: activeSession.value.id,
      documentId: activeGeneratedDocumentId.value,
      title: generatedDocumentTitle.value.trim(),
      contentText,
      contentHtml: generatedDocumentHtml.value
    })
    const index = sessionDocuments.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) {
      const existing = sessionDocuments.value[index]
      sessionDocuments.value[index] = {
        ...existing,
        ...updated,
        attached: existing?.attached ?? false
      }
    }
    generatedDocumentTitle.value = updated.title
    generatedDocumentHtml.value = updated.contentHtml
  } catch (err) {
    generatedDocumentError.value = `保存失败：${normalizeApiError(err).message}`
  } finally {
    generatedDocumentBusy.value = false
  }
}

async function attachGeneratedDocument(document: ChiefDocument) {
  if (!activeSession.value || document.attached) return
  generatedDocumentBusy.value = true
  generatedDocumentError.value = ''
  try {
    const result = await request<{
      document: ChiefDocument
      message: ChiefMessage | null
      alreadyAttached: boolean
    }>('/front/chief/workspace/documents/attach', {
      sessionId: activeSession.value.id,
      documentId: document.id
    })
    const index = sessionDocuments.value.findIndex((item) => item.id === document.id)
    if (index >= 0) {
      sessionDocuments.value[index] = {
        ...sessionDocuments.value[index],
        ...result.document,
        attached: true
      }
    }
    if (result.message && !messages.value.some((item) => item.id === result.message?.id)) {
      messages.value.push(result.message)
      await scrollToBottom()
    }
  } catch (err) {
    generatedDocumentError.value = `加入会话失败：${normalizeApiError(err).message}`
  } finally {
    generatedDocumentBusy.value = false
  }
}

async function deleteGeneratedDocument(document: ChiefDocument) {
  if (!activeSession.value || generatedDocumentBusy.value) return
  if (pendingDeleteDocumentId.value !== document.id) {
    pendingDeleteDocumentId.value = document.id
    window.setTimeout(() => {
      if (pendingDeleteDocumentId.value === document.id) pendingDeleteDocumentId.value = ''
    }, 8000)
    return
  }
  pendingDeleteDocumentId.value = ''
  generatedDocumentBusy.value = true
  generatedDocumentError.value = ''
  try {
    await request('/front/chief/workspace/documents/delete', {
      sessionId: activeSession.value.id,
      documentId: document.id
    })
    sessionDocuments.value = sessionDocuments.value.filter((item) => item.id !== document.id)
    messages.value = messages.value.filter((item) => item.meta?.documentId !== document.id)
    if (document.kind !== 'custom' && document.projectId) {
      await loadProjectDetail(document.projectId)
    }
    if (activeGeneratedDocumentId.value === document.id && document.kind === 'custom') {
      generatedDocumentOpen.value = false
      activeGeneratedDocumentId.value = ''
    }
  } catch (err) {
    generatedDocumentError.value = `删除失败：${normalizeApiError(err).message}`
  } finally {
    generatedDocumentBusy.value = false
  }
}

function splitSpeechText(text: string): string[] {
  const sentences = text
    .split(/(?<=[。！？!?；;\n])\s*/)
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

async function loadSessions(preferredId = '', archived = showArchived.value) {
  showArchived.value = archived
  const data = await request<{ items: ChiefSession[] }>('/front/chief/sessions/list', {
    archived
  })
  sessions.value = data.items
  const visibleItems =
    sidebarMode.value === 'projects' ? data.items : data.items.filter((item) => !item.projectId)
  const target =
    visibleItems.find((item) => item.id === (preferredId || activeSessionId.value)) ||
    visibleItems[0]
  if (target) await selectSession(target.id, true)
  else if (archived) {
    activeSessionId.value = ''
    activeSession.value = null
    messages.value = []
    sessionDocuments.value = []
    currentRun.value = null
  } else if (sidebarMode.value === 'sessions') await createSession()
  else {
    activeSessionId.value = ''
    activeSession.value = null
    messages.value = []
    sessionDocuments.value = []
    currentRun.value = null
  }
}

async function selectSession(id: string, preserveCall = false) {
  stopMessageAudio()
  if (!preserveCall) composerRef.value?.endCall()
  activeSessionId.value = id
  projectArtifactFullscreen.value = false
  error.value = ''
  currentRun.value = null
  const data = await request<ChiefSession & { messages: ChiefMessage[] }>(
    '/front/chief/sessions/get',
    { session_id: id }
  )
  activeSession.value = data
  messages.value = data.messages || []
  sessionDocuments.value = data.documents || []
  await loadProjectDetail(data.projectId || '')
  edited.value = false
  const latest = (data.runs || []).find(
    (run) => run.status === 'awaiting_approval' || run.status === 'completed'
  )
  if (latest) await refreshRun(latest.id)
  await scrollToBottom()
}

async function createSession() {
  composerRef.value?.endCall()
  const data = await request<ChiefSession>('/front/chief/sessions/create', { title: '新会话' })
  await loadSessions(data.id, false)
}

async function loadProjectExperts() {
  const data = await request<{ items: ChiefExpertOption[] }>('/front/chief/experts/list')
  projectExperts.value = data.items
}

async function openProjectCreator() {
  projectCreatorForm.name = ''
  projectCreatorForm.description = ''
  projectCreatorForm.expertId = 'none'
  projectCreatorError.value = ''
  projectCreatorOpen.value = true
  if (!projectExperts.value.length) {
    try {
      await loadProjectExperts()
    } catch (err) {
      projectCreatorError.value = `专家加载失败：${normalizeApiError(err).message}`
    }
  }
}

async function createProjectFromChief() {
  const name = projectCreatorForm.name.trim()
  if (!name || projectCreatorBusy.value) return
  projectCreatorBusy.value = true
  projectCreatorError.value = ''
  try {
    const created = await request<ChiefProject>('/front/chief/workspace/projects/create', {
      name,
      description: projectCreatorForm.description.trim(),
      status: '进行中',
      expertId: projectCreatorForm.expertId === 'none' ? undefined : projectCreatorForm.expertId
    })
    const projectSession = await request<ChiefSession>('/front/chief/sessions/create', {
      title: created.name,
      project_id: created.id
    })
    projectCreatorOpen.value = false
    await loadProjects()
    suppressSidebarWatch = true
    sidebarMode.value = 'projects'
    await nextTick()
    suppressSidebarWatch = false
    await loadSessions(projectSession.id, false)
    rightPanel.value = 'document'
    documentVisible.value = true
  } catch (err) {
    projectCreatorError.value = `新建项目失败：${normalizeApiError(err).message}`
  } finally {
    projectCreatorBusy.value = false
  }
}

async function loadProjects() {
  const data = await request<{ items: ChiefProject[] }>('/front/chief/projects/list')
  projects.value = data.items
}

function artifactKindForPhase(phase?: string): ProjectArtifactKind | null {
  if (phase === 'requirements' || phase === 'requirements_confirmed') {
    return 'requirements' as const
  }
  if (phase === 'solution' || phase === 'solution_confirmed') {
    return 'solution' as const
  }
  if (phase === 'task_planning' || phase === 'tasks_confirmed') {
    return 'task_plan' as const
  }
  return null
}

const activeProjectArtifact = computed(() => {
  const kind = viewedProjectArtifactKind.value
  return kind ? projectDetail.value?.documents?.[kind] || null : null
})

const projectArtifactLabel = computed(() => {
  const kind = viewedProjectArtifactKind.value
  if (kind === 'requirements') return '需求文档'
  if (kind === 'solution') return '方案文档'
  if (kind === 'task_plan') return '计划清单'
  return '文档'
})

const projectArtifactEditable = computed(
  () =>
    viewedProjectArtifactKind.value === artifactKindForPhase(projectDetail.value?.phase) &&
    ['requirements', 'solution', 'task_planning'].includes(projectDetail.value?.phase || '')
)
const projectArtifactViewingHistorical = computed(
  () =>
    Boolean(viewedProjectArtifactKind.value) &&
    viewedProjectArtifactKind.value !== artifactKindForPhase(projectDetail.value?.phase)
)
const nextProjectArtifactVersion = computed(
  () => (activeProjectArtifact.value?.latestVersionNo || 0) + 1
)

function markdownLike(value: string) {
  return /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+\.\s|>\s)|\*\*|__|~~|`|^\|.+\|/m.test(value)
}

function artifactHtmlForEditor(html: string, plainText: string) {
  if (!html || markdownLike(plainText)) return renderMarkdown(plainText)
  return html
}

function syncProjectArtifactDraft(
  project: ChiefProjectDetail,
  kind = artifactKindForPhase(project.phase)
) {
  if (kind === 'requirements') {
    projectArtifactDraft.value =
      project.documents?.requirements?.draftText || project.requirementText || ''
    projectArtifactHtml.value = artifactHtmlForEditor(
      project.documents?.requirements?.draftHtml || project.requirementHtml || '',
      projectArtifactDraft.value
    )
  } else if (kind === 'solution') {
    projectArtifactDraft.value =
      project.documents?.solution?.draftText || project.solutionText || ''
    projectArtifactHtml.value = artifactHtmlForEditor(
      project.documents?.solution?.draftHtml || project.solutionHtml || '',
      projectArtifactDraft.value
    )
  } else if (kind === 'task_plan') {
    projectArtifactDraft.value = JSON.stringify(project.taskPlan || { packages: [] }, null, 2)
    projectArtifactHtml.value = ''
  } else {
    projectArtifactDraft.value = ''
    projectArtifactHtml.value = ''
  }
}

async function loadProjectDetail(projectId = '') {
  if (!projectId) {
    projectDetail.value = null
    viewedProjectArtifactKind.value = null
    projectArtifactDraft.value = ''
    projectArtifactHtml.value = ''
    projectArtifactError.value = ''
    return
  }
  projectArtifactLoading.value = true
  projectArtifactError.value = ''
  try {
    const data = await request<{ items: ChiefProjectDetail[] }>('/front/chief/workspace/get')
    projectDetail.value = data.items.find((item) => item.id === projectId) || null
    if (projectDetail.value) {
      viewedProjectArtifactKind.value = artifactKindForPhase(projectDetail.value.phase)
      syncProjectArtifactDraft(projectDetail.value)
    }
  } catch (err) {
    projectArtifactError.value = `文档加载失败：${normalizeApiError(err).message}`
  } finally {
    projectArtifactLoading.value = false
  }
}

function selectProjectArtifact(kind: ProjectArtifactKind) {
  if (!projectDetail.value) return
  viewedProjectArtifactKind.value = kind
  syncProjectArtifactDraft(projectDetail.value, kind)
  rightPanel.value = 'document'
  documentVisible.value = true
}

function htmlToPlainText(value: string) {
  const doc = new DOMParser().parseFromString(value, 'text/html')

  function serialize(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent || ''
    }
    if (!(node instanceof HTMLElement)) return ''
    const children = Array.from(node.childNodes).map(serialize).join('')
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '\n'
    if (tag === 'strong' || tag === 'b') return `**${children}**`
    if (tag === 'em' || tag === 'i') return `*${children}*`
    if (tag === 'code' && node.parentElement?.tagName.toLowerCase() !== 'pre') {
      return `\`${children}\``
    }
    if (tag === 'a') {
      const href = node.getAttribute('href') || ''
      return href ? `[${children}](${href})` : children
    }
    if (/^h[1-6]$/.test(tag)) {
      return `\n\n${'#'.repeat(Number(tag[1]))} ${children.trim()}\n\n`
    }
    if (tag === 'li') return `\n- ${children.trim()}`
    if (tag === 'blockquote') {
      return `\n${children
        .trim()
        .split('\n')
        .map((line) => `> ${line}`)
        .join('\n')}\n`
    }
    if (tag === 'tr') {
      return `\n| ${Array.from(node.children)
        .map((cell) => (cell.textContent || '').trim())
        .join(' | ')} |`
    }
    if (tag === 'p' || tag === 'div' || tag === 'pre' || tag === 'table') {
      return `\n${children}\n`
    }
    return children
  }

  return Array.from(doc.body.childNodes)
    .map(serialize)
    .join('')
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

async function saveProjectArtifact() {
  const project = projectDetail.value
  if (!project || !projectArtifactEditable.value) return false
  projectArtifactBusy.value = true
  projectArtifactError.value = ''
  try {
    if (project.phase === 'task_planning') {
      let plan: Record<string, unknown>
      try {
        const parsed = JSON.parse(projectArtifactDraft.value)
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('计划必须是 JSON 对象')
        }
        plan = parsed as Record<string, unknown>
      } catch (err) {
        throw new Error(`计划 JSON 无效：${normalizeApiError(err).message}`, {
          cause: err
        })
      }
      await request('/front/chief/workspace/projects/task-plan/save', {
        projectId: project.id,
        plan
      })
    } else {
      const stage = project.phase === 'requirements' ? 'requirements' : 'solution'
      const contentText = htmlToPlainText(projectArtifactHtml.value)
      if (!contentText) {
        throw new Error(`${projectArtifactLabel.value}内容不能为空`)
      }
      await request('/front/chief/workspace/projects/document/save', {
        projectId: project.id,
        stage,
        contentText,
        contentHtml: projectArtifactHtml.value
      })
    }
    await loadProjectDetail(project.id)
    return true
  } catch (err) {
    projectArtifactError.value = `保存失败：${normalizeApiError(err).message}`
    return false
  } finally {
    projectArtifactBusy.value = false
  }
}

async function confirmProjectArtifact() {
  const project = projectDetail.value
  if (!project || !projectArtifactEditable.value) return
  if (!(await saveProjectArtifact())) return
  projectArtifactBusy.value = true
  projectArtifactError.value = ''
  try {
    if (project.phase === 'task_planning') {
      await request('/front/chief/workspace/projects/task-plan/confirm', {
        projectId: project.id
      })
    } else {
      await request('/front/chief/workspace/projects/document/confirm', {
        projectId: project.id,
        stage: project.phase === 'requirements' ? 'requirements' : 'solution'
      })
    }
    await loadProjectDetail(project.id)
  } catch (err) {
    projectArtifactError.value = `确认失败：${normalizeApiError(err).message}`
  } finally {
    projectArtifactBusy.value = false
  }
}

async function adjustConfirmedProjectArtifact(): Promise<boolean> {
  const project = projectDetail.value
  if (!project) return false
  projectArtifactBusy.value = true
  projectArtifactError.value = ''
  try {
    if (project.phase === 'tasks_confirmed') {
      await request('/front/chief/workspace/projects/task-plan/save', {
        projectId: project.id,
        plan: project.taskPlan || {}
      })
    } else {
      const stage = project.phase === 'requirements_confirmed' ? 'requirements' : 'solution'
      const contentText =
        stage === 'requirements' ? project.requirementText || '' : project.solutionText || ''
      const contentHtml =
        stage === 'requirements' ? project.requirementHtml || '' : project.solutionHtml || ''
      await request('/front/chief/workspace/projects/document/save', {
        projectId: project.id,
        stage,
        contentText,
        contentHtml
      })
    }
    await loadProjectDetail(project.id)
    return true
  } catch (err) {
    projectArtifactError.value = `进入调整失败：${normalizeApiError(err).message}`
    return false
  } finally {
    projectArtifactBusy.value = false
  }
}

async function openProject(project: ChiefProject) {
  const existing = sessions.value.find((item) => item.projectId === project.id)
  if (existing) {
    await selectSession(existing.id)
    return
  }
  const created = await request<ChiefSession>('/front/chief/sessions/create', {
    title: project.name,
    project_id: project.id
  })
  await loadSessions(created.id)
}

watch(sidebarMode, async (mode) => {
  if (suppressSidebarWatch) return
  if (loading.value) return
  if (mode === 'sessions') {
    if (!activeSession.value || activeSession.value.projectId) {
      await loadSessions('', showArchived.value)
    }
    return
  }
  const target = projects.value[0]
  if (!activeSession.value?.projectId && target) await openProject(target)
})

async function deleteSession(session: ChiefSession) {
  if (!window.confirm(`确定删除会话「${session.title}」吗？`)) return
  try {
    await request('/front/chief/sessions/delete', { session_id: session.id })
    if (activeSessionId.value === session.id) {
      activeSessionId.value = ''
      currentRun.value = null
      messages.value = []
      sessionDocuments.value = []
    }
    await loadSessions('', showArchived.value)
  } catch (err) {
    error.value = normalizeApiError(err).message
  }
}

async function archiveSession(session: ChiefSession) {
  try {
    await request('/front/chief/sessions/archive', { session_id: session.id })
    if (activeSessionId.value === session.id) {
      activeSessionId.value = ''
      currentRun.value = null
      messages.value = []
      sessionDocuments.value = []
    }
    await loadSessions('', false)
  } catch (err) {
    error.value = normalizeApiError(err).message
  }
}

async function restoreSession(session: ChiefSession) {
  try {
    await request('/front/chief/sessions/restore', { session_id: session.id })
    await loadSessions('', true)
  } catch (err) {
    error.value = normalizeApiError(err).message
  }
}

async function toggleArchived() {
  if (activeSessionId.value) {
    currentRun.value = null
  }
  await loadSessions('', !showArchived.value)
}

function sessionMenuItems(session: ChiefSession): DropdownMenuItem[][] {
  return showArchived.value
    ? [
        [
          { label: '恢复', onSelect: () => void restoreSession(session) },
          {
            label: '删除',
            color: 'error',
            onSelect: () => void deleteSession(session)
          }
        ]
      ]
    : [
        [
          { label: '归档', onSelect: () => void archiveSession(session) },
          {
            label: '删除',
            color: 'error',
            onSelect: () => void deleteSession(session)
          }
        ]
      ]
}

async function refreshRun(runId: string) {
  if (!runId) return
  try {
    currentRun.value = await request<ChiefRun>('/front/chief/runs/get', { run_id: runId })
  } catch {
    currentRun.value = null
  }
}

async function uploadFiles(files: File[], names: string[]) {
  if (!files.length) return []
  const formData = new FormData()
  formData.append('form_code', 'ADMIN_CHAT')
  files.forEach((file) => formData.append('files', file))
  const config = useRuntimeConfig()
  const response = await $fetch<{
    code: number
    message: string
    data: Array<{
      uuid: string
      original_name: string
      file_ext: string
      file_size: number
      mime_type: string
    }>
  }>('/front/upload/files', {
    baseURL: config.public.apiBase as string,
    method: 'POST',
    headers: { Authorization: `Bearer ${getAdminToken()}` },
    body: formData
  })
  if (response.code !== 200) throw new Error(response.message)
  return response.data.map((item, index) => ({
    uuid: item.uuid,
    name: item.original_name || names[index] || '附件',
    mime_type: item.mime_type,
    size: item.file_size
  }))
}

async function scrollToBottom() {
  await nextTick()
  if (body.value) body.value.scrollTop = body.value.scrollHeight
}

async function streamVoiceReply(message: string) {
  const config = useRuntimeConfig()
  const tempId = `voice-live-${Date.now()}`
  const liveMessage: ChiefMessage = {
    id: tempId,
    role: 'assistant',
    content: '',
    meta: { mode: 'voice' },
    attachments: []
  }
  messages.value.push(liveMessage)
  await scrollToBottom()
  const response = await fetch(`${config.public.apiBase}/front/chief/messages/send/voice/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getAdminToken()}`
    },
    body: JSON.stringify({
      session_id: activeSessionId.value,
      message
    })
  })
  if (!response.ok || !response.body) {
    messages.value = messages.value.filter((item) => item.id !== tempId)
    throw new Error(`语音快速通道请求失败（HTTP ${response.status}）`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let speechBuffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let separator = buffer.indexOf('\n\n')
      while (separator >= 0) {
        const block = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        separator = buffer.indexOf('\n\n')
        const eventName =
          block
            .split('\n')
            .find((line) => line.startsWith('event:'))
            ?.slice(6)
            .trim() || 'message'
        const dataText = block
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('\n')
        if (!dataText) continue
        const data = JSON.parse(dataText)
        if (eventName === 'delta') {
          const delta = String(data.text || '')
          liveMessage.content += delta
          speechBuffer += delta
          const match = speechBuffer.match(/[\s\S]*[。！？!?；;\n]/)
          if (match) {
            const spoken = match[0].trim()
            speechBuffer = speechBuffer.slice(match[0].length)
            if (spoken) composerRef.value?.speakStream(spoken)
          }
          await scrollToBottom()
        } else if (eventName === 'final') {
          if (speechBuffer.trim()) {
            composerRef.value?.speakStream(speechBuffer.trim())
            speechBuffer = ''
          }
          liveMessage.content = String(data.answer || liveMessage.content)
          await loadSessions(activeSessionId.value)
        } else if (eventName === 'error') {
          throw new Error(data.message || '语音快速通道失败')
        }
      }
    }
  } finally {
    messages.value = messages.value.filter((item) => item.id !== tempId)
  }
}

async function handleSend(payload: {
  text: string
  files: string[]
  rawFiles: File[]
  depth: string
  quote: { text: string; range: string } | null
  source: 'text' | 'voice'
}) {
  if (sending.value) return
  const text = payload.quote
    ? `引用 ${payload.quote.range}\n${payload.quote.text}\n\n${payload.text}`.trim()
    : payload.text.trim()
  if (!text && !payload.files.length) return
  sending.value = true
  liveEvents.value = []
  error.value = ''
  try {
    const fixedCommand = payload.text.trim()
    const isProjectCommand =
      /^#(生成需求|生成方案|生成计划|开始执行|需求沟通|需求文档|方案沟通|方案文档|任务计划|计划清单)#$/.test(
        fixedCommand
      )
    if (isProjectCommand && payload.source === 'text') {
      const result = await request<{
        message: string
        projectId: string
        projectCreated: boolean
      }>('/front/chief/workspace/workflow/command', {
        sessionId: activeSession.value?.id,
        message: fixedCommand
      })
      currentRun.value = null
      if (fixedCommand === '#开始执行#') {
        await navigateTo({
          path: '/',
          query: { projectId: result.projectId }
        })
        return
      }
      if (result.projectCreated || activeSession.value?.projectId) {
        await loadProjects()
        suppressSidebarWatch = true
        sidebarMode.value = 'projects'
        await nextTick()
        suppressSidebarWatch = false
      }
      await loadSessions(activeSessionId.value)
      rightPanel.value = 'document'
      documentVisible.value = true
      composerRef.value?.speak(result.message)
      return
    }
    if (payload.source === 'voice') {
      await streamVoiceReply(text)
      return
    }
    const attachments = await uploadFiles(payload.rawFiles, payload.files)
    const config = useRuntimeConfig()
    const response = await fetch(`${config.public.apiBase}/front/chief/messages/send/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAdminToken()}`
      },
      body: JSON.stringify({
        session_id: activeSessionId.value,
        message: text,
        attachments,
        recursion_mode: recursionMode.value,
        recursion_k: recursionK.value
      })
    })
    if (!response.ok || !response.body) {
      throw new Error(`总管请求失败（HTTP ${response.status}）`)
    }
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let run: ChiefRun | null = null
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let separator = buffer.indexOf('\n\n')
      while (separator >= 0) {
        const block = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        separator = buffer.indexOf('\n\n')
        const eventName =
          block
            .split('\n')
            .find((line) => line.startsWith('event:'))
            ?.slice(6)
            .trim() || 'message'
        const dataText = block
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trim())
          .join('\n')
        if (!dataText) continue
        const data = JSON.parse(dataText)
        if (eventName === 'progress') {
          liveEvents.value.push(data as RunEvent)
        } else if (eventName === 'final') {
          run = data as ChiefRun
        } else if (eventName === 'error') {
          throw new Error(data.message || '总管运行失败')
        }
      }
    }
    if (!run) throw new Error('总管运行未返回最终结果')
    currentRun.value = run
    await loadSessions(activeSessionId.value)
    if (run.status === 'awaiting_approval') {
      composerRef.value?.speak(`候选已生成，当前为 ${run.riskTier} 任务，需要您确认后继续。`)
    } else {
      composerRef.value?.speak(run.answer || '')
    }
  } catch (err) {
    error.value = normalizeApiError(err).message
    if (payload.source === 'voice') {
      composerRef.value?.speak('总管处理失败，请查看页面提示。')
    }
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

async function approveRun() {
  if (!currentRun.value) return
  try {
    currentRun.value = await request<ChiefRun>('/front/chief/runs/approve', {
      run_id: currentRun.value.id
    })
    await loadSessions(activeSessionId.value)
    composerRef.value?.speak(currentRun.value.answer || '')
  } catch (err) {
    error.value = normalizeApiError(err).message
    composerRef.value?.speak('候选采纳失败，请查看页面提示。')
  }
}

async function rejectRun() {
  if (!currentRun.value) return
  try {
    currentRun.value = await request<ChiefRun>('/front/chief/runs/reject', {
      run_id: currentRun.value.id
    })
    await loadSessions(activeSessionId.value)
    composerRef.value?.speak('已拒绝当前候选。')
  } catch (err) {
    error.value = normalizeApiError(err).message
  }
}

const attachments = computed<ChiefAttachment[]>(() =>
  messages.value.flatMap((message) =>
    (message.attachments || [])
      .filter((file) => file.kind !== 'document')
      .map((file) => ({ ...file, role: message.role }))
  )
)

const activeGeneratedDocument = computed(
  () =>
    sessionDocuments.value.find(
      (item) => item.id === activeGeneratedDocumentId.value && item.kind === 'custom'
    ) || null
)

const attachmentTotalCount = computed(
  () => attachments.value.length + sessionDocuments.value.length
)

function documentKindLabel(document: ChiefDocument) {
  if (document.kind === 'requirements') return '需求文档'
  if (document.kind === 'solution') return '方案文档'
  if (document.kind === 'task_plan') return '计划清单'
  return '文档'
}

function documentStateLabel(document: ChiefDocument) {
  if (document.status === 'stale') return '已过期'
  if (document.status === 'confirmed') return '已确认'
  return '草稿'
}

function openManagedDocument(document: ChiefDocument) {
  if (document.kind === 'custom') {
    openGeneratedDocument(document)
    return
  }
  selectProjectArtifact(document.kind)
}

const generalSessions = computed(() => sessions.value.filter((session) => !session.projectId))
const projectExpertOptions = computed(() => [
  { label: '自动选择可用专家', value: 'none' },
  ...projectExperts.value
    .filter((expert) => expert.enabled)
    .map((expert) => ({
      label: `${expert.name} · ${expert.role}`,
      value: expert.id
    }))
])

const sessionMarkdown = computed(() => {
  const lines = ['## 总管会话', '']
  if (!messages.value.length) {
    lines.push('_开始提问后，这里生成最终文档。_')
  } else {
    messages.value.forEach((message) => {
      lines.push(`### ${message.role === 'user' ? '我的问题' : '总管回复'}`, '')
      lines.push(escapeMarkdown(message.content), '')
    })
  }
  if (currentRun.value?.candidates?.length) {
    lines.push('### Harness 证据', '')
    currentRun.value.candidates.forEach((candidate) => {
      lines.push(`- ${candidate.label}：${candidate.score} 分，${candidate.latencyMs} ms`)
    })
  }
  return lines.join('\n')
})

watch(
  sessionMarkdown,
  (value) => {
    if (!edited.value) documentHtml.value = renderMarkdown(value)
  },
  { immediate: true }
)

function openPreview(file: ChiefAttachment) {
  previewFile.value = {
    title: file.name,
    ext: file.ext.toUpperCase(),
    meta: `${file.mimeType} · ${file.size} bytes`
  }
  previewOpen.value = true
}

function quoteToAi(payload: { text: string; range: string }) {
  rightPanel.value = 'document'
  composerRef.value?.setQuote(payload)
}

function openHarnessPanel() {
  projectArtifactFullscreen.value = false
  rightPanel.value = 'harness'
  harnessVisible.value = true
}

function openDocumentPanel() {
  rightPanel.value = 'document'
  documentVisible.value = true
}

function closeRightPanel() {
  projectArtifactFullscreen.value = false
  if (rightPanel.value === 'harness') harnessVisible.value = !harnessVisible.value
  else documentVisible.value = !documentVisible.value
}

const layoutClass = computed(() => {
  const right = rightPanel.value === 'document' ? documentVisible.value : harnessVisible.value
  if (!right && !attachmentVisible.value) return 'min-[1200px]:grid-cols-[280px_minmax(0,1fr)]'
  if (!right) return 'min-[1200px]:grid-cols-[280px_minmax(0,1fr)_280px]'
  if (!attachmentVisible.value) return 'min-[1200px]:grid-cols-[280px_minmax(0,1fr)_minmax(0,1fr)]'
  return 'min-[1200px]:grid-cols-[280px_minmax(0,1fr)_minmax(0,1fr)_280px]'
})

function handleFullscreenKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && projectArtifactFullscreen.value) {
    projectArtifactFullscreen.value = false
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleFullscreenKeydown)
  try {
    const [runtime, callSettings] = await Promise.all([
      request<{
        recursionMode: 'sequential' | 'parallel'
        recursionK: number
      }>('/front/admin/chief/get-settings'),
      request<{ pushToTalkKey: string }>('/front/admin/call/get-settings')
    ])
    recursionMode.value = runtime.recursionMode
    recursionK.value = runtime.recursionK
    stopSpeechKey.value = callSettings.pushToTalkKey || 'Escape'
    await Promise.all([loadSessions(), loadProjects()])
  } catch (err) {
    error.value = normalizeApiError(err).message
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleFullscreenKeydown)
  stopMessageAudio()
})
</script>

<template>
  <div class="flex h-dvh flex-col bg-default">
    <AppTopBar title="总管" current="chief" />
    <div
      class="flex min-h-0 flex-1 flex-col overflow-y-auto min-[1200px]:grid min-[1200px]:overflow-hidden"
      :class="layoutClass"
    >
      <section
        class="flex flex-col border-b border-default min-[1200px]:min-h-0 min-[1200px]:border-e min-[1200px]:border-b-0"
        aria-label="会话列表"
      >
        <header class="flex h-12 items-center gap-2 border-b border-default px-4">
          <USelect
            v-model="sidebarMode"
            :items="[
              { label: '会话列表', value: 'sessions' },
              { label: '项目', value: 'projects' }
            ]"
            class="w-32"
            size="sm"
            aria-label="左侧内容切换"
          />
          <UBadge color="neutral" variant="subtle" size="sm">
            {{ sidebarMode === 'sessions' ? generalSessions.length : projects.length }}
          </UBadge>
          <UButton
            v-if="sidebarMode === 'sessions' && !showArchived"
            class="ms-auto"
            color="neutral"
            variant="ghost"
            square
            @click="createSession"
          >
            ＋
          </UButton>
          <UButton
            v-else-if="sidebarMode === 'projects'"
            class="ms-auto"
            color="neutral"
            variant="ghost"
            square
            aria-label="新建项目"
            @click="openProjectCreator"
          >
            ＋
          </UButton>
        </header>
        <div class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
          <template v-if="sidebarMode === 'sessions'">
            <p v-if="!generalSessions.length" class="px-2 py-4 text-xs text-muted">
              {{ showArchived ? '暂无归档会话' : '暂无会话' }}
            </p>
            <div
              v-for="session in generalSessions"
              :key="session.id"
              class="relative rounded-md"
              :class="session.id === activeSessionId ? 'bg-primary/10' : 'bg-elevated/40'"
            >
              <button
                class="w-full rounded-md px-3 py-2 pe-9 text-left"
                @click="selectSession(session.id)"
              >
                <span class="block truncate text-sm">{{ session.title }}</span>
                <span class="mt-1 block truncate text-xs text-dimmed">
                  {{ session.domain }} · {{ session.riskTier }} · {{ session.messageCount || 0 }} 条
                </span>
              </button>
              <div class="absolute end-1 top-2">
                <UDropdownMenu :items="sessionMenuItems(session)" :content="{ align: 'end' }">
                  <UButton
                    color="neutral"
                    variant="ghost"
                    square
                    size="xs"
                    :aria-label="`会话操作 ${session.title}`"
                  >
                    ⋯
                  </UButton>
                </UDropdownMenu>
              </div>
            </div>
          </template>
          <template v-else>
            <p v-if="!projects.length" class="px-2 py-4 text-xs text-muted">暂无项目</p>
            <button
              v-for="project in projects"
              :key="project.id"
              class="flex flex-col gap-2 rounded-lg border p-3 text-left transition-colors"
              :class="
                activeSession?.projectId === project.id
                  ? 'border-primary bg-primary/10'
                  : 'border-default bg-elevated/40 hover:bg-elevated/60'
              "
              @click="openProject(project)"
            >
              <span class="flex items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ project.name }}</span>
                <UBadge color="neutral" variant="subtle" size="sm">{{ project.status }}</UBadge>
              </span>
              <span class="text-xs text-muted">{{ project.description }}</span>
              <span class="text-[11px] text-dimmed">
                额度 ¥{{ project.used.toLocaleString() }} / ¥{{ project.limit.toLocaleString() }}
              </span>
            </button>
          </template>
        </div>
        <div v-if="sidebarMode === 'sessions'" class="mt-auto border-t border-default px-3 py-2">
          <UButton
            color="neutral"
            :variant="showArchived ? 'soft' : 'ghost'"
            size="sm"
            block
            @click="toggleArchived"
          >
            {{ showArchived ? '返回会话' : '已归档' }}
          </UButton>
        </div>
      </section>

      <section class="flex min-h-0 flex-col" aria-label="总管聊天">
        <header class="flex h-12 items-center gap-2 border-b border-default px-4">
          <h2 class="text-sm font-semibold">{{ activeSession?.title || '新会话' }}</h2>
          <UBadge color="neutral" variant="subtle" size="sm">{{ messages.length }}</UBadge>
          <UButton
            class="ms-auto"
            color="neutral"
            :variant="attachmentVisible ? 'soft' : 'ghost'"
            size="sm"
            @click="attachmentVisible = !attachmentVisible"
          >
            附件
          </UButton>
          <UButton color="neutral" variant="soft" size="sm" @click="openHarnessPanel">
            Harness
          </UButton>
          <UButton color="neutral" variant="soft" size="sm" @click="openDocumentPanel">
            文档
          </UButton>
        </header>
        <main ref="body" class="min-h-0 flex-1 overflow-y-auto p-4">
          <UAlert
            v-if="error"
            color="error"
            variant="subtle"
            title="总管运行失败"
            :description="error"
          />
          <UAlert
            v-if="messageActionError"
            color="error"
            variant="subtle"
            :description="messageActionError"
          />
          <div v-if="loading" class="text-sm text-muted">正在加载会话…</div>
          <ul class="mx-auto flex max-w-[720px] flex-col gap-3">
            <li
              v-for="message in messages"
              :key="message.id"
              class="flex max-w-[86%] flex-col gap-1"
              :class="message.role === 'user' ? 'self-end items-end' : 'self-start items-start'"
            >
              <!-- renderMarkdown escapes raw HTML and sanitizes unsafe URL protocols. -->
              <!-- eslint-disable vue/no-v-html -->
              <div
                class="chat-markdown rounded-lg px-3 py-2 text-sm"
                :class="message.role === 'user' ? 'bg-primary/10 text-primary' : 'bg-elevated/60'"
                v-html="renderMarkdown(message.content)"
              />
              <!-- eslint-enable vue/no-v-html -->
              <span v-if="message.attachments.length" class="text-xs text-dimmed">
                附件：{{ message.attachments.map((item) => item.name).join('、') }}
              </span>
              <span class="text-[11px] text-dimmed">
                {{ message.meta?.domain || '' }}
                {{ message.meta?.riskTier ? `· ${message.meta.riskTier}` : '' }}
              </span>
              <div v-if="message.role === 'assistant'" class="flex flex-wrap items-center gap-1">
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  :disabled="Boolean(messageActionId)"
                  @click="copyMessage(message)"
                >
                  {{ copiedMessageId === message.id ? '已复制' : '复制' }}
                </UButton>
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  :disabled="Boolean(messageActionId)"
                  @click="playMessage(message)"
                >
                  {{ playingMessageId === message.id ? '停止' : '播音' }}
                </UButton>
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  :loading="convertingMessageId === message.id"
                  :disabled="Boolean(convertingMessageId)"
                  @click="convertMessageToDocument(message)"
                >
                  {{
                    convertingMessageId === message.id
                      ? '正在写入'
                      : convertedMessageId === message.id
                        ? '已写入文档'
                        : '转成文档'
                  }}
                </UButton>
              </div>
            </li>
          </ul>
          <div v-if="sending" class="mt-4 rounded-lg bg-elevated/60 p-3 text-sm text-muted">
            {{ liveEvents.at(-1)?.message || '正在连接总管并组装上下文…' }}
          </div>
          <div
            v-if="currentRun?.status === 'awaiting_approval'"
            class="mx-auto mt-4 max-w-[720px] rounded-lg border border-warning/40 bg-warning/10 p-4"
          >
            <p class="text-sm font-medium">候选已生成，等待确认</p>
            <p class="mt-1 text-xs text-muted">
              当前为 {{ currentRun.riskTier }} 任务，采纳 Harness 变更前需要人工确认。
            </p>
            <p v-if="currentRun.autoAdoptReason" class="mt-1 text-xs text-dimmed">
              {{ currentRun.autoAdoptReason }}
            </p>
            <div class="mt-3 flex gap-2">
              <UButton @click="approveRun">采纳并完成</UButton>
              <UButton color="error" variant="outline" @click="rejectRun">拒绝候选</UButton>
            </div>
          </div>
        </main>
        <div class="flex-none">
          <div class="mx-auto w-full max-w-[720px]">
            <WorkbenchComposer
              ref="composerRef"
              placeholder="下达任务、粘贴网址，或输入 #抓取# URL、#搜索# 关键词…"
              :busy="sending"
              :stop-speech-key="stopSpeechKey"
              @barge-in="stopMessageAudio"
              @send="handleSend"
            />
          </div>
        </div>
      </section>

      <aside
        v-if="rightPanel === 'harness' ? harnessVisible : documentVisible"
        :class="
          projectArtifactFullscreen && rightPanel === 'document' && activeSession?.projectId
            ? 'fixed inset-0 z-50 flex min-h-0 flex-col bg-default'
            : 'flex min-h-0 flex-col border-t border-default min-[1200px]:border-s min-[1200px]:border-t-0'
        "
      >
        <header class="flex h-12 items-center gap-2 border-b border-default px-4">
          <h2 class="text-sm font-semibold">
            {{
              rightPanel === 'harness' ? 'Harness 运行' : activeSession?.projectId ? '文档' : '文档'
            }}
          </h2>
          <UButton
            v-if="rightPanel === 'document' && activeSession?.projectId && projectDetail"
            class="ms-auto"
            color="neutral"
            variant="soft"
            size="sm"
            @click="projectArtifactFullscreen = !projectArtifactFullscreen"
          >
            {{ projectArtifactFullscreen ? '退出全屏' : '全屏' }}
          </UButton>
          <UButton
            :class="rightPanel === 'document' && activeSession?.projectId ? '' : 'ms-auto'"
            color="neutral"
            variant="ghost"
            square
            @click="closeRightPanel"
          >
            ×
          </UButton>
        </header>

        <div v-if="rightPanel === 'document'" class="min-h-0 flex-1 overflow-y-auto">
          <div v-if="activeSession?.projectId" class="flex flex-col gap-3 p-4">
            <div v-if="projectArtifactLoading" class="text-sm text-muted">正在加载文档…</div>
            <UAlert
              v-if="projectArtifactError"
              color="error"
              variant="subtle"
              :description="projectArtifactError"
            />

            <template v-if="projectDetail">
              <div class="flex flex-wrap items-center gap-2">
                <p class="text-sm font-medium">{{ projectArtifactLabel }}</p>
                <UBadge
                  v-if="activeProjectArtifact?.latestVersionNo"
                  color="success"
                  variant="subtle"
                  size="sm"
                >
                  最新 V{{ activeProjectArtifact.latestVersionNo }}
                </UBadge>
                <UBadge v-else color="neutral" variant="subtle" size="sm"> 草稿 </UBadge>
                <UBadge
                  v-if="activeProjectArtifact?.status === 'stale'"
                  color="warning"
                  variant="subtle"
                  size="sm"
                >
                  上游已变更
                </UBadge>
              </div>

              <template v-if="projectArtifactViewingHistorical">
                <UAlert
                  color="neutral"
                  variant="subtle"
                  description="当前查看的是已保存的文档，只读；如需修改请切换到该文档对应阶段。"
                />
                <pre
                  v-if="viewedProjectArtifactKind === 'task_plan'"
                  class="max-h-[60vh] overflow-y-auto whitespace-pre-wrap rounded-md bg-elevated/50 p-3 text-sm"
                  >{{ activeProjectArtifact?.draftText }}</pre>
                <!-- renderMarkdown escapes raw HTML and sanitizes unsafe URL protocols. -->
                <!-- eslint-disable vue/no-v-html -->
                <div
                  v-else
                  class="chat-markdown max-h-[60vh] overflow-y-auto rounded-md bg-elevated/50 p-3 text-sm"
                  v-html="renderMarkdown(activeProjectArtifact?.draftText || '')"
                />
                <!-- eslint-enable vue/no-v-html -->
              </template>

              <template v-else-if="projectArtifactEditable">
                <UTextarea
                  v-if="projectDetail.phase === 'task_planning'"
                  v-model="projectArtifactDraft"
                  :rows="18"
                  placeholder="编辑计划清单 JSON"
                />
                <div v-else class="min-h-[50vh] overflow-hidden rounded-md border border-default">
                  <ClientOnly>
                    <RichTextEditor
                      v-model="projectArtifactHtml"
                      :placeholder="`编辑${projectArtifactLabel}`"
                    />
                  </ClientOnly>
                </div>
                <p v-if="projectDetail.phase === 'task_planning'" class="text-xs text-muted">
                  计划清单使用 JSON 编辑，保存后仍可继续人工调整。
                </p>
                <div class="flex flex-wrap justify-end gap-2">
                  <UButton
                    color="neutral"
                    variant="outline"
                    :loading="projectArtifactBusy"
                    @click="saveProjectArtifact"
                  >
                    保存草稿
                  </UButton>
                  <UButton
                    :loading="projectArtifactBusy"
                    :disabled="
                      projectDetail.phase === 'task_planning'
                        ? !projectArtifactDraft.trim()
                        : !projectArtifactHtml.trim()
                    "
                    @click="confirmProjectArtifact"
                  >
                    确认 V{{ nextProjectArtifactVersion }}
                  </UButton>
                </div>
              </template>

              <template v-else-if="projectDetail.phase.endsWith('_confirmed')">
                <div
                  v-if="projectDetail.phase === 'task_planning'"
                  class="max-h-[55vh] overflow-y-auto whitespace-pre-wrap rounded-md bg-elevated/50 p-3 text-sm"
                >
                  {{ activeProjectArtifact?.draftText || projectArtifactDraft }}
                </div>
                <!-- renderMarkdown escapes raw HTML and sanitizes unsafe URL protocols. -->
                <!-- eslint-disable vue/no-v-html -->
                <div
                  v-else
                  class="chat-markdown max-h-[55vh] overflow-y-auto rounded-md bg-elevated/50 p-3 text-sm"
                  v-html="renderMarkdown(activeProjectArtifact?.draftText || projectArtifactDraft)"
                />
                <!-- eslint-enable vue/no-v-html -->
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <span class="text-xs text-muted">
                    {{
                      projectDetail.phase === 'requirements_confirmed'
                        ? '发送 #生成方案# 进入方案阶段'
                        : '发送 #生成计划# 进入任务计划阶段'
                    }}
                  </span>
                  <UButton
                    color="neutral"
                    variant="outline"
                    :loading="projectArtifactBusy"
                    @click="adjustConfirmedProjectArtifact"
                  >
                    继续调整
                  </UButton>
                </div>
              </template>

              <template v-else-if="projectDetail.phase === 'tasks_confirmed'">
                <p class="text-sm text-muted">
                  需求、方案和计划均已确认。发送
                  <code>#开始执行#</code> 后创建任务并进入项目工作台。
                </p>
                <UButton
                  color="neutral"
                  variant="outline"
                  :loading="projectArtifactBusy"
                  @click="adjustConfirmedProjectArtifact"
                >
                  继续调整计划
                </UButton>
              </template>

              <template v-else>
                <UAlert
                  color="neutral"
                  variant="subtle"
                  :description="
                    projectDetail.phase === 'executing'
                      ? '任务正在执行，完成后进入项目工作台确认成果。'
                      : '后续任务执行与成果确认请在项目工作台完成。'
                  "
                />
              </template>

              <details
                v-if="activeProjectArtifact?.versions?.length"
                class="rounded-md border border-default p-3 text-xs"
              >
                <summary class="cursor-pointer font-medium">
                  历史版本（{{ activeProjectArtifact.versions.length }}）
                </summary>
                <div class="mt-2 flex flex-col gap-2">
                  <details
                    v-for="version in activeProjectArtifact.versions"
                    :key="version.id"
                    class="rounded bg-elevated/40 p-2"
                  >
                    <summary class="cursor-pointer">
                      V{{ version.versionNo }} · {{ version.confirmedAt }}
                      {{ version.sourceVersionNo ? `· 基于上游 V${version.sourceVersionNo}` : '' }}
                    </summary>
                    <!-- renderMarkdown escapes raw HTML and sanitizes unsafe URL protocols. -->
                    <!-- eslint-disable vue/no-v-html -->
                    <div
                      class="chat-markdown mt-2 max-h-40 overflow-y-auto"
                      v-html="renderMarkdown(version.contentText)"
                    />
                    <!-- eslint-enable vue/no-v-html -->
                  </details>
                </div>
              </details>
            </template>
          </div>

          <ClientOnly v-else>
            <RichTextEditor
              v-model="documentHtml"
              placeholder="编辑最终文档…"
              @quote="quoteToAi"
              @change="edited = true"
            />
          </ClientOnly>
        </div>

        <div v-else class="min-h-0 flex-1 overflow-y-auto p-4">
          <UAlert
            v-if="!currentRun && !liveEvents.length"
            color="neutral"
            variant="subtle"
            title="尚无运行"
            description="发送任务后，这里显示 Harness 候选、评分和执行轨迹。"
          />
          <ol v-if="liveEvents.length && !currentRun" class="flex flex-col gap-2">
            <li
              v-for="event in liveEvents"
              :key="`${event.seq}-${event.stage}`"
              class="flex gap-2 text-xs"
            >
              <span class="mt-1 size-2 shrink-0 rounded-full bg-primary" />
              <div>
                <p class="font-medium text-default">{{ event.stage }}</p>
                <p class="text-muted">{{ event.message }}</p>
              </div>
            </li>
          </ol>
          <template v-else-if="currentRun">
            <div class="flex items-center gap-2">
              <UBadge :color="currentRun.status === 'completed' ? 'success' : 'warning'">
                {{ currentRun.status }}
              </UBadge>
              <span class="text-xs text-muted"
                >{{ currentRun.domain }} · {{ currentRun.riskTier }}</span
              >
              <span class="ms-auto text-xs text-muted">{{ currentRun.modelName }}</span>
            </div>
            <p class="mt-2 text-xs text-muted">
              {{ currentRun.recursionMode || 'sequential' }} · K={{ currentRun.recursionK || 1 }} ·
              Tokens {{ (currentRun.inputTokens || 0) + (currentRun.outputTokens || 0) }} · 预估 ¥{{
                Number(currentRun.estimatedCost || 0).toFixed(4)
              }}
              · 回归 {{ currentRun.regressionPassed === false ? '未通过' : '通过/未触发' }}
            </p>
            <p v-if="currentRun.autoAdoptReason" class="mt-1 text-xs text-dimmed">
              {{ currentRun.autoAdoptReason }}
            </p>

            <ol class="mt-4 flex flex-col gap-2">
              <li v-for="event in currentRun.events" :key="event.seq" class="flex gap-2 text-xs">
                <span
                  class="mt-1 size-2 shrink-0 rounded-full"
                  :class="event.status === 'failed' ? 'bg-error' : 'bg-success'"
                />
                <div>
                  <p class="font-medium text-default">{{ event.stage }}</p>
                  <p class="text-muted">{{ event.message }}</p>
                </div>
              </li>
            </ol>

            <div class="mt-5 flex flex-col gap-3">
              <article
                v-for="candidate in currentRun.candidates"
                :key="candidate.id"
                class="rounded-lg border p-3"
                :class="
                  candidate.harnessId === currentRun.selectedHarnessId
                    ? 'border-primary bg-primary/5'
                    : 'border-default bg-elevated/30'
                "
              >
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium">{{ candidate.label }}</span>
                  <UBadge color="neutral" variant="subtle" size="sm">{{ candidate.scope }}</UBadge>
                  <span class="ms-auto text-sm font-semibold">{{ candidate.score }}</span>
                </div>
                <p class="mt-1 text-xs text-muted">
                  第 {{ candidate.step || 1 }} 步 · {{ candidate.latencyMs }} ms ·
                  {{ candidate.trace.diff?.length || 0 }} 个组件变化 ·
                  {{ candidate.trace.ok ? '执行成功' : '执行失败' }} · ¥{{
                    Number(candidate.estimatedCost || 0).toFixed(4)
                  }}
                </p>
                <div class="mt-2 flex flex-wrap gap-1">
                  <UBadge
                    v-for="change in candidate.trace.diff || []"
                    :key="change.component"
                    color="neutral"
                    variant="subtle"
                    size="sm"
                  >
                    {{ change.component }}
                  </UBadge>
                </div>
                <!-- Candidate answers use the same sanitized Markdown renderer as chat bubbles. -->
                <!-- eslint-disable vue/no-v-html -->
                <div
                  class="chat-markdown mt-3 max-h-44 overflow-y-auto rounded-md bg-default/60 p-2 text-xs"
                  v-html="renderMarkdown(candidate.answer)"
                />
                <!-- eslint-enable vue/no-v-html -->
              </article>
            </div>

            <UButton
              v-if="currentRun.status === 'awaiting_approval'"
              class="mt-4 w-full"
              @click="approveRun"
            >
              采纳当前候选并完成
            </UButton>
          </template>
        </div>
      </aside>

      <aside
        v-if="attachmentVisible"
        class="flex min-h-0 flex-col border-t border-default min-[1200px]:border-s min-[1200px]:border-t-0"
      >
        <header class="flex h-12 items-center gap-2 border-b border-default px-4">
          <h2 class="text-sm font-semibold">附件</h2>
          <UBadge size="sm" color="neutral" variant="subtle">{{ attachmentTotalCount }}</UBadge>
        </header>
        <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
          <UAlert
            v-if="generatedDocumentError"
            color="error"
            variant="subtle"
            :description="generatedDocumentError"
          />
          <template v-if="sessionDocuments.length">
            <p class="px-1 text-xs font-medium text-muted">文档</p>
            <div
              v-for="document in sessionDocuments"
              :key="document.id"
              class="rounded-md bg-elevated/40 p-3"
            >
              <button class="w-full text-left" @click="openManagedDocument(document)">
                <span class="flex items-center gap-2">
                  <span class="min-w-0 flex-1 truncate text-sm">{{ document.title }}</span>
                  <UBadge
                    :color="
                      document.attached
                        ? 'success'
                        : document.status === 'stale'
                          ? 'warning'
                          : document.status === 'confirmed'
                            ? 'success'
                            : 'neutral'
                    "
                    variant="subtle"
                    size="sm"
                  >
                    {{ document.attached ? '已加入会话' : documentStateLabel(document) }}
                  </UBadge>
                </span>
                <span class="mt-1 block text-xs text-dimmed">
                  {{ documentKindLabel(document) }} · {{ document.contentText.length }} 字符
                </span>
              </button>
              <div class="mt-2 flex justify-end gap-1">
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  :disabled="document.attached || generatedDocumentBusy"
                  @click="attachGeneratedDocument(document)"
                >
                  {{ document.attached ? '已加入会话' : '加入会话' }}
                </UButton>
                <UButton
                  color="error"
                  variant="ghost"
                  size="xs"
                  :disabled="generatedDocumentBusy"
                  @click="deleteGeneratedDocument(document)"
                >
                  {{ pendingDeleteDocumentId === document.id ? '确认删除' : '删除' }}
                </UButton>
              </div>
            </div>
          </template>
          <p v-if="attachments.length" class="px-1 pt-2 text-xs font-medium text-muted">会话附件</p>
          <button
            v-for="file in attachments"
            :key="file.uuid"
            class="w-full rounded-md bg-elevated/40 p-3 text-left"
            @click="openPreview(file)"
          >
            <span class="block truncate text-sm">{{ file.name }}</span>
            <span class="mt-1 block text-xs text-dimmed">
              {{ file.ext.toUpperCase() }} · {{ file.role === 'user' ? '输入' : '产出' }} ·
              {{ file.size }} bytes
            </span>
          </button>
          <p v-if="!attachmentTotalCount" class="text-xs text-muted">暂无附件</p>
        </div>
      </aside>
    </div>

    <UModal v-model:open="generatedDocumentOpen" title="编辑文档">
      <template #body>
        <div class="flex flex-col gap-3">
          <UFormField label="文档标题" required>
            <UInput v-model="generatedDocumentTitle" class="w-full" maxlength="200" />
          </UFormField>
          <UAlert
            v-if="generatedDocumentError"
            color="error"
            variant="subtle"
            :description="generatedDocumentError"
          />
          <div class="h-[55vh] min-h-[320px] overflow-hidden rounded-md border border-default">
            <ClientOnly>
              <RichTextEditor
                v-model="generatedDocumentHtml"
                placeholder="编辑文档正文…"
                @change="generatedDocumentError = ''"
              />
            </ClientOnly>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full flex-wrap items-center justify-end gap-2">
          <UButton
            v-if="activeGeneratedDocument"
            color="neutral"
            variant="outline"
            :disabled="activeGeneratedDocument.attached || generatedDocumentBusy"
            @click="attachGeneratedDocument(activeGeneratedDocument)"
          >
            {{ activeGeneratedDocument.attached ? '已加入会话' : '加入会话' }}
          </UButton>
          <UButton color="neutral" variant="ghost" @click="generatedDocumentOpen = false">
            关闭
          </UButton>
          <UButton :loading="generatedDocumentBusy" @click="saveGeneratedDocument">
            保存文档
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="projectCreatorOpen" title="新建项目">
      <template #body>
        <div class="flex flex-col gap-4">
          <UAlert
            v-if="projectCreatorError"
            color="error"
            variant="subtle"
            title="新建项目失败"
            :description="projectCreatorError"
          />
          <UFormField label="项目名称" required>
            <UInput
              v-model="projectCreatorForm.name"
              placeholder="例如：Mac App 开发"
              class="w-full"
              autofocus
            />
          </UFormField>
          <UFormField label="项目说明">
            <UTextarea
              v-model="projectCreatorForm.description"
              :rows="4"
              placeholder="目标、范围、背景或当前想法"
              class="w-full"
            />
          </UFormField>
          <UFormField label="项目专家">
            <USelect
              v-model="projectCreatorForm.expertId"
              :items="projectExpertOptions"
              class="w-full"
            />
            <p class="mt-1 text-xs text-muted">
              选择“自动”时，生成需求或方案时会自动绑定具备可用模型的专家。
            </p>
          </UFormField>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="projectCreatorOpen = false">
            取消
          </UButton>
          <UButton
            :disabled="!projectCreatorForm.name.trim() || projectCreatorBusy"
            :loading="projectCreatorBusy"
            @click="createProjectFromChief"
          >
            创建项目
          </UButton>
        </div>
      </template>
    </UModal>

    <FilePreview v-model:open="previewOpen" :file="previewFile" />
  </div>
</template>

<style scoped>
.chat-markdown :deep(> :first-child) {
  margin-top: 0;
}

.chat-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.chat-markdown :deep(p) {
  margin: 0.5rem 0;
  line-height: 1.7;
}

.chat-markdown :deep(h1),
.chat-markdown :deep(h2),
.chat-markdown :deep(h3) {
  margin: 0.9rem 0 0.45rem;
  font-weight: 650;
  line-height: 1.35;
}

.chat-markdown :deep(h1) {
  font-size: 1.15rem;
}

.chat-markdown :deep(h2) {
  font-size: 1.05rem;
}

.chat-markdown :deep(h3) {
  font-size: 1rem;
}

.chat-markdown :deep(ul),
.chat-markdown :deep(ol) {
  margin: 0.5rem 0;
  padding-inline-start: 1.35rem;
}

.chat-markdown :deep(ul) {
  list-style: disc;
}

.chat-markdown :deep(ol) {
  list-style: decimal;
}

.chat-markdown :deep(li) {
  margin: 0.25rem 0;
  line-height: 1.65;
}

.chat-markdown :deep(blockquote) {
  margin: 0.65rem 0;
  border-inline-start: 3px solid var(--ui-border);
  padding-inline-start: 0.75rem;
  color: var(--ui-text-muted);
}

.chat-markdown :deep(code) {
  border-radius: 0.25rem;
  background: var(--ui-bg-elevated);
  padding: 0.1rem 0.3rem;
  font-size: 0.9em;
}

.chat-markdown :deep(pre) {
  margin: 0.65rem 0;
  overflow-x: auto;
  border-radius: 0.5rem;
  background: var(--ui-bg-elevated);
  padding: 0.75rem;
}

.chat-markdown :deep(pre code) {
  background: transparent;
  padding: 0;
}

.chat-markdown :deep(table) {
  margin: 0.65rem 0;
  width: 100%;
  border-collapse: collapse;
}

.chat-markdown :deep(th),
.chat-markdown :deep(td) {
  border: 1px solid var(--ui-border);
  padding: 0.4rem 0.55rem;
  text-align: start;
}

.chat-markdown :deep(a) {
  color: var(--ui-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}
</style>
