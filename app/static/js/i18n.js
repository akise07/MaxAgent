// i18n - MaxAgent 前端文案

const translations = {
  'zh-CN': {
    config: { base_url: 'API 地址' },
    sidebar: {
      new_task: '新建任务',
      no_conversations: '暂无任务，点击上方新建',
      no_match: '没有匹配的任务',
      no_messages: '暂无消息',
      open_home: '打开 Home 目录',
      open_home_ok: '已在文件管理器中打开',
      open_home_failed: '打开 Home 目录失败',
      settings: '设置',
      skills: '技能',
      automation: '自动化',
      appearance: '外观',
      tasks: '任务列表',
      theme_dark: '深色',
      theme_light: '浅色',
      switch_to_dark: '切换为深色',
      switch_to_light: '切换为浅色',
      search_sessions: '搜索任务...',
      language: '语言',
      delete: '删除',
      confirm_delete: '确定要删除任务「{title}」吗？',
    },
    skills: { select_hint: '技能库即将上线，敬请期待' },
    tool: {
      running_command: '运行命令',
      calling: '调用工具',
      arguments: '参数',
      result: '结果',
      thinking: '深度思考',
    },
    common: { loading: '加载中...', request_failed: '请求失败' },
    chat: {
      welcome_title: '有什么我可以帮您的？',
      welcome_subtitle: '开始对话，探索无限可能',
      thinking: '思考中...',
      message_placeholder: '输入消息...',
      start_chat: '开始对话吧',
    },
    task: {
      create_title: '创建任务',
      input_placeholder: '描述你的任务目标或指令…',
      send: '发送',
      empty_task: '请先输入任务内容',
      cap_docs: '文档处理',
      cap_finance: '金融服务',
      cap_data: '数据分析及可视化',
      cap_more: '更多',
      plus_file: '添加文件',
      plus_ref: '引用对话中的文件',
      plus_skill: '技能',
      plus_mcp: '连接器（MCP）',
      ref_todo: '引用对话文件即将支持',
      mcp_todo: 'MCP 连接器即将支持',
      more_todo: '更多能力即将上线',
      ws_select: '选择工作空间',
      ws_none: '不选择工作空间',
      perm_default: '默认权限',
      perm_full: '允许完全访问',
    },
    settings: {
      tab_system: '系统设置',
      tab_memory: '记忆',
      tab_models: '模型',
      memory_hint: '记忆文件位于项目 home/memory 目录。',
      add_model: '添加模型',
      edit_model: '编辑模型',
      back: '返回',
      model_name: '显示名称',
      api_endpoint: 'API 端点',
      api_key: 'API Key',
      model_id: '模型 ID',
      set_default: '设为默认模型',
      save: '保存',
      saved: '已保存',
      delete: '删除',
      deleted: '已删除',
      default: '默认',
      no_models: '暂无模型，请添加',
      key_keep: '留空则不修改',
      required_fields: 'API 端点与模型 ID 不能为空',
      confirm_delete_model: '确定删除该模型？',
      advanced: '高级配置',
      adv_tool: '工具调用',
      adv_image: '图片输入',
      adv_thinking: '思考模式',
      adv_thinking_only: '仅思考模式',
      adv_allow_disable: '允许关闭思考',
      adv_default_intensity: '默认思考强度',
      adv_supported_intensity: '支持的思考强度',
      adv_input: '输入',
      adv_output: '输出',
    },
    status: { ready: '就绪', model_name: '模型' },
    cron: { no_jobs: '自动化任务即将上线' },
  },
  'en': {
    config: { base_url: 'Base URL' },
    sidebar: {
      new_task: 'New Task',
      no_conversations: 'No tasks yet — create one above',
      no_match: 'No matching tasks',
      no_messages: 'No messages',
      open_home: 'Open Home directory',
      open_home_ok: 'Opened in file explorer',
      open_home_failed: 'Failed to open Home directory',
      settings: 'Settings',
      skills: 'Skills',
      automation: 'Automation',
      appearance: 'Appearance',
      tasks: 'Tasks',
      theme_dark: 'Dark',
      theme_light: 'Light',
      switch_to_dark: 'Switch to Dark',
      switch_to_light: 'Switch to Light',
      search_sessions: 'Search tasks...',
      language: 'Language',
      delete: 'Delete',
      confirm_delete: 'Delete task "{title}"?',
    },
    skills: { select_hint: 'Skills library coming soon' },
    tool: {
      running_command: 'Running command',
      calling: 'Calling tool',
      arguments: 'Arguments',
      result: 'Result',
      thinking: 'Deep Thinking',
    },
    common: { loading: 'Loading...', request_failed: 'Request failed' },
    chat: {
      welcome_title: 'What can I help you with?',
      welcome_subtitle: 'Start a conversation and explore infinite possibilities',
      thinking: 'Thinking...',
      message_placeholder: 'Type a message...',
      start_chat: 'Start chatting',
    },
    task: {
      create_title: 'Create Task',
      input_placeholder: 'Describe your task goal or instructions…',
      send: 'Send',
      empty_task: 'Please enter a task first',
      cap_docs: 'Documents',
      cap_finance: 'Finance',
      cap_data: 'Data & Visualization',
      cap_more: 'More',
      plus_file: 'Add file',
      plus_ref: 'Reference chat files',
      plus_skill: 'Skills',
      plus_mcp: 'Connectors (MCP)',
      ref_todo: 'Chat file reference coming soon',
      mcp_todo: 'MCP connectors coming soon',
      more_todo: 'More capabilities coming soon',
      ws_select: 'Select workspace',
      ws_none: 'No workspace',
      perm_default: 'Default permissions',
      perm_full: 'Allow full access',
    },
    settings: {
      tab_system: 'System',
      tab_memory: 'Memory',
      tab_models: 'Models',
      memory_hint: 'Memory files live under home/memory.',
      add_model: 'Add model',
      edit_model: 'Edit model',
      back: 'Back',
      model_name: 'Display name',
      api_endpoint: 'API endpoint',
      api_key: 'API Key',
      model_id: 'Model ID',
      set_default: 'Set as default',
      save: 'Save',
      saved: 'Saved',
      delete: 'Delete',
      deleted: 'Deleted',
      default: 'Default',
      no_models: 'No models yet — add one',
      key_keep: 'Leave blank to keep',
      required_fields: 'API endpoint and Model ID are required',
      confirm_delete_model: 'Delete this model?',
      advanced: 'Advanced',
      adv_tool: 'Tool calling',
      adv_image: 'Image input',
      adv_thinking: 'Thinking mode',
      adv_thinking_only: 'Thinking-only mode',
      adv_allow_disable: 'Allow disable thinking',
      adv_default_intensity: 'Default thinking intensity',
      adv_supported_intensity: 'Supported thinking intensities',
      adv_input: 'Input',
      adv_output: 'Output',
    },
    status: { ready: 'Ready', model_name: 'Model' },
    cron: { no_jobs: 'Automation coming soon' },
  },
};

function resolveLang(lang) {
  if (translations[lang]) return lang;
  const prefix = lang.split('-')[0];
  for (const key of Object.keys(translations)) {
    if (key.startsWith(prefix)) return key;
  }
  console.warn('[i18n] Unsupported language, falling back to default:', lang);
  return null;
}

let currentLang = 'zh-CN';

const urlLang = new URLSearchParams(window.location.search).get('lang');
if (urlLang) {
  const resolved = resolveLang(urlLang);
  if (resolved) currentLang = resolved;
}

function t(key, ...args) {
  const keys = key.split('.');
  let value = translations[currentLang];
  for (const k of keys) {
    if (value && typeof value === 'object') value = value[k];
    else return key;
  }
  if (value === undefined) return key;
  if (args.length > 0 && typeof value === 'string') {
    return value.replace(/\{(\d+)\}/g, (match, index) => {
      return args[parseInt(index)] !== undefined ? args[parseInt(index)] : match;
    });
  }
  return value;
}

function setLang(lang) {
  const resolved = resolveLang(lang);
  if (resolved) {
    currentLang = resolved;
    window.dispatchEvent(new CustomEvent('language-changed'));
  }
}
