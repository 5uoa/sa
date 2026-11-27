﻿
<script setup lang="ts">
import { getAdminToken } from '~/composables/useAdminSession'
import { renderMarkdown } from '~/utils/markdown'

interface ExpertTool {
  id: string
  name: string
  description: string
  meta: string
  /** 连接/加载状态：新注册为未测试，测试后标记可用或异常 */
  status: '可用' | '异常' | '未测试'
  /** MCP 的启动命令或 URL、模型的 API 地址；SKILL 为空 */
  endpoint?: string
  modelKey?: string
  config?: Record<string, unknown>
  /** 模型是否已配置 API Key（后端仅返回密文掩码，不回传明文） */
  hasApiKey?: boolean
  apiKeyMask?: string
  hasSecrets?: boolean
  secretKeys?: string[]
  provider?: string
  capabilities?: ModelCapabilities
  enabled?: boolean
  priority?: number
  healthStatus?: 'healthy' | 'degraded' | 'down' | 'unknown'
}

interface ModelCapabilities {
  contextWindow?: number
  maxOutputTokens?: number
  tools?: boolean
  vision?: boolean
  json?: boolean
  streaming?: boolean
  embeddings?: boolean
  audio?: boolean
}

interface Expert {
  id: string
  name: string
  role: string
  model: string
  modelId?: string
  temperature: string
  prompt: string
  enabled: boolean
  mcpIds: string[]
  skillIds: string[]
  settings?: {
    maxToolSteps?: number
    allowWriteTools?: boolean
    toolTimeoutSeconds?: number
    maxOutputTokens?: number
    contextBudgetTokens?: number
    routingMode?: 'fixed' | 'fallback' | 'auto'
    fallbackModelIds?: string[]
    toolPolicies?: Record<string, 'allow' | 'deny' | 'confirm'>
  }
}

/** 专家管理：专家 Agent / 模型 / MCP / SKILL 四类资源的注册与配置（数据来自管理后台接口） */

const mcpServers = ref<ExpertTool[]>([])
const skills = ref<ExpertTool[]>([])
/** 模型注册表：专家设置的模型下拉只读取这里的可用项 */
const models = ref<ExpertTool[]>([])
const experts = ref<Expert[]>([])

/** 标签页：模型 / MCP / SKILL 各自独立管理，专家页做能力授权 */
type TabKey = 'model' | 'mcp' | 'skill' | 'expert'
type RegistryKind = 'mcp' | 'skill' | 'model'
type ConfigTab = 'basic' | 'mcp' | 'tools' | 'skill'
type StatusColor = 'success' | 'error' | 'warning' | 'neutral'

const props = defineProps<{ kind: TabKey }>()
const emit = defineEmits<{ manage: [kind: RegistryKind] }>()

const registryKind = computed<RegistryKind>(() => (props.kind === 'expert' ? 'mcp' : props.kind))
const registryTitle = computed(() => {
  if (registryKind.value === 'mcp') return 'MCP 注册'
  return registryKind.value === 'skill' ? 'SKILL 注册' : '模型注册'
})
const registryUnit = computed(() => {
  if (registryKind.value === 'mcp') return 'MCP'
  return registryKind.value === 'skill' ? 'SKILL' : '模型'
})
const registrySubtitle = computed(() => {
  if (registryKind.value === 'mcp') return '统一登记 MCP 服务，测试通过后在专家设置中授权使用'
  return registryKind.value === 'skill'
    ? '统一登记 SKILL 能力，专家按需勾选启用'
    : '统一登记可用模型，专家设置中的模型列表取自这里'
})

const modelOptions = computed(() => models.value.map((model) => model.name))
function modelIdByName(name: string) {
  return models.value.find((item) => item.name === name)?.id || configDraft.value.modelId || ''
}
const temperatureOptions = ['精确 · 0.2', '均衡 · 0.7', '发散 · 1.0']
const routingModeOptions = [
  { label: '固定模型', value: 'fixed' },
  { label: '主模型 + 备用模型', value: 'fallback' },
  { label: '自动选择', value: 'auto' }
]
const fallbackModelOptions = computed(() =>
  models.value
    .filter((model) => model.name !== configDraft.value.model)
    .map((model) => ({ label: model.name, value: model.id }))
)

/** 状态徽标配色：可用为成功色，异常为错误色，未测试为中性色 */
function statusColor(status: ExpertTool['status']): StatusColor {
  if (status === '可用') return 'success'
  if (status === '异常') return 'error'
  return 'neutral'
}

function healthColor(status?: ExpertTool['healthStatus']): StatusColor {
  if (status === 'healthy') return 'success'
  if (status === 'degraded') return 'warning'
  if (status === 'down') return 'error'
  return 'neutral'
}

function providerLabel(value?: string) {
  return providerOptions.find((item) => item.value === value)?.label || 'OpenAI 兼容'
}

function capabilityLabels(tool: ExpertTool) {
  const labels: string[] = []
  if (tool.capabilities?.tools) labels.push('工具')
  if (tool.capabilities?.vision) labels.push('视觉')
  if (tool.capabilities?.json) labels.push('JSON')
  if (tool.capabilities?.streaming) labels.push('流式')
  return labels
}

/** 接口数据加载：每类资源独立维护加载状态与错误提示 */
type ResourceKey = RegistryKind | 'expert'

const loading = reactive<Record<ResourceKey, boolean>>({
  model: false,
  mcp: false,
  skill: false,
  expert: false
})
const loadErrors = reactive<Record<ResourceKey, string>>({
  model: '',
  mcp: '',
  skill: '',
  expert: ''
})
/** 进行中的请求：避免同一资源被重复并发拉取 */
const pendingResources = new Set<ResourceKey>()

const registryPaths: Record<RegistryKind, string> = {
  model: 'models',
  mcp: 'mcp',
  skill: 'skills'
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

async function request<T>(path: string, body: Record<string, unknown> = {}) {
  const response = await useApi<ApiEnvelope<T>>(path, body)
  if (response.code !== 200) {
    throw new Error(response.message || '请求失败，请重试')
  }
  return response.data
}

async function loadRegistry(kind: RegistryKind) {
  if (pendingResources.has(kind)) return
  pendingResources.add(kind)
  loading[kind] = true
  loadErrors[kind] = ''
  try {
    const data = await request<{ items: ExpertTool[] }>(`/front/admin/${registryPaths[kind]}/list`)
    const items = data.items ?? []
    if (kind === 'model') models.value = items
    else if (kind === 'mcp') mcpServers.value = items
    else skills.value = items
  } catch (error) {
    loadErrors[kind] = normalizeApiError(error).message
  } finally {
    loading[kind] = false
    pendingResources.delete(kind)
  }
}

async function loadExperts() {
  if (pendingResources.has('expert')) return
  pendingResources.add('expert')
  loading.expert = true
  loadErrors.expert = ''
  try {
    const data = await request<{ items: Expert[] }>('/front/admin/experts/list')
    experts.value = data.items ?? []
  } catch (error) {
    loadErrors.expert = normalizeApiError(error).message
  } finally {
    loading.expert = false
    pendingResources.delete('expert')
  }
}

function loadAll() {
  void loadRegistry('model')
  void loadRegistry('mcp')
  void loadRegistry('skill')
  void loadExperts()
}

onMounted(loadAll)

/** 专家配置弹窗：以草稿编辑，保存后写回列表 */
const configOpen = ref(false)
const configDraft = ref<Expert>({
  id: '',
  name: '',
  role: '',
  model: '',
  temperature: '均衡 · 0.7',
  prompt: '',
  enabled: true,
  mcpIds: [],
  skillIds: [],
  settings: {
    maxToolSteps: 6,
    allowWriteTools: false,
    toolTimeoutSeconds: 20,
    maxOutputTokens: 2000,
    contextBudgetTokens: 0,
    routingMode: 'fixed',
    fallbackModelIds: [],
    toolPolicies: {}
  }
})
const testing = ref(false)
const testResult = ref<{ ok: boolean; text: string } | null>(null)
const configError = ref('')

/** 配置弹窗分区：基础设置 / MCP / SKILL，避免授权项过多时滚动过长 */
const configTab = ref<ConfigTab>('basic')
const mcpQuery = ref('')
const skillQuery = ref('')

interface McpToolInfo {
  mcpId: string
  name: string
  description: string
  readOnly: boolean
  parameters: Record<string, unknown>
}

const mcpTools = ref<Record<string, McpToolInfo[]>>({})
const mcpToolWarnings = ref<Record<string, string[]>>({})
const mcpToolLoading = ref<Record<string, boolean>>({})
const toolPolicyOptions = [
  { label: '安全默认', value: 'default' },
  { label: '直接允许', value: 'allow' },
  { label: '禁止', value: 'deny' },
  { label: '每次确认', value: 'confirm' }
]

function toolPolicyKey(mcpId: string, toolName: string) {
  return `${mcpId}:${toolName}`
}

function toolPolicy(mcpId: string, toolName: string) {
  return configDraft.value.settings?.toolPolicies?.[toolPolicyKey(mcpId, toolName)] || 'default'
}

function setToolPolicy(mcpId: string, toolName: string, value: string) {
  let policies = {
    ...(configDraft.value.settings?.toolPolicies || {})
  }
  const key = toolPolicyKey(mcpId, toolName)
  if (value === 'default') {
    policies = Object.fromEntries(
      Object.entries(policies).filter(([item]) => item !== key)
    ) as Record<string, 'allow' | 'deny' | 'confirm'>
  } else policies[key] = value as 'allow' | 'deny' | 'confirm'
  configDraft.value.settings = {
    ...(configDraft.value.settings || {}),
    toolPolicies: policies
  }
}

async function loadMcpTools(server: ExpertTool, force = false) {
  if (!force && (mcpTools.value[server.id] || mcpToolLoading.value[server.id])) return
  mcpToolLoading.value[server.id] = true
  mcpToolWarnings.value[server.id] = []
  try {
    const result = await request<{ items: McpToolInfo[]; warnings?: string[] }>(
      '/front/admin/mcp/tools',
      { id: server.id }
    )
    mcpTools.value[server.id] = result.items || []
    mcpToolWarnings.value[server.id] = result.warnings || []
  } catch (error) {
    mcpToolWarnings.value[server.id] = [normalizeApiError(error).message]
  } finally {
    mcpToolLoading.value[server.id] = false
  }
}

async function loadSelectedMcpTools() {
  await Promise.all(
    configDraft.value.mcpIds
      .map((id) => mcpServers.value.find((item) => item.id === id))
      .filter((item): item is ExpertTool => Boolean(item))
      .map((item) => loadMcpTools(item))
  )
}

const configMcpCount = computed(() => configDraft.value.mcpIds.length)
const configSkillCount = computed(() => configDraft.value.skillIds.length)

const configTabItems = computed(() => [
  { label: '基础设置', value: 'basic' },
  { label: 'MCP', value: 'mcp', badge: `${configMcpCount.value}/${mcpServers.value.length}` },
  {
    label: '工具权限',
    value: 'tools',
    badge: `${Object.keys(configDraft.value.settings?.toolPolicies || {}).length}`
  },
  { label: 'SKILL', value: 'skill', badge: `${configSkillCount.value}/${skills.value.length}` }
])

const filteredMcpServers = computed(() => {
  const query = mcpQuery.value.trim().toLowerCase()
  if (!query) return mcpServers.value
  return mcpServers.value.filter((server) =>
    `${server.name} ${server.description}`.toLowerCase().includes(query)
  )
})

const selectedMcpServers = computed(() =>
  mcpServers.value.filter((server) => configDraft.value.mcpIds.includes(server.id))
)

const selectedSkills = computed(() =>
  skills.value.filter((skill) => configDraft.value.skillIds.includes(skill.id))
)

const filteredSkills = computed(() => {
  const query = skillQuery.value.trim().toLowerCase()
  if (!query) return skills.value
  return skills.value.filter((skill) =>
    `${skill.name} ${skill.description}`.toLowerCase().includes(query)
  )
})

function openExpertConfig(expert: Expert) {
  configDraft.value = {
    ...expert,
    mcpIds: [...expert.mcpIds],
    skillIds: [...expert.skillIds],
    settings: {
      maxToolSteps: expert.settings?.maxToolSteps ?? 6,
      allowWriteTools: expert.settings?.allowWriteTools ?? false,
      toolTimeoutSeconds: expert.settings?.toolTimeoutSeconds ?? 20,
      maxOutputTokens: expert.settings?.maxOutputTokens ?? 2000,
      contextBudgetTokens: expert.settings?.contextBudgetTokens ?? 0,
      routingMode: expert.settings?.routingMode ?? 'fixed',
      fallbackModelIds: [...(expert.settings?.fallbackModelIds || [])],
      toolPolicies: { ...(expert.settings?.toolPolicies || {}) }
    }
  }
  configTab.value = 'basic'
  mcpQuery.value = ''
  skillQuery.value = ''
  testResult.value = null
  configError.value = ''
  configOpen.value = true
}

function closeExpertConfig() {
  configOpen.value = false
  testResult.value = null
  configError.value = ''
}

function applyConfig() {
  const target = experts.value.find((expert) => expert.id === configDraft.value.id)
  if (!target) return
  Object.assign(target, configDraft.value, {
    mcpIds: [...configDraft.value.mcpIds],
    skillIds: [...configDraft.value.skillIds]
  })
}

function isMcpEnabled(id: string) {
  return configDraft.value.mcpIds.includes(id)
}

function toggleMcp(id: string) {
  const ids = configDraft.value.mcpIds
  const index = ids.indexOf(id)
  if (index === -1) {
    ids.push(id)
  } else {
    ids.splice(index, 1)
  }
}

function isSkillEnabled(id: string) {
  return configDraft.value.skillIds.includes(id)
}

function toggleSkill(id: string) {
  const ids = configDraft.value.skillIds
  const index = ids.indexOf(id)
  if (index === -1) {
    ids.push(id)
  } else {
    ids.splice(index, 1)
  }
}

/** 批量授权：仅作用于当前搜索结果 */
function toggleAllMcp(enabled: boolean) {
  const ids = new Set(configDraft.value.mcpIds)
  filteredMcpServers.value.forEach((server) => {
    if (enabled) ids.add(server.id)
    else ids.delete(server.id)
  })
  configDraft.value.mcpIds = [...ids]
}

function toggleAllSkill(enabled: boolean) {
  const ids = new Set(configDraft.value.skillIds)
  filteredSkills.value.forEach((skill) => {
    if (enabled) ids.add(skill.id)
    else ids.delete(skill.id)
  })
  configDraft.value.skillIds = [...ids]
}

/** 写回专家配置（不关闭弹窗），供保存与保存并测试共用 */
async function persistExpert() {
  const draft = configDraft.value
  await request('/front/admin/experts/update', {
    id: draft.id,
    name: draft.name,
    role: draft.role,
    model: draft.model,
    modelId: modelIdByName(draft.model),
    temperature: draft.temperature,
    prompt: draft.prompt,
    enabled: draft.enabled,
    mcpIds: [...draft.mcpIds],
    skillIds: [...draft.skillIds],
    settings: {
      maxToolSteps: Number(draft.settings?.maxToolSteps ?? 6),
      allowWriteTools: Boolean(draft.settings?.allowWriteTools),
      toolTimeoutSeconds: Number(draft.settings?.toolTimeoutSeconds ?? 20),
      maxOutputTokens: Number(draft.settings?.maxOutputTokens ?? 2000),
      contextBudgetTokens: Number(draft.settings?.contextBudgetTokens ?? 0),
      routingMode: draft.settings?.routingMode || 'fixed',
      fallbackModelIds: [...(draft.settings?.fallbackModelIds || [])],
      toolPolicies: { ...(draft.settings?.toolPolicies || {}) }
    }
  })
  applyConfig()
  await loadExperts()
}

async function saveConfig() {
  configError.value = ''
  try {
    await persistExpert()
    closeExpertConfig()
  } catch (error) {
    configError.value = normalizeApiError(error).message
  }
}

/** 保存并测试：先持久化配置，再按所选模型真实探测供应商 */
async function saveAndTestConfig() {
  if (testing.value || !configOpen.value) return
  testing.value = true
  testResult.value = null
  configError.value = ''
  try {
    await persistExpert()
    const result = await request<{
      ok: boolean
      message: string
      model: string
      latencyMs: number
      mcpCount: number
      skillCount: number
      checks?: Array<{ kind: string; name: string; ok: boolean; message: string }>
    }>('/front/admin/experts/test', { id: configDraft.value.id })
    testResult.value = {
      ok: result.ok,
      text: result.ok
        ? `测试通过：${result.message}`
        : `测试未通过：${result.message}${
            result.checks?.length
              ? `（${result.checks
                  .filter((item) => !item.ok)
                  .map((item) => item.name)
                  .join('、')}）`
              : ''
          }`
    }
  } catch (error) {
    configError.value = normalizeApiError(error).message
  } finally {
    testing.value = false
  }
}

/** 配置弹窗内跳转到对应注册模块（由后台页切换左侧导航） */
function manageRegistry(tab: RegistryKind) {
  closeExpertConfig()
  emit('manage', tab)
}

/** 新建专家：弹窗填写名称与职责，创建后选中并配置 MCP / SKILL */
const expertDialogOpen = ref(false)
const expertDraft = ref({ name: '', role: '' })
const expertDialogError = ref('')
const expertActionError = ref('')

interface ExpertChatMessage {
  role: 'user' | 'assistant'
  content: string
  meta?: string
  attachments?: ChatAttachment[]
}

interface ChatAttachment {
  uuid: string
  name: string
  ext: string
  size: number
  mimeType: string
  previewUrl?: string
  isImage: boolean
}

interface ExpertRun {
  id: string
  sessionId?: string
  model: string
  question: string
  answer: string
  status: 'completed' | 'failed' | 'awaiting_approval'
  toolTrace: Array<{
    step: number
    alias: string
    mcp: string
    tool: string
    ok: boolean
    durationMs: number
    resultPreview: string
  }>
  warnings: string[]
  inputTokens: number
  outputTokens: number
  latencyMs: number
  cost?: number
  modelAttempts?: Array<{
    model: string
    status: string
    message?: string
    latencyMs?: number
    cost?: number
  }>
  pendingApproval?: {
    runId?: string
    calls: Omit<ApprovalCall, 'approved'>[]
  }
  createTime: string
}

interface ExpertSessionSummary {
  id: string
  expertId: string
  title: string
  messageCount: number
  preview: string
  createTime: string
  updateTime: string
}

const chatOpen = ref(false)
const chatExpert = ref<Expert | null>(null)
const chatSessionId = ref('')
const chatMessages = ref<ExpertChatMessage[]>([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatError = ref('')
const chatWarnings = ref<string[]>([])
const chatToolTrace = ref<
  Array<{
    step: number
    alias: string
    mcp: string
    tool: string
    ok: boolean
    durationMs: number
    resultPreview: string
  }>
>([])
interface ApprovalCall {
  callId: string
  kind: string
  mcp: string
  tool: string
  risk: string
  requiresConfirmation: boolean
  arguments: Record<string, unknown>
  approved: boolean
}

interface ExpertChatResult {
  ok: boolean
  content: string
  message: string
  model: string
  latencyMs: number
  warnings?: string[]
  toolTrace?: typeof chatToolTrace.value
  usedTools?: number
  provider?: string
  cost?: number
  contextBudget?: {
    estimatedTokens?: number
    budgetTokens?: number
    droppedMessages?: number
  }
  modelAttempts?: Array<{
    model: string
    status: string
    message?: string
    latencyMs?: number
    cost?: number
  }>
  runId?: string
  sessionId?: string
  requiresApproval?: boolean
  pendingApproval?: {
    runId?: string
    calls: Omit<ApprovalCall, 'approved'>[]
  } | null
}

const chatApproval = ref<{ runId: string; calls: ApprovalCall[] } | null>(null)
const chatResuming = ref(false)
const chatRuns = ref<ExpertRun[]>([])
const chatRunsLoading = ref(false)
const chatRunsError = ref('')
const chatSessions = ref<ExpertSessionSummary[]>([])
const chatSessionsLoading = ref(false)
const chatSessionsError = ref('')
const chatScroll = ref<HTMLElement | null>(null)
const pendingChatAttachments = ref<ChatAttachment[]>([])
const chatUploading = ref(false)
const attachmentInput = ref<{ inputRef?: HTMLInputElement } | null>(null)
const previewUrls = new Set<string>()

interface BrowserSpeechRecognition {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    0: { transcript: string }
    isFinal: boolean
  }>
}

let recognition: BrowserSpeechRecognition | null = null
let callTimer: ReturnType<typeof setInterval> | null = null
let speechResumeTimer: ReturnType<typeof setTimeout> | null = null
const inCall = ref(false)
const callMuted = ref(false)
const callSpeaking = ref(false)
const speakerOn = ref(true)
const callSeconds = ref(0)
const callTime = computed(() => {
  const minutes = String(Math.floor(callSeconds.value / 60)).padStart(2, '0')
  const seconds = String(callSeconds.value % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
})

async function scrollChatToBottom() {
  await nextTick()
  if (chatScroll.value) chatScroll.value.scrollTop = chatScroll.value.scrollHeight
}

function formatRunTime(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

async function loadChatRuns(expertId: string) {
  if (chatRunsLoading.value) return
  chatRunsLoading.value = true
  chatRunsError.value = ''
  try {
    const result = await request<{ items: ExpertRun[] }>('/front/admin/experts/runs', {
      id: expertId,
      limit: 5
    })
    if (chatExpert.value?.id === expertId) chatRuns.value = result.items || []
  } catch (error) {
    chatRunsError.value = normalizeApiError(error).message
  } finally {
    chatRunsLoading.value = false
  }
}

async function loadChatSessions(expertId: string) {
  if (chatSessionsLoading.value) return
  chatSessionsLoading.value = true
  chatSessionsError.value = ''
  try {
    const result = await request<{ items: ExpertSessionSummary[] }>(
      '/front/admin/experts/sessions/list',
      { id: expertId, limit: 30 }
    )
    if (chatExpert.value?.id === expertId) {
      chatSessions.value = result.items || []
    }
  } catch (error) {
    chatSessionsError.value = normalizeApiError(error).message
  } finally {
    chatSessionsLoading.value = false
  }
}

function restoreRunApproval(run: ExpertRun) {
  const calls = run.pendingApproval?.calls || []
  if (!calls.length) return
  chatApproval.value = {
    runId: run.pendingApproval?.runId || run.id,
    calls: calls.map((call) => ({ ...call, approved: false }))
  }
  chatError.value = ''
}

function clearChatPreviews() {
  for (const url of previewUrls) URL.revokeObjectURL(url)
  previewUrls.clear()
}

async function onChatFilesChange(event: Event) {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files ?? [])
  target.value = ''
  if (!files.length) return
  if (pendingChatAttachments.value.length + files.length > 5) {
    chatError.value = '每条消息最多添加 5 个附件'
    return
  }
  chatUploading.value = true
  chatError.value = ''
  try {
    const previews = new Map<string, string>()
    for (const file of files) {
      if (file.type.startsWith('image/')) {
        const url = URL.createObjectURL(file)
        previewUrls.add(url)
        previews.set(`${file.name}-${file.size}-${file.lastModified}`, url)
      }
    }
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
    const uploaded = response.data.map((item, index) => {
      const file = files[index]!
      return {
        uuid: item.uuid,
        name: item.original_name,
        ext: item.file_ext,
        size: item.file_size,
        mimeType: item.mime_type,
        previewUrl: previews.get(`${file.name}-${file.size}-${file.lastModified}`),
        isImage: item.mime_type.startsWith('image/')
      } satisfies ChatAttachment
    })
    pendingChatAttachments.value.push(...uploaded)
  } catch (error) {
    chatError.value = normalizeApiError(error).message
  } finally {
    chatUploading.value = false
  }
}

function removeChatAttachment(index: number) {
  const [removed] = pendingChatAttachments.value.splice(index, 1)
  if (removed?.previewUrl) {
    URL.revokeObjectURL(removed.previewUrl)
    previewUrls.delete(removed.previewUrl)
  }
}

function speakReply(text: string) {
  if (!inCall.value || !speakerOn.value || !('speechSynthesis' in window)) return
  const speechText = markdownToSpeech(text)
  if (!speechText) return
  recognition?.stop()
  window.speechSynthesis.cancel()
  if (speechResumeTimer) clearTimeout(speechResumeTimer)
  const utterance = new SpeechSynthesisUtterance(speechText)
  utterance.lang = 'zh-CN'
  callSpeaking.value = true
  utterance.onend = () => {
    if (speechResumeTimer) clearTimeout(speechResumeTimer)
    speechResumeTimer = null
    callSpeaking.value = false
    resumeRecognition()
  }
  utterance.onerror = () => {
    if (speechResumeTimer) clearTimeout(speechResumeTimer)
    speechResumeTimer = null
    callSpeaking.value = false
    resumeRecognition()
  }
  window.speechSynthesis.speak(utterance)
  speechResumeTimer = setTimeout(
    () => {
      callSpeaking.value = false
      speechResumeTimer = null
      window.speechSynthesis.cancel()
      resumeRecognition()
    },
    Math.max(3000, Math.min(30000, speechText.length * 220))
  )
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

async function startCall() {
  if (inCall.value) return
  chatError.value = ''
  try {
    if (!window.isSecureContext) {
      throw new Error('语音通话需要 HTTPS 或 localhost 安全环境')
    }
    const speechWindow = window as unknown as {
      SpeechRecognition?: new () => BrowserSpeechRecognition
      webkitSpeechRecognition?: new () => BrowserSpeechRecognition
    }
    const SpeechConstructor = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
    if (!SpeechConstructor) {
      throw new Error('当前浏览器不支持语音识别，请使用 Chrome 或 Edge')
    }
    recognition = new SpeechConstructor()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onresult = (event) => {
      if (chatLoading.value || callMuted.value) return
      let finalText = ''
      let interimText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]!
        const transcript = result[0].transcript
        if (result.isFinal) finalText += transcript
        else interimText += transcript
      }
      chatInput.value = finalText || interimText
      if (finalText.trim()) {
        chatInput.value = finalText.trim()
        void sendExpertChat()
      }
    }
    recognition.onerror = (event) => {
      if (!['aborted', 'no-speech'].includes(event.error)) {
        chatError.value = speechErrorMessage(event.error)
        if (event.error !== 'network') endCall()
      }
    }
    recognition.onend = () => {
      resumeRecognition()
    }
    inCall.value = true
    callMuted.value = false
    speakerOn.value = true
    callSeconds.value = 0
    callTimer = setInterval(() => {
      callSeconds.value += 1
    }, 1000)
    resumeRecognition()
  } catch (error) {
    chatError.value = speechErrorMessage(error)
    endCall()
  }
}

function toggleCallMute() {
  callMuted.value = !callMuted.value
  if (callMuted.value) recognition?.stop()
  else resumeRecognition()
}

function resumeRecognition() {
  if (!inCall.value || callMuted.value || chatLoading.value || callSpeaking.value) return
  try {
    recognition?.start()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'InvalidStateError') return
    chatError.value = speechErrorMessage(error)
  }
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
    return '未检测到可用麦克风，请连接或启用系统麦克风后重试；也可以继续使用文字输入。'
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
    return '语音识别网络服务不可用，请检查网络或改用文字输入。'
  }
  return error instanceof Error && error.message
    ? `语音通话启动失败：${error.message}`
    : '未检测到可用麦克风或语音识别服务不可用，请检查麦克风连接和浏览器权限，或继续使用文字输入。'
}

function endCall() {
  inCall.value = false
  callMuted.value = false
  callSpeaking.value = false
  if (speechResumeTimer) clearTimeout(speechResumeTimer)
  speechResumeTimer = null
  if (callTimer) clearInterval(callTimer)
  callTimer = null
  recognition?.stop()
  recognition = null
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

watch(chatOpen, (open) => {
  if (!open) {
    endCall()
    chatSessionId.value = ''
    pendingChatAttachments.value = []
    chatApproval.value = null
    chatSessions.value = []
    chatSessionsError.value = ''
    clearChatPreviews()
  }
})

watch(speakerOn, (enabled) => {
  if (!inCall.value || enabled) return
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
  callSpeaking.value = false
  if (speechResumeTimer) clearTimeout(speechResumeTimer)
  speechResumeTimer = null
  resumeRecognition()
})

onBeforeUnmount(() => {
  endCall()
  clearChatPreviews()
})

function expertGreeting(expert: Expert): ExpertChatMessage {
  return {
    role: 'assistant',
    content: `我是${expert.name}。当前使用 ${expert.model}，可以直接向我提问。`,
    meta: expert.role
  }
}

function resetExpertChat(expert: Expert) {
  endCall()
  clearChatPreviews()
  chatExpert.value = expert
  chatSessionId.value = ''
  chatMessages.value = [expertGreeting(expert)]
  chatInput.value = ''
  pendingChatAttachments.value = []
  chatError.value = ''
  chatApproval.value = null
}

async function openPersistedChatSession(sessionId: string) {
  const expert = chatExpert.value
  if (!expert) return
  chatError.value = ''
  try {
    const session = await request<{
      id: string
      expertId: string
      title: string
      messages: Array<{
        id: string
        role: 'user' | 'assistant'
        content: string
        attachments?: Array<{
          uuid: string
          name: string
          ext?: string
          size?: number
          mimeType?: string
        }>
        meta?: Record<string, unknown>
        createTime?: string
      }>
    }>('/front/admin/experts/sessions/get', { id: sessionId })
    if (chatExpert.value?.id !== session.expertId) return
    chatSessionId.value = session.id
    chatMessages.value = [
      expertGreeting(expert),
      ...session.messages.map((message) => ({
        role: message.role,
        content: message.content,
        meta:
          message.role === 'assistant' ? String(message.meta?.model || '') || undefined : undefined,
        attachments: (message.attachments || []).map((file) => ({
          uuid: file.uuid,
          name: file.name,
          ext: file.ext || '',
          size: Number(file.size || 0),
          mimeType: file.mimeType || 'application/octet-stream',
          isImage: String(file.mimeType || '').startsWith('image/')
        }))
      }))
    ]
    chatApproval.value = null
    await scrollChatToBottom()
  } catch (error) {
    chatError.value = normalizeApiError(error).message
  }
}

async function openExpertChat(expert: Expert) {
  if (!expert.enabled) {
    expertActionError.value = '该专家已停用，请启用后再对话。'
    return
  }
  resetExpertChat(expert)
  chatRuns.value = []
  chatRunsError.value = ''
  chatSessions.value = []
  chatSessionsError.value = ''
  chatOpen.value = true
  await Promise.all([loadChatRuns(expert.id), loadChatSessions(expert.id)])
  void scrollChatToBottom()
}

function startNewExpertChat() {
  if (!chatExpert.value) return
  resetExpertChat(chatExpert.value)
  void scrollChatToBottom()
}

async function deleteExpertChatSession(session: ExpertSessionSummary) {
  if (!window.confirm(`确定删除会话「${session.title}」及其消息吗？`)) return
  chatSessionsError.value = ''
  try {
    await request('/front/admin/experts/sessions/delete', { id: session.id })
    if (chatSessionId.value === session.id && chatExpert.value) {
      resetExpertChat(chatExpert.value)
    }
    await loadChatSessions(session.expertId)
  } catch (error) {
    chatSessionsError.value = normalizeApiError(error).message
  }
}

function applyExpertChatResult(result: ExpertChatResult) {
  if (result.sessionId) chatSessionId.value = result.sessionId
  chatWarnings.value = result.warnings || []
  chatToolTrace.value = result.toolTrace || []
  if (result.requiresApproval && result.pendingApproval) {
    const runId = result.pendingApproval.runId || result.runId || ''
    chatApproval.value = {
      runId,
      calls: (result.pendingApproval.calls || []).map((call) => ({
        ...call,
        approved: false
      }))
    }
    chatError.value = ''
    void scrollChatToBottom()
    return
  }
  chatApproval.value = null
  if (!result.ok) {
    chatError.value = result.message
    return
  }
  chatMessages.value.push({
    role: 'assistant',
    content: result.content,
    meta: `${result.model || chatExpert.value?.model || '专家'} · ${result.latencyMs} ms · 工具 ${result.usedTools || 0} 次 · ¥${(result.cost || 0).toFixed(4)}`
  })
  speakReply(result.content)
  void scrollChatToBottom()
}

async function resumeExpertChat(approveAll = true) {
  const approval = chatApproval.value
  const expert = chatExpert.value
  if (!approval || !expert || chatResuming.value) return
  if (approveAll === false) {
    approval.calls.forEach((call) => {
      call.approved = false
    })
  }
  chatResuming.value = true
  chatError.value = ''
  try {
    const result = await request<ExpertChatResult>('/front/admin/experts/chat/resume', {
      id: approval.runId,
      approvals: approval.calls.map((call) => ({
        callId: call.callId,
        approved: call.approved
      }))
    })
    applyExpertChatResult(result)
  } catch (error) {
    chatError.value = normalizeApiError(error).message
  } finally {
    chatResuming.value = false
    void loadChatRuns(expert.id)
    void loadChatSessions(expert.id)
  }
}

async function sendExpertChat() {
  const message = chatInput.value.trim()
  const attachments = [...pendingChatAttachments.value]
  if (
    (!message && !attachments.length) ||
    !chatExpert.value ||
    chatLoading.value ||
    chatApproval.value
  )
    return
  const expert = chatExpert.value
  chatInput.value = ''
  chatError.value = ''
  chatWarnings.value = []
  chatToolTrace.value = []
  chatMessages.value.push({ role: 'user', content: message || '请查看附件', attachments })
  pendingChatAttachments.value = []
  void scrollChatToBottom()
  chatLoading.value = true
  try {
    const result = await request<ExpertChatResult>('/front/admin/experts/chat', {
      id: expert.id,
      sessionId: chatSessionId.value || undefined,
      message,
      attachments: attachments.map((file) => ({
        uuid: file.uuid,
        name: file.name,
        ext: file.ext,
        size: file.size,
        mimeType: file.mimeType
      }))
    })
    applyExpertChatResult(result)
  } catch (error) {
    chatError.value = normalizeApiError(error).message
  } finally {
    chatLoading.value = false
    void loadChatRuns(expert.id)
    void loadChatSessions(expert.id)
  }
}

function startAddExpert() {
  expertDraft.value.name = ''
  expertDraft.value.role = ''
  expertDialogError.value = ''
  expertDialogOpen.value = true
}

function closeExpertDialog() {
  expertDialogOpen.value = false
  expertDialogError.value = ''
}

async function submitExpert() {
  const name = expertDraft.value.name.trim()
  if (!name) return
  expertDialogError.value = ''
  try {
    const created = await request<{ id: string }>('/front/admin/experts/create', {
      name,
      role: expertDraft.value.role.trim() || '待配置'
    })
    closeExpertDialog()
    await loadExperts()
    const expert = experts.value.find((item) => item.id === created.id)
    if (expert) openExpertConfig(expert)
  } catch (error) {
    expertDialogError.value = normalizeApiError(error).message
  }
}

/** 删除专家卡片 */
async function removeExpert(expert: Expert) {
  if (!window.confirm(`确定删除专家「${expert.name}」吗？`)) return
  expertActionError.value = ''
  try {
    await request('/front/admin/experts/delete', { id: expert.id })
    await loadExperts()
  } catch (error) {
    expertActionError.value = normalizeApiError(error).message
  }
}

/** 注册弹窗：模型 / MCP / SKILL 共用一套新增、编辑表单 */
const registryDialogOpen = ref(false)

interface RegistryDraft {
  id: string | null
  name: string
  description: string
  meta: string
  endpoint: string
  modelKey: string
  provider: string
  priority: number
  enabled: boolean
  capabilities: ModelCapabilities
  configText: string
  /** 仅模型使用：新填写的 API Key（留空表示不修改已保存的密钥） */
  apiKey: string
  /** 已保存密钥的掩码，仅用于提示 */
  apiKeyMask: string
}

const registryDraft = reactive<RegistryDraft>({
  id: null,
  name: '',
  description: '',
  meta: '',
  endpoint: '',
  modelKey: '',
  provider: 'openai_compatible',
  priority: 100,
  enabled: true,
  capabilities: {
    contextWindow: 32768,
    maxOutputTokens: 2048,
    tools: false,
    vision: false,
    json: false,
    streaming: false,
    embeddings: false,
    audio: false
  },
  configText: '{}',
  apiKey: '',
  apiKeyMask: ''
})
const registryError = ref('')
const registryNotice = ref('')
const registryDeleteError = ref('')
const testingRegistryId = ref('')
const healthChecking = ref(false)
const providerOptions = [
  { label: 'OpenAI 兼容', value: 'openai_compatible' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Azure OpenAI', value: 'azure_openai' },
  { label: 'Google Gemini', value: 'google' },
  { label: 'Ollama', value: 'ollama' }
]

const registryItems = computed(() => {
  if (registryKind.value === 'mcp') return mcpServers.value
  return registryKind.value === 'skill' ? skills.value : models.value
})

const registryLoading = computed(() => loading[registryKind.value])
const registryLoadError = computed(() => loadErrors[registryKind.value])
const expertCardError = computed(
  () =>
    expertActionError.value ||
    loadErrors.expert ||
    loadErrors.model ||
    loadErrors.mcp ||
    loadErrors.skill
)

/** 组件在各管理分区复用：kind 变化时只刷新对应列表 */
watch(
  () => props.kind,
  (kind) => {
    registryNotice.value = ''
    registryDeleteError.value = ''
    if (kind === 'expert') void loadExperts()
    else void loadRegistry(kind)
  }
)

function onConfigTabChange(value: string | number) {
  configTab.value = value as ConfigTab
  if (configTab.value === 'tools') void loadSelectedMcpTools()
}

function resetRegistryDraft() {
  registryDraft.id = null
  registryDraft.name = ''
  registryDraft.description = ''
  registryDraft.meta = ''
  registryDraft.endpoint = ''
  registryDraft.modelKey = ''
  registryDraft.provider = 'openai_compatible'
  registryDraft.priority = 100
  registryDraft.enabled = true
  registryDraft.capabilities = {
    contextWindow: 32768,
    maxOutputTokens: 2048,
    tools: false,
    vision: false,
    json: false,
    streaming: false,
    embeddings: false,
    audio: false
  }
  registryDraft.configText = '{}'
  registryDraft.apiKey = ''
  registryDraft.apiKeyMask = ''
}

function openRegistryDialog(tool?: ExpertTool) {
  registryDialogOpen.value = true
  registryError.value = ''
  if (tool) {
    registryDraft.id = tool.id
    registryDraft.name = tool.name
    registryDraft.description = tool.description
    registryDraft.meta = tool.meta
    registryDraft.endpoint = tool.endpoint ?? ''
    registryDraft.modelKey = tool.modelKey ?? ''
    registryDraft.provider = tool.provider || 'openai_compatible'
    registryDraft.priority = tool.priority ?? 100
    registryDraft.enabled = tool.enabled ?? true
    registryDraft.capabilities = {
      contextWindow: tool.capabilities?.contextWindow ?? 32768,
      maxOutputTokens: tool.capabilities?.maxOutputTokens ?? 2048,
      tools: tool.capabilities?.tools ?? false,
      vision: tool.capabilities?.vision ?? false,
      json: tool.capabilities?.json ?? false,
      streaming: tool.capabilities?.streaming ?? false,
      embeddings: tool.capabilities?.embeddings ?? false,
      audio: tool.capabilities?.audio ?? false
    }
    registryDraft.configText = JSON.stringify(tool.config ?? {}, null, 2)
    registryDraft.apiKey = ''
    registryDraft.apiKeyMask = tool.apiKeyMask ?? ''
  } else {
    resetRegistryDraft()
  }
}

function closeRegistryDialog() {
  registryDialogOpen.value = false
  registryError.value = ''
}

async function submitRegistry() {
  const name = registryDraft.name.trim()
  if (!name) {
    registryError.value = '请填写名称'
    return
  }
  const kind = registryKind.value
  const path = registryPaths[kind]
  const description = registryDraft.description.trim()
  const withEndpoint = kind !== 'skill'
  const metaFallback = kind === 'model' ? '自定义模型' : ''
  const meta = registryDraft.meta.trim() || metaFallback
  const endpoint = withEndpoint ? registryDraft.endpoint.trim() : ''
  const apiKey = registryDraft.apiKey.trim()
  let config: Record<string, unknown> = {}
  try {
    const parsed = JSON.parse(registryDraft.configText || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new Error('配置必须是 JSON 对象')
    }
    config = parsed as Record<string, unknown>
  } catch {
    registryError.value = '高级配置必须是合法的 JSON 对象'
    return
  }
  const modelKey = registryDraft.modelKey.trim()
  if (kind === 'model') {
    if (!endpoint) {
      registryError.value = '请填写 API 地址'
      return
    }
    if (!registryDraft.id && !apiKey) {
      registryError.value = '请填写 API Key'
      return
    }
    if (!modelKey) {
      registryError.value = '请填写供应商模型标识'
      return
    }
  }
  const payload: Record<string, unknown> = {
    name,
    description,
    meta,
    status: '未测试',
    endpoint,
    config
  }
  if (kind === 'model') {
    payload.apiKey = apiKey
    payload.modelKey = modelKey
    payload.provider = registryDraft.provider
    payload.priority = Number(registryDraft.priority)
    payload.enabled = registryDraft.enabled
    payload.capabilities = { ...registryDraft.capabilities }
  }
  registryError.value = ''
  try {
    if (registryDraft.id) {
      await request(`/front/admin/${path}/update`, { id: registryDraft.id, ...payload })
      registryNotice.value = `已更新「${name}」，请重新测试`
    } else {
      await request(`/front/admin/${path}/create`, payload)
      registryNotice.value = `已注册「${name}」，测试通过后可授权给专家`
    }
    registryDialogOpen.value = false
    await loadRegistry(kind)
  } catch (error) {
    registryError.value = normalizeApiError(error).message
  }
}

/** 测试：模型走供应商探测、MCP 走端点/命令探测、SKILL 校验定义完整性，均由后端执行 */
async function testRegistry(tool: ExpertTool) {
  if (testingRegistryId.value) return
  const kind = registryKind.value
  testingRegistryId.value = tool.id
  registryNotice.value = `正在测试「${tool.name}」…`
  try {
    const result = await request<{
      ok: boolean
      status: ExpertTool['status']
      latencyMs: number
      message: string
    }>(`/front/admin/${registryPaths[kind]}/test`, {
      id: tool.id,
      deep: kind === 'model'
    })
    registryNotice.value = `「${tool.name}」${result.ok ? '测试通过' : '测试失败'}：${result.message}`
    await loadRegistry(kind)
  } catch (error) {
    registryNotice.value = `「${tool.name}」测试失败：${normalizeApiError(error).message}`
    await loadRegistry(kind)
  } finally {
    testingRegistryId.value = ''
  }
}

async function healthCheckModels() {
  if (healthChecking.value) return
  healthChecking.value = true
  registryNotice.value = '正在检查模型健康状态…'
  try {
    const result = await request<{ healthy: number; total: number }>(
      '/front/admin/models/health-check'
    )
    registryNotice.value = `模型健康检查完成：${result.healthy}/${result.total} 可用`
    await loadRegistry('model')
  } catch (error) {
    registryNotice.value = `模型健康检查失败：${normalizeApiError(error).message}`
  } finally {
    healthChecking.value = false
  }
}

/** 引用检查：被专家引用的注册项不允许直接删除；模型按名称比对 */
function referenceCount(id: string) {
  if (registryKind.value === 'model') {
    const tool = models.value.find((item) => item.id === id)
    return tool ? experts.value.filter((expert) => expert.model === tool.name).length : 0
  }
  return experts.value.filter((expert) =>
    registryKind.value === 'mcp' ? expert.mcpIds.includes(id) : expert.skillIds.includes(id)
  ).length
}

async function removeRegistry(tool: ExpertTool) {
  const count = referenceCount(tool.id)
  if (count > 0) {
    registryNotice.value = `「${tool.name}」被 ${count} 个专家引用，请先在专家侧停用`
    return
  }
  if (!window.confirm(`确定删除${registryUnit.value}「${tool.name}」吗？`)) return
  const kind = registryKind.value
  registryDeleteError.value = ''
  try {
    await request(`/front/admin/${registryPaths[kind]}/delete`, { id: tool.id })
    registryNotice.value = `已删除「${tool.name}」`
    await loadRegistry(kind)
  } catch (error) {
    registryDeleteError.value = normalizeApiError(error).message
  }
}
</script>

<template>
  <div class="flex flex-col">
    <UCard v-if="kind !== 'expert'" :aria-label="registryTitle">
      <template #header>
        <div class="flex items-center gap-3">
          <h2 class="text-sm font-semibold text-highlighted">{{ registryTitle }}</h2>
          <UBadge color="neutral" variant="subtle" size="sm">{{ registryItems.length }}</UBadge>
          <UButton
            v-if="registryKind === 'model'"
            color="neutral"
            variant="ghost"
            size="sm"
            :loading="healthChecking"
            class="ms-auto"
            @click="healthCheckModels"
          >
            健康检查
          </UButton>
          <UButton :class="{ 'ms-auto': registryKind !== 'model' }" @click="openRegistryDialog()">
            新增
          </UButton>
        </div>
      </template>

      <div class="flex flex-col gap-3">
        <p class="text-xs text-muted">{{ registrySubtitle }}</p>
        <UAlert
          v-if="registryLoading"
          color="neutral"
          variant="subtle"
          role="status"
          description="正在加载…"
        />
        <UAlert
          v-if="registryLoadError"
          color="error"
          variant="subtle"
          role="alert"
          :description="registryLoadError"
        />
        <UAlert
          v-if="registryDeleteError"
          color="error"
          variant="subtle"
          role="alert"
          :description="registryDeleteError"
        />
        <UAlert
          v-if="registryNotice"
          color="primary"
          variant="subtle"
          role="status"
          :description="registryNotice"
        />

        <ul
          role="list"
          class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]"
        >
          <li v-for="tool in registryItems" :key="tool.id">
            <UCard class="h-full">
              <div class="flex h-full flex-col gap-2">
                <div class="flex items-center gap-2">
                  <span class="min-w-0 flex-1 truncate text-sm font-medium text-highlighted">
                    {{ tool.name }}
                  </span>
                  <UBadge :color="statusColor(tool.status)" variant="subtle" size="sm">
                    {{ tool.status }}
                  </UBadge>
                </div>
                <p class="flex-1 text-xs text-muted">{{ tool.description || '暂无描述' }}</p>
                <p class="text-xs text-dimmed">
                  <template v-if="tool.meta">{{ tool.meta }} · </template>被
                  {{ referenceCount(tool.id) }} 个专家引用
                </p>
                <p v-if="registryKind === 'model'" class="text-xs text-dimmed">
                  {{ providerLabel(tool.provider) }} · 优先级 {{ tool.priority ?? 100 }} · API Key：
                  {{ tool.apiKeyMask || '未配置' }}
                </p>
                <div v-if="registryKind === 'model'" class="flex flex-wrap items-center gap-1">
                  <UBadge :color="healthColor(tool.healthStatus)" variant="subtle" size="sm">
                    {{ tool.healthStatus || 'unknown' }}
                  </UBadge>
                  <UBadge
                    v-for="capability in capabilityLabels(tool)"
                    :key="capability"
                    color="neutral"
                    variant="subtle"
                    size="sm"
                  >
                    {{ capability }}
                  </UBadge>
                  <span v-if="!tool.enabled" class="text-xs text-error">已停用</span>
                </div>
                <div class="flex flex-wrap justify-end gap-1">
                  <UButton
                    color="neutral"
                    variant="outline"
                    :disabled="testingRegistryId === tool.id"
                    @click="testRegistry(tool)"
                  >
                    {{ testingRegistryId === tool.id ? '测试中…' : '测试' }}
                  </UButton>
                  <UButton color="neutral" variant="ghost" @click="openRegistryDialog(tool)">
                    编辑
                  </UButton>
                  <UButton color="error" variant="ghost" @click="removeRegistry(tool)">
                    删除
                  </UButton>
                </div>
              </div>
            </UCard>
          </li>
        </ul>
      </div>
    </UCard>

    <UCard v-else aria-label="专家">
      <template #header>
        <div class="flex items-center gap-3">
          <h2 class="text-sm font-semibold text-highlighted">专家</h2>
          <UBadge color="neutral" variant="subtle" size="sm">{{ experts.length }}</UBadge>
          <UButton class="ms-auto" @click="startAddExpert">新增</UButton>
        </div>
      </template>

      <div class="flex flex-col gap-3">
        <p class="text-xs text-muted">点击专家卡片配置模型、MCP 与 SKILL 授权</p>
        <UAlert
          v-if="loading.expert"
          color="neutral"
          variant="subtle"
          role="status"
          description="正在加载…"
        />
        <UAlert
          v-if="expertCardError"
          color="error"
          variant="subtle"
          role="alert"
          :description="expertCardError"
        />

        <ul
          role="list"
          class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(300px,1fr))]"
        >
          <li v-for="expert in experts" :key="expert.id">
            <UCard class="h-full">
              <div class="flex h-full min-h-24 flex-col gap-2">
                <button
                  type="button"
                  class="flex flex-1 flex-col gap-1 rounded-md text-left focus-visible:outline-3 focus-visible:outline-primary/25"
                  @click="openExpertConfig(expert)"
                >
                  <span class="flex items-center gap-2">
                    <span class="min-w-0 flex-1 truncate text-sm font-medium text-highlighted">
                      {{ expert.name }}
                    </span>
                    <UBadge
                      :color="expert.enabled ? 'success' : 'neutral'"
                      variant="subtle"
                      size="sm"
                    >
                      {{ expert.enabled ? '启用' : '停用' }}
                    </UBadge>
                  </span>
                  <span class="block text-xs text-muted">{{ expert.role }}</span>
                  <span class="block text-xs text-dimmed">
                    {{ expert.model }} · MCP {{ expert.mcpIds.length }} · SKILL
                    {{ expert.skillIds.length }}
                  </span>
                </button>
                <div class="flex justify-end gap-1">
                  <UButton
                    color="primary"
                    variant="soft"
                    :disabled="!expert.enabled"
                    @click="openExpertChat(expert)"
                  >
                    对话
                  </UButton>
                  <UButton color="neutral" variant="ghost" @click="openExpertConfig(expert)">
                    编辑
                  </UButton>
                  <UButton color="error" variant="ghost" @click="removeExpert(expert)">
                    删除
                  </UButton>
                </div>
              </div>
            </UCard>
          </li>
        </ul>
      </div>
    </UCard>

    <!-- 注册弹窗：新增与编辑共用 -->
    <UModal
      v-model:open="registryDialogOpen"
      :title="`${registryDraft.id ? '编辑' : '新增'}${registryUnit}`"
    >
      <template #close>
        <UButton color="neutral" variant="ghost" aria-label="关闭">关闭</UButton>
      </template>

      <template #body>
        <div class="flex flex-col gap-4">
          <UFormField label="名称">
            <UInput
              v-model="registryDraft.name"
              class="w-full"
              :placeholder="registryKind === 'model' ? '如 Qwen3-235B' : '如 设计规范检索'"
            />
          </UFormField>

          <UFormField label="描述">
            <UInput
              v-model="registryDraft.description"
              class="w-full"
              :placeholder="registryKind === 'model' ? '提供商 · 说明' : '能力说明'"
            />
          </UFormField>

          <UFormField
            v-if="registryKind !== 'skill'"
            :label="registryKind === 'mcp' ? '启动命令或 URL' : 'API 地址'"
          >
            <UInput
              v-model="registryDraft.endpoint"
              class="w-full"
              :placeholder="registryKind === 'mcp' ? 'npx … 或 http://…' : 'https://…'"
            />
          </UFormField>

          <UFormField v-if="registryKind === 'model'" label="上下文">
            <UInput v-model="registryDraft.meta" class="w-full" placeholder="如 128K 上下文" />
          </UFormField>

          <div v-if="registryKind === 'model'" class="grid grid-cols-2 gap-3">
            <UFormField label="供应商适配器">
              <USelect v-model="registryDraft.provider" :items="providerOptions" class="w-full" />
            </UFormField>
            <UFormField label="路由优先级">
              <UInput
                v-model.number="registryDraft.priority"
                type="number"
                min="1"
                max="1000"
                class="w-full"
              />
            </UFormField>
            <UFormField label="上下文窗口">
              <UInput
                v-model.number="registryDraft.capabilities.contextWindow"
                type="number"
                min="1024"
                class="w-full"
              />
            </UFormField>
            <UFormField label="最大输出 Token">
              <UInput
                v-model.number="registryDraft.capabilities.maxOutputTokens"
                type="number"
                min="1"
                class="w-full"
              />
            </UFormField>
          </div>

          <div v-if="registryKind === 'model'" class="grid grid-cols-2 gap-2">
            <USwitch v-model="registryDraft.enabled" label="启用模型" />
            <USwitch v-model="registryDraft.capabilities.tools" label="Tool Calling" />
            <USwitch v-model="registryDraft.capabilities.vision" label="图片理解" />
            <USwitch v-model="registryDraft.capabilities.json" label="JSON 输出" />
            <USwitch v-model="registryDraft.capabilities.streaming" label="流式输出" />
            <USwitch v-model="registryDraft.capabilities.embeddings" label="Embedding" />
          </div>

          <UFormField v-if="registryKind === 'model'" label="供应商模型标识">
            <UInput
              v-model="registryDraft.modelKey"
              class="w-full"
              placeholder="如 gpt-5、claude-sonnet-4、deepseek-v4-pro"
            />
          </UFormField>

          <UFormField v-if="registryKind === 'model'" label="API Key">
            <UInput
              v-model="registryDraft.apiKey"
              type="password"
              autocomplete="new-password"
              class="w-full"
              :placeholder="
                registryDraft.id
                  ? `已保存 ${registryDraft.apiKeyMask || '密钥'}，留空表示不修改`
                  : 'sk-…'
              "
            />
          </UFormField>

          <UFormField v-else :label="registryKind === 'mcp' ? 'MCP 高级配置' : 'SKILL 高级配置'">
            <UTextarea
              v-model="registryDraft.configText"
              :rows="6"
              class="w-full font-mono text-xs"
              :placeholder="
                registryKind === 'mcp'
                  ? '例如 cwd、timeout；headers/env 会自动加密保存'
                  : '例如 instructions、handler、input_schema、output_schema，请输入 JSON 对象'
              "
            />
            <p v-if="registryKind === 'mcp'" class="mt-2 text-xs text-muted">
              在 headers 或 env 中填写的密钥只会以密文保存，列表接口不会返回明文。
            </p>
            <UAlert
              v-if="
                registryKind === 'mcp' &&
                registryDraft.id &&
                mcpServers.find((item) => item.id === registryDraft.id)?.hasSecrets
              "
              color="success"
              variant="subtle"
              :description="`已加密保存：${mcpServers.find((item) => item.id === registryDraft.id)?.secretKeys?.join('、') || '密钥'}。不重新填写 headers/env 时保持原密钥。`"
            />
          </UFormField>

          <UAlert
            v-if="registryError"
            color="error"
            variant="subtle"
            role="alert"
            :description="registryError"
          />
        </div>
      </template>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="closeRegistryDialog">取消</UButton>
          <UButton @click="submitRegistry">保存</UButton>
        </div>
      </template>
    </UModal>

    <!-- 新增专家弹窗 -->
    <UModal v-model:open="expertDialogOpen" title="新增专家">
      <template #close>
        <UButton color="neutral" variant="ghost" aria-label="关闭">关闭</UButton>
      </template>

      <template #body>
        <div class="flex flex-col gap-4">
          <UFormField label="名称">
            <UInput v-model="expertDraft.name" class="w-full" placeholder="如 品牌策略专家" />
          </UFormField>

          <UFormField label="职责">
            <UInput v-model="expertDraft.role" class="w-full" placeholder="如 品牌与内容策略" />
          </UFormField>

          <UAlert
            v-if="expertDialogError"
            color="error"
            variant="subtle"
            role="alert"
            :description="expertDialogError"
          />
        </div>
      </template>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="closeExpertDialog">取消</UButton>
          <UButton :disabled="!expertDraft.name.trim()" @click="submitExpert">创建</UButton>
        </div>
      </template>
    </UModal>

    <!-- 专家配置弹窗 -->
    <UModal v-model:open="configOpen" title="配置专家" :ui="{ content: 'sm:max-w-2xl' }">
      <template #close>
        <UButton color="neutral" variant="ghost" aria-label="关闭">关闭</UButton>
      </template>

      <template #body>
        <div class="flex flex-col gap-4">
          <UTabs
            :model-value="configTab"
            :items="configTabItems"
            :content="false"
            color="primary"
            @update:model-value="onConfigTabChange"
          />

          <UAlert
            v-if="testResult"
            :color="testResult.ok ? 'success' : 'error'"
            variant="subtle"
            role="status"
            :description="testResult.text"
          />

          <UAlert
            v-if="configError"
            color="error"
            variant="subtle"
            role="alert"
            :description="configError"
          />

          <template v-if="configTab === 'basic'">
            <UFormField label="名称">
              <UInput v-model="configDraft.name" class="w-full" />
            </UFormField>

            <UFormField label="职责">
              <UInput v-model="configDraft.role" class="w-full" />
            </UFormField>

            <UFormField label="系统提示词">
              <UTextarea v-model="configDraft.prompt" :rows="4" class="w-full" />
            </UFormField>

            <div class="grid grid-cols-2 gap-4">
              <UFormField label="模型">
                <USelect v-model="configDraft.model" :items="modelOptions" class="w-full" />
              </UFormField>

              <UFormField label="温度">
                <USelect
                  v-model="configDraft.temperature"
                  :items="temperatureOptions"
                  class="w-full"
                />
              </UFormField>
            </div>

            <USwitch
              v-model="configDraft.enabled"
              label="启用专家"
              description="停用后不出现在总管可调用的专家列表"
            />

            <USeparator />
            <div class="grid grid-cols-2 gap-4">
              <UFormField label="最大工具调用步数">
                <UInput
                  v-model.number="configDraft.settings!.maxToolSteps"
                  type="number"
                  min="0"
                  max="12"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="工具超时（秒）">
                <UInput
                  v-model.number="configDraft.settings!.toolTimeoutSeconds"
                  type="number"
                  min="3"
                  max="120"
                  class="w-full"
                />
              </UFormField>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <UFormField label="最大输出 Token">
                <UInput
                  v-model.number="configDraft.settings!.maxOutputTokens"
                  type="number"
                  min="1"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="上下文预算 Token（0=自动）">
                <UInput
                  v-model.number="configDraft.settings!.contextBudgetTokens"
                  type="number"
                  min="0"
                  class="w-full"
                />
              </UFormField>
            </div>
            <UFormField label="模型路由">
              <USelect
                v-model="configDraft.settings!.routingMode"
                :items="routingModeOptions"
                class="w-full"
              />
            </UFormField>
            <UFormField
              v-if="configDraft.settings!.routingMode === 'fallback'"
              label="备用模型"
              description="主模型出现超时、限流或 5xx 且尚未执行工具时自动切换"
            >
              <USelect
                v-model="configDraft.settings!.fallbackModelIds"
                :items="fallbackModelOptions"
                multiple
                class="w-full"
              />
            </UFormField>
            <USwitch
              v-model="configDraft.settings!.allowWriteTools"
              label="允许写入类 MCP 工具"
              description="关闭时写入工具默认禁用；开启后仍需按工具级策略确认，或显式设为直接允许"
            />
          </template>

          <template v-else-if="configTab === 'mcp'">
            <div class="flex items-center gap-2">
              <UInput v-model="mcpQuery" class="flex-1" placeholder="搜索 MCP" />
              <UButton color="neutral" variant="ghost" @click="toggleAllMcp(true)"> 全选 </UButton>
              <UButton color="neutral" variant="ghost" @click="toggleAllMcp(false)"> 清空 </UButton>
              <UButton
                color="primary"
                variant="link"
                class="ms-auto"
                @click="manageRegistry('mcp')"
              >
                管理
              </UButton>
            </div>
            <p class="text-xs text-muted">
              已启用 {{ configMcpCount }} / {{ mcpServers.length }} 个 MCP
            </p>
            <div class="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
              <div
                v-for="server in filteredMcpServers"
                :key="server.id"
                class="flex items-center gap-2 rounded-md bg-elevated/60 px-3 py-2"
              >
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm text-default">{{ server.name }}</p>
                  <p v-if="server.meta" class="truncate text-xs text-dimmed">{{ server.meta }}</p>
                </div>
                <USwitch
                  :model-value="isMcpEnabled(server.id)"
                  :aria-label="`${isMcpEnabled(server.id) ? '停用' : '启用'} ${server.name}`"
                  @update:model-value="toggleMcp(server.id)"
                />
              </div>
            </div>
            <UAlert
              v-if="!filteredMcpServers.length"
              color="neutral"
              variant="subtle"
              description="没有匹配的 MCP"
            />
          </template>

          <template v-else-if="configTab === 'tools'">
            <UAlert
              color="neutral"
              variant="subtle"
              description="安全默认：只读工具直接运行，写入工具默认每次确认。工具级策略可覆盖默认行为。"
            />
            <UAlert
              v-if="!selectedMcpServers.length && !selectedSkills.length"
              color="neutral"
              variant="subtle"
              description="请先在 MCP 或 SKILL 页签中启用至少一个能力"
            />
            <div v-else class="flex max-h-[42vh] flex-col gap-3 overflow-y-auto pe-1">
              <UCard
                v-for="server in selectedMcpServers"
                :key="server.id"
                :ui="{ body: 'p-3 sm:p-3' }"
              >
                <div class="mb-2 flex items-center gap-2">
                  <p class="text-sm font-medium">{{ server.name }}</p>
                  <UBadge color="neutral" variant="subtle" size="sm">
                    {{ mcpTools[server.id]?.length || 0 }} 个工具
                  </UBadge>
                  <UButton
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    class="ms-auto"
                    :loading="mcpToolLoading[server.id]"
                    @click="loadMcpTools(server, true)"
                  >
                    刷新
                  </UButton>
                </div>
                <UAlert
                  v-for="warning in mcpToolWarnings[server.id] || []"
                  :key="warning"
                  color="warning"
                  variant="subtle"
                  class="mb-2"
                  :description="warning"
                />
                <p
                  v-if="!mcpToolLoading[server.id] && !(mcpTools[server.id] || []).length"
                  class="text-xs text-muted"
                >
                  暂无已发现工具
                </p>
                <div class="flex flex-col gap-2">
                  <div
                    v-for="tool in mcpTools[server.id] || []"
                    :key="tool.name"
                    class="grid items-center gap-2 rounded-md bg-elevated/50 px-3 py-2 md:grid-cols-[1fr_140px]"
                  >
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-2">
                        <span class="font-mono text-xs font-medium">{{ tool.name }}</span>
                        <UBadge
                          :color="tool.readOnly ? 'success' : 'warning'"
                          variant="subtle"
                          size="sm"
                        >
                          {{ tool.readOnly ? '只读' : '写入' }}
                        </UBadge>
                      </div>
                      <p class="mt-1 line-clamp-2 text-xs text-muted">
                        {{ tool.description || '未提供说明' }}
                      </p>
                    </div>
                    <USelect
                      :model-value="toolPolicy(server.id, tool.name)"
                      :items="toolPolicyOptions"
                      class="w-full"
                      :aria-label="`${server.name} ${tool.name} 权限策略`"
                      @update:model-value="
                        (value) => setToolPolicy(server.id, tool.name, String(value))
                      "
                    />
                  </div>
                </div>
              </UCard>
              <UCard
                v-for="skill in selectedSkills"
                :key="`skill-${skill.id}`"
                :ui="{ body: 'p-3 sm:p-3' }"
              >
                <div class="grid items-center gap-2 md:grid-cols-[1fr_140px]">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-2">
                      <span class="text-sm font-medium">SKILL / {{ skill.name }}</span>
                      <UBadge
                        :color="skill.config?.handler ? 'success' : 'error'"
                        variant="subtle"
                        size="sm"
                      >
                        {{ skill.config?.handler ? '可执行' : '缺少 handler' }}
                      </UBadge>
                    </div>
                    <p class="mt-1 text-xs text-muted">
                      {{ skill.description || '未提供说明' }}
                    </p>
                  </div>
                  <USelect
                    :model-value="toolPolicy(skill.id, skill.name)"
                    :items="toolPolicyOptions"
                    class="w-full"
                    :aria-label="`${skill.name} 权限策略`"
                    @update:model-value="
                      (value) => setToolPolicy(skill.id, skill.name, String(value))
                    "
                  />
                </div>
              </UCard>
            </div>
          </template>

          <template v-else-if="configTab === 'skill'">
            <div class="flex items-center gap-2">
              <UInput v-model="skillQuery" class="flex-1" placeholder="搜索 SKILL" />
              <UButton color="neutral" variant="ghost" @click="toggleAllSkill(true)">
                全选
              </UButton>
              <UButton color="neutral" variant="ghost" @click="toggleAllSkill(false)">
                清空
              </UButton>
              <UButton
                color="primary"
                variant="link"
                class="ms-auto"
                @click="manageRegistry('skill')"
              >
                管理
              </UButton>
            </div>
            <p class="text-xs text-muted">
              已启用 {{ configSkillCount }} / {{ skills.length }} 个 SKILL
            </p>
            <div class="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
              <div
                v-for="skill in filteredSkills"
                :key="skill.id"
                class="flex items-center gap-2 rounded-md bg-elevated/60 px-3 py-2"
              >
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm text-default">{{ skill.name }}</p>
                  <p v-if="skill.meta" class="truncate text-xs text-dimmed">{{ skill.meta }}</p>
                </div>
                <USwitch
                  :model-value="isSkillEnabled(skill.id)"
                  :aria-label="`${isSkillEnabled(skill.id) ? '停用' : '启用'} ${skill.name}`"
                  @update:model-value="toggleSkill(skill.id)"
                />
              </div>
            </div>
            <UAlert
              v-if="!filteredSkills.length"
              color="neutral"
              variant="subtle"
              description="没有匹配的 SKILL"
            />
            <UAlert
              color="primary"
              variant="subtle"
              description="SKILL 测试和专家对话都会实际执行 handler，并校验 input_schema 与 output_schema。"
            />
          </template>
        </div>
      </template>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="ghost" @click="closeExpertConfig">取消</UButton>
          <UButton
            color="primary"
            variant="outline"
            :disabled="testing"
            :aria-busy="testing"
            @click="saveAndTestConfig"
          >
            {{ testing ? '测试中…' : '保存并测试' }}
          </UButton>
          <UButton @click="saveConfig">保存</UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="chatOpen"
      :title="chatExpert ? `与 ${chatExpert.name} 对话` : '专家对话'"
      :ui="{ content: 'sm:max-w-3xl' }"
    >
      <template #body>
        <div class="flex h-[58vh] min-h-96 flex-col gap-4">
          <div class="flex items-center gap-2">
            <span class="text-xs text-muted">
              {{ chatSessionId ? '已恢复历史会话' : '新会话' }}
            </span>
            <UButton
              size="xs"
              color="neutral"
              variant="soft"
              class="ms-auto"
              @click="startNewExpertChat"
            >
              新建会话
            </UButton>
          </div>
          <UCollapsible class="rounded-md border border-default px-3 py-2">
            <UButton color="neutral" variant="ghost" block class="justify-between">
              <span class="text-xs">历史会话 {{ chatSessions.length }}</span>
              <span class="text-[11px] text-muted">
                {{ chatSessionsLoading ? '加载中…' : '展开' }}
              </span>
            </UButton>
            <template #content>
              <div class="mt-2 flex max-h-56 flex-col gap-2 overflow-y-auto">
                <UAlert
                  v-if="chatSessionsError"
                  color="error"
                  variant="subtle"
                  :description="chatSessionsError"
                />
                <p
                  v-else-if="!chatSessionsLoading && !chatSessions.length"
                  class="text-xs text-muted"
                >
                  暂无历史会话
                </p>
                <div
                  v-for="session in chatSessions"
                  :key="session.id"
                  class="flex items-center gap-2 rounded-md p-1"
                  :class="session.id === chatSessionId ? 'bg-primary/10' : 'bg-elevated/50'"
                >
                  <button
                    type="button"
                    class="min-w-0 flex-1 rounded px-2 py-1 text-left"
                    @click="openPersistedChatSession(session.id)"
                  >
                    <span class="block truncate text-xs font-medium">
                      {{ session.title }}
                    </span>
                    <span class="mt-0.5 block truncate text-[11px] text-dimmed">
                      {{ formatRunTime(session.updateTime) }} · {{ session.messageCount }} 条
                      {{ session.preview ? `· ${session.preview}` : '' }}
                    </span>
                  </button>
                  <UButton
                    color="error"
                    variant="ghost"
                    size="xs"
                    square
                    :aria-label="`删除专家会话 ${session.title}`"
                    @click="deleteExpertChatSession(session)"
                  >
                    ×
                  </UButton>
                </div>
              </div>
            </template>
          </UCollapsible>
          <UCollapsible class="rounded-md border border-default px-3 py-2">
            <UButton color="neutral" variant="ghost" block class="justify-between">
              <span class="text-xs">最近运行记录 {{ chatRuns.length }}</span>
              <span class="text-[11px] text-muted">
                {{ chatRunsLoading ? '加载中…' : '展开' }}
              </span>
            </UButton>
            <template #content>
              <div class="mt-2 flex max-h-56 flex-col gap-2 overflow-y-auto">
                <UAlert
                  v-if="chatRunsError"
                  color="error"
                  variant="subtle"
                  :description="chatRunsError"
                />
                <p v-else-if="!chatRunsLoading && !chatRuns.length" class="text-xs text-muted">
                  暂无运行记录
                </p>
                <article
                  v-for="run in chatRuns"
                  :key="run.id"
                  class="rounded-md bg-elevated/50 p-2 text-xs"
                >
                  <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-dimmed">
                    <span
                      class="font-medium"
                      :class="
                        run.status === 'completed'
                          ? 'text-success'
                          : run.status === 'awaiting_approval'
                            ? 'text-warning'
                            : 'text-error'
                      "
                    >
                      {{
                        run.status === 'completed'
                          ? '完成'
                          : run.status === 'awaiting_approval'
                            ? '等待确认'
                            : '失败'
                      }}
                    </span>
                    <span>{{ formatRunTime(run.createTime) }}</span>
                    <span>{{ run.latencyMs }} ms</span>
                    <span>工具 {{ run.toolTrace.length }}</span>
                    <span>Token {{ run.inputTokens + run.outputTokens }}</span>
                    <span>费用 ¥{{ (run.cost || 0).toFixed(4) }}</span>
                    <span>模型尝试 {{ run.modelAttempts?.length || 1 }}</span>
                  </div>
                  <p class="mt-1 line-clamp-2 text-default">问：{{ run.question }}</p>
                  <!-- Run answers use the same sanitized Markdown renderer as live expert replies. -->
                  <!-- eslint-disable vue/no-v-html -->
                  <div
                    v-if="run.answer"
                    class="chat-markdown mt-1 max-h-24 overflow-hidden text-muted"
                    v-html="renderMarkdown(run.answer)"
                  />
                  <!-- eslint-enable vue/no-v-html -->
                  <UButton
                    v-if="run.status === 'awaiting_approval'"
                    color="warning"
                    variant="soft"
                    size="xs"
                    class="mt-2"
                    @click="restoreRunApproval(run)"
                  >
                    继续确认
                  </UButton>
                </article>
              </div>
            </template>
          </UCollapsible>
          <div ref="chatScroll" class="flex-1 space-y-3 overflow-y-auto pe-1">
            <div
              v-for="(message, index) in chatMessages"
              :key="`${message.role}-${index}`"
              class="flex"
              :class="message.role === 'user' ? 'justify-end' : 'justify-start'"
            >
              <div
                class="max-w-[82%] rounded-xl px-4 py-3 text-sm"
                :class="
                  message.role === 'user' ? 'bg-primary text-inverted' : 'bg-elevated text-default'
                "
              >
                <!-- renderMarkdown escapes raw HTML and sanitizes unsafe protocols. -->
                <!-- eslint-disable vue/no-v-html -->
                <div
                  v-if="message.role === 'assistant'"
                  class="chat-markdown"
                  v-html="renderMarkdown(message.content)"
                />
                <div v-else class="whitespace-pre-wrap">{{ message.content }}</div>
                <!-- eslint-enable vue/no-v-html -->
                <div v-if="message.attachments?.length" class="mt-3 grid grid-cols-2 gap-2">
                  <template v-for="file in message.attachments" :key="file.uuid">
                    <img
                      v-if="file.isImage && file.previewUrl"
                      :src="file.previewUrl"
                      :alt="file.name"
                      class="max-h-44 w-full rounded-lg object-cover"
                    />
                    <div
                      v-else
                      class="flex min-w-0 items-center gap-2 rounded-md bg-default/70 px-2.5 py-2 text-xs text-default"
                    >
                      <span class="font-semibold">{{ file.ext.toUpperCase() }}</span>
                      <span class="truncate">{{ file.name }}</span>
                    </div>
                  </template>
                </div>
                <p v-if="message.meta" class="mt-2 text-[11px] opacity-70">
                  {{ message.meta }}
                </p>
              </div>
            </div>
            <p v-if="chatLoading" class="text-xs text-muted">正在思考…</p>
          </div>
          <UAlert
            v-if="chatError"
            color="error"
            variant="subtle"
            title="对话失败"
            :description="chatError"
          />
          <UCard v-if="chatApproval" :ui="{ body: 'p-3 sm:p-3' }" class="border-warning/40">
            <div class="mb-3 flex items-center gap-2">
              <p class="text-sm font-medium text-warning">工具调用等待确认</p>
              <UBadge color="warning" variant="subtle" size="sm">
                {{ chatApproval.calls.length }} 个调用
              </UBadge>
            </div>
            <div class="flex max-h-56 flex-col gap-2 overflow-y-auto">
              <div
                v-for="call in chatApproval.calls"
                :key="call.callId"
                class="rounded-md bg-elevated/60 p-3"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <span class="font-mono text-xs font-medium">
                    {{ call.mcp }} / {{ call.tool }}
                  </span>
                  <UBadge
                    :color="call.risk === 'read' ? 'success' : 'warning'"
                    variant="subtle"
                    size="sm"
                  >
                    {{ call.risk }}
                  </UBadge>
                  <USwitch
                    v-model="call.approved"
                    class="ms-auto"
                    size="sm"
                    :aria-label="`${call.approved ? '拒绝' : '批准'} ${call.tool}`"
                  />
                  <span class="text-xs text-muted">{{ call.approved ? '批准' : '拒绝' }}</span>
                </div>
                <pre
                  class="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-all rounded bg-default/70 p-2 text-[11px]"
                  >{{ JSON.stringify(call.arguments, null, 2) }}</pre>
              </div>
            </div>
            <div class="mt-3 flex justify-end gap-2">
              <UButton
                color="neutral"
                variant="ghost"
                :disabled="chatResuming"
                @click="resumeExpertChat(false)"
              >
                全部拒绝
              </UButton>
              <UButton color="warning" :loading="chatResuming" @click="resumeExpertChat(true)">
                按选择继续
              </UButton>
            </div>
          </UCard>
          <UAlert
            v-if="chatWarnings.length"
            color="warning"
            variant="subtle"
            title="工具运行提示"
            :description="chatWarnings.join('；')"
          />
          <UCollapsible v-if="chatToolTrace.length" class="rounded-md border border-default p-2">
            <UButton color="neutral" variant="ghost" block class="justify-between">
              <span class="text-xs">工具调用记录 {{ chatToolTrace.length }}</span>
              <span class="text-[11px] text-muted">展开</span>
            </UButton>
            <template #content>
              <div class="mt-2 flex flex-col gap-2">
                <div
                  v-for="trace in chatToolTrace"
                  :key="`${trace.step}-${trace.alias}`"
                  class="rounded-md bg-elevated/50 p-2 text-xs"
                >
                  <p class="font-medium">
                    {{ trace.mcp }} / {{ trace.tool }}
                    <span :class="trace.ok ? 'text-success' : 'text-error'">
                      {{ trace.ok ? '成功' : '失败' }}
                    </span>
                  </p>
                  <p class="mt-1 text-dimmed">{{ trace.durationMs }} ms</p>
                  <p class="mt-1 line-clamp-3 text-muted">{{ trace.resultPreview }}</p>
                </div>
              </div>
            </template>
          </UCollapsible>
          <div v-if="pendingChatAttachments.length" class="flex flex-wrap gap-2">
            <div
              v-for="(file, index) in pendingChatAttachments"
              :key="file.uuid"
              class="relative flex items-center gap-2 rounded-lg bg-elevated px-2 py-1.5 text-xs"
            >
              <img
                v-if="file.isImage && file.previewUrl"
                :src="file.previewUrl"
                :alt="file.name"
                class="size-12 rounded object-cover"
              />
              <span class="max-w-48 truncate">{{ file.name }}</span>
              <UButton
                color="neutral"
                variant="ghost"
                square
                size="xs"
                :aria-label="`移除附件 ${file.name}`"
                @click="removeChatAttachment(index)"
              >
                ×
              </UButton>
            </div>
          </div>
          <div v-if="inCall" class="flex flex-wrap items-center gap-2 rounded-lg bg-primary/10 p-3">
            <span class="size-2 animate-pulse rounded-full bg-primary" aria-hidden="true" />
            <span class="font-medium tabular-nums text-primary">{{ callTime }}</span>
            <span class="text-xs text-muted">正在与 {{ chatExpert?.name }} 通话</span>
            <UButton color="neutral" variant="ghost" @click="toggleCallMute">
              {{ callMuted ? '取消静音' : '静音' }}
            </UButton>
            <UButton
              color="neutral"
              :variant="speakerOn ? 'soft' : 'ghost'"
              @click="speakerOn = !speakerOn"
            >
              {{ speakerOn ? '关闭扬声器' : '打开扬声器' }}
            </UButton>
            <UButton color="error" class="ms-auto" @click="endCall">挂断</UButton>
          </div>
          <div class="border-t border-default pt-3">
            <div class="mb-2 flex flex-wrap items-center gap-1">
              <UInput
                ref="attachmentInput"
                type="file"
                class="hidden"
                multiple
                accept=".jpg,.jpeg,.png,.webp,.gif,.pdf,.txt,.md,.csv,.json,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip"
                @change="onChatFilesChange"
              />
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :loading="chatUploading"
                @click="attachmentInput?.inputRef?.click()"
              >
                附件
              </UButton>
              <UButton v-if="!inCall" color="neutral" variant="ghost" size="sm" @click="startCall">
                通话
              </UButton>
              <span class="ms-auto text-[11px] text-dimmed">Ctrl + Enter 发送</span>
            </div>
            <div class="flex items-end gap-2">
              <UTextarea
                v-model="chatInput"
                :rows="3"
                class="flex-1"
                :placeholder="`向 ${chatExpert?.name || '专家'} 提问`"
                :disabled="chatLoading || Boolean(chatApproval)"
                @keydown.ctrl.enter.prevent="sendExpertChat"
              />
              <UButton
                :loading="chatLoading"
                :disabled="
                  (!chatInput.trim() && !pendingChatAttachments.length) ||
                  chatUploading ||
                  inCall ||
                  Boolean(chatApproval)
                "
                @click="sendExpertChat"
              >
                发送
              </UButton>
            </div>
          </div>
        </div>
      </template>
    </UModal>
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
