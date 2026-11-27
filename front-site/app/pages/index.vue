<script setup lang="ts">
import { siteConfig } from '~/utils/siteConfig'

definePageMeta({ layout: false })

useSeoMeta({
  title: '项目工作台 - 项目·任务包·任务·会话·附件',
  description:
    'xf 项目工作台把项目、任务包、任务、会话记录与任务附件五栏并排呈现，支持项目背景绑定、项目内 Agent 沟通和协作留痕。',
  ogTitle: '项目工作台 - 五栏协作视图',
  ogDescription: '项目、任务包、任务、会话和附件统一管理，沟通限定在当前项目背景下。',
  ogImage: '/og-home.png',
  ogType: 'website',
  robots: 'index, follow'
})

useSchemaOrg([
  defineWebSite({
    name: siteConfig.name,
    description: '项目、任务包、任务、会话记录与任务相关附件五栏并排的项目工作台。',
    inLanguage: 'zh-CN'
  })
])
</script>

<template>
  <div class="flex h-dvh flex-col bg-default">
    <AppTopBar title="项目工作台" current="project" />
    <ProjectWorkspace class="min-h-0 flex-1" />
  </div>
</template>
