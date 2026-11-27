<script setup lang="ts">
import { getAdminToken } from '~/composables/useAdminSession'
import { normalizeApiError } from '~/composables/useApi'
import { escapeMarkdown, renderMarkdown } from '~/utils/markdown'
import type { DropdownMenuItem } from '@nuxt/ui'

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

interface ProjectAttachment {
  id: string
  taskId: string
  uuid: string
  name: string
  ext: string
  size: number
  mimeType: string
  kind: '输入' | '产出'
  createTime?: string
}

interface ProjectMessageAttachment {
  uuid: string
  name: string
  ext?: string
  size?: number
  mimeType?: string
}

interface ProjectMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  attachments?: ProjectMessageAttachment[]
  createTime?: string
}

interface ProjectTask {
  id: string
  projectId: string
  milestoneId: string
  sessionId: string
  title: string
  priority: string
  status: string
  dueAt?: string
  expertId?: string
  expertName?: string
  expertRole?: string
  phase: 'communicating' | 'spec_confirmed' | 'executing' | 'adjusting' | 'confirmed' | 'completed'
  specSnapshot?: {
    objective?: string
    scope?: string
    acceptanceCriteria?: string
  }
  specConfirmedAt?: string
  activeDeliverableId?: string
  deliverable?: ProjectDeliverable | null
  attachments: ProjectAttachment[]
  messages: ProjectMessage[]
}

interface ProjectDeliverableVersion {
  id: string
  versionNo: number
  contentHtml: string
  contentText: string
  contentHash: string
  sourceMessageId?: string
  sourceSessionId?: string
  sourceRunId?: string
  sourceExpertId?: string
  confirmedAt: string
}

interface ProjectDeliverable {
  id: string
  title: string
  status: 'draft' | 'confirmed'
  latestVersionNo: number
  draftHtml: string
  draftText: string
  draftSourceMessageId?: string
  draftSourceRunId?: string
  draftUpdateTime?: string
  versions: ProjectDeliverableVersion[]
}

interface ProjectMilestone {
  id: string
  projectId: string
  title: string
  status: string
  startsAt?: string
  dueAt?: string
  tasks: ProjectMilestoneTask[]
}

interface ProjectMilestoneTask extends Omit<ProjectTask, 'attachments' | 'messages'> {
  attachments: ProjectAttachment[]
  messages: ProjectMessage[]
}

interface ProjectDocumentVersion {
  id: string
  versionNo: number
  contentHtml: string
  contentText: string
  contentHash: string
  sourceDeliverableId?: string
  sourceVersionId?: string
  sourceVersionNo?: number
  confirmedAt: string
}

interface ProjectDocumentArtifact {
  id: string
  kind: 'requirements' | 'solution' | 'task_plan'
  title: string
  status: 'draft' | 'confirmed' | 'stale'
  latestVersionNo: number
  draftHtml: string
  draftText: string
  sourceDeliverableId?: string
  sourceVersionId?: string
  sourceVersionNo?: number
  draftUpdateTime?: string
  versions: ProjectDocumentVersion[]
}

interface Project {
  id: string
  name: string
  description: string
  status: string
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
  archived: boolean
  context: {
    objective?: string
    scope?: string
    constraints?: string[]
  }
  used: number
  limit: number
  expertId?: string
  expertName?: string
  expertRole?: string
  requirementHtml?: string
  requirementText?: string
  requirementConfirmedAt?: string
  solutionHtml?: string
  solutionText?: string
  solutionConfirmedAt?: string
  taskPlan?: ProjectTaskPlan
  taskPlanConfirmedAt?: string
  executionStatus: 'idle' | 'running' | 'completed' | 'failed'
  executionError?: string
  executionStartedAt?: string
  executionFinishedAt?: string
  sourceSessionId?: string
  documents?: Partial<Record<'requirements' | 'solution' | 'task_plan', ProjectDocumentArtifact>>
  milestones: ProjectMilestone[]
}

interface ProjectPlanTask {
  key?: string
  title: string
  description?: string
  acceptanceCriteria?: string
  priority?: string
  dependsOn?: string[]
}

interface ProjectPlanPackage {
  name: string
  tasks: ProjectPlanTask[]
}

interface ProjectTaskPlan {
  packages?: ProjectPlanPackage[]
}

interface ExpertOption {
  id: string
  name: string
  role: string
  model: string
  enabled: boolean
}

interface ExpertApprovalCall {
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
  sessionId?: string
  runId?: string
  model?: string
  latencyMs?: number
  requiresApproval?: boolean
  pendingApproval?: {
    runId?: string
    calls: Array<Omit<ExpertApprovalCall, 'approved'>>
  } | null
}

interface ComposerPayload {
  text: string
  files: string[]
  rawFiles: File[]
  depth: string
  quote: { text: string; range: string } | null
  source: 'text' | 'voice'
}

const route = useRoute()
const projects = ref<Project[]>([])
const experts = ref<ExpertOption[]>([])
const stopSpeechKey = ref('Escape')
const loading = ref(true)
const ready = ref(false)
const busy = ref(false)
const error = ref('')
const chatError = ref('')
const showArchived = ref(false)
const selectedProjectId = ref('')
const selectedMilestoneId = ref('')
const selectedTaskId = ref('')
const pendingRun = ref<{ runId: string; calls: ExpertApprovalCall[] } | null>(null)

const addingProject = ref(false)
const addingMilestone = ref(false)
const addingTask = ref(false)
const projectDraft = ref('')
const newProjectExpertId = ref('none')
const milestoneDraft = ref('')
const taskDraft = ref('')

const collapsedColumns = ref<boolean[]>([false, false, false, false, false])
const attachmentVisible = ref(true)
const editorVisible = ref(false)
const documentHtml = ref('')
const composerRef = ref<{ setQuote: (payload: { text: string; range: string }) => void } | null>(
  null
)
const projectEditorOpen = ref(false)
const taskEditorOpen = ref(false)
const specConfirmOpen = ref(false)
const workflowOpen = ref(false)
const workflowBusy = ref(false)
const workflowError = ref('')
const requirementDraft = ref('')
const solutionDraft = ref('')
const specDraft = reactive({
  objective: '',
  scope: '',
  acceptanceCriteria: ''
})
const editingProjectId = ref('')
const editingTaskId = ref('')
const projectForm = reactive({
  name: '',
  description: '',
  status: '进行中',
  objective: '',
  scope: '',
  expertId: 'none'
})
const taskForm = reactive({
  title: '',
  priority: 'P2',
  status: '未开始',
  dueAt: ''
})

const previewOpen = ref(false)
const previewFile = ref<{ title: string; ext: string; meta: string } | null>(null)

const expertItems = computed(() => [
  { label: '未绑定（创建任务前需绑定专家）', value: 'none' },
  ...experts.value
    .filter((expert) => expert.enabled)
    .map((expert) => ({
      label: `${expert.name}${expert.role ? ` · ${expert.role}` : ''}${expert.enabled ? '' : '（已停用）'}`,
      value: expert.id
    }))
])
const selectedProject = computed(
  () =>
    projects.value.find((project) => project.id === selectedProjectId.value) ?? projects.value[0]
)
const milestones = computed(() => selectedProject.value?.milestones ?? [])
const selectedMilestone = computed(
  () =>
    milestones.value.find((item) => item.id === selectedMilestoneId.value) ?? milestones.value[0]
)
const tasks = computed(() => selectedMilestone.value?.tasks ?? [])
const selectedTask = computed(
  () => tasks.value.find((item) => item.id === selectedTaskId.value) ?? tasks.value[0]
)
const selectedDeliverable = computed(() => selectedTask.value?.deliverable ?? null)
const messages = computed(() => selectedTask.value?.messages ?? [])
const attachments = computed(() => selectedTask.value?.attachments ?? [])
const projectExpertDisabled = computed(() => {
  const expertId = selectedProject.value?.expertId
  if (!expertId) return false
  return !experts.value.some((expert) => expert.id === expertId && expert.enabled)
})
const projectExpertAvailable = computed(() => {
  const expertId = selectedProject.value?.expertId
  return Boolean(
    expertId && experts.value.some((expert) => expert.id === expertId && expert.enabled)
  )
})
const planPackages = computed(() => selectedProject.value?.taskPlan?.packages || [])
const requirementsDocument = computed(() => selectedProject.value?.documents?.requirements)
const solutionDocument = computed(() => selectedProject.value?.documents?.solution)
const taskPlanDocument = computed(() => selectedProject.value?.documents?.task_plan)
const executionTaskCount = computed(
  () => selectedProject.value?.milestones.reduce((total, item) => total + item.tasks.length, 0) || 0
)
const allProjectTasksConfirmed = computed(() => {
  const tasks = selectedProject.value?.milestones.flatMap((milestone) => milestone.tasks) || []
  return tasks.length > 0 && tasks.every((task) => (task.deliverable?.latestVersionNo || 0) > 0)
})

let workflowPoll: ReturnType<typeof setInterval> | null = null

watch(
  () => selectedProject.value?.executionStatus,
  (status) => {
    if (workflowPoll) {
      clearInterval(workflowPoll)
      workflowPoll = null
    }
    if (!status || status === 'idle') return
    if (status === 'running') {
      workflowPoll = setInterval(() => {
        void loadWorkspace(
          selectedProject.value?.id,
          selectedMilestone.value?.id,
          selectedTask.value?.id
        )
      }, 3000)
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (workflowPoll) clearInterval(workflowPoll)
})
const attachmentGroups = computed(() =>
  (['输入', '产出'] as const).map((kind) => ({
    kind,
    items: attachments.value.filter((item) => item.kind === kind)
  }))
)
const attachmentGroupsOpen = reactive<Record<'输入' | '产出', boolean>>({
  输入: true,
  产出: true
})
const boardTracks = computed(() => {
  const tracks: string[] = []
  collapsedColumns.value.forEach((collapsed, index) => {
    if (index === 4 && !attachmentVisible.value) return
    if (index === 3) {
      tracks.push('minmax(320px, 1fr)')
      if (editorVisible.value) tracks.push('minmax(0, 1fr)')
      return
    }
    tracks.push(collapsed && index < 3 ? '80px' : '280px')
  })
  return tracks.join(' ')
})

function messageOf(errorValue: unknown) {
  return normalizeApiError(errorValue).message
}

async function request<T>(path: string, payload: Record<string, unknown> = {}) {
  const response = await useApi<ApiEnvelope<T>>(path, payload)
  if (response.code !== 200) throw new Error(response.message)
  return response.data
}

function pickSelection(projectId = '', milestoneId = '', taskId = '') {
  const project = projects.value.find((item) => item.id === projectId) ?? projects.value[0]
  selectedProjectId.value = project?.id ?? ''
  const milestone =
    project?.milestones.find((item) => item.id === milestoneId) ?? project?.milestones[0]
  selectedMilestoneId.value = milestone?.id ?? ''
  selectedTaskId.value =
    milestone?.tasks.find((item) => item.id === taskId)?.id ?? milestone?.tasks[0]?.id ?? ''
}

async function loadWorkspace(projectId = '', milestoneId = '', taskId = '') {
  loading.value = true
  error.value = ''
  try {
    const [data, expertData, callSettings] = await Promise.all([
      request<{ items: Project[] }>('/front/chief/workspace/get', {
        archived: showArchived.value
      }),
      request<{ items: ExpertOption[] }>('/front/chief/experts/list').catch(() => ({
        items: []
      })),
      request<{ pushToTalkKey: string }>('/front/admin/call/get-settings').catch(() => ({
        pushToTalkKey: 'Escape'
      }))
    ])
    projects.value = data.items
    experts.value = expertData.items
    stopSpeechKey.value = callSettings.pushToTalkKey || 'Escape'
    pickSelection(
      projectId || selectedProjectId.value,
      milestoneId || selectedMilestoneId.value,
      taskId || selectedTaskId.value
    )
    documentHtml.value = selectedTask.value?.deliverable?.draftHtml || ''
    ready.value = true
  } catch (err) {
    error.value = `项目工作台加载失败：${messageOf(err)}`
  } finally {
    loading.value = false
  }
}

async function toggleArchived() {
  showArchived.value = !showArchived.value
  selectedProjectId.value = ''
  selectedMilestoneId.value = ''
  selectedTaskId.value = ''
  await loadWorkspace()
}

function projectPhaseLabel(project: Project) {
  return (
    {
      requirements: '需求',
      requirements_confirmed: '需求已确定',
      solution: '方案',
      solution_confirmed: '方案已确定',
      task_planning: '任务分解',
      tasks_confirmed: '任务已确定',
      executing: '执行中',
      reviewing: '待确认成果',
      completed: '已完成'
    } as Record<string, string>
  )[project.phase]
}

function openProjectWorkflow(target?: Project) {
  const project = target ?? selectedProject.value
  if (!project) return
  if (selectedProjectId.value !== project.id) selectProject(project)
  requirementDraft.value = project.requirementText || ''
  solutionDraft.value = project.solutionText || ''
  workflowError.value = ''
  workflowOpen.value = true
}

async function refreshWorkflowProject() {
  await loadWorkspace(
    selectedProject.value?.id,
    selectedMilestone.value?.id,
    selectedTask.value?.id
  )
  requirementDraft.value = selectedProject.value?.requirementText || ''
  solutionDraft.value = selectedProject.value?.solutionText || ''
}

async function generateProjectDocument(stage: 'requirements' | 'solution') {
  const project = selectedProject.value
  if (!project || workflowBusy.value) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    const result = await request<{ contentText: string }>(
      '/front/chief/workspace/projects/document/generate',
      { projectId: project.id, stage }
    )
    if (stage === 'requirements') requirementDraft.value = result.contentText
    else solutionDraft.value = result.contentText
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `生成失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function saveProjectDocument(stage: 'requirements' | 'solution') {
  const project = selectedProject.value
  if (!project || workflowBusy.value) return false
  const contentText =
    stage === 'requirements' ? requirementDraft.value.trim() : solutionDraft.value.trim()
  if (!contentText) {
    workflowError.value = '内容不能为空。'
    return false
  }
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/document/save', {
      projectId: project.id,
      stage,
      contentText,
      contentHtml: contentText
        .split('\n')
        .filter(Boolean)
        .map((line) => `<p>${escapeMarkdown(line)}</p>`)
        .join('')
    })
    await refreshWorkflowProject()
    return true
  } catch (err) {
    workflowError.value = `保存失败：${messageOf(err)}`
    return false
  } finally {
    workflowBusy.value = false
  }
}

async function confirmProjectDocument(stage: 'requirements' | 'solution') {
  const project = selectedProject.value
  if (!project) return
  if (!(await saveProjectDocument(stage))) return
  workflowBusy.value = true
  try {
    await request('/front/chief/workspace/projects/document/confirm', {
      projectId: project.id,
      stage
    })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `确认失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function adjustProjectDocument(stage: 'requirements' | 'solution') {
  const project = selectedProject.value
  if (!project || workflowBusy.value) return
  const contentText =
    stage === 'requirements' ? project.requirementText || '' : project.solutionText || ''
  if (!contentText.trim()) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/document/save', {
      projectId: project.id,
      stage,
      contentText,
      contentHtml:
        stage === 'requirements' ? project.requirementHtml || '' : project.solutionHtml || ''
    })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `进入调整失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function generateProjectTaskPlan() {
  const project = selectedProject.value
  if (!project || workflowBusy.value) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/task-plan/generate', {
      projectId: project.id
    })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `任务分解失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function confirmProjectTaskPlan() {
  const project = selectedProject.value
  if (!project) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/task-plan/confirm', {
      projectId: project.id
    })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `确认任务失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function adjustProjectTaskPlan() {
  const project = selectedProject.value
  if (!project || workflowBusy.value) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/task-plan/save', {
      projectId: project.id,
      plan: project.taskPlan || {}
    })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `进入计划调整失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function executeProjectTasks() {
  const project = selectedProject.value
  if (!project) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/execute', { projectId: project.id })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `启动执行失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

async function completeProject() {
  const project = selectedProject.value
  if (!project) return
  workflowBusy.value = true
  workflowError.value = ''
  try {
    await request('/front/chief/workspace/projects/complete', { projectId: project.id })
    await refreshWorkflowProject()
  } catch (err) {
    workflowError.value = `项目完成失败：${messageOf(err)}`
  } finally {
    workflowBusy.value = false
  }
}

onMounted(() => {
  void loadWorkspace(String(route.query.projectId || ''))
})

function selectProject(project: Project) {
  if (project.id === selectedProjectId.value) return
  selectedProjectId.value = project.id
  selectedMilestoneId.value = project.milestones[0]?.id ?? ''
  selectedTaskId.value = project.milestones[0]?.tasks[0]?.id ?? ''
  pendingRun.value = null
}

function selectMilestone(milestone: ProjectMilestone | undefined) {
  selectedMilestoneId.value = milestone?.id ?? ''
  selectedTaskId.value = milestone?.tasks[0]?.id ?? ''
  pendingRun.value = null
}

function selectTask(task: ProjectTask | undefined) {
  selectedTaskId.value = task?.id ?? ''
  pendingRun.value = null
  documentHtml.value = task?.deliverable?.draftHtml || ''
}

function openSpecConfirmation() {
  const task = selectedTask.value
  if (!task) return
  specDraft.objective =
    textValue(task.specSnapshot?.objective) ||
    textValue(selectedProject.value?.context.objective) ||
    task.title
  specDraft.scope =
    textValue(task.specSnapshot?.scope) || textValue(selectedProject.value?.context.scope)
  specDraft.acceptanceCriteria = textValue(task.specSnapshot?.acceptanceCriteria)
  specConfirmOpen.value = true
}

function textValue(value: unknown) {
  return typeof value === 'string' ? value : ''
}

async function refreshSelectedTask() {
  await loadWorkspace(
    selectedProject.value?.id,
    selectedMilestone.value?.id,
    selectedTask.value?.id
  )
  documentHtml.value = selectedTask.value?.deliverable?.draftHtml || ''
}

async function confirmTaskSpec() {
  const task = selectedTask.value
  if (!task || !specDraft.objective.trim()) return
  try {
    await request('/front/chief/workspace/tasks/confirm-spec', {
      taskId: task.id,
      objective: specDraft.objective.trim(),
      scope: specDraft.scope.trim(),
      acceptanceCriteria: specDraft.acceptanceCriteria.trim()
    })
    specConfirmOpen.value = false
    await refreshSelectedTask()
  } catch (err) {
    chatError.value = `确认需求失败：${messageOf(err)}`
  }
}

async function startTaskExecution() {
  const task = selectedTask.value
  if (!task) return
  try {
    await request('/front/chief/workspace/tasks/start-execution', { taskId: task.id })
    await refreshSelectedTask()
  } catch (err) {
    chatError.value = `开始执行失败：${messageOf(err)}`
  }
}

async function setMessageAsDraft(message: ProjectMessage) {
  const task = selectedTask.value
  if (!task || message.role !== 'assistant') return
  try {
    await request('/front/chief/workspace/deliverables/from-message', {
      taskId: task.id,
      messageId: message.id,
      contentHtml: renderMarkdown(message.content),
      contentText: message.content
    })
    await refreshSelectedTask()
    editorVisible.value = true
  } catch (err) {
    chatError.value = `生成成果草稿失败：${messageOf(err)}`
  }
}

function htmlToText(value: string) {
  const doc = new DOMParser().parseFromString(value, 'text/html')
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim()
}

async function saveDeliverableDraft() {
  const task = selectedTask.value
  const deliverable = selectedDeliverable.value
  if (!task || !deliverable) return false
  try {
    await request('/front/chief/workspace/deliverables/save-draft', {
      taskId: task.id,
      deliverableId: deliverable.id,
      contentHtml: documentHtml.value,
      contentText: htmlToText(documentHtml.value)
    })
    await refreshSelectedTask()
    return true
  } catch (err) {
    chatError.value = `保存成果草稿失败：${messageOf(err)}`
    return false
  }
}

async function confirmDeliverableVersion() {
  const task = selectedTask.value
  const deliverable = selectedDeliverable.value
  if (!task || !deliverable) return
  if (!(await saveDeliverableDraft())) return
  try {
    await request('/front/chief/workspace/deliverables/confirm', {
      taskId: task.id,
      deliverableId: deliverable.id
    })
    await refreshSelectedTask()
    editorVisible.value = true
  } catch (err) {
    chatError.value = `确认版本失败：${messageOf(err)}`
  }
}

async function adjustDeliverable() {
  const deliverable = selectedDeliverable.value
  if (!deliverable) return
  try {
    await request('/front/chief/workspace/deliverables/adjust', {
      deliverableId: deliverable.id
    })
    await refreshSelectedTask()
    editorVisible.value = true
  } catch (err) {
    chatError.value = `开始调整失败：${messageOf(err)}`
  }
}

async function completeTaskDelivery() {
  const task = selectedTask.value
  if (!task) return
  try {
    await request('/front/chief/workspace/tasks/complete', { taskId: task.id })
    await refreshSelectedTask()
  } catch (err) {
    chatError.value = `完成任务失败：${messageOf(err)}`
  }
}

function toggleColumn(index: number) {
  const next = [...collapsedColumns.value]
  next[index] = !next[index]
  collapsedColumns.value = next
}

function statusMeta(status: string, detail = '') {
  return detail ? `${status} · ${detail}` : status
}

function milestoneMeta(milestone: ProjectMilestone) {
  const range = [milestone.startsAt, milestone.dueAt].filter(Boolean).join(' ~ ')
  return statusMeta(milestone.status, range || `${milestone.tasks.length} 个任务`)
}

function taskMeta(task: ProjectTask) {
  const phase = taskPhaseLabel(task)
  return [task.priority, phase, task.dueAt].filter(Boolean).join(' · ')
}

function taskPhaseLabel(task: ProjectTask) {
  if (task.phase === 'confirmed' && task.deliverable?.latestVersionNo) {
    return `已确定 V${task.deliverable.latestVersionNo}`
  }
  return (
    {
      communicating: '沟通中',
      spec_confirmed: '需求已确认',
      executing: '执行中',
      adjusting: '调整中',
      confirmed: '已确定',
      completed: '已完成'
    } as Record<string, string>
  )[task.phase]
}

function projectMeta(project: Project) {
  const taskTotal = project.milestones.reduce(
    (total, milestone) => total + milestone.tasks.length,
    0
  )
  return `${project.status} · ${project.milestones.length} 个任务包 · ${taskTotal} 个任务`
}

function formatSize(size: number) {
  if (!size) return '0 KB'
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function resetProjectDraft() {
  projectDraft.value = ''
  newProjectExpertId.value = 'none'
  addingProject.value = false
}

async function submitProject() {
  const name = projectDraft.value.trim()
  if (!name) return
  try {
    const created = await request<Project>('/front/chief/workspace/projects/create', {
      name,
      description: '',
      status: '进行中',
      expertId: newProjectExpertId.value === 'none' ? undefined : newProjectExpertId.value
    })
    resetProjectDraft()
    await loadWorkspace(created.id)
  } catch (err) {
    error.value = `新增项目失败：${messageOf(err)}`
  }
}

function editProject(project: Project) {
  editingProjectId.value = project.id
  projectForm.name = project.name
  projectForm.description = project.description
  projectForm.status = project.status
  projectForm.objective = project.context.objective || ''
  projectForm.scope = project.context.scope || ''
  const expertDisabled = !experts.value.some(
    (expert) => expert.id === project.expertId && expert.enabled
  )
  projectForm.expertId = project.expertId && !expertDisabled ? project.expertId : 'none'
  projectEditorOpen.value = true
}

async function saveProject() {
  if (!projectForm.name.trim()) return
  const existing = projects.value.find((project) => project.id === editingProjectId.value)
  try {
    await request('/front/chief/workspace/projects/update', {
      projectId: editingProjectId.value,
      name: projectForm.name.trim(),
      description: projectForm.description.trim(),
      status: projectForm.status,
      expertId: projectForm.expertId === 'none' ? '' : projectForm.expertId,
      context: {
        ...(existing?.context || {}),
        objective: projectForm.objective.trim(),
        scope: projectForm.scope.trim()
      }
    })
    projectEditorOpen.value = false
    await loadWorkspace(editingProjectId.value)
  } catch (err) {
    error.value = `保存项目失败：${messageOf(err)}`
  }
}

async function duplicateProject(project: Project) {
  try {
    const copy = await request<Project>('/front/chief/workspace/projects/duplicate', {
      projectId: project.id,
      name: `${project.name} 副本`
    })
    await loadWorkspace(copy.id)
  } catch (err) {
    error.value = `复制项目失败：${messageOf(err)}`
  }
}

async function setProjectArchived(project: Project, archived: boolean) {
  try {
    await request(
      archived
        ? '/front/chief/workspace/projects/archive'
        : '/front/chief/workspace/projects/restore',
      { projectId: project.id }
    )
    await loadWorkspace()
  } catch (err) {
    error.value = `${archived ? '归档' : '恢复'}项目失败：${messageOf(err)}`
  }
}

async function deleteProject(project: Project) {
  if (!window.confirm(`确定删除项目「${project.name}」及其全部任务和会话吗？`)) return
  try {
    await request('/front/chief/workspace/projects/delete', { projectId: project.id })
    await loadWorkspace()
  } catch (err) {
    error.value = `删除项目失败：${messageOf(err)}`
  }
}

function projectMenuItems(project: Project): DropdownMenuItem[][] {
  return [
    [
      {
        label: project.executionStatus === 'running' ? '查看自动执行' : '项目流程',
        onSelect: () => void openProjectWorkflow(project)
      },
      { label: '编辑项目', onSelect: () => editProject(project) },
      { label: '创建副本', onSelect: () => void duplicateProject(project) }
    ],
    [
      {
        label: showArchived.value ? '恢复项目' : '归档项目',
        onSelect: () => void setProjectArchived(project, !showArchived.value)
      },
      {
        label: '删除',
        color: 'error',
        onSelect: () => void deleteProject(project)
      }
    ]
  ]
}

function startAddMilestone() {
  addingMilestone.value = true
  milestoneDraft.value = ''
}

async function submitMilestone() {
  const title = milestoneDraft.value.trim()
  const project = selectedProject.value
  if (!title || !project) return
  try {
    const created = await request<ProjectMilestone>('/front/chief/workspace/milestones/create', {
      projectId: project.id,
      title,
      status: '未开始'
    })
    addingMilestone.value = false
    milestoneDraft.value = ''
    await loadWorkspace(project.id, created.id)
  } catch (err) {
    error.value = `新增任务包失败：${messageOf(err)}`
  }
}

async function renameMilestone(milestone: ProjectMilestone) {
  const title = window.prompt('任务包名称', milestone.title)?.trim()
  if (!title || title === milestone.title) return
  try {
    await request('/front/chief/workspace/milestones/update', {
      milestoneId: milestone.id,
      title
    })
    await loadWorkspace(selectedProject.value?.id, milestone.id, selectedTask.value?.id)
  } catch (err) {
    error.value = `修改任务包失败：${messageOf(err)}`
  }
}

async function toggleMilestoneStatus(milestone: ProjectMilestone) {
  const status = milestone.status === '已完成' ? '进行中' : '已完成'
  try {
    await request('/front/chief/workspace/milestones/update', {
      milestoneId: milestone.id,
      status
    })
    await loadWorkspace(selectedProject.value?.id, milestone.id, selectedTask.value?.id)
  } catch (err) {
    error.value = `更新任务包失败：${messageOf(err)}`
  }
}

async function deleteMilestone(milestone: ProjectMilestone) {
  if (!window.confirm(`确定删除任务包「${milestone.title}」及其任务吗？`)) return
  try {
    await request('/front/chief/workspace/milestones/delete', {
      milestoneId: milestone.id
    })
    await loadWorkspace(selectedProject.value?.id)
  } catch (err) {
    error.value = `删除任务包失败：${messageOf(err)}`
  }
}

function milestoneMenuItems(milestone: ProjectMilestone): DropdownMenuItem[][] {
  return [
    [
      { label: '重命名', onSelect: () => void renameMilestone(milestone) },
      {
        label: milestone.status === '已完成' ? '标记进行中' : '标记完成',
        onSelect: () => void toggleMilestoneStatus(milestone)
      }
    ],
    [
      {
        label: '删除',
        color: 'error',
        onSelect: () => void deleteMilestone(milestone)
      }
    ]
  ]
}

function startAddTask() {
  addingTask.value = true
  taskDraft.value = ''
}

async function submitTask() {
  const title = taskDraft.value.trim()
  const project = selectedProject.value
  const milestone = selectedMilestone.value
  if (!title || !project || !milestone) return
  try {
    const created = await request<ProjectTask>('/front/chief/workspace/tasks/create', {
      projectId: project.id,
      milestoneId: milestone.id,
      title,
      priority: 'P2',
      status: '未开始'
    })
    addingTask.value = false
    taskDraft.value = ''
    await loadWorkspace(project.id, milestone.id, created.id)
  } catch (err) {
    error.value = `新增任务失败：${messageOf(err)}`
  }
}

function editTask(task: ProjectTask) {
  editingTaskId.value = task.id
  taskForm.title = task.title
  taskForm.priority = task.priority
  taskForm.status = task.status
  taskForm.dueAt = task.dueAt || ''
  taskEditorOpen.value = true
}

async function saveTask() {
  if (!taskForm.title.trim()) return
  try {
    await request('/front/chief/workspace/tasks/update', {
      taskId: editingTaskId.value,
      title: taskForm.title.trim(),
      priority: taskForm.priority,
      status: taskForm.status,
      dueAt: taskForm.dueAt || null
    })
    taskEditorOpen.value = false
    await loadWorkspace(selectedProject.value?.id, selectedMilestone.value?.id, editingTaskId.value)
  } catch (err) {
    error.value = `保存任务失败：${messageOf(err)}`
  }
}

async function toggleTaskStatus(task: ProjectTask) {
  const status = task.status === '已完成' ? '进行中' : '待审核'
  try {
    await request('/front/chief/workspace/tasks/update', {
      taskId: task.id,
      status
    })
    await loadWorkspace(selectedProject.value?.id, selectedMilestone.value?.id, task.id)
  } catch (err) {
    error.value = `更新任务失败：${messageOf(err)}`
  }
}

async function deleteTask(task: ProjectTask) {
  if (!window.confirm(`确定删除任务「${task.title}」及其会话吗？`)) return
  try {
    await request('/front/chief/workspace/tasks/delete', { taskId: task.id })
    await loadWorkspace(selectedProject.value?.id, selectedMilestone.value?.id)
  } catch (err) {
    error.value = `删除任务失败：${messageOf(err)}`
  }
}

function taskMenuItems(task: ProjectTask): DropdownMenuItem[][] {
  return [
    [
      { label: '编辑任务', onSelect: () => editTask(task) },
      {
        label: task.status === '已完成' ? '重新打开' : '标记待审核',
        onSelect: () => void toggleTaskStatus(task)
      }
    ],
    [
      {
        label: '删除',
        color: 'error',
        onSelect: () => void deleteTask(task)
      }
    ]
  ]
}

async function refreshTaskSession(task: ProjectTask) {
  if (!task.sessionId) return
  const session = await request<{ messages: ProjectMessage[] }>(
    '/front/admin/experts/sessions/get',
    { id: task.sessionId }
  )
  task.messages = session.messages || []
}

async function uploadFile(file: File) {
  const config = useRuntimeConfig()
  const body = new FormData()
  body.append('form_code', 'ADMIN_CHAT')
  body.append('files', file)
  const response = await fetch(`${config.public.apiBase}/front/upload/files`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getAdminToken()}` },
    body
  })
  const payload = (await response.json()) as ApiEnvelope<
    Array<{
      uuid: string
      original_name: string
      file_ext: string
      file_size: number
      mime_type: string
    }>
  >
  if (!response.ok || payload.code !== 200) {
    throw new Error(payload.message || `附件上传失败（HTTP ${response.status}）`)
  }
  return payload.data[0]
}

async function handleSendMessage(payload: ComposerPayload) {
  const task = selectedTask.value
  const project = selectedProject.value
  const fixedCommand = payload.text.trim()
  if (
    /^#(生成需求|生成方案|生成计划|开始执行|需求沟通|需求文档|方案沟通|方案文档|任务计划|计划清单)#$/.test(
      fixedCommand
    )
  ) {
    chatError.value = '项目流程固定指令请在“总管”页选中当前项目后发送。'
    return
  }
  if (!task?.sessionId || busy.value) return
  if (!project?.expertId) {
    chatError.value = '请先为当前项目绑定专家 Agent。'
    return
  }
  busy.value = true
  chatError.value = ''
  pendingRun.value = null
  try {
    const chatAttachments: ProjectMessageAttachment[] = []
    for (const file of payload.rawFiles) {
      const uploaded = await uploadFile(file)
      if (!uploaded) throw new Error(`附件「${file.name}」上传后未返回文件信息。`)
      await request('/front/chief/workspace/attachments/add', {
        taskId: task.id,
        kind: '输入',
        file: {
          uuid: uploaded.uuid,
          name: uploaded.original_name,
          ext: uploaded.file_ext,
          size: uploaded.file_size,
          mimeType: uploaded.mime_type
        }
      })
      chatAttachments.push({
        uuid: uploaded.uuid,
        name: uploaded.original_name,
        ext: uploaded.file_ext,
        size: uploaded.file_size,
        mimeType: uploaded.mime_type
      })
    }
    const result = await request<ExpertChatResult>('/front/admin/experts/chat', {
      id: project.expertId,
      sessionId: task.sessionId,
      message: payload.text,
      attachments: payload.rawFiles.length ? chatAttachments : []
    })
    await refreshTaskSession(task)
    if (result.requiresApproval && result.pendingApproval) {
      pendingRun.value = {
        runId: result.pendingApproval.runId || result.runId || '',
        calls: (result.pendingApproval.calls || []).map((call) => ({
          ...call,
          approved: false
        }))
      }
    } else if (!result.ok) {
      throw new Error(result.message || '专家 Agent 未能生成回复。')
    }
  } catch (err) {
    chatError.value = messageOf(err)
    if (selectedTask.value?.sessionId) {
      await refreshTaskSession(selectedTask.value).catch(() => undefined)
    }
  } finally {
    busy.value = false
  }
}

async function approveRun() {
  if (!pendingRun.value) return
  busy.value = true
  try {
    const result = await request<ExpertChatResult>('/front/admin/experts/chat/resume', {
      id: pendingRun.value.runId,
      approvals: pendingRun.value.calls.map((call) => ({
        callId: call.callId,
        approved: call.approved
      }))
    })
    if (selectedTask.value) await refreshTaskSession(selectedTask.value)
    if (result.requiresApproval && result.pendingApproval) {
      pendingRun.value = {
        runId: result.pendingApproval.runId || result.runId || pendingRun.value.runId,
        calls: (result.pendingApproval.calls || []).map((call) => ({
          ...call,
          approved: false
        }))
      }
    } else {
      pendingRun.value = null
      if (!result.ok) throw new Error(result.message || '专家 Agent 未能完成工具调用。')
    }
  } catch (err) {
    chatError.value = `继续执行失败：${messageOf(err)}`
  } finally {
    busy.value = false
  }
}

async function rejectRun() {
  if (!pendingRun.value) return
  pendingRun.value.calls.forEach((call) => {
    call.approved = false
  })
  await approveRun()
}

function openPreview(file: ProjectAttachment) {
  previewFile.value = {
    title: file.name,
    ext: file.ext.toUpperCase(),
    meta: `${formatSize(file.size)} · ${file.kind}`
  }
  previewOpen.value = true
}

async function downloadAttachment(file: ProjectAttachment) {
  try {
    const config = useRuntimeConfig()
    const response = await fetch(`${config.public.apiBase}/front/upload/download`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getAdminToken()}`
      },
      body: JSON.stringify({ uuid: file.uuid })
    })
    if (!response.ok) throw new Error(`下载失败（HTTP ${response.status}）`)
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    error.value = `下载附件失败：${messageOf(err)}`
  }
}

async function deleteAttachment(file: ProjectAttachment) {
  if (!window.confirm(`确定从任务中移除附件「${file.name}」吗？`)) return
  try {
    await request('/front/chief/workspace/attachments/delete', {
      attachmentId: file.id
    })
    await loadWorkspace(
      selectedProject.value?.id,
      selectedMilestone.value?.id,
      selectedTask.value?.id
    )
  } catch (err) {
    error.value = `删除附件失败：${messageOf(err)}`
  }
}

function attachmentMenuItems(file: ProjectAttachment): DropdownMenuItem[][] {
  return [
    [
      { label: '下载', onSelect: () => void downloadAttachment(file) },
      {
        label: '移除',
        color: 'error',
        onSelect: () => void deleteAttachment(file)
      }
    ]
  ]
}

async function handleQuoteToAi(payload: { text: string; range: string }) {
  editorVisible.value = false
  await nextTick()
  composerRef.value?.setQuote(payload)
}
</script>

<template>
  <div class="flex h-dvh flex-col bg-default" :data-ready="ready ? 'true' : 'false'">
    <main
      class="flex min-h-0 flex-1 flex-col overflow-y-auto min-[1360px]:grid min-[1360px]:overflow-hidden min-[1360px]:grid-cols-[var(--wb-tracks)] min-[1360px]:divide-x min-[1360px]:divide-default"
      :style="{ '--wb-tracks': boardTracks }"
    >
      <UAlert
        v-if="error"
        class="m-3"
        color="error"
        variant="subtle"
        title="项目工作台"
        :description="error"
        :close="true"
        @update:open="error = ''"
      />

      <WorkbenchColumn
        title="项目"
        :count="projects.length"
        :collapsed="collapsedColumns[0]"
        hide-scrollbar
        @toggle="toggleColumn(0)"
      >
        <template #action>
          <UBadge v-if="showArchived" color="warning" variant="subtle" size="sm">归档</UBadge>
          <UButton
            v-if="!showArchived"
            color="neutral"
            variant="ghost"
            square
            aria-label="新增项目"
            @click="addingProject = true"
          >
            ＋
          </UButton>
        </template>
        <form v-if="addingProject" class="flex flex-col gap-2 pb-1" @submit.prevent="submitProject">
          <UInput v-model="projectDraft" placeholder="项目名称" aria-label="项目名称" autofocus />
          <USelect v-model="newProjectExpertId" :items="expertItems" aria-label="新项目绑定专家" />
          <div class="flex justify-end gap-1">
            <UButton type="submit" variant="ghost" :disabled="!projectDraft.trim()">确定</UButton>
            <UButton type="button" color="neutral" variant="ghost" @click="resetProjectDraft">
              取消
            </UButton>
          </div>
        </form>
        <p v-if="loading" class="px-2 py-4 text-xs text-muted">正在加载项目…</p>
        <p v-else-if="!projects.length" class="px-2 py-4 text-xs text-muted">
          {{ showArchived ? '暂无归档项目' : '暂无项目，点击 ＋ 新建' }}
        </p>
        <div v-for="project in projects" :key="project.id" class="relative">
          <button
            type="button"
            class="flex min-h-16 w-full items-center gap-2 rounded-md p-2.5 pe-10 text-left transition-colors"
            :class="
              project.id === selectedProjectId
                ? 'bg-primary/10'
                : 'bg-elevated/40 hover:bg-elevated/60'
            "
            @click="selectProject(project)"
          >
            <span v-if="collapsedColumns[0]" class="mx-auto text-2xl">
              {{ project.name.slice(0, 1) }}
            </span>
            <span v-else class="flex min-w-0 flex-1 flex-col gap-1">
              <span class="flex items-center gap-1">
                <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ project.name }}</span>
                <UBadge color="neutral" variant="subtle" size="sm">{{ project.status }}</UBadge>
                <UBadge color="primary" variant="subtle" size="sm">
                  {{ projectPhaseLabel(project) }}
                </UBadge>
              </span>
              <span class="flex min-w-0 items-center gap-1">
                <span class="min-w-0 flex-1 truncate text-xs text-muted">
                  {{ project.description || '未填写项目说明' }}
                </span>
                <UBadge
                  :color="project.expertId ? 'primary' : 'neutral'"
                  variant="subtle"
                  size="sm"
                  class="max-w-24 shrink-0"
                >
                  {{ project.expertName || '未绑定专家' }}
                </UBadge>
              </span>
              <span class="truncate text-[11px] text-dimmed">
                {{ projectMeta(project) }} · ¥{{ project.used.toFixed(2) }}/¥{{
                  project.limit.toFixed(2)
                }}
              </span>
            </span>
          </button>
          <div v-if="!collapsedColumns[0]" class="absolute end-1 top-2">
            <UDropdownMenu :items="projectMenuItems(project)">
              <UButton
                color="neutral"
                variant="ghost"
                size="xs"
                square
                :aria-label="`项目操作 ${project.name}`"
              >
                ⋯
              </UButton>
            </UDropdownMenu>
          </div>
        </div>
        <template #footer>
          <div class="border-t border-default px-3 py-2">
            <UButton color="neutral" variant="ghost" block size="sm" @click="toggleArchived">
              {{ showArchived ? '返回' : '归档' }}
            </UButton>
          </div>
        </template>
      </WorkbenchColumn>

      <WorkbenchColumn
        title="任务包"
        :count="milestones.length"
        :collapsed="collapsedColumns[1]"
        @toggle="toggleColumn(1)"
      >
        <template #action>
          <UButton
            color="neutral"
            variant="ghost"
            square
            aria-label="新增任务包"
            :disabled="!selectedProject || showArchived"
            @click="startAddMilestone"
          >
            ＋
          </UButton>
        </template>
        <form
          v-if="addingMilestone"
          class="flex flex-col gap-2 pb-1"
          @submit.prevent="submitMilestone"
        >
          <UInput v-model="milestoneDraft" placeholder="任务包名称" aria-label="任务包名称" />
          <div class="flex justify-end gap-1">
            <UButton type="submit" variant="ghost" :disabled="!milestoneDraft.trim()">确定</UButton>
            <UButton type="button" color="neutral" variant="ghost" @click="addingMilestone = false">
              取消
            </UButton>
          </div>
        </form>
        <div v-for="milestone in milestones" :key="milestone.id" class="relative">
          <button
            type="button"
            class="flex min-h-16 w-full items-center gap-2 rounded-md p-2.5 pe-10 text-left transition-colors"
            :class="
              milestone.id === selectedMilestoneId
                ? 'bg-primary/10'
                : 'bg-elevated/40 hover:bg-elevated/60'
            "
            @click="selectMilestone(milestone)"
          >
            <span v-if="collapsedColumns[1]" class="mx-auto text-2xl">
              {{ milestone.title.slice(0, 1) }}
            </span>
            <span v-else class="flex min-w-0 flex-1 flex-col gap-1">
              <span class="truncate text-sm">{{ milestone.title }}</span>
              <span class="truncate text-xs text-dimmed">{{ milestoneMeta(milestone) }}</span>
            </span>
          </button>
          <div v-if="!collapsedColumns[1]" class="absolute end-1 top-2">
            <UDropdownMenu :items="milestoneMenuItems(milestone)">
              <UButton
                color="neutral"
                variant="ghost"
                size="xs"
                square
                :aria-label="`任务包操作 ${milestone.title}`"
              >
                ⋯
              </UButton>
            </UDropdownMenu>
          </div>
        </div>
      </WorkbenchColumn>

      <WorkbenchColumn
        title="任务"
        :count="tasks.length"
        :collapsed="collapsedColumns[2]"
        @toggle="toggleColumn(2)"
      >
        <template #action>
          <UButton
            color="neutral"
            variant="ghost"
            square
            aria-label="新增任务"
            :disabled="!selectedMilestone || showArchived || !projectExpertAvailable"
            @click="startAddTask"
          >
            ＋
          </UButton>
        </template>
        <form v-if="addingTask" class="flex flex-col gap-2 pb-1" @submit.prevent="submitTask">
          <UInput v-model="taskDraft" placeholder="任务名称" aria-label="任务名称" />
          <div class="flex justify-end gap-1">
            <UButton type="submit" variant="ghost" :disabled="!taskDraft.trim()">确定</UButton>
            <UButton type="button" color="neutral" variant="ghost" @click="addingTask = false">
              取消
            </UButton>
          </div>
        </form>
        <div v-for="task in tasks" :key="task.id" class="relative">
          <button
            type="button"
            class="flex min-h-16 w-full items-center gap-2 rounded-md p-2.5 pe-10 text-left transition-colors"
            :class="
              task.id === selectedTaskId ? 'bg-primary/10' : 'bg-elevated/40 hover:bg-elevated/60'
            "
            @click="selectTask(task)"
          >
            <span v-if="collapsedColumns[2]" class="mx-auto text-2xl">
              {{ task.title.slice(0, 1) }}
            </span>
            <span v-else class="flex min-w-0 flex-1 flex-col gap-1">
              <span class="truncate text-sm">{{ task.title }}</span>
              <span class="truncate text-xs text-dimmed">{{ taskMeta(task) }}</span>
            </span>
          </button>
          <div v-if="!collapsedColumns[2]" class="absolute end-1 top-2">
            <UDropdownMenu :items="taskMenuItems(task)">
              <UButton
                color="neutral"
                variant="ghost"
                size="xs"
                square
                :aria-label="`任务操作 ${task.title}`"
              >
                ⋯
              </UButton>
            </UDropdownMenu>
          </div>
        </div>
      </WorkbenchColumn>

      <WorkbenchColumn title="会话" :count="messages.length" :collapsible="false">
        <template #action>
          <UButton
            color="neutral"
            variant="ghost"
            square
            :aria-label="attachmentVisible ? '隐藏附件栏' : '显示附件栏'"
            @click="attachmentVisible = !attachmentVisible"
          >
            {{ attachmentVisible ? '◉' : '○' }}
          </UButton>
          <UButton
            color="neutral"
            variant="ghost"
            square
            :aria-label="editorVisible ? '隐藏成果物编辑器' : '显示成果物编辑器'"
            @click="editorVisible = !editorVisible"
          >
            ▤
          </UButton>
        </template>
        <div class="flex h-full min-h-0 flex-col gap-3 overflow-y-auto">
          <div
            v-if="!selectedTask"
            class="rounded-md border border-dashed border-default p-4 text-xs text-muted"
          >
            先在左侧选择或新建一个任务。任务会自动创建独立会话，并限定在当前项目背景下。
          </div>
          <template v-else>
            <div v-if="!messages.length" class="px-2 py-5 text-center text-xs text-muted">
              还没有沟通记录，发送第一条任务消息。
            </div>
            <div
              v-for="message in messages"
              :key="message.id"
              class="flex max-w-[88%] flex-col gap-1"
              :class="message.role === 'user' ? 'self-end items-end' : 'self-start items-start'"
            >
              <!-- renderMarkdown sanitizes raw HTML and unsafe URL protocols. -->
              <!-- eslint-disable vue/no-v-html -->
              <div
                class="project-chat-markdown rounded-lg px-3 py-2 text-sm"
                :class="message.role === 'user' ? 'bg-primary/10' : 'bg-elevated/60'"
                v-html="renderMarkdown(message.content)"
              />
              <!-- eslint-enable vue/no-v-html -->
              <span v-if="message.attachments?.length" class="text-[11px] text-dimmed">
                附件：{{ message.attachments.map((file) => file.name).join('、') }}
              </span>
              <div v-if="message.role === 'assistant'" class="flex gap-1">
                <UButton
                  color="neutral"
                  variant="ghost"
                  size="xs"
                  :disabled="!['executing', 'adjusting', 'confirmed'].includes(selectedTask.phase)"
                  @click="setMessageAsDraft(message)"
                >
                  设为成果草稿
                </UButton>
              </div>
            </div>
            <div v-if="busy" class="rounded-md bg-elevated/40 px-3 py-2 text-xs text-muted">
              专家 Agent 正在结合当前项目上下文处理…
            </div>
            <div v-if="pendingRun" class="rounded-md border border-warning/40 bg-warning/10 p-3">
              <p class="text-sm font-medium">工具调用等待确认</p>
              <p class="mt-1 text-xs text-muted">默认全部拒绝，请逐项确认允许执行的工具调用。</p>
              <div class="mt-2 flex flex-col gap-2">
                <div
                  v-for="call in pendingRun.calls"
                  :key="call.callId"
                  class="rounded-md bg-default/60 p-2"
                >
                  <div class="flex items-center gap-2">
                    <span class="min-w-0 flex-1 truncate font-mono text-xs">
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
                      size="sm"
                      :aria-label="`${call.approved ? '拒绝' : '允许'} ${call.tool}`"
                    />
                  </div>
                  <pre
                    class="mt-1 max-h-24 overflow-auto whitespace-pre-wrap break-all text-[11px] text-muted"
                    >{{ JSON.stringify(call.arguments, null, 2) }}</pre>
                </div>
              </div>
              <div class="mt-2 flex gap-2">
                <UButton size="xs" :loading="busy" @click="approveRun">按选择继续</UButton>
                <UButton
                  size="xs"
                  color="error"
                  variant="outline"
                  :disabled="busy"
                  @click="rejectRun"
                >
                  全部拒绝
                </UButton>
              </div>
            </div>
          </template>
        </div>
        <template #footer>
          <div v-if="selectedTask" class="border-t border-default">
            <UAlert
              v-if="chatError"
              class="m-2"
              color="error"
              variant="subtle"
              :description="chatError"
            />
            <div class="flex flex-wrap items-center gap-2 border-b border-default px-3 py-2">
              <UBadge color="neutral" variant="subtle" size="sm">
                {{ taskPhaseLabel(selectedTask) }}
              </UBadge>
              <UButton
                v-if="selectedTask.phase === 'communicating'"
                size="xs"
                @click="openSpecConfirmation"
              >
                确定需求
              </UButton>
              <UButton
                v-else-if="selectedTask.phase === 'spec_confirmed'"
                size="xs"
                @click="startTaskExecution"
              >
                开始执行
              </UButton>
              <template v-else-if="selectedTask.phase === 'executing'">
                <span class="text-xs text-muted">专家执行后，将满意回复设为成果草稿</span>
              </template>
              <template v-else-if="selectedTask.phase === 'adjusting'">
                <UButton
                  v-if="selectedDeliverable"
                  size="xs"
                  color="neutral"
                  variant="outline"
                  @click="editorVisible = true"
                >
                  编辑草稿
                </UButton>
                <UButton v-if="selectedDeliverable" size="xs" @click="confirmDeliverableVersion">
                  确定 V{{ (selectedDeliverable?.latestVersionNo || 0) + 1 }}
                </UButton>
              </template>
              <template v-else-if="selectedTask.phase === 'confirmed'">
                <UButton size="xs" color="neutral" variant="outline" @click="editorVisible = true">
                  查看 V{{ selectedDeliverable?.latestVersionNo }}
                </UButton>
                <UButton size="xs" color="neutral" variant="soft" @click="adjustDeliverable">
                  继续调整
                </UButton>
                <UButton size="xs" @click="completeTaskDelivery">完成任务</UButton>
              </template>
              <UBadge
                v-else-if="selectedTask.phase === 'completed'"
                color="success"
                variant="subtle"
                size="sm"
              >
                已完成
              </UBadge>
            </div>
            <WorkbenchComposer
              ref="composerRef"
              :reset-key="selectedTask.id"
              :busy="busy"
              :show-depth="false"
              :stop-speech-key="stopSpeechKey"
              @send="handleSendMessage"
            />
          </div>
        </template>
      </WorkbenchColumn>

      <aside
        v-if="editorVisible"
        class="flex min-h-0 flex-col overflow-hidden border-b border-default bg-default max-[1359px]:min-h-[480px] min-[1360px]:border-b-0"
        aria-label="成果物编辑器"
      >
        <header
          class="flex min-h-12 flex-wrap items-center gap-2 border-b border-default px-4 py-2"
        >
          <h2 class="min-w-0 flex-1 truncate text-sm font-semibold">
            {{ selectedDeliverable?.title || '成果物' }}
          </h2>
          <UBadge v-if="selectedDeliverable" color="neutral" variant="subtle" size="sm">
            {{
              selectedDeliverable.latestVersionNo
                ? `V${selectedDeliverable.latestVersionNo}`
                : '草稿'
            }}
          </UBadge>
          <UButton
            v-if="selectedDeliverable"
            color="neutral"
            variant="ghost"
            size="xs"
            @click="saveDeliverableDraft"
          >
            保存草稿
          </UButton>
          <UButton
            color="neutral"
            variant="ghost"
            square
            aria-label="关闭成果物编辑器"
            @click="editorVisible = false"
          >
            ×
          </UButton>
        </header>
        <div class="min-h-0 flex-1 overflow-hidden">
          <ClientOnly>
            <div
              v-if="!selectedDeliverable"
              class="flex h-full items-center justify-center p-6 text-center text-sm text-muted"
            >
              将专家回复设为成果草稿后，可在这里编辑和确认版本。
            </div>
            <RichTextEditor
              v-else
              v-model="documentHtml"
              placeholder="编辑成果草稿…"
              @quote="handleQuoteToAi"
            />
            <template #fallback><div class="h-full bg-default" /></template>
          </ClientOnly>
        </div>
        <div
          v-if="selectedDeliverable?.versions.length"
          class="flex max-h-24 flex-none flex-wrap gap-1 overflow-y-auto border-t border-default p-2"
        >
          <UBadge
            v-for="version in selectedDeliverable.versions"
            :key="version.id"
            color="success"
            variant="subtle"
            size="sm"
          >
            V{{ version.versionNo }}
          </UBadge>
        </div>
      </aside>

      <WorkbenchColumn
        v-if="attachmentVisible"
        title="附件"
        :count="attachments.length"
        :collapsible="false"
      >
        <UCollapsible
          v-for="group in attachmentGroups"
          :key="group.kind"
          v-model:open="attachmentGroupsOpen[group.kind]"
        >
          <UButton color="neutral" variant="ghost" block class="justify-between px-2">
            <span>{{ group.kind }} · {{ group.items.length }}</span>
            <span>{{ attachmentGroupsOpen[group.kind] ? '⌃' : '⌄' }}</span>
          </UButton>
          <template #content>
            <div
              v-for="file in group.items"
              :key="file.id"
              class="relative my-2 rounded-lg border border-default bg-elevated/40 p-2.5 pe-9"
            >
              <button
                type="button"
                class="flex w-full min-w-0 flex-col gap-1 text-left"
                @click="openPreview(file)"
              >
                <span class="truncate text-sm">{{ file.name }}</span>
                <span class="truncate text-[11px] text-dimmed">
                  {{ file.ext.toUpperCase() }} · {{ formatSize(file.size) }}
                </span>
              </button>
              <div class="absolute end-1 top-1">
                <UDropdownMenu :items="attachmentMenuItems(file)">
                  <UButton
                    color="neutral"
                    variant="ghost"
                    size="xs"
                    square
                    :aria-label="`附件操作 ${file.name}`"
                  >
                    ⋯
                  </UButton>
                </UDropdownMenu>
              </div>
            </div>
          </template>
        </UCollapsible>
      </WorkbenchColumn>
    </main>

    <UModal v-model:open="projectEditorOpen" title="编辑项目">
      <template #body>
        <form id="project-form" class="grid gap-3" @submit.prevent="saveProject">
          <label class="grid gap-1 text-sm">
            项目名称
            <UInput v-model="projectForm.name" />
          </label>
          <label class="grid gap-1 text-sm">
            项目说明
            <UTextarea v-model="projectForm.description" :rows="2" />
          </label>
          <UAlert
            v-if="projectExpertDisabled"
            color="warning"
            variant="subtle"
            description="当前绑定的专家已停用，请重新选择启用中的专家后再保存。"
          />
          <label class="grid gap-1 text-sm">
            绑定专家 Agent
            <USelect
              v-model="projectForm.expertId"
              :items="expertItems"
              placeholder="选择专家 Agent"
            />
            <span class="text-xs font-normal text-muted">
              项目内所有任务会话会继承并锁定使用该专家；更换后，现有任务会话同步切换。
            </span>
          </label>
          <label class="grid gap-1 text-sm">
            项目目标
            <UTextarea
              v-model="projectForm.objective"
              :rows="3"
              placeholder="会作为专家 Agent 沟通时的重要上下文"
            />
          </label>
          <label class="grid gap-1 text-sm">
            项目范围
            <UTextarea v-model="projectForm.scope" :rows="3" />
          </label>
          <label class="grid gap-1 text-sm">
            状态
            <USelect
              v-model="projectForm.status"
              :items="['进行中', '待验收', '已完成', '复盘', '试验']"
            />
          </label>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="outline" @click="projectEditorOpen = false"
            >取消</UButton
          >
          <UButton type="submit" form="project-form" :disabled="!projectForm.name.trim()"
            >保存</UButton
          >
        </div>
      </template>
    </UModal>

    <UModal v-model:open="taskEditorOpen" title="编辑任务">
      <template #body>
        <form id="task-form" class="grid gap-3" @submit.prevent="saveTask">
          <label class="grid gap-1 text-sm">
            任务名称
            <UInput v-model="taskForm.title" />
          </label>
          <label class="grid gap-1 text-sm">
            优先级
            <USelect v-model="taskForm.priority" :items="['P0', 'P1', 'P2']" />
          </label>
          <label class="grid gap-1 text-sm">
            状态
            <USelect v-model="taskForm.status" :items="['未开始', '进行中', '待审核']" />
          </label>
          <label class="grid gap-1 text-sm">
            截止日期
            <UInput v-model="taskForm.dueAt" type="date" />
          </label>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="outline" @click="taskEditorOpen = false">取消</UButton>
          <UButton type="submit" form="task-form" :disabled="!taskForm.title.trim()">保存</UButton>
        </div>
      </template>
    </UModal>

    <UModal v-model:open="specConfirmOpen" title="确定任务需求">
      <template #body>
        <form id="task-spec-form" class="grid gap-3" @submit.prevent="confirmTaskSpec">
          <label class="grid gap-1 text-sm">
            任务目标
            <UTextarea
              v-model="specDraft.objective"
              :rows="3"
              placeholder="这次任务最终要解决什么"
            />
          </label>
          <label class="grid gap-1 text-sm">
            范围与约束
            <UTextarea v-model="specDraft.scope" :rows="3" placeholder="包含什么、不包含什么" />
          </label>
          <label class="grid gap-1 text-sm">
            验收标准
            <UTextarea
              v-model="specDraft.acceptanceCriteria"
              :rows="3"
              placeholder="满足哪些条件才算完成"
            />
          </label>
        </form>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton color="neutral" variant="outline" @click="specConfirmOpen = false">
            取消
          </UButton>
          <UButton type="submit" form="task-spec-form" :disabled="!specDraft.objective.trim()">
            确认需求
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="workflowOpen"
      :title="selectedProject ? `${selectedProject.name} · 项目流程` : '项目流程'"
      :ui="{ content: 'sm:max-w-3xl' }"
    >
      <template #body>
        <div class="flex flex-col gap-4">
          <UAlert
            v-if="workflowError"
            color="error"
            variant="subtle"
            :description="workflowError"
          />

          <template v-if="selectedProject">
            <div v-if="selectedProject.phase === 'requirements'" class="flex flex-col gap-3">
              <p class="text-sm font-medium">需求</p>
              <UTextarea
                v-model="requirementDraft"
                :rows="10"
                placeholder="项目目标、范围、不包含事项、交付标准和时间要求"
              />
              <p class="text-xs text-muted">当前为草稿，确认后锁定为正式版本。</p>
              <div class="flex flex-wrap justify-end gap-2">
                <UButton
                  color="neutral"
                  variant="soft"
                  :loading="workflowBusy"
                  @click="generateProjectDocument('requirements')"
                >
                  专家生成需求
                </UButton>
                <UButton
                  color="neutral"
                  variant="outline"
                  :disabled="workflowBusy"
                  @click="saveProjectDocument('requirements')"
                >
                  保存草稿
                </UButton>
                <UButton
                  :loading="workflowBusy"
                  :disabled="!requirementDraft.trim()"
                  @click="confirmProjectDocument('requirements')"
                >
                  确定需求
                </UButton>
              </div>
            </div>

            <div
              v-else-if="selectedProject.phase === 'requirements_confirmed'"
              class="flex flex-col gap-3"
            >
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">需求已确定</p>
                <UBadge color="success" variant="subtle" size="sm">
                  V{{ requirementsDocument?.latestVersionNo || 0 }}
                </UBadge>
              </div>
              <div
                class="max-h-56 overflow-y-auto rounded-md bg-elevated/50 p-3 text-sm whitespace-pre-wrap"
              >
                {{ selectedProject.requirementText }}
              </div>
              <details
                v-if="requirementsDocument?.versions?.length"
                class="rounded-md border border-default p-3 text-xs"
              >
                <summary class="cursor-pointer font-medium">
                  需求版本历史（{{ requirementsDocument.versions.length }}）
                </summary>
                <div class="mt-2 flex flex-col gap-2">
                  <details
                    v-for="version in requirementsDocument.versions"
                    :key="version.id"
                    class="rounded bg-elevated/40 p-2"
                  >
                    <summary class="cursor-pointer">
                      V{{ version.versionNo }} · {{ version.confirmedAt }}
                    </summary>
                    <pre class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap text-xs">{{
                      version.contentText
                    }}</pre>
                  </details>
                </div>
              </details>
              <UAlert
                v-if="solutionDocument?.status === 'stale'"
                color="warning"
                variant="subtle"
                description="需求已变更，当前方案需要重新生成或重新确认。"
              />
              <div class="flex justify-end gap-2">
                <UButton
                  color="neutral"
                  variant="outline"
                  :loading="workflowBusy"
                  @click="adjustProjectDocument('requirements')"
                >
                  调整需求
                </UButton>
                <UButton :loading="workflowBusy" @click="generateProjectDocument('solution')">
                  生成项目方案
                </UButton>
              </div>
            </div>

            <div v-else-if="selectedProject.phase === 'solution'" class="flex flex-col gap-3">
              <p class="text-sm font-medium">方案</p>
              <UTextarea
                v-model="solutionDraft"
                :rows="12"
                placeholder="整体思路、阶段、关键路径、风险、依赖和验收方式"
              />
              <p class="text-xs text-muted">当前为草稿，确认后锁定为正式版本。</p>
              <div class="flex flex-wrap justify-end gap-2">
                <UButton
                  color="neutral"
                  variant="soft"
                  :loading="workflowBusy"
                  @click="generateProjectDocument('solution')"
                >
                  专家生成方案
                </UButton>
                <UButton
                  color="neutral"
                  variant="outline"
                  :disabled="workflowBusy"
                  @click="saveProjectDocument('solution')"
                >
                  保存草稿
                </UButton>
                <UButton
                  :loading="workflowBusy"
                  :disabled="!solutionDraft.trim()"
                  @click="confirmProjectDocument('solution')"
                >
                  确定方案
                </UButton>
              </div>
            </div>

            <div
              v-else-if="selectedProject.phase === 'solution_confirmed'"
              class="flex flex-col gap-3"
            >
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">方案已确定</p>
                <UBadge color="success" variant="subtle" size="sm">
                  V{{ solutionDocument?.latestVersionNo || 0 }}
                </UBadge>
                <UBadge
                  v-if="solutionDocument?.sourceVersionNo"
                  color="neutral"
                  variant="subtle"
                  size="sm"
                >
                  基于需求 V{{ solutionDocument.sourceVersionNo }}
                </UBadge>
              </div>
              <div
                class="max-h-56 overflow-y-auto rounded-md bg-elevated/50 p-3 text-sm whitespace-pre-wrap"
              >
                {{ selectedProject.solutionText }}
              </div>
              <details
                v-if="solutionDocument?.versions?.length"
                class="rounded-md border border-default p-3 text-xs"
              >
                <summary class="cursor-pointer font-medium">
                  方案版本历史（{{ solutionDocument.versions.length }}）
                </summary>
                <div class="mt-2 flex flex-col gap-2">
                  <details
                    v-for="version in solutionDocument.versions"
                    :key="version.id"
                    class="rounded bg-elevated/40 p-2"
                  >
                    <summary class="cursor-pointer">
                      V{{ version.versionNo }} · {{ version.confirmedAt }}
                    </summary>
                    <pre class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap text-xs">{{
                      version.contentText
                    }}</pre>
                  </details>
                </div>
              </details>
              <UAlert
                v-if="taskPlanDocument?.status === 'stale'"
                color="warning"
                variant="subtle"
                description="方案已变更，当前计划清单需要重新生成或重新确认。"
              />
              <div class="flex justify-end gap-2">
                <UButton
                  color="neutral"
                  variant="outline"
                  :loading="workflowBusy"
                  @click="adjustProjectDocument('solution')"
                >
                  调整方案
                </UButton>
                <UButton :loading="workflowBusy" @click="generateProjectTaskPlan">
                  生成任务分解
                </UButton>
              </div>
            </div>

            <div v-else-if="selectedProject.phase === 'task_planning'" class="flex flex-col gap-3">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">任务分解</p>
                <UBadge color="neutral" variant="subtle" size="sm"> 草稿 </UBadge>
                <UButton
                  class="ms-auto"
                  size="xs"
                  color="neutral"
                  variant="soft"
                  :loading="workflowBusy"
                  @click="generateProjectTaskPlan"
                >
                  重新生成
                </UButton>
              </div>
              <div class="max-h-[48vh] space-y-2 overflow-y-auto pe-1">
                <UCard
                  v-for="(pkg, packageIndex) in planPackages"
                  :key="`${pkg.name}-${packageIndex}`"
                  :ui="{ body: 'p-3 sm:p-3' }"
                >
                  <p class="text-sm font-medium">{{ pkg.name }}</p>
                  <div class="mt-2 flex flex-col gap-1.5">
                    <div
                      v-for="(task, taskIndex) in pkg.tasks"
                      :key="`${task.key || taskIndex}`"
                      class="rounded-md bg-elevated/50 px-2.5 py-2 text-xs"
                    >
                      <p class="font-medium">
                        {{ task.key ? `${task.key} · ` : '' }}{{ task.title }}
                      </p>
                      <p v-if="task.description" class="mt-1 text-muted">
                        {{ task.description }}
                      </p>
                      <p v-if="task.acceptanceCriteria" class="mt-1 text-dimmed">
                        验收：{{ task.acceptanceCriteria }}
                      </p>
                    </div>
                  </div>
                </UCard>
              </div>
              <div class="flex justify-end">
                <UButton
                  :loading="workflowBusy"
                  :disabled="!planPackages.length"
                  @click="confirmProjectTaskPlan"
                >
                  确定任务
                </UButton>
              </div>
            </div>

            <div
              v-else-if="selectedProject.phase === 'tasks_confirmed'"
              class="flex flex-col gap-3"
            >
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">任务已确定</p>
                <UBadge color="success" variant="subtle" size="sm">
                  V{{ taskPlanDocument?.latestVersionNo || 0 }}
                </UBadge>
                <UBadge
                  v-if="taskPlanDocument?.sourceVersionNo"
                  color="neutral"
                  variant="subtle"
                  size="sm"
                >
                  基于方案 V{{ taskPlanDocument.sourceVersionNo }}
                </UBadge>
              </div>
              <p class="text-sm text-muted">
                执行时将创建 {{ planPackages.length }} 个任务包和
                {{ planPackages.reduce((total, pkg) => total + pkg.tasks.length, 0) }}
                个任务，并由专家 Agent 自动生成草稿。
              </p>
              <details
                v-if="taskPlanDocument?.versions?.length"
                class="rounded-md border border-default p-3 text-xs"
              >
                <summary class="cursor-pointer font-medium">
                  计划版本历史（{{ taskPlanDocument.versions.length }}）
                </summary>
                <div class="mt-2 flex flex-col gap-2">
                  <details
                    v-for="version in taskPlanDocument.versions"
                    :key="version.id"
                    class="rounded bg-elevated/40 p-2"
                  >
                    <summary class="cursor-pointer">
                      V{{ version.versionNo }} · {{ version.confirmedAt }}
                    </summary>
                    <pre class="mt-2 max-h-40 overflow-y-auto whitespace-pre-wrap text-xs">{{
                      version.contentText
                    }}</pre>
                  </details>
                </div>
              </details>
              <div class="flex justify-end gap-2">
                <UButton
                  color="neutral"
                  variant="outline"
                  :loading="workflowBusy"
                  @click="adjustProjectTaskPlan"
                >
                  调整计划
                </UButton>
                <UButton :loading="workflowBusy" @click="executeProjectTasks">
                  开始自动执行
                </UButton>
              </div>
            </div>

            <div v-else class="flex flex-col gap-3">
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">{{ projectPhaseLabel(selectedProject) }}</p>
                <UBadge
                  :color="
                    selectedProject.executionStatus === 'failed'
                      ? 'error'
                      : selectedProject.executionStatus === 'completed'
                        ? 'success'
                        : 'warning'
                  "
                  variant="subtle"
                  size="sm"
                >
                  {{ selectedProject.executionStatus }}
                </UBadge>
              </div>
              <p class="text-sm text-muted">
                已创建 {{ executionTaskCount }} 个任务。自动执行只生成成果草稿，V1/V2
                仍需在任务中人工确定。
              </p>
              <UAlert
                v-if="selectedProject.executionError"
                color="error"
                variant="subtle"
                :description="selectedProject.executionError"
              />
              <div v-if="selectedProject.executionStatus === 'failed'" class="flex justify-end">
                <UButton :loading="workflowBusy" @click="executeProjectTasks">
                  重试自动执行
                </UButton>
              </div>
              <div
                v-else-if="selectedProject.phase === 'reviewing' && allProjectTasksConfirmed"
                class="flex justify-end"
              >
                <UButton :loading="workflowBusy" @click="completeProject"> 完成项目 </UButton>
              </div>
            </div>
          </template>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end">
          <UButton color="neutral" variant="outline" @click="workflowOpen = false"> 关闭 </UButton>
        </div>
      </template>
    </UModal>

    <FilePreview v-model:open="previewOpen" :file="previewFile" />
  </div>
</template>

<style scoped>
.project-chat-markdown :deep(> :first-child) {
  margin-top: 0;
}

.project-chat-markdown :deep(> :last-child) {
  margin-bottom: 0;
}

.project-chat-markdown :deep(p) {
  margin: 0.35rem 0;
  line-height: 1.65;
}

.project-chat-markdown :deep(h1),
.project-chat-markdown :deep(h2),
.project-chat-markdown :deep(h3) {
  margin: 0.65rem 0 0.35rem;
  font-weight: 600;
  line-height: 1.35;
}

.project-chat-markdown :deep(h1) {
  font-size: 1.05rem;
}

.project-chat-markdown :deep(h2) {
  font-size: 1rem;
}

.project-chat-markdown :deep(h3) {
  font-size: 0.95rem;
}

.project-chat-markdown :deep(ul),
.project-chat-markdown :deep(ol) {
  margin: 0.35rem 0;
  padding-inline-start: 1.25rem;
}

.project-chat-markdown :deep(ul) {
  list-style: disc;
}

.project-chat-markdown :deep(ol) {
  list-style: decimal;
}

.project-chat-markdown :deep(code) {
  border-radius: 0.25rem;
  background: var(--ui-bg-muted);
  padding: 0.08rem 0.25rem;
}

.project-chat-markdown :deep(pre) {
  overflow-x: auto;
  border-radius: 0.45rem;
  background: var(--ui-bg-muted);
  padding: 0.6rem;
}

.project-chat-markdown :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.project-chat-markdown :deep(th),
.project-chat-markdown :deep(td) {
  border: 1px solid var(--ui-border);
  padding: 0.35rem 0.45rem;
  text-align: left;
}
</style>
