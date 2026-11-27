<script setup lang="ts">
/** 个人设置 · 账号安全 */
import { clearAdminSession, getAdminToken } from '~/composables/useAdminSession'

definePageMeta({ layout: 'console', title: '个人设置' })

const state = useSettingsState()
const message = ref('')
const failed = ref(false)

async function updatePassword() {
  if (!state.value.password.current || !state.value.password.next) {
    failed.value = true
    message.value = '请填写当前密码与新密码'
    return
  }
  if (state.value.password.next.length < 8) {
    failed.value = true
    message.value = '新密码至少 8 位'
    return
  }
  if (state.value.password.next !== state.value.password.confirm) {
    failed.value = true
    message.value = '两次输入的新密码不一致'
    return
  }
  try {
    const config = useRuntimeConfig()
    const response = await $fetch<{ code: number; message: string }>(
      '/front/admin/auth/change-password',
      {
        baseURL: config.public.apiBase as string,
        method: 'POST',
        headers: { Authorization: `Bearer ${getAdminToken()}` },
        body: {
          current_password: state.value.password.current,
          new_password: state.value.password.next
        }
      }
    )
    if (response.code !== 200) throw new Error(response.message)
    failed.value = false
    message.value = '密码已更新，请重新登录'
    state.value.password.current = ''
    state.value.password.next = ''
    state.value.password.confirm = ''
    clearAdminSession()
    await navigateTo('/login')
  } catch (error) {
    failed.value = true
    message.value = normalizeApiError(error).message
  }
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
          <h2 class="text-sm font-semibold text-highlighted">修改密码</h2>
        </template>

        <div class="flex flex-col gap-5">
          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="当前密码" name="current-password">
              <UInput v-model="state.password.current" type="password" class="w-full" />
            </UFormField>
            <div class="hidden sm:block" />
            <UFormField label="新密码" name="new-password">
              <UInput v-model="state.password.next" type="password" class="w-full" />
            </UFormField>
            <UFormField label="确认新密码" name="confirm-password">
              <UInput v-model="state.password.confirm" type="password" class="w-full" />
            </UFormField>
          </div>

          <UAlert
            v-if="message"
            :color="failed ? 'error' : 'success'"
            variant="subtle"
            :title="message"
          >
            <template #actions>
              <UButton color="neutral" variant="ghost" @click="message = ''">关闭</UButton>
            </template>
          </UAlert>

          <div class="flex justify-end">
            <UButton @click="updatePassword">更新密码</UButton>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
