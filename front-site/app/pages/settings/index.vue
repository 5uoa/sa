<script setup lang="ts">
/** 个人设置 · 基本资料 */
definePageMeta({ layout: 'console', title: '个人设置' })

const state = useSettingsState()
const avatarPicker = ref<{ inputRef?: HTMLInputElement }>()
const saved = ref(false)

function pickAvatar() {
  avatarPicker.value?.inputRef?.click()
}

function onAvatarChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) state.value.avatarUrl = URL.createObjectURL(file)
}

function saveProfile() {
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
          <h2 class="text-sm font-semibold text-highlighted">基本资料</h2>
        </template>

        <div class="flex flex-col gap-5">
          <div class="flex items-center gap-4">
            <UAvatar :src="state.avatarUrl" text="王" size="3xl" />
            <div class="flex flex-col gap-1">
              <span class="text-sm font-medium text-highlighted">{{ state.profile.name }}</span>
              <span class="text-xs text-muted">{{ state.profile.email }}</span>
            </div>
            <UButton class="ms-auto" color="neutral" variant="outline" @click="pickAvatar">
              更换头像
            </UButton>
            <UInput
              ref="avatarPicker"
              type="file"
              accept="image/*"
              class="hidden"
              @change="onAvatarChange"
            />
          </div>

          <div class="grid gap-4 sm:grid-cols-2">
            <UFormField label="姓名" name="name">
              <UInput v-model="state.profile.name" class="w-full" />
            </UFormField>
            <UFormField label="职位" name="title">
              <UInput v-model="state.profile.title" class="w-full" />
            </UFormField>
            <UFormField label="邮箱" name="email">
              <UInput v-model="state.profile.email" type="email" class="w-full" />
            </UFormField>
            <UFormField label="手机号" name="phone">
              <UInput v-model="state.profile.phone" class="w-full" />
            </UFormField>
          </div>

          <UAlert
            v-if="saved"
            color="success"
            variant="subtle"
            title="个人资料已保存"
            description="演示环境仅保存在当前会话状态，刷新后会恢复默认值。"
          >
            <template #actions>
              <UButton color="neutral" variant="ghost" @click="saved = false">关闭</UButton>
            </template>
          </UAlert>

          <div class="flex justify-end">
            <UButton @click="saveProfile">保存修改</UButton>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
