<script setup lang="ts">
/** 用户头像菜单：个人设置 / 管理后台 / 额度管理 / 退出 */
import type { DropdownMenuItem } from '@nuxt/ui'

const { user, logout } = useAdminSession()
const userMenuItems: DropdownMenuItem[][] = [
  [
    { label: '个人设置', onSelect: () => navigateTo('/settings') },
    { label: '管理后台', onSelect: () => navigateTo('/admin') },
    { label: '额度管理', onSelect: () => navigateTo('/quota') }
  ],
  [
    {
      label: '退出',
      color: 'error',
      onSelect: async () => {
        logout()
        await navigateTo('/login')
      }
    }
  ]
]
</script>

<template>
  <UDropdownMenu :items="userMenuItems" :content="{ align: 'end' }">
    <UButton color="neutral" variant="ghost" square class="p-0" aria-label="用户菜单">
      <UAvatar :text="user?.name?.slice(0, 1) || '我'" size="md" />
    </UButton>
  </UDropdownMenu>
</template>
