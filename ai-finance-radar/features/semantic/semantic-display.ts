export const relations: Record<string, string> = {
  duplicate: '重复信息',
  complement: '同事件有增量',
  conflict: '同事件有冲突',
  related: '主题相关',
  unrelated: '不相关',
  uncertain: '信息不足',
};
export const date = (value: string | null) =>
  value
    ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
    : '发布日期未知';
