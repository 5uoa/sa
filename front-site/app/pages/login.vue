<script setup lang="ts">
/** 登录页：使用 admin_member 账号与密码登录管理后台。 */
import {
  developmentAdminLogin,
  persistAdminSession,
  type AdminUser
} from '~/composables/useAdminSession'

definePageMeta({ layout: false })

const account = ref('')
const password = ref('')
const error = ref('')
const submitting = ref(false)
const route = useRoute()

onMounted(async () => {
  const config = useRuntimeConfig()
  if (config.public.authDisabled) {
    await navigateTo((route.query.redirect as string) || '/')
    return
  }
  const user = await developmentAdminLogin()
  if (user) await navigateTo((route.query.redirect as string) || '/admin')
})

interface LoginResponse {
  code: number
  message: string
  data: { token: string; user: AdminUser }
}

async function submit() {
  if (submitting.value) return
  if (!account.value.trim() || !password.value) {
    error.value = '请输入账号与密码'
    return
  }
  error.value = ''
  submitting.value = true
  try {
    const config = useRuntimeConfig()
    const response = await $fetch<LoginResponse>('/front/admin/auth/login', {
      baseURL: config.public.apiBase as string,
      method: 'POST',
      body: { email: account.value.trim(), password: password.value }
    })
    if (response.code !== 200) throw new Error(response.message)
    persistAdminSession(response.data.token, response.data.user)
    await navigateTo(
      response.data.user.mustChangePassword
        ? '/change-password'
        : (route.query.redirect as string) || '/admin'
    )
  } catch (err) {
    error.value = normalizeApiError(err).message
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center bg-elevated/40 p-4">
    <div class="w-full max-w-sm">
      <div class="mb-6 flex flex-col items-center gap-1">
        <span class="text-xl font-semibold text-highlighted">Super Agent 工作台</span>
        <span class="text-sm text-muted">登录以继续管理项目与 Agent</span>
      </div>

      <UCard>
        <form class="flex flex-col gap-4" @submit.prevent="submit">
          <UFormField label="账号" name="account">
            <UInput
              v-model="account"
              placeholder="name@example.com"
              autocomplete="username"
              class="w-full"
            />
          </UFormField>

          <UFormField label="密码" name="password">
            <UInput
              v-model="password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
              class="w-full"
            />
          </UFormField>

          <UAlert v-if="error" color="error" variant="subtle" :title="error" />

          <UButton type="submit" block :loading="submitting">登录</UButton>
        </form>
      </UCard>

      <p class="mt-4 text-center text-xs text-muted">还没有账号？请联系管理员开通</p>
    </div>
  </div>
</template>
