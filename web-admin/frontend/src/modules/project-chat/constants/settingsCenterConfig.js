// Static metadata for the ProjectChat settings center.

export const CHAT_PARAMETER_SECTION_CONFIG = {
  image: [
    {
      key: "image_aspect_ratio",
      label: "图片比例",
      helper: "先确定画面构图比例，再选择对应输出尺寸。",
      control: "segmented",
      maxSegmentedOptions: 5,
    },
    {
      key: "image_resolution",
      label: "图片分辨率",
      helper: "在比例确定后，再选择固定尺寸档位，后端会自动换算最终输出尺寸。",
      control: "select",
    },
    {
      key: "image_style",
      label: "图片风格",
      helper: "控制图片整体视觉风格。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "image_quality",
      label: "图片质量",
      helper: "平衡生成速度和细节质量。",
      control: "segmented",
      maxSegmentedOptions: 3,
    },
  ],
  video: [
    {
      key: "video_aspect_ratio",
      label: "视频比例",
      helper: "控制视频画幅比例。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_style",
      label: "视频风格",
      helper: "控制镜头和整体表现风格。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_duration_seconds",
      label: "视频时长",
      helper: "控制单次生成片段长度。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
    {
      key: "video_motion_strength",
      label: "动作强度",
      helper: "控制镜头和主体的动态程度。",
      control: "segmented",
      maxSegmentedOptions: 4,
    },
  ],
};
export const SETTINGS_CENTER_ITEM_DEFS = [
  {
    id: "chat",
    label: "对话设置",
    desc: "当前项目的 AI 对话运行参数",
    kind: "internal",
  },
];
export const SETTINGS_CENTER_PANEL_META = {
  chat: {
    label: "对话设置",
    desc: "当前项目的 AI 对话运行参数",
    contextLabel: "对话配置",
  },
  projects: {
    label: "项目详情",
    desc: "查看当前项目的配置、成员、记忆和任务推进。",
    contextLabel: "项目详情",
  },
};
export const ROLE_LABEL_MAP = {
  admin: "管理员",
  user: "普通用户",
};
export const SETTINGS_GUIDE_REASON_MAP = {
  chat: "先把项目、执行员工、模型和工具预算收束到同一轮上下文里。",
};
