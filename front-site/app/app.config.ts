/**
 * 主题配色：主色映射站点品牌蓝，中性色使用 zinc。
 * 组件尺寸与外观全部走 Nuxt UI 默认值，不再覆写按钮档位。
 */
export default defineAppConfig({
  ui: {
    colors: {
      primary: 'brand',
      neutral: 'zinc'
    }
  }
})
