<script setup lang="ts">
import { persistAdminSession, type AdminUser } from '~/composables/useAdminSession'

definePageMeta({ layout: false })

const route = useRoute()
const name = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const saving = ref(false)

async function submit() {
  error.value = ''
  if (password.value.length < 8) {
    error.value = '密码至少 8 位'
    return
  }
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  saving.value = true
  try {
    const config = useRuntimeConfig()
    const response = await $fetch<{
      code: number
      message: string
      data: { token: string; user: AdminUser }
    }>('/front/admin/auth/accept-invite', {
      baseURL: config.public.apiBase as string,
      method: 'POST',
      body: { token: route.query.token, password: password.value, name: name.value }
    })
    if (response.code !== 200) throw new Error(response.message)
    persistAdminSession(response.data.token, response.data.user)
    await navigateTo(['拥有者', '管理员'].includes(response.data.user.role) ? '/admin' : '/')
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
        <h1 class="text-lg font-semibold text-highlighted">接受邀请</h1>
        <p class="mt-1 text-xs text-muted">设置姓名与密码以激活账号。</p>
      </template>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <UFormField label="姓名">
          <UInput v-model="name" autocomplete="name" />
        </UFormField>
        <UFormField label="密码">
          <UInput v-model="password" type="password" autocomplete="new-password" />
        </UFormField>
        <UFormField label="确认密码">
          <UInput v-model="confirmPassword" type="password" autocomplete="new-password" />
        </UFormField>
        <UAlert v-if="error" color="error" variant="subtle" :title="error" />
        <UButton type="submit" block :loading="saving">激活账号</UButton>
      </form>
    </UCard>
  </div>
</template>
