﻿<script setup lang="ts">
/** 顶栏：页面标题 + 「项目 / 总管」分段切换 + 用户头像菜单，供各页面共用 */
const props = defineProps<{
  title: string
  current: 'project' | 'chief'
}>()

const tabs = [
  { value: 'project', label: '项目', to: '/' },
  { value: 'chief', label: '总管', to: '/chief' }
] as const

const tabItems = tabs.map(({ value, label }) => ({ value, label }))

function handleTabChange(value: string | number) {
  const tab = tabs.find((item) => item.value === value)
  if (tab && tab.value !== props.current) navigateTo(tab.to)
}
</script>

<template>
  <header
    class="flex h-14 flex-none items-center justify-between gap-2 border-b border-default bg-default px-4 max-[767px]:px-3"
  >
    <h1 class="truncate text-lg font-semibold text-highlighted">{{ title }}</h1>

    <div class="flex flex-none items-center gap-2">
      <UTabs
        :items="tabItems"
        :model-value="current"
        :content="false"
        class="w-fit"
        aria-label="页面切换"
        @update:model-value="handleTabChange"
      />

      <AppUserMenu />
    </div>
  </header>
</template>
