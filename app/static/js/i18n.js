// i18n - MaxAgent 前端文案（仅保留当前页面实际使用的 key）

const translations = {
  'zh-CN': {
    config: {
      base_url: 'API 地址',
    },
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
    skills: {
      select_hint: '技能库即将上线，敬请期待',
    },
    common: {
      loading: '加载中...',
      request_failed: '请求失败',
    },
    chat: {
      welcome_title: '有什么我可以帮您的？',
      welcome_subtitle: '开始对话，探索无限可能',
      thinking: '思考中...',
      message_placeholder: '输入消息...',
      start_chat: '开始对话吧',
      suggest_quantum: '什么是量子计算？',
      suggest_python: '写一个 Python 函数',
      suggest_ml: '机器学习类型',
      suggest_roadmap: '学习 Python 路线',
    },
    status: {
      ready: '就绪',
      model_name: '模型',
    },
    cron: {
      no_jobs: '自动化任务即将上线',
    },
  },
  'en': {
    config: {
      base_url: 'Base URL',
    },
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
    skills: {
      select_hint: 'Skills library coming soon',
    },
    common: {
      loading: 'Loading...',
      request_failed: 'Request failed',
    },
    chat: {
      welcome_title: 'What can I help you with?',
      welcome_subtitle: 'Start a conversation and explore infinite possibilities',
      thinking: 'Thinking...',
      message_placeholder: 'Type a message...',
      start_chat: 'Start chatting',
      suggest_quantum: 'What is quantum computing?',
      suggest_python: 'Write a Python function',
      suggest_ml: 'Types of machine learning',
      suggest_roadmap: 'Python learning path',
    },
    status: {
      ready: 'Ready',
      model_name: 'Model',
    },
    cron: {
      no_jobs: 'Automation coming soon',
    },
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
    if (value && typeof value === 'object') {
      value = value[k];
    } else {
      return key;
    }
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
