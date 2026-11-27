<script setup lang="ts">
/** 管理后台：按配置依赖排序（用户与角色 → 模型 → MCP → SKILL → 专家 → 额度总览 → 操作日志） */
import {
  callShortcutKeyLabel,
  isCallShortcutKeyEvent,
  normalizeCallShortcutKey
} from '~/utils/callShortcut'

definePageMeta({ layout: 'console', title: '管理后台', middleware: 'admin-auth' })

const sections = [
  { value: 'users', label: '用户与角色' },
  { value: 'model', label: '模型' },
  { value: 'mcp', label: 'MCP' },
  { value: 'skill', label: 'SKILL' },
  { value: 'expert', label: '专家' },
  { value: 'quota', label: '额度总览' },
  { value: 'logs', label: '操作日志' },
  { value: 'chief', label: '总管设置' },
  { value: 'call', label: '通话设置' }
] as const
const section = ref<(typeof sections)[number]['value']>('users')

type RegistryTab = 'expert' | 'model' | 'mcp' | 'skill'
/** 专家 / 模型 / MCP / SKILL 共用同一资源管理组件，仅传入当前模块 */
const registryTab = computed<RegistryTab>(() => {
  const value = section.value
  return value === 'users' ||
    value === 'quota' ||
    value === 'logs' ||
    value === 'chief' ||
    value === 'call'
    ? 'expert'
    : value
})

const roles = ['拥有者', '管理员', '成员', '访客']

interface Member {
  id: string
  name: string
  email: string
  role: string
  enabled: boolean
  lastActive: string
  accountStatus: 'invited' | 'password_change_required' | 'active'
}

interface QuotaSummaryItem {
  label: string
  value: string
  note: string
}

interface ProjectQuota {
  id: string
  name: string
  used: number
  limit: number
}

interface ModelQuota {
  id: string
  model: string
  price: string
  used: number
  limit: number
}

interface AlertSettings {
  threshold: string
  channel: string
  notifyAdmin: boolean
  stopOnExceed: boolean
}

interface ChiefSettings {
  enabled: boolean
  recursionMode: 'sequential' | 'parallel'
  recursionK: number
  recursionMax: number
  regressionEnabled: boolean
  regressionCases: number
  autoAdoptMinScore: number
  autoAdoptMinGain: number
  domainExperts: Record<string, string>
}

interface VoiceCallSettings {
  pushToTalkKey: string
  asrUrl: string
  ttsUrl: string
  updateBy?: string | null
  updateTime?: string
}

interface ExpertOption {
  id: string
  name: string
  role: string
  enabled: boolean
}

const chiefSettings = reactive<ChiefSettings>({
  enabled: true,
  recursionMode: 'sequential',
  recursionK: 1,
  recursionMax: 2,
  regressionEnabled: true,
  regressionCases: 2,
  autoAdoptMinScore: 60,
  autoAdoptMinGain: 5,
  domainExperts: {}
})
const chiefExperts = ref<ExpertOption[]>([])
const chiefSettingsLoading = ref(false)
const chiefSettingsError = ref('')
const chiefSettingsSaved = ref(false)
const chiefDomains = [
  { value: 'customer', label: '客户' },
  { value: 'project', label: '项目' },
  { value: 'content', label: '内容' },
  { value: 'operations', label: '事务' },
  { value: 'programming', label: '编程' },
  { value: 'general', label: '通用' }
] as const
const callStopSpeechKey = ref('Escape')
const callAsrUrl = ref('https://api.deepseek.com/v1/tools/asr')
const callTtsUrl = ref('https://api.deepseek.com/v1/tools/tts')
const callSettingsLoading = ref(false)
const callSettingsError = ref('')
const callSettingsSaved = ref(false)
const callSettingsLoaded = ref(false)
const callShortcutTesting = ref(false)
const callShortcutTestState = ref<'idle' | 'waiting' | 'passed' | 'failed'>('idle')
const callShortcutTestMessage = ref('点击测试，然后按一下当前快捷键。')
const callShortcutTestToneClass = computed(() => {
  if (callShortcutTestState.value === 'passed') return 'text-success'
  if (callShortcutTestState.value === 'failed') return 'text-error'
  return 'text-muted'
})
let callShortcutTestTimer: ReturnType<typeof setTimeout> | null = null
const callShortcutOptions = [
  { label: 'Esc', value: 'Escape' },
  { label: '空格键', value: 'Space' },
  { label: 'Fn', value: 'Fn' },
  { label: 'F2', value: 'F2' },
  { label: 'F8', value: 'F8' },
  { label: 'V 键', value: 'KeyV' },
  { label: 'Q 键', value: 'KeyQ' }
]
const chiefExpertOptions = computed(() => [
  { label: '自动选择', value: '__auto__' },
  ...chiefExperts.value.map((expert) => ({
    label: `${expert.name} · ${expert.role}${expert.enabled ? '' : '（已停用）'}`,
    value: expert.id,
    disabled: !expert.enabled
  }))
])
for (const domain of chiefDomains) {
  chiefSettings.domainExperts[domain.value] = '__auto__'
}

interface OperationLog {
  id: string
  time: string
  user: string
  action: string
  target: string
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

/** 统一校验 {code,message,data} 信封：非 200 时抛出带后端 message 的错误 */
async function request<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const response = await useApi<ApiEnvelope<T>>(path, body)
  if (response.code !== 200) throw new Error(response.message || '请求失败。')
  return response.data
}

// ---------------- 用户与角色 ----------------

const members = ref<Member[]>([])
const membersLoading = ref(false)
const membersError = ref('')
const pendingMemberIds = ref<string[]>([])

const memberKeyword = ref('')
const filteredMembers = computed(() => {
  const keyword = memberKeyword.value.trim().toLowerCase()
  if (!keyword) return members.value
  return members.value.filter(
    (member) =>
      member.name.toLowerCase().includes(keyword) || member.email.toLowerCase().includes(keyword)
  )
})

const memberColumns = [
  { accessorKey: 'name', header: '成员' },
  { accessorKey: 'email', header: '邮箱' },
  { accessorKey: 'role', header: '角色' },
  { accessorKey: 'enabled', header: '状态' },
  { accessorKey: 'lastActive', header: '最近活跃' },
  { id: 'actions', header: '操作' }
]

async function loadMembers() {
  membersLoading.value = true
  membersError.value = ''
  try {
    const data = await request<{ items: Member[] }>('/front/admin/members/list')
    members.value = data.items
  } catch (error) {
    membersError.value = normalizeApiError(error).message
  } finally {
    membersLoading.value = false
  }
}

function isMemberPending(id: string) {
  return pendingMemberIds.value.includes(id)
}

function setMemberPending(id: string, pending: boolean) {
  pendingMemberIds.value = pending
    ? [...pendingMemberIds.value, id]
    : pendingMemberIds.value.filter((item) => item !== id)
}

const inviteOpen = ref(false)
const inviteEmail = ref('')
const inviteRole = ref('成员')
const inviteLoading = ref(false)
const inviteError = ref('')
const inviteUrl = ref('')

function openInvite() {
  inviteError.value = ''
  inviteUrl.value = ''
  inviteOpen.value = true
}

async function sendInvite() {
  const email = inviteEmail.value.trim()
  if (!email || inviteLoading.value) return
  inviteLoading.value = true
  inviteError.value = ''
  try {
    const created = await request<{ id: string; inviteToken: string }>(
      '/front/admin/members/create',
      {
        email,
        role: inviteRole.value
      }
    )
    inviteUrl.value = `${window.location.origin}/accept-invite?token=${encodeURIComponent(created.inviteToken)}`
    inviteEmail.value = ''
    logsLoaded.value = false
    await loadMembers()
  } catch (error) {
    inviteError.value = normalizeApiError(error).message
  } finally {
    inviteLoading.value = false
  }
}

async function toggleMember(member: Member) {
  if (isMemberPending(member.id)) return
  setMemberPending(member.id, true)
  membersError.value = ''
  try {
    await request('/front/admin/members/update', { id: member.id, enabled: !member.enabled })
    logsLoaded.value = false
    await loadMembers()
  } catch (error) {
    membersError.value = normalizeApiError(error).message
  } finally {
    setMemberPending(member.id, false)
  }
}

async function removeMember(member: Member) {
  if (isMemberPending(member.id)) return
  if (!window.confirm(`确定移除成员「${member.name}」吗？`)) return
  setMemberPending(member.id, true)
  membersError.value = ''
  try {
    await request('/front/admin/members/delete', { id: member.id })
    logsLoaded.value = false
    await loadMembers()
  } catch (error) {
    membersError.value = normalizeApiError(error).message
  } finally {
    setMemberPending(member.id, false)
  }
}

async function resendInvite(member: Member) {
  if (isMemberPending(member.id)) return
  setMemberPending(member.id, true)
  membersError.value = ''
  try {
    const data = await request<{ inviteToken: string }>('/front/admin/members/resend-invite', {
      id: member.id
    })
    inviteUrl.value = `${window.location.origin}/accept-invite?token=${encodeURIComponent(data.inviteToken)}`
    inviteOpen.value = true
  } catch (error) {
    membersError.value = normalizeApiError(error).message
  } finally {
    setMemberPending(member.id, false)
  }
}

async function copyInviteUrl() {
  if (!inviteUrl.value) return
  await navigator.clipboard.writeText(inviteUrl.value)
}

async function changeRole(member: Member, role: string) {
  if (role === member.role || isMemberPending(member.id)) return
  const previous = member.role
  member.role = role
  setMemberPending(member.id, true)
  membersError.value = ''
  try {
    await request('/front/admin/members/update', { id: member.id, role })
    logsLoaded.value = false
  } catch (error) {
    member.role = previous
    membersError.value = normalizeApiError(error).message
  } finally {
    setMemberPending(member.id, false)
  }
}

// ---------------- 总管设置 ----------------

async function loadChiefSettings() {
  chiefSettingsLoading.value = true
  chiefSettingsError.value = ''
  try {
    const [settings, expertData] = await Promise.all([
      request<ChiefSettings>('/front/admin/chief/get-settings'),
      request<{ items: ExpertOption[] }>('/front/admin/experts/list')
    ])
    Object.assign(chiefSettings, settings)
    chiefSettings.domainExperts = Object.fromEntries(
      chiefDomains.map((domain) => [
        domain.value,
        settings.domainExperts?.[domain.value] || '__auto__'
      ])
    )
    chiefExperts.value = expertData.items
  } catch (error) {
    chiefSettingsError.value = normalizeApiError(error).message
  } finally {
    chiefSettingsLoading.value = false
  }
}

async function saveChiefSettings() {
  chiefSettingsLoading.value = true
  chiefSettingsError.value = ''
  chiefSettingsSaved.value = false
  try {
    if (chiefSettings.recursionK > chiefSettings.recursionMax) {
      chiefSettings.recursionK = chiefSettings.recursionMax
    }
    const data = await request<ChiefSettings>('/front/admin/chief/update-settings', {
      ...chiefSettings,
      domainExperts: Object.fromEntries(
        Object.entries(chiefSettings.domainExperts).map(([domain, expertId]) => [
          domain,
          expertId === '__auto__' ? '' : expertId
        ])
      )
    })
    Object.assign(chiefSettings, data)
    chiefSettings.domainExperts = Object.fromEntries(
      chiefDomains.map((domain) => [domain.value, data.domainExperts?.[domain.value] || '__auto__'])
    )
    chiefSettingsSaved.value = true
  } catch (error) {
    chiefSettingsError.value = normalizeApiError(error).message
  } finally {
    chiefSettingsLoading.value = false
  }
}

async function loadCallSettings() {
  callSettingsLoading.value = true
  callSettingsError.value = ''
  try {
    const data = await request<VoiceCallSettings>('/front/admin/call/get-settings')
    callStopSpeechKey.value = normalizeCallShortcutKey(data.pushToTalkKey)
    callAsrUrl.value = data.asrUrl
    callTtsUrl.value = data.ttsUrl
    callSettingsLoaded.value = true
  } catch (error) {
    callSettingsError.value = normalizeApiError(error).message
  } finally {
    callSettingsLoading.value = false
  }
}

async function saveCallSettings() {
  callSettingsLoading.value = true
  callSettingsError.value = ''
  callSettingsSaved.value = false
  try {
    const data = await request<VoiceCallSettings>('/front/admin/call/update-settings', {
      pushToTalkKey: normalizeCallShortcutKey(callStopSpeechKey.value),
      asrUrl: callAsrUrl.value.trim(),
      ttsUrl: callTtsUrl.value.trim()
    })
    callStopSpeechKey.value = normalizeCallShortcutKey(data.pushToTalkKey)
    callAsrUrl.value = data.asrUrl
    callTtsUrl.value = data.ttsUrl
    callSettingsSaved.value = true
  } catch (error) {
    callSettingsError.value = normalizeApiError(error).message
  } finally {
    callSettingsLoading.value = false
  }
}

function clearCallShortcutTestTimer() {
  if (!callShortcutTestTimer) return
  clearTimeout(callShortcutTestTimer)
  callShortcutTestTimer = null
}

function resetCallShortcutTest() {
  clearCallShortcutTestTimer()
  callShortcutTesting.value = false
  callShortcutTestState.value = 'idle'
  callShortcutTestMessage.value = '点击测试，然后按一下当前快捷键。'
}

function startCallShortcutTest() {
  clearCallShortcutTestTimer()
  callShortcutTesting.value = true
  callShortcutTestState.value = 'waiting'
  const label = callShortcutKeyLabel(callStopSpeechKey.value)
  callShortcutTestMessage.value = `请按一下 ${label}。`
  callShortcutTestTimer = setTimeout(() => {
    if (!callShortcutTesting.value) return
    callShortcutTesting.value = false
    callShortcutTestState.value = 'failed'
    callShortcutTestMessage.value =
      callStopSpeechKey.value === 'Fn'
        ? '未收到 Fn 键事件：当前浏览器或系统可能把 Fn 交给硬件处理，请改用 F2、F8 或空格。'
        : `未收到 ${label} 键事件，请确认窗口处于前台后重试。`
    callShortcutTestTimer = null
  }, 10_000)
}

function handleCallShortcutTestKeydown(event: KeyboardEvent) {
  if (
    !callShortcutTesting.value ||
    event.repeat ||
    !isCallShortcutKeyEvent(event, callStopSpeechKey.value)
  ) {
    return
  }
  event.preventDefault()
  clearCallShortcutTestTimer()
  callShortcutTesting.value = false
  callShortcutTestState.value = 'passed'
  callShortcutTestMessage.value = `测试通过：${callShortcutKeyLabel(
    callStopSpeechKey.value
  )} 可用于停止播报。`
}

// ---------------- 额度总览 ----------------

const quotaSummary = ref<QuotaSummaryItem[]>([])
const quotaByProject = ref<ProjectQuota[]>([])
const quotaByModel = ref<ModelQuota[]>([])
const alertThreshold = ref('80%')
const alertChannel = ref('站内 + 邮件')
const alertNotifyAdmin = ref(true)
const alertStopOnExceed = ref(false)
const newProjectName = ref('')
const newProjectLimit = ref(0)
const quotaSaved = ref('')
const quotaUsed = ref(0)
const quotaLimit = ref(0)
const quotaLoading = ref(false)
const quotaError = ref('')
const quotaLoaded = ref(false)

async function loadQuota() {
  quotaLoading.value = true
  quotaError.value = ''
  try {
    const [summary, projects, models, alerts] = await Promise.all([
      request<{ summary: QuotaSummaryItem[]; used: number; limit: number }>(
        '/front/admin/quota/get-summary'
      ),
      request<{ items: ProjectQuota[] }>('/front/admin/quota/get-project-quotas'),
      request<{ items: ModelQuota[] }>('/front/admin/quota/get-model-quotas'),
      request<AlertSettings>('/front/admin/quota/get-alert-settings')
    ])
    quotaSummary.value = summary.summary
    quotaUsed.value = summary.used
    quotaLimit.value = summary.limit
    quotaByProject.value = projects.items
    quotaByModel.value = models.items
    alertThreshold.value = alerts.threshold
    alertChannel.value = alerts.channel
    alertNotifyAdmin.value = alerts.notifyAdmin
    alertStopOnExceed.value = alerts.stopOnExceed
    quotaLoaded.value = true
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  } finally {
    quotaLoading.value = false
  }
}

async function saveProjectQuotas() {
  try {
    await request('/front/admin/quota/update-project-quotas', {
      items: quotaByProject.value.map((item) => ({ id: item.id, limit: Number(item.limit) }))
    })
    quotaSaved.value = '项目额度已保存'
    await loadQuota()
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  }
}

async function saveModelQuotas() {
  try {
    await request('/front/admin/quota/update-model-quotas', {
      items: quotaByModel.value.map((item) => ({ id: item.id, limit: Number(item.limit) }))
    })
    quotaSaved.value = '模型额度已保存'
    await loadQuota()
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  }
}

async function saveAlertSettings() {
  try {
    await request('/front/admin/quota/update-alert-settings', {
      threshold: alertThreshold.value,
      channel: alertChannel.value,
      notifyAdmin: alertNotifyAdmin.value,
      stopOnExceed: alertStopOnExceed.value
    })
    quotaSaved.value = '告警设置已保存'
    await loadQuota()
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  }
}

async function createProjectQuota() {
  if (!newProjectName.value.trim()) return
  try {
    await request('/front/admin/quota/create-project', {
      name: newProjectName.value.trim(),
      used: 0,
      limit: Number(newProjectLimit.value || 0)
    })
    newProjectName.value = ''
    newProjectLimit.value = 0
    quotaSaved.value = '项目额度已新增'
    await loadQuota()
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  }
}

async function deleteProjectQuota(project: ProjectQuota) {
  if (!window.confirm(`确定删除额度项目「${project.name}」吗？`)) return
  try {
    await request('/front/admin/quota/delete-project', { id: project.id })
    quotaSaved.value = '项目额度已删除'
    await loadQuota()
  } catch (error) {
    quotaError.value = normalizeApiError(error).message
  }
}

function formatMoney(value: number) {
  return `¥${value.toLocaleString('zh-CN')}`
}

function usagePercent(used: number, limit: number) {
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

// ---------------- 操作日志 ----------------

const logs = ref<OperationLog[]>([])
const logsLoading = ref(false)
const logsError = ref('')
const logsLoaded = ref(false)
const logsTotal = ref(0)
const logsPage = ref(1)
const logsPageSize = 20
const logsTotalPages = ref(1)
const logKeyword = ref('')
const logAction = ref('')
const logStartTime = ref('')
const logEndTime = ref('')

async function loadLogs() {
  logsLoading.value = true
  logsError.value = ''
  try {
    const data = await request<{
      items: OperationLog[]
      total: number
      page: number
      total_pages: number
    }>('/front/admin/logs/list', {
      page: logsPage.value,
      page_size: logsPageSize,
      keyword: logKeyword.value.trim(),
      action: logAction.value.trim(),
      start_time: logStartTime.value || null,
      end_time: logEndTime.value || null
    })
    logs.value = data.items
    logsTotal.value = data.total
    logsTotalPages.value = data.total_pages
    logsLoaded.value = true
  } catch (error) {
    logsError.value = normalizeApiError(error).message
  } finally {
    logsLoading.value = false
  }
}

async function applyLogFilters() {
  logsPage.value = 1
  await loadLogs()
}

function previousLogsPage() {
  if (logsPage.value <= 1) return
  logsPage.value -= 1
  void loadLogs()
}

function nextLogsPage() {
  if (logsPage.value >= logsTotalPages.value) return
  logsPage.value += 1
  void loadLogs()
}

async function exportLogs() {
  const allItems: OperationLog[] = []
  let page = 1
  let totalPages = 1
  do {
    const data = await request<{
      items: OperationLog[]
      total_pages: number
    }>('/front/admin/logs/list', {
      page,
      page_size: 200,
      keyword: logKeyword.value.trim(),
      action: logAction.value.trim(),
      start_time: logStartTime.value || null,
      end_time: logEndTime.value || null
    })
    allItems.push(...data.items)
    totalPages = data.total_pages
    page += 1
  } while (page <= totalPages)
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`
  const csv = [
    ['时间', '操作人', '操作', '对象'].map(escape).join(','),
    ...allItems.map((item) =>
      [item.time, item.user, item.action, item.target].map(escape).join(',')
    )
  ].join('\n')
  const url = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `operation-logs-${new Date().toISOString().slice(0, 10)}.csv`
  link.click()
  URL.revokeObjectURL(url)
}

const logColumns = [
  { accessorKey: 'time', header: '时间' },
  { accessorKey: 'user', header: '操作人' },
  { accessorKey: 'action', header: '操作' },
  { accessorKey: 'target', header: '对象' }
]

// ---------------- 分区懒加载 ----------------

onMounted(() => {
  void Promise.allSettled([loadMembers(), loadChiefSettings()])
  window.addEventListener('keydown', handleCallShortcutTestKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleCallShortcutTestKeydown)
  clearCallShortcutTestTimer()
})
watch(section, (value) => {
  if (value === 'quota' && !quotaLoaded.value) loadQuota()
  if (value === 'logs' && !logsLoaded.value) loadLogs()
  if (value === 'chief' && !chiefExperts.value.length) loadChiefSettings()
  if (value === 'call' && !callSettingsLoaded.value) loadCallSettings()
  if (value !== 'call') resetCallShortcutTest()
})
watch(callStopSpeechKey, () => resetCallShortcutTest())
</script>

<template>
  <div
    class="mx-auto flex max-w-6xl items-start gap-6 max-[767px]:flex-col max-[767px]:items-stretch"
  >
    <nav class="flex w-44 flex-none flex-col gap-1 max-[767px]:w-full" aria-label="管理后台模块">
      <UButton
        v-for="item in sections"
        :key="item.value"
        color="neutral"
        :variant="section === item.value ? 'soft' : 'ghost'"
        block
        class="justify-start"
        :aria-current="section === item.value ? 'page' : undefined"
        @click="section = item.value"
      >
        {{ item.label }}
      </UButton>
    </nav>

    <div class="flex min-w-0 flex-1 flex-col gap-6">
      <template v-if="section === 'users'">
        <div v-if="membersError" class="flex items-center gap-3">
          <UAlert
            color="error"
            variant="subtle"
            title="加载失败"
            :description="membersError"
            class="flex-1"
          />
          <UButton color="neutral" variant="outline" :loading="membersLoading" @click="loadMembers">
            重试
          </UButton>
        </div>

        <UCard>
          <template #header>
            <div class="flex flex-wrap items-center gap-3">
              <h2 class="text-sm font-semibold text-highlighted">用户与角色</h2>
              <UBadge color="neutral" variant="subtle" size="sm">{{ members.length }}</UBadge>
              <UInput
                v-model="memberKeyword"
                placeholder="搜索姓名或邮箱"
                class="ms-auto w-56"
                aria-label="搜索用户或邮箱"
              />
              <UButton @click="openInvite">邀请成员</UButton>
            </div>
          </template>

          <UTable :data="filteredMembers" :columns="memberColumns" :loading="membersLoading">
            <template #name-cell="{ row }">
              <div class="flex items-center gap-2.5">
                <UAvatar :text="row.original.name.slice(0, 1)" size="sm" />
                <span class="text-sm text-highlighted">{{ row.original.name }}</span>
              </div>
            </template>

            <template #role-cell="{ row }">
              <USelect
                :model-value="row.original.role"
                :items="roles"
                class="w-28"
                :disabled="row.original.role === '拥有者' || isMemberPending(row.original.id)"
                :aria-label="`${row.original.name} 的角色`"
                @update:model-value="(value) => changeRole(row.original, String(value))"
              />
            </template>

            <template #enabled-cell="{ row }">
              <UBadge
                :color="row.original.enabled ? 'success' : 'neutral'"
                variant="subtle"
                size="sm"
              >
                {{ row.original.enabled ? '启用' : '停用' }}
              </UBadge>
              <p class="mt-1 text-[11px] text-dimmed">
                {{
                  row.original.accountStatus === 'active'
                    ? '已激活'
                    : row.original.accountStatus === 'invited'
                      ? '待接受邀请'
                      : '需改密码'
                }}
              </p>
            </template>

            <template #actions-cell="{ row }">
              <div class="flex items-center gap-1">
                <UButton
                  color="neutral"
                  variant="ghost"
                  :disabled="row.original.role === '拥有者' || isMemberPending(row.original.id)"
                  @click="toggleMember(row.original)"
                >
                  {{ row.original.enabled ? '停用' : '启用' }}
                </UButton>
                <UButton
                  color="error"
                  variant="ghost"
                  :disabled="row.original.role === '拥有者' || isMemberPending(row.original.id)"
                  @click="removeMember(row.original)"
                >
                  移除
                </UButton>
                <UButton
                  v-if="row.original.accountStatus === 'invited'"
                  color="neutral"
                  variant="ghost"
                  :disabled="isMemberPending(row.original.id)"
                  @click="resendInvite(row.original)"
                >
                  重发邀请
                </UButton>
              </div>
            </template>
          </UTable>
        </UCard>
      </template>

      <template v-else-if="section === 'chief'">
        <UAlert
          v-if="chiefSettingsError"
          color="error"
          variant="subtle"
          title="总管设置加载或保存失败"
          :description="chiefSettingsError"
        />
        <UAlert
          v-if="chiefSettingsSaved"
          color="success"
          variant="subtle"
          title="总管设置已保存"
          description="后续总管任务将使用最新配置。"
        />
        <UProgress v-if="chiefSettingsLoading" :model-value="null" />

        <UCard>
          <template #header>
            <div class="flex items-center gap-3">
              <div>
                <h2 class="text-sm font-semibold text-highlighted">总管设置</h2>
                <p class="mt-1 text-xs text-muted">控制 Harness 递归、历史回归和自动采纳策略。</p>
              </div>
              <USwitch v-model="chiefSettings.enabled" class="ms-auto" label="启用总管" />
            </div>
          </template>

          <div class="flex flex-col gap-6">
            <div class="grid gap-5 md:grid-cols-2">
              <UFormField label="默认递归模式">
                <USelect
                  v-model="chiefSettings.recursionMode"
                  :items="[
                    { label: '顺序递归', value: 'sequential' },
                    { label: '并行递归', value: 'parallel' }
                  ]"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="最大递归预算">
                <UInput
                  v-model.number="chiefSettings.recursionMax"
                  type="number"
                  min="1"
                  max="4"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="默认 K 值">
                <UInput
                  v-model.number="chiefSettings.recursionK"
                  type="number"
                  min="1"
                  :max="chiefSettings.recursionMax"
                  class="w-full"
                />
              </UFormField>
              <div />
              <UFormField label="自动采纳最低得分">
                <UInput
                  v-model.number="chiefSettings.autoAdoptMinScore"
                  type="number"
                  min="0"
                  max="100"
                  class="w-full"
                />
              </UFormField>
              <UFormField label="相对历史均值最低提升（%）">
                <UInput
                  v-model.number="chiefSettings.autoAdoptMinGain"
                  type="number"
                  min="0"
                  max="100"
                  class="w-full"
                />
              </UFormField>
            </div>

            <USeparator />

            <div class="grid gap-5 md:grid-cols-2">
              <div class="flex items-center justify-between gap-4 rounded-md bg-elevated/40 p-4">
                <div>
                  <p class="text-sm text-highlighted">历史回归门禁</p>
                  <p class="text-xs text-muted">采纳前重跑同领域历史案例</p>
                </div>
                <USwitch v-model="chiefSettings.regressionEnabled" />
              </div>
              <UFormField label="回归案例数量">
                <UInput
                  v-model.number="chiefSettings.regressionCases"
                  type="number"
                  min="0"
                  max="10"
                  class="w-full"
                />
              </UFormField>
            </div>

            <USeparator />

            <div class="flex flex-col gap-3">
              <div>
                <h3 class="text-sm font-semibold text-highlighted">业务域专家映射</h3>
                <p class="mt-1 text-xs text-muted">
                  选项来自后台“专家管理”，留空时由总管根据语义自动选择专家。
                </p>
              </div>
              <div class="grid gap-4 md:grid-cols-2">
                <UFormField
                  v-for="domain in chiefDomains"
                  :key="domain.value"
                  :label="domain.label"
                >
                  <USelect
                    v-model="chiefSettings.domainExperts[domain.value]"
                    :items="chiefExpertOptions"
                    class="w-full"
                  />
                </UFormField>
              </div>
            </div>
          </div>

          <template #footer>
            <div class="flex justify-end">
              <UButton :loading="chiefSettingsLoading" @click="saveChiefSettings">
                保存总管设置
              </UButton>
            </div>
          </template>
        </UCard>
      </template>

      <template v-else-if="section === 'call'">
        <UAlert
          v-if="callSettingsError"
          color="error"
          variant="subtle"
          title="通话设置加载或保存失败"
          :description="callSettingsError"
        />
        <UAlert
          v-if="callSettingsSaved"
          color="success"
          variant="subtle"
          title="通话设置已保存"
          description="新的快捷键和语音接口地址会在后续通话中使用。"
        />
        <UProgress v-if="callSettingsLoading" :model-value="null" />

        <UCard>
          <template #header>
            <div>
              <h2 class="text-sm font-semibold text-highlighted">通话设置</h2>
              <p class="mt-1 text-xs text-muted">
                配置通话中的停止播音快捷键，以及 ASR 和 TTS 服务地址。
              </p>
            </div>
          </template>

          <div class="grid gap-5 md:grid-cols-2">
            <UFormField label="停止播音快捷键">
              <USelect v-model="callStopSpeechKey" :items="callShortcutOptions" />
              <p class="mt-1 text-xs text-muted">
                通话中按一下此键立即停止 AI 播报，之后仍可继续聆听和识别语音。 Esc 是推荐键位；部分
                macOS 浏览器会由硬件直接处理 Fn，如无法触发请改用 F2、F8 或空格。
              </p>
            </UFormField>
            <UFormField label="测试当前快捷键">
              <div class="flex flex-col gap-2">
                <UButton
                  color="neutral"
                  variant="outline"
                  :loading="callShortcutTesting"
                  @click="startCallShortcutTest"
                >
                  {{ callShortcutTesting ? '等待按键…' : '测试快捷键' }}
                </UButton>
                <p class="text-xs" :class="callShortcutTestToneClass" aria-live="polite">
                  {{ callShortcutTestMessage }}
                </p>
              </div>
            </UFormField>
            <UFormField label="ASR 语音识别地址">
              <UInput
                v-model="callAsrUrl"
                placeholder="https://api.deepseek.com/v1/tools/asr"
                class="w-full"
              />
            </UFormField>
            <UFormField label="TTS 语音合成地址">
              <UInput
                v-model="callTtsUrl"
                placeholder="https://api.deepseek.com/v1/tools/tts"
                class="w-full"
              />
            </UFormField>
          </div>
          <p class="mt-4 text-xs text-muted">
            接口需兼容 DeepSeek ASR multipart 上传与 TTS 流式 WAV 返回协议。
          </p>

          <template #footer>
            <div class="flex justify-end">
              <UButton :loading="callSettingsLoading" @click="saveCallSettings">
                保存通话设置
              </UButton>
            </div>
          </template>
        </UCard>
      </template>

      <template v-else-if="section === 'quota'">
        <div v-if="quotaError" class="flex items-center gap-3">
          <UAlert
            color="error"
            variant="subtle"
            title="加载失败"
            :description="quotaError"
            class="flex-1"
          />
          <UButton color="neutral" variant="outline" :loading="quotaLoading" @click="loadQuota">
            重试
          </UButton>
        </div>

        <UProgress v-if="quotaLoading" :model-value="null" />

        <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <UCard v-for="item in quotaSummary" :key="item.label">
            <div class="flex flex-col gap-1">
              <span class="text-xs text-muted">{{ item.label }}</span>
              <span class="text-2xl font-semibold text-highlighted">{{ item.value }}</span>
              <span class="text-xs text-dimmed">{{ item.note }}</span>
            </div>
          </UCard>
        </div>

        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-semibold text-highlighted">本月用量</h2>
              <span class="text-xs text-muted">
                {{ formatMoney(quotaUsed) }} / {{ formatMoney(quotaLimit) }}
              </span>
            </div>
          </template>

          <UProgress :model-value="quotaUsed" :max="quotaLimit || 1" />
        </UCard>

        <UCard>
          <template #header>
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-semibold text-highlighted">按项目分配</h2>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :loading="quotaLoading"
                @click="loadQuota"
              >
                刷新
              </UButton>
            </div>
          </template>

          <ul class="flex flex-col gap-4">
            <li v-for="item in quotaByProject" :key="item.id" class="flex flex-col gap-2">
              <div class="grid items-center gap-3 text-sm sm:grid-cols-[1fr_140px_88px]">
                <span class="text-highlighted">{{ item.name }}</span>
                <UInput
                  v-model.number="item.limit"
                  type="number"
                  min="0"
                  :aria-label="`${item.name} 额度上限`"
                />
                <UButton color="error" variant="ghost" @click="deleteProjectQuota(item)"
                  >删除</UButton
                >
              </div>
              <span class="text-xs text-muted">
                已用 {{ formatMoney(item.used) }} / {{ formatMoney(item.limit) }}
              </span>
              <UProgress
                :model-value="usagePercent(item.used, item.limit)"
                :max="100"
                :color="usagePercent(item.used, item.limit) >= 90 ? 'error' : 'primary'"
              />
            </li>
          </ul>
          <div class="mt-4 grid gap-3 border-t border-default pt-4 sm:grid-cols-[1fr_150px_auto]">
            <UInput v-model="newProjectName" placeholder="新项目名称" />
            <UInput v-model.number="newProjectLimit" type="number" min="0" placeholder="额度上限" />
            <UButton color="neutral" variant="outline" @click="createProjectQuota"
              >新增项目</UButton
            >
          </div>
          <div class="mt-4 flex justify-end">
            <UButton @click="saveProjectQuotas">保存项目额度</UButton>
          </div>
        </UCard>

        <UCard>
          <template #header>
            <h2 class="text-sm font-semibold text-highlighted">按模型额度</h2>
          </template>
          <div class="flex flex-col gap-3">
            <div
              v-for="item in quotaByModel"
              :key="item.id"
              class="grid items-center gap-3 rounded-md bg-elevated/50 p-3 sm:grid-cols-[1fr_120px_140px]"
            >
              <div>
                <p class="text-sm text-highlighted">{{ item.model }}</p>
                <p class="text-xs text-muted">
                  {{ item.price }} · 已用 {{ formatMoney(item.used) }}
                </p>
              </div>
              <UProgress
                :model-value="usagePercent(item.used, item.limit)"
                :max="100"
                :color="usagePercent(item.used, item.limit) >= 90 ? 'error' : 'primary'"
              />
              <UInput v-model.number="item.limit" type="number" min="0" />
            </div>
            <div class="flex justify-end">
              <UButton @click="saveModelQuotas">保存模型额度</UButton>
            </div>
          </div>
        </UCard>

        <UCard>
          <template #header>
            <h2 class="text-sm font-semibold text-highlighted">额度告警</h2>
          </template>
          <div class="flex flex-col gap-4">
            <div class="grid gap-4 sm:grid-cols-2">
              <UFormField label="预警阈值">
                <USelect v-model="alertThreshold" :items="['70%', '80%', '90%']" class="w-full" />
              </UFormField>
              <UFormField label="通知方式">
                <USelect
                  v-model="alertChannel"
                  :items="['站内通知', '邮件', '站内 + 邮件']"
                  class="w-full"
                />
              </UFormField>
            </div>
            <USwitch v-model="alertNotifyAdmin" label="达到阈值时通知管理员" />
            <USwitch v-model="alertStopOnExceed" label="额度用尽后停止模型调用" />
            <div class="flex justify-end">
              <UButton @click="saveAlertSettings">保存告警设置</UButton>
            </div>
          </div>
        </UCard>
        <UAlert v-if="quotaSaved" color="success" variant="subtle" :title="quotaSaved" />
      </template>

      <UCard v-else-if="section === 'logs'">
        <template #header>
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-sm font-semibold text-highlighted">操作日志</h2>
            <div class="flex items-center gap-2">
              <span class="text-xs text-muted">共 {{ logsTotal }} 条</span>
              <UButton color="neutral" variant="outline" size="sm" @click="exportLogs">
                导出 CSV
              </UButton>
              <UButton
                color="neutral"
                variant="ghost"
                size="sm"
                :loading="logsLoading"
                @click="loadLogs"
              >
                刷新
              </UButton>
            </div>
          </div>
        </template>

        <div v-if="logsError" class="mb-3 flex items-center gap-3">
          <UAlert
            color="error"
            variant="subtle"
            title="加载失败"
            :description="logsError"
            class="flex-1"
          />
          <UButton color="neutral" variant="outline" :loading="logsLoading" @click="loadLogs">
            重试
          </UButton>
        </div>

        <UTable :data="logs" :columns="logColumns" :loading="logsLoading" />

        <div class="mt-4 flex flex-wrap items-center gap-2">
          <UInput
            v-model="logKeyword"
            placeholder="搜索操作人或对象"
            class="w-52"
            @keyup.enter="applyLogFilters"
          />
          <UInput
            v-model="logAction"
            placeholder="操作类型，如 修改成员"
            class="w-48"
            @keyup.enter="applyLogFilters"
          />
          <UInput v-model="logStartTime" type="datetime-local" aria-label="日志开始时间" />
          <UInput v-model="logEndTime" type="datetime-local" aria-label="日志结束时间" />
          <UButton color="neutral" variant="outline" @click="applyLogFilters">筛选</UButton>
          <span class="ms-auto text-xs text-muted"
            >第 {{ logsPage }} / {{ logsTotalPages }} 页</span
          >
          <UButton
            color="neutral"
            variant="outline"
            :disabled="logsPage <= 1"
            @click="previousLogsPage"
          >
            上一页
          </UButton>
          <UButton
            color="neutral"
            variant="outline"
            :disabled="logsPage >= logsTotalPages"
            @click="nextLogsPage"
          >
            下一页
          </UButton>
        </div>
      </UCard>

      <ExpertManager v-else :kind="registryTab" @manage="section = $event" />

      <UModal v-model:open="inviteOpen" title="邀请成员">
        <template #body>
          <div class="flex flex-col gap-4">
            <UAlert
              v-if="inviteError"
              color="error"
              variant="subtle"
              title="邀请失败"
              :description="inviteError"
            />
            <UFormField label="邮箱" name="invite-email">
              <UInput
                v-model="inviteEmail"
                type="email"
                placeholder="name@example.com"
                class="w-full"
              />
            </UFormField>
            <UFormField label="角色" name="invite-role">
              <USelect v-model="inviteRole" :items="roles" class="w-full" />
            </UFormField>
            <UAlert
              v-if="inviteUrl"
              color="success"
              variant="subtle"
              title="邀请已创建"
              :description="inviteUrl"
            >
              <template #actions>
                <UButton color="neutral" variant="ghost" @click="copyInviteUrl">复制链接</UButton>
              </template>
            </UAlert>
          </div>
        </template>

        <template #footer>
          <div class="flex w-full justify-end gap-2">
            <UButton color="neutral" variant="ghost" @click="inviteOpen = false">取消</UButton>
            <UButton
              :disabled="!inviteEmail.trim() || inviteLoading"
              :loading="inviteLoading"
              @click="sendInvite"
            >
              发送邀请
            </UButton>
          </div>
        </template>
      </UModal>
    </div>
  </div>
</template>
