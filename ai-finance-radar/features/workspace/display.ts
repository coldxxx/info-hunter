export const engineeringCategories = [
  '工具更新',
  '工程实践',
  '开源项目',
  '评测与性能',
  '安全与可靠性',
  '模型与研究',
  '手动收录',
];

export const regions = ['全球', '中国大陆', '日本', '韩国', '台湾'];

export const topics = [
  '算力与芯片',
  '资本开支与基础设施',
  '模型与商业化',
  '业绩与估值',
  '政策与供应链',
];

export const stamp = (v: string | null) =>
  v
    ? new Date(v).toLocaleString('zh-CN', {
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      })
    : '时间未知';
