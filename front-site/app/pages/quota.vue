<script setup lang="ts">
/** 额度管理：团队总额度、模型单价与额度上限、告警设置 */
definePageMeta({ layout: 'console', title: '额度管理', middleware: 'admin-auth' })

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface SummaryItem {
  label: string
  value: string
  note: string
}

interface SummaryPayload {
  summary: SummaryItem[]
  used: number
  limit: number
}

interface QuotaRow {
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

const loading = ref(true)
const error = ref('')

const summary = ref<SummaryItem[]>([])
const totalUsed = ref(0)
const totalLimit = ref(0)

const quotas = ref<QuotaRow[]>([])

const quotaColumns = [
  { accessorKey: 'model', header: '模型' },
  { accessorKey: 'price', header: '单价' },
  { accessorKey: 'used', header: '本月用量' },
  { accessorKey: 'limit', header: '额度上限' },
  { id: 'usage', header: '使用率' }
]

function usagePercent(used: number, limit: number) {
  if (limit <= 0) return 100
  return Math.min(100, Math.round((used / limit) * 100))
}

function usageColor(used: number, limit: number) {
  const percent = usagePercent(used, limit)
  if (percent >= 100) return 'error'
  if (percent >= 80) return 'warning'
  return 'primary'
}

function formatMoney(value: number) {
  return `¥${Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`
}

const alerts = reactive<AlertSettings>({
  threshold: '80%',
  channel: '站内 + 邮件',
  notifyAdmin: true,
  stopOnExceed: false
})

const saved = ref(false)
const savingQuotas = ref(false)
const quotaError = ref('')

const sections = [
  { value: 'usage', label: '额度概览' },
  { value: 'alerts', label: '告警设置' }
] as const
const section = ref<(typeof sections)[number]['value']>('usage')

const savedAlerts = ref(false)
const savingAlerts = ref(false)
const alertError = ref('')

async function loadSummary() {
  const response = await useApi<ApiResponse<SummaryPayload>>('/front/admin/quota/get-summary')
  if (response.code !== 200) throw new Error(response.message || '请求失败')
  summary.value = response.data.summary
  totalUsed.value = response.data.used
  totalLimit.value = response.data.limit
}

async function loadQuotas() {
  const response = await useApi<ApiResponse<{ items: QuotaRow[] }>>(
    '/front/admin/quota/get-model-quotas'
  )
  if (response.code !== 200) throw new Error(response.message || '请求失败')
  quotas.value = response.data.items
}

async function loadAlerts() {
  const response = await useApi<ApiResponse<AlertSettings>>('/front/admin/quota/get-alert-settings')
  if (response.code !== 200) throw new Error(response.message || '请求失败')
  alerts.threshold = response.data.threshold
  alerts.channel = response.data.channel
  alerts.notifyAdmin = response.data.notifyAdmin
  alerts.stopOnExceed = response.data.stopOnExceed
}

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    await Promise.all([loadSummary(), loadQuotas(), loadAlerts()])
  } catch (err) {
    error.value = normalizeApiError(err).message
  } finally {
    loading.value = false
  }
}

async function saveQuotas() {
  savingQuotas.value = true
  quotaError.value = ''
  saved.value = false
  try {
    const response = await useApi<ApiResponse<null>>('/front/admin/quota/update-model-quotas', {
      items: quotas.value.map((row) => ({ id: row.id, limit: Number(row.limit) }))
    })
    if (response.code !== 200) throw new Error(response.message || '请求失败')
    await loadQuotas()
    saved.value = true
  } catch (err) {
    quotaError.value = normalizeApiError(err).message
  } finally {
    savingQuotas.value = false
  }
}

async function saveAlerts() {
  savingAlerts.value = true
  alertError.value = ''
  savedAlerts.value = false
  try {
    const response = await useApi<ApiResponse<null>>('/front/admin/quota/update-alert-settings', {
      threshold: alerts.threshold,
      channel: alerts.channel,
      notifyAdmin: alerts.notifyAdmin,
      stopOnExceed: alerts.stopOnExceed
    })
    if (response.code !== 200) throw new Error(response.message || '请求失败')
    await loadAlerts()
    savedAlerts.value = true
  } catch (err) {
    alertError.value = normalizeApiError(err).message
  } finally {
    savingAlerts.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div
    class="mx-auto flex max-w-6xl items-start gap-6 max-[767px]:flex-col max-[767px]:items-stretch"
  >
    <nav class="flex w-44 flex-none flex-col gap-1 max-[767px]:w-full" aria-label="额度管理分区">
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
      <UAlert
        v-if="error && !loading"
        color="error"
        variant="subtle"
        title="加载失败"
        :description="error"
      >
        <template #actions>
          <UButton color="neutral" variant="ghost" @click="loadAll">重试</UButton>
        </template>
      </UAlert>

      <UAlert
        v-if="loading"
        color="neutral"
        variant="subtle"
        title="加载中"
        description="正在获取额度数据，请稍候。"
      />

      <template v-if="!loading && !error">
        <template v-if="section === 'usage'">
          <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <UCard v-for="item in summary" :key="item.label">
              <div class="flex flex-col gap-1">
                <span class="text-xs text-muted">{{ item.label }}</span>
                <span class="text-2xl font-semibold text-highlighted">{{ item.value }}</span>
                <span class="text-xs text-dimmed">{{ item.note }}</span>
              </div>
            </UCard>
          </div>

          <UCard>
            <template #header>
              <h2 class="text-sm font-semibold text-highlighted">本月额度使用</h2>
            </template>

            <div class="flex flex-col gap-2">
              <div class="flex items-center justify-between text-sm">
                <span class="text-highlighted">
                  {{ formatMoney(totalUsed) }} / {{ formatMoney(totalLimit) }}
                </span>
                <span class="text-muted">{{ usagePercent(totalUsed, totalLimit) }}%</span>
              </div>
              <UProgress
                :model-value="usagePercent(totalUsed, totalLimit)"
                :max="100"
                :color="usageColor(totalUsed, totalLimit)"
              />
            </div>
          </UCard>

          <UCard>
            <template #header>
              <div class="flex flex-wrap items-center gap-3">
                <h2 class="text-sm font-semibold text-highlighted">按模型额度</h2>
                <span class="text-xs text-muted">调整上限后点击保存</span>
              </div>
            </template>

            <div class="flex flex-col gap-4">
              <UTable :data="quotas" :columns="quotaColumns">
                <template #model-cell="{ row }">
                  <span class="text-sm text-highlighted">{{ row.original.model }}</span>
                </template>

                <template #used-cell="{ row }">
                  <span class="text-sm text-default">¥{{ row.original.used }}</span>
                </template>

                <template #limit-cell="{ row }">
                  <UInput
                    v-model.number="row.original.limit"
                    type="number"
                    min="0"
                    class="w-28"
                    :aria-label="`${row.original.model} 额度上限`"
                  />
                </template>

                <template #usage-cell="{ row }">
                  <div class="flex items-center gap-3">
                    <UProgress
                      :model-value="usagePercent(row.original.used, row.original.limit)"
                      :max="100"
                      :color="usageColor(row.original.used, row.original.limit)"
                      class="w-28"
                    />
                    <span class="text-xs text-muted">
                      {{ usagePercent(row.original.used, row.original.limit) }}%
                    </span>
                  </div>
                </template>
              </UTable>

              <UAlert
                v-if="quotaError"
                color="error"
                variant="subtle"
                title="保存失败"
                :description="quotaError"
              />

              <UAlert
                v-if="saved"
                color="success"
                variant="subtle"
                title="额度设置已保存"
                description="模型额度上限已更新为最新值。"
              >
                <template #actions>
                  <UButton color="neutral" variant="ghost" @click="saved = false">关闭</UButton>
                </template>
              </UAlert>

              <div class="flex justify-end">
                <UButton :loading="savingQuotas" @click="saveQuotas">保存修改</UButton>
              </div>
            </div>
          </UCard>
        </template>

        <UCard v-else>
          <template #header>
            <h2 class="text-sm font-semibold text-highlighted">告警设置</h2>
          </template>

          <div class="flex flex-col gap-5">
            <div class="grid gap-4 sm:grid-cols-2">
              <UFormField label="预警阈值" name="threshold">
                <USelect v-model="alerts.threshold" :items="['70%', '80%', '90%']" class="w-full" />
              </UFormField>
              <UFormField label="通知方式" name="channel">
                <USelect
                  v-model="alerts.channel"
                  :items="['站内通知', '邮件', '站内 + 邮件']"
                  class="w-full"
                />
              </UFormField>
            </div>

            <USeparator />

            <div class="flex items-center justify-between gap-4">
              <div class="flex flex-col gap-0.5">
                <span class="text-sm text-highlighted">通知管理员</span>
                <span class="text-xs text-muted">达到阈值时提醒拥有者与管理员</span>
              </div>
              <USwitch v-model="alerts.notifyAdmin" />
            </div>

            <div class="flex items-center justify-between gap-4">
              <div class="flex flex-col gap-0.5">
                <span class="text-sm text-highlighted">超额停用</span>
                <span class="text-xs text-muted">额度用尽后暂停该模型的调用</span>
              </div>
              <USwitch v-model="alerts.stopOnExceed" />
            </div>

            <UAlert
              v-if="alertError"
              color="error"
              variant="subtle"
              title="保存失败"
              :description="alertError"
            />

            <UAlert
              v-if="savedAlerts"
              color="success"
              variant="subtle"
              title="告警设置已保存"
              description="预警阈值与通知方式已更新为最新值。"
            >
              <template #actions>
                <UButton color="neutral" variant="ghost" @click="savedAlerts = false">关闭</UButton>
              </template>
            </UAlert>

            <div class="flex justify-end">
              <UButton :loading="savingAlerts" @click="saveAlerts">保存修改</UButton>
            </div>
          </div>
        </UCard>
      </template>
    </div>
  </div>
</template>
