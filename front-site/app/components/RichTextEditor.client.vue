<script lang="ts">
/** 选区弹窗「引用到 AI」菜单：模块级只注册一次，exec 时回调当前编辑器实例 */
import '@wangeditor/editor/dist/css/style.css'
import { Boot } from '@wangeditor/editor'
import type { IButtonMenu, IDomEditor, IEditorConfig, IToolbarConfig } from '@wangeditor/editor'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'

let quoteSink: ((payload: { text: string; range: string }) => void) | null = null

/** 选区所在行范围（按段落块计数），如 L1:L28 */
function selectionRange(editor: IDomEditor): string {
  const selection = editor.selection
  if (!selection) return 'L1:L1'
  const start = Number(selection.anchor.path?.[0] ?? 0) + 1
  const end = Number(selection.focus.path?.[0] ?? 0) + 1
  return `L${Math.min(start, end)}:L${Math.max(start, end)}`
}

class QuoteToAiMenu implements IButtonMenu {
  readonly title = '引用到 AI'
  readonly tag = 'button'

  getValue() {
    return ''
  }

  isActive() {
    return false
  }

  isDisabled(editor: IDomEditor) {
    return editor.selection == null
  }

  exec(editor: IDomEditor) {
    const text = editor.getSelectionText().trim()
    if (text) quoteSink?.({ text, range: selectionRange(editor) })
  }
}

const menuRegistry = globalThis as typeof globalThis & {
  __xfQuoteToAIMenuRegistered?: boolean
}
if (!menuRegistry.__xfQuoteToAIMenuRegistered) {
  Boot.registerMenu({ key: 'quoteToAI', factory: () => new QuoteToAiMenu() })
  menuRegistry.__xfQuoteToAIMenuRegistered = true
}
</script>

<script setup lang="ts">
/** wangEditor 富文本编辑器：仅客户端渲染，供总管文档编辑使用 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
  }>(),
  { placeholder: '开始编辑…' }
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: []
  /** 选区「引用到 AI」：把选中文本与行范围交给父级写入输入框 */
  quote: [payload: { text: string; range: string }]
}>()

const editorRef = shallowRef<IDomEditor>()
const html = ref(props.modelValue)

/** 选区弹窗点击「引用到 AI」时，把选中文本交给父级 */
quoteSink = (payload) => emit('quote', payload)

watch(
  () => props.modelValue,
  (value) => {
    if (value !== html.value) html.value = value
  }
)

// 工具栏：Markdown 语法操作 + 对齐/缩进/图片/表格
const toolbarConfig: Partial<IToolbarConfig> = {
  toolbarKeys: [
    'headerSelect',
    'bold',
    'italic',
    'code',
    'bulletedList',
    'numberedList',
    'todo',
    'blockquote',
    'codeBlock',
    'insertLink',
    'divider',
    // 分组必须是对象：字符串 key 会抛 "Not found menu item factory"
    {
      key: 'group-justify',
      title: '对齐',
      iconSvg:
        '<svg viewBox="0 0 1024 1024"><path d="M768 793.6v102.4H51.2v-102.4h716.8z m204.8-230.4v102.4H51.2v-102.4h921.6z m-204.8-230.4v102.4H51.2v-102.4h716.8zM972.8 102.4v102.4H51.2V102.4h921.6z"></path></svg>',
      menuKeys: ['justifyLeft', 'justifyRight', 'justifyCenter', 'justifyJustify']
    },
    {
      key: 'group-indent',
      title: '缩进',
      iconSvg:
        '<svg viewBox="0 0 1024 1024"><path d="M0 64h1024v128H0z m384 192h640v128H384z m0 192h640v128H384z m0 192h640v128H384zM0 832h1024v128H0z m0-128V320l256 192z"></path></svg>',
      menuKeys: ['indent', 'delIndent']
    },
    'insertImage',
    'insertTable',
    'undo',
    'redo'
  ]
}
const editorConfig: Partial<IEditorConfig> = {
  placeholder: props.placeholder,
  scroll: true,
  autoFocus: false,
  // 选中文本后的弹窗：首项为「引用到 AI」，其余沿用默认项
  hoverbarKeys: {
    text: {
      menuKeys: [
        'quoteToAI',
        '|',
        'headerSelect',
        'insertLink',
        'bulletedList',
        '|',
        'bold',
        'through',
        'color',
        'bgColor',
        'clearStyle'
      ]
    }
  }
}

function handleCreated(editor: IDomEditor) {
  editorRef.value = editor
}

/** 焦点在编辑器或工具栏内才算用户编辑，避免程序写入内容触发 change */
function isUserEditing(): boolean {
  const active = document.activeElement
  return active instanceof HTMLElement && active.closest('.rich-editor') !== null
}

function handleChange(editor: IDomEditor) {
  const value = editor.getHtml()
  if (value !== props.modelValue) emit('update:modelValue', value)
  if (isUserEditing()) emit('change')
}

onBeforeUnmount(() => {
  quoteSink = null
  editorRef.value?.destroy()
})
</script>

<template>
  <div class="rich-editor flex h-full min-h-0 flex-col">
    <Toolbar
      class="rich-editor__toolbar flex-none border-b border-default"
      :editor="editorRef"
      :default-config="toolbarConfig"
      mode="default"
    />
    <Editor
      v-model="html"
      class="rich-editor__body min-h-0 flex-1 overflow-y-auto"
      :default-config="editorConfig"
      mode="default"
      @on-created="handleCreated"
      @on-change="handleChange"
    />
  </div>
</template>

<style scoped>
/* wangEditor 第三方内部结构：仅覆盖必要外观，取值全部来自 Nuxt UI 主题变量 */
.rich-editor__toolbar :deep(.w-e-toolbar) {
  flex-wrap: wrap;
  padding: 0.375rem 0.5rem;
  border: 0;
  background-color: transparent;
}

.rich-editor__toolbar :deep(.w-e-bar-item) {
  flex: none;
}

.rich-editor__toolbar :deep(.w-e-bar-item button) {
  height: 1.75rem;
  border-radius: var(--ui-radius);
  color: var(--ui-text-muted);
  transition:
    background-color 0.15s,
    color 0.15s;
}

.rich-editor__toolbar :deep(.w-e-bar-item button:hover) {
  background-color: var(--ui-bg-elevated);
  color: var(--ui-text);
}

.rich-editor__toolbar :deep(.w-e-bar-item button.active) {
  background-color: color-mix(in srgb, var(--ui-primary) 10%, transparent);
  color: var(--ui-primary);
}

/* 选区弹窗「引用到 AI」：主色文字按钮 */
.rich-editor__body :deep(.w-e-hover-bar button[data-menu-key='quoteToAI']) {
  color: var(--ui-primary);
  font-weight: 600;
}

.rich-editor__body :deep(.w-e-text-container) {
  height: 100%;
  border: 0;
  background-color: transparent;
}

.rich-editor__body :deep(.w-e-text-placeholder) {
  top: 0.75rem;
  left: 1rem;
  color: var(--ui-text-muted);
  font-size: 0.875rem;
  font-style: normal;
}

.rich-editor__body :deep([data-slate-editor]) {
  padding: 0.75rem 1rem 1rem;
  color: var(--ui-text);
  font-size: 0.875rem;
  line-height: 1.65;
}

.rich-editor__body :deep([data-slate-editor] h1),
.rich-editor__body :deep([data-slate-editor] h2) {
  margin: 0 0 0.5rem;
  color: var(--ui-text-highlighted);
  font-size: 1.125rem;
  font-weight: 600;
  line-height: 1.3;
}

.rich-editor__body :deep([data-slate-editor] h3) {
  margin: 1rem 0 0.5rem;
  color: var(--ui-text-highlighted);
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.35;
}

.rich-editor__body :deep([data-slate-editor] p) {
  margin: 0 0 0.5rem;
}

.rich-editor__body :deep([data-slate-editor] ul),
.rich-editor__body :deep([data-slate-editor] ol) {
  margin: 0 0 0.5rem;
  padding-left: 1.25rem;
  list-style: disc;
}

.rich-editor__body :deep([data-slate-editor] ol) {
  list-style: decimal;
}

.rich-editor__body :deep([data-slate-editor] li) {
  margin: 0.125rem 0;
}

.rich-editor__body :deep([data-slate-editor] blockquote) {
  margin: 0 0 0.5rem;
  padding-left: 0.75rem;
  border-left: 2px solid var(--ui-border);
  color: var(--ui-text-muted);
}

.rich-editor__body :deep([data-slate-editor] em) {
  color: var(--ui-text-muted);
  font-size: 0.8125rem;
  font-style: normal;
}

.rich-editor__body :deep([data-slate-editor] code) {
  padding: 0.125rem 0.375rem;
  border-radius: var(--ui-radius);
  background-color: var(--ui-bg-elevated);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.8125rem;
}

.rich-editor__body :deep([data-slate-editor] pre) {
  margin: 0 0 0.5rem;
  padding: 0.75rem;
  border-radius: var(--ui-radius);
  background-color: var(--ui-bg-elevated);
  overflow-x: auto;
}

.rich-editor__body :deep([data-slate-editor] pre code) {
  padding: 0;
  background-color: transparent;
}

.rich-editor__body :deep([data-slate-editor] a) {
  color: var(--ui-primary);
}

.rich-editor__body :deep([data-slate-editor] table) {
  width: 100%;
  margin: 0 0 0.5rem;
  border-collapse: collapse;
  font-size: 0.8125rem;
}

.rich-editor__body :deep([data-slate-editor] th),
.rich-editor__body :deep([data-slate-editor] td) {
  padding: 0.375rem 0.5rem;
  border: 1px solid var(--ui-border);
  text-align: left;
}

.rich-editor__body :deep([data-slate-editor] th) {
  background-color: var(--ui-bg-elevated);
  font-weight: 600;
}
</style>
