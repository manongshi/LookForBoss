export const platformNames = {
  boss: 'BOSS 直聘', liepin: '猎聘', job51: '前程无忧', zhilian: '智联招聘',
}
export const platformName = (value) => platformNames[value || 'boss'] || value
export const deliveryName = (value, action) => value === 'confirmed' && action === 'message' ? '消息已发送' : value === 'confirmed' && action === 'contact' ? '已建立沟通' : ({
  pending: '执行中', confirmed: '已确认完成', unknown: '待核对', failed: '未发送', not_sent: '已确认未发送',
}[value] || '未投递')
