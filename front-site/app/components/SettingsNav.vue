<script setup lang="ts">
/** 个人设置左侧导航：基本资料 / 偏好设置 / 账号安全（各自独立路由） */
const route = useRoute()

const sections = [
  { value: '/settings', label: '基本资料' },
  { value: '/settings/preferences', label: '偏好设置' },
  { value: '/settings/security', label: '账号安全' }
]
</script>

<template>
  <nav class="flex flex-col gap-1" aria-label="个人设置分区">
    <UButton
      v-for="section in sections"
      :key="section.value"
      :to="section.value"
      color="neutral"
      :variant="route.path === section.value ? 'soft' : 'ghost'"
      block
      class="justify-start"
      :aria-current="route.path === section.value ? 'page' : undefined"
    >
      {{ section.label }}
    </UButton>
  </nav>
</template>
