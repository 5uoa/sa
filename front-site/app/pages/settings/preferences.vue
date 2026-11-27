<script setup lang="ts">
/** 个人设置 · 偏好设置 */
definePageMeta({ layout: 'console', title: '个人设置' })

const state = useSettingsState()
const saved = ref(false)

function savePreferences() {
  saved.value = true
}
</script>

<template>
  <div
    class="mx-auto flex max-w-6xl items-start gap-6 max-[767px]:flex-col max-[767px]:items-stretch"
  >
    <SettingsNav class="w-44 flex-none max-[767px]:w-full" />

    <div class="flex min-w-0 flex-1 flex-col gap-6">
      <UCard>
        <template #header>
          <h2 class="text-sm font-semibold text-highlighted">偏好设置</h2>
        </template>

        <div class="flex flex-col gap-5">
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="界面语言" name="language">
              <USelect
                v-model="state.prefs.language"
                :items="['简体中文', 'English']"
                class="w-full"
              />
            </UFormField>
            <UFormField label="时区" name="timezone">
              <USelect
                v-model="state.prefs.timezone"
                :items="['(GMT+08:00) 北京', '(GMT+09:00) 东京', '(GMT+00:00) 伦敦']"
                class="w-full"
              />
            </UFormField>
          </div>

          <USeparator />

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-0.5">
              <span class="text-sm text-highlighted">邮件通知</span>
              <span class="text-xs text-muted">任务验收、会话提及等关键事件发送邮件</span>
            </div>
            <USwitch v-model="state.prefs.emailNotify" />
          </div>

          <USeparator />

          <div class="flex items-center justify-between gap-4">
            <div class="flex flex-col gap-0.5">
              <span class="text-sm text-highlighted">每周摘要</span>
              <span class="text-xs text-muted">每周一汇总项目进度与额度消耗</span>
            </div>
            <USwitch v-model="state.prefs.weeklyDigest" />
          </div>

          <UAlert
            v-if="saved"
            color="success"
            variant="subtle"
            title="偏好设置已保存"
            description="演示环境仅保存在当前会话状态，刷新后会恢复默认值。"
          >
            <template #actions>
              <UButton color="neutral" variant="ghost" @click="saved = false">关闭</UButton>
            </template>
          </UAlert>

          <div class="flex justify-end">
            <UButton @click="savePreferences">保存修改</UButton>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
