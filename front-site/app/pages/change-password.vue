<script setup lang="ts">
import { clearAdminSession, getAdminToken } from '~/composables/useAdminSession'

definePageMeta({ layout: false, middleware: 'admin-auth' })

const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const error = ref('')
const saving = ref(false)

async function submit() {
  error.value = ''
  if (newPassword.value.length < 8) {
    error.value = '新密码至少 8 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    error.value = '两次输入的新密码不一致'
    return
  }
  saving.value = true
  try {
    const config = useRuntimeConfig()
    const response = await $fetch<{ code: number; message: string }>(
      '/front/admin/auth/change-password',
      {
        baseURL: config.public.apiBase as string,
        method: 'POST',
        headers: { Authorization: `Bearer ${getAdminToken()}` },
        body: {
          current_password: currentPassword.value,
          new_password: newPassword.value
        }
      }
    )
    if (response.code !== 200) throw new Error(response.message)
    clearAdminSession()
    await navigateTo({ path: '/login', query: { passwordChanged: '1' } })
  } catch (err) {
    error.value = normalizeApiError(err).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-elevated/40 p-4">
    <UCard class="w-full max-w-sm">
      <template #header>
        <h1 class="text-lg font-semibold text-highlighted">修改管理密码</h1>
        <p class="mt-1 text-xs text-muted">首次登录必须设置新密码后才能进入管理后台。</p>
      </template>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <UFormField label="当前密码">
          <UInput v-model="currentPassword" type="password" autocomplete="current-password" />
        </UFormField>
        <UFormField label="新密码">
          <UInput v-model="newPassword" type="password" autocomplete="new-password" />
        </UFormField>
        <UFormField label="确认新密码">
          <UInput v-model="confirmPassword" type="password" autocomplete="new-password" />
        </UFormField>
        <UAlert v-if="error" color="error" variant="subtle" :title="error" />
        <UButton type="submit" block :loading="saving">保存并重新登录</UButton>
      </form>
    </UCard>
  </div>
</template>
