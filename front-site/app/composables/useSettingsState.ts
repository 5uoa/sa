/** 个人设置：基本资料 / 偏好设置 / 账号安全 三个页面共享的演示数据，切换页面不丢失编辑 */
export function useSettingsState() {
  return useState('settings-state', () => ({
    avatarUrl: '',
    profile: {
      name: '演示用户',
      email: 'owner@example.com',
      phone: '',
      title: '品牌内容负责人'
    },
    prefs: {
      language: '简体中文',
      timezone: '(GMT+08:00) 北京',
      emailNotify: true,
      weeklyDigest: false
    },
    password: { current: '', next: '', confirm: '' }
  }))
}
