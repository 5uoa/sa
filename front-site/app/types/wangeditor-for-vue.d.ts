/**
 * @wangeditor/editor-for-vue 的 package.json exports 未声明 types 条件，
 * TS 无法解析其 dist/src/index.d.ts；按该库实际组件 props 补充声明。
 */
declare module '@wangeditor/editor-for-vue' {
  import type { DefineComponent } from 'vue'
  import type { IDomEditor, IEditorConfig, IToolbarConfig } from '@wangeditor/editor'

  export const Editor: DefineComponent<{
    modelValue?: string
    defaultHtml?: string
    mode?: string
    defaultConfig?: Partial<IEditorConfig>
  }>

  export const Toolbar: DefineComponent<{
    editor?: IDomEditor
    mode?: string
    defaultConfig?: Partial<IToolbarConfig>
  }>
}
