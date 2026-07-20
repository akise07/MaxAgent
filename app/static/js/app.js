// MaxAgent Frontend App
(function () {
    'use strict';

    // ===== State =====
    let currentConversationId = null;
    let conversations = [];
    let isLoading = false;
    let currentView = 'chat';
    let theme = localStorage.getItem('maxagent-theme') || 'dark';
    let taskAttachments = [];
    let models = [];
    let selectedModelId = localStorage.getItem('maxagent-model-id') || null;
    let workspaceMode = localStorage.getItem('maxagent-workspace') || 'select';
    let permissionMode = localStorage.getItem('maxagent-permission') || 'default';
    let settingsTab = 'system';
    let editingModelId = null;

    // ===== DOM refs =====
    const $ = (id) => document.getElementById(id);
    const welcome = $('welcome');
    const chatArea = $('chat-area');
    const chatTitle = $('chat-title');
    const messagesEl = $('messages');
    const messageInput = $('message-input');
    const sendBtn = $('send-btn');
    const conversationList = $('conversation-list');
    const newTaskBtn = $('new-task-btn');
    const skillsBtn = $('skills-btn');
    const automationBtn = $('automation-btn');
    const searchInput = $('search-input');
    const statusDot = $('status-dot');
    const statusText = $('status-text');
    const userBar = $('user-bar');
    const userMenu = $('user-menu');
    const themeLabel = $('theme-label');
    const langLabel = $('lang-label');
    const settingsModal = $('settings-modal');
    const settingsModel = $('settings-model');
    const settingsEndpoint = $('settings-endpoint');
    const settingsThemeBtn = $('settings-theme-btn');
    const panelSkills = $('panel-skills');
    const panelAutomation = $('panel-automation');
    const toastEl = $('toast');
    const newTaskPage = $('new-task-page');
    const taskInput = $('task-input');
    const taskSendBtn = $('task-send-btn');
    const taskAttachmentsEl = $('task-attachments');
    const taskFileInput = $('task-file-input');
    const taskModelLabel = $('task-model-label');
    const taskModelBtn = $('task-model-btn');
    const taskModelMenu = $('task-model-menu');
    const chatModelLabel = $('chat-model-label');
    const chatModelBtn = $('chat-model-btn');
    const chatModelMenu = $('chat-model-menu');
    const closeNewTaskBtn = $('close-new-task-btn');
    const welcomeNewTaskBtn = $('welcome-new-task-btn');
    const taskPlusBtn = $('task-plus-btn');
    const taskPlusMenu = $('task-plus-menu');
    const workspaceBtn = $('workspace-btn');
    const workspaceMenu = $('workspace-menu');
    const workspaceLabel = $('workspace-label');
    const permissionBtn = $('permission-btn');
    const permissionMenu = $('permission-menu');
    const permissionLabel = $('permission-label');
    const modelListEl = $('model-list');

    // ===== API Helpers =====
    async function api(url, options = {}) {
        const config = {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        };
        const response = await fetch(url, config);
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || t('common.request_failed'));
        }
        if (response.status === 204) return null;
        return response.json();
    }

    // ===== Toast =====
    let toastTimer = null;
    function showToast(msg, isError = false) {
        toastEl.textContent = msg;
        toastEl.classList.toggle('error', !!isError);
        toastEl.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2600);
    }

    // ===== Theme =====
    function applyTheme(next) {
        theme = next === 'light' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('maxagent-theme', theme);
        updateThemeLabels();
    }
    function toggleTheme() { applyTheme(theme === 'dark' ? 'light' : 'dark'); }
    function updateThemeLabels() {
        const label = theme === 'light' ? t('sidebar.theme_light') : t('sidebar.theme_dark');
        if (themeLabel) themeLabel.textContent = label;
        if (settingsThemeBtn) {
            settingsThemeBtn.textContent = theme === 'light'
                ? t('sidebar.switch_to_dark')
                : t('sidebar.switch_to_light');
        }
    }

    // ===== i18n =====
    function applyI18n() {
        document.documentElement.lang = currentLang === 'en' ? 'en' : 'zh-CN';
        document.querySelectorAll('[data-i18n]').forEach((el) => {
            const key = el.getAttribute('data-i18n');
            const val = t(key);
            if (val && val !== key) el.textContent = val;
        });
        document.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
            const key = el.getAttribute('data-i18n-placeholder');
            const val = t(key);
            if (val && val !== key) el.placeholder = val;
        });
        document.querySelectorAll('[data-i18n-title]').forEach((el) => {
            const key = el.getAttribute('data-i18n-title');
            const val = t(key);
            if (val && val !== key) el.title = val;
        });
        if (langLabel) langLabel.textContent = currentLang === 'en' ? 'English' : '中文';
        document.querySelectorAll('.lang-option').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.lang === currentLang);
        });
        updateThemeLabels();
        updateWorkspaceLabel();
        updatePermissionLabel();
        updateModelPickerLabel();
        renderConversationList(searchInput ? searchInput.value : '');
        if (statusDot && !statusDot.classList.contains('busy') && !statusDot.classList.contains('error')) {
            setStatus('idle', t('status.ready'));
        }
    }

    // ===== Models =====
    async function loadModels() {
        try {
            const data = await api('/api/models');
            models = data.models || [];
            if (!selectedModelId || !models.some((m) => m.id === selectedModelId)) {
                selectedModelId = data.default_model_id || (models[0] && models[0].id) || null;
                if (selectedModelId) localStorage.setItem('maxagent-model-id', selectedModelId);
            }
            updateModelPickerLabel();
            renderModelMenu();
            renderModelList();
        } catch (e) {
            console.error(e);
        }
    }

    function getSelectedModel() {
        return models.find((m) => m.id === selectedModelId) || models[0] || null;
    }

    function getModelContextSize() {
        const m = getSelectedModel();
        return (m && m.advanced && m.advanced.context_size) || 0;
    }

    async function updateContextIndicator() {
        const arc = $('context-progress-arc');
        const tooltip = $('context-tooltip-text');
        if (!arc || !tooltip) return;
        if (!currentConversationId) {
            arc.setAttribute('stroke-dashoffset', '94.2');
            tooltip.textContent = '0% 0K/0K ' + t('chat.context_used');
            return;
        }
        try {
            const data = await api('/api/chat/context-usage?conversation_id=' + encodeURIComponent(currentConversationId) + '&model_id=' + encodeURIComponent(selectedModelId || ''));
            const usedTokens = data.used_tokens || 0;
            const contextSize = data.context_size || 0;
            if (!contextSize) {
                arc.setAttribute('stroke-dashoffset', '94.2');
                tooltip.textContent = '-- ' + t('chat.context_na');
                return;
            }
            const pct = Math.min(100, Math.round((usedTokens / contextSize) * 100));
            const circumference = 94.2;
            const offset = circumference - (pct / 100) * circumference;
            arc.setAttribute('stroke-dashoffset', String(offset));
            const usedK = Math.round(usedTokens / 1000);
            const totalK = Math.round(contextSize / 1000);
            tooltip.textContent = pct + '% ' + usedK + 'K/' + totalK + 'K ' + t('chat.context_used');
        } catch (e) {
            console.error('获取上下文使用量失败:', e);
            arc.setAttribute('stroke-dashoffset', '94.2');
            tooltip.textContent = '-- ' + t('chat.context_na');
        }
    }

    function updateModelPickerLabel() {
        const m = getSelectedModel();
        const label = m ? (m.name || m.model_id || 'model') : '-';
        if (taskModelLabel) taskModelLabel.textContent = label;
        if (chatModelLabel) chatModelLabel.textContent = label;
    }

    function renderModelMenu() {
        const menus = [taskModelMenu, chatModelMenu].filter(Boolean);
        menus.forEach((menu) => {
            if (!models.length) {
                menu.innerHTML = `<div class="dropdown-item" style="cursor:default;opacity:.7">${t('settings.no_models')}</div>`;
                return;
            }
            menu.innerHTML = models.map((m) => `
                <button type="button" class="dropdown-item ${m.id === selectedModelId ? 'active' : ''}" data-model-id="${m.id}">
                    <span>${escapeHtml(m.name || m.model_id)}</span>
                    ${m.is_default ? `<span class="badge-default">${t('settings.default')}</span>` : ''}
                </button>
            `).join('');
            menu.querySelectorAll('[data-model-id]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    selectedModelId = btn.dataset.modelId;
                    localStorage.setItem('maxagent-model-id', selectedModelId);
                    updateModelPickerLabel();
                    updateContextIndicator();
                    closeAllDropdowns();
                });
            });
        });
    }

    function renderModelList() {
        if (!modelListEl) return;
        if (!models.length) {
            modelListEl.innerHTML = `<div class="settings-hint">${t('settings.no_models')}</div>`;
            return;
        }
        modelListEl.innerHTML = models.map((m) => `
            <div class="model-list-item" data-id="${m.id}">
                <div class="meta">
                    <div class="name">
                        ${escapeHtml(m.name || m.model_id || 'model')}
                        ${m.is_default ? `<span class="badge-default">${t('settings.default')}</span>` : ''}
                    </div>
                    <div class="sub">${escapeHtml(m.model_id || '')} · ${escapeHtml(m.api_endpoint || '')}</div>
                </div>
                <button type="button" class="model-edit-btn" data-edit-model="${m.id}" title="${t('settings.edit_model')}">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
                    </svg>
                </button>
            </div>
        `).join('');
        modelListEl.querySelectorAll('[data-edit-model]').forEach((btn) => {
            btn.addEventListener('click', () => openModelEdit(btn.dataset.editModel));
        });
    }

    // ===== Conversation =====
    async function loadConversations() {
        try {
            const data = await api('/api/conversations');
            conversations = data.conversations || [];
            renderConversationList(searchInput ? searchInput.value : '');
            await updateContextIndicator();
        } catch (e) {
            console.error('加载会话列表失败:', e);
        }
    }

    async function createConversation(title) {
        title = title || t('sidebar.new_task');
        try {
            const data = await api('/api/conversations/new', {
                method: 'POST',
                body: JSON.stringify({ title }),
            });
            conversations.unshift({
                id: data.conversation_id,
                title: data.title,
                preview: '',
                message_count: 0,
            });
            renderConversationList();
            return data.conversation_id;
        } catch (e) {
            console.error(e);
            showToast(e.message, true);
            return null;
        }
    }

    async function deleteConversation(id) {
        try {
            await api(`/api/conversations/${id}`, { method: 'DELETE' });
            conversations = conversations.filter((c) => c.id !== id);
            renderConversationList(searchInput ? searchInput.value : '');
            if (currentConversationId === id) {
                currentConversationId = null;
                if (conversations.length > 0) await switchToConversation(conversations[0].id);
                else showWelcome();
            }
        } catch (e) {
            showToast(e.message, true);
        }
    }

    async function loadMessages(conversationId) {
        try {
            const data = await api(`/api/conversations/${conversationId}`);
            return data.messages || [];
        } catch (e) {
            return [];
        }
    }

    // 全局 AbortController，用于中断流式请求
    let _streamAbortController = null;

    async function sendMessageStream(conversationId, message, modelId, callbacks) {
        const { onToken, onThinking, onToolCall, onToolResult, onDone } = callbacks;
        // 创建 AbortController
        _streamAbortController = new AbortController();
        const signal = _streamAbortController.signal;
        try {
            setStatus('busy', t('chat.thinking'));
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal,
                body: JSON.stringify({
                    conversation_id: conversationId,
                    message,
                    model_id: modelId || selectedModelId || null,
                }),
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({ detail: response.statusText }));
                onDone('', `${t('common.request_failed')}: ${err.detail}`);
                return;
            }
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let fullReply = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const dataStr = line.slice(6).trim();
                    if (!dataStr) continue;
                    try {
                        const event = JSON.parse(dataStr);
                        switch (event.type) {
                            case 'token':
                                fullReply += event.content;
                                onToken(event.content);
                                break;
                            case 'thinking':
                                onThinking(event.content);
                                break;
                            case 'tool_call':
                                onToolCall(event);
                                break;
                            case 'tool_result':
                                onToolResult(event);
                                break;
                            case 'done':
                                onDone(event.content, null);
                                return;
                            case 'error':
                                onDone('', event.content);
                                return;
                        }
                    } catch (e) { /* skip malformed JSON */ }
                }
            }
            onDone(fullReply, null);
        } catch (e) {
            if (e.name === 'AbortError') {
                onDone('', null);  // 用户主动停止，不报错
            } else {
                onDone('', `${t('common.request_failed')}: ${e.message}`);
            }
        } finally {
            _streamAbortController = null;
            setStatus('idle', t('status.ready'));
        }
    }

    function makeStreamCallbacks(messagesEl, onFinish) {
        // 创建公共的流式回调，用于 handleSend 和 submitNewTask
        let assistantBubble = null;
        let thinkingRow = null;
        let thinkingContentEl = null;
        return {
            onToken: (token) => {
                if (!assistantBubble) {
                    removeTyping();
                    // 思考结束，开始输出正式内容：停止 spinner，移除蓝色边框
                    const activeRow = thinkingRow || messagesEl.querySelector('.thinking-row .tool-row.thinking-active');
                    if (activeRow) {
                        const spinner = activeRow.querySelector('.thinking-spinner');
                        if (spinner) {
                            // 替换 spinner 为静态 SVG 图标
                            const iconSpan = spinner.parentElement;
                            spinner.remove();
                            iconSpan.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/></svg>`;
                        }
                        activeRow.classList.remove('thinking-active');
                    }
                    const div = document.createElement('div');
                    div.className = 'message assistant';
                    div.innerHTML = '<div class="bubble"></div>';
                    messagesEl.appendChild(div);
                    assistantBubble = div.querySelector('.bubble');
                    scrollToBottom();
                }
                assistantBubble.innerHTML = formatContent(assistantBubble.textContent + token);
                scrollToBottom();
            },
            onThinking: (content) => {
                removeTyping();
                if (!thinkingRow) {
                    const wrapper = document.createElement('div');
                    wrapper.className = 'thinking-row';
                    wrapper.innerHTML = `
                        <div class="tool-row thinking-active" data-expanded="true">
                            <div class="tool-row-header">
                                <span class="tool-row-icon">
                                    <span class="thinking-spinner"></span>
                                </span>
                                <span class="tool-row-title">${escapeHtml(t('tool.thinking'))}</span>
                                <span class="tool-row-arrow">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                        <polyline points="9 18 15 12 9 6"></polyline>
                                    </svg>
                                </span>
                            </div>
                            <div class="tool-row-details">
                                <pre class="tool-row-content"></pre>
                            </div>
                        </div>
                    `;
                    const toolRow = wrapper.querySelector('.tool-row');
                    thinkingContentEl = wrapper.querySelector('.tool-row-content');
                    // 点击头部切换展开/折叠 — 使用局部变量 toolRow 而非 thinkingRow
                    const header = toolRow.querySelector('.tool-row-header');
                    header.addEventListener('click', () => {
                        const expanded = toolRow.dataset.expanded === 'true';
                        toolRow.dataset.expanded = expanded ? 'false' : 'true';
                        const details = toolRow.querySelector('.tool-row-details');
                        if (details) details.hidden = expanded;
                    });
                    thinkingRow = toolRow;
                    messagesEl.appendChild(wrapper);
                    scrollToBottom();
                }
                thinkingContentEl.textContent += content;
                scrollToBottom();
            },
            onToolCall: (event) => {
                removeTyping();
                // 停止第一轮 thinking 的 spinner 并移除蓝色边框
                const prevThinking = thinkingRow || messagesEl.querySelector('.thinking-row .tool-row.thinking-active');
                if (prevThinking) {
                    const spinner = prevThinking.querySelector('.thinking-spinner');
                    if (spinner) {
                        const iconSpan = spinner.parentElement;
                        spinner.remove();
                        iconSpan.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/></svg>`;
                    }
                    prevThinking.classList.remove('thinking-active');
                }
                // 重置 thinkingRow 和 assistantBubble，让第二轮 thinking/token 创建新消息框
                thinkingRow = null;
                thinkingContentEl = null;
                assistantBubble = null;
                const row = createToolCallRow(event.name, event.args, event.id);
                messagesEl.appendChild(row);
                scrollToBottom();
            },
            onToolResult: (event) => {
                updateToolResult(messagesEl, event.id, event.content);
            },
            onDone: (reply, error) => {
                removeTyping();
                // 如果 thinking 行还在（没有 token 输出），停止 spinner 并移除蓝色边框
                const activeRow = thinkingRow || messagesEl.querySelector('.thinking-row .tool-row.thinking-active');
                if (activeRow) {
                    const spinner = activeRow.querySelector('.thinking-spinner');
                    if (spinner) {
                        const iconSpan = spinner.parentElement;
                        spinner.remove();
                        iconSpan.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/></svg>`;
                    }
                    activeRow.classList.remove('thinking-active');
                }
                if (error) {
                    appendMessage('assistant', error);
                } else if (!assistantBubble && reply) {
                    appendMessage('assistant', reply);
                }
                // 重置状态，为下一次消息做准备
                assistantBubble = null;
                thinkingRow = null;
                thinkingContentEl = null;
                if (onFinish) onFinish();
            },
        };
    }

    function renderConversationList(filter = '') {
        if (!conversationList) return;
        const filtered = filter
            ? conversations.filter((c) => (c.title || '').includes(filter))
            : conversations;
        if (filtered.length === 0) {
            conversationList.innerHTML = `
                <div class="empty-state" style="padding: 40px 16px; text-align: center;">
                    ${filter ? t('sidebar.no_match') : t('sidebar.no_conversations')}
                </div>`;
            return;
        }
        conversationList.innerHTML = filtered.map((c) => `
            <div class="conversation-item ${c.id === currentConversationId ? 'active' : ''}" data-id="${c.id}">
                <div class="conv-icon">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                    </svg>
                </div>
                <div class="conv-info">
                    <div class="conv-title">${escapeHtml(c.title)}</div>
                    <div class="conv-preview">${escapeHtml(c.preview || t('sidebar.no_messages'))}</div>
                </div>
                <button class="conv-delete" title="${t('sidebar.delete')}" data-id="${c.id}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `).join('');
        conversationList.querySelectorAll('.conversation-item').forEach((el) => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete')) return;
                switchToConversation(el.dataset.id);
            });
        });
        conversationList.querySelectorAll('.conv-delete').forEach((btn) => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const conv = conversations.find((c) => c.id === id);
                const msg = t('sidebar.confirm_delete').replace('{title}', conv ? conv.title : '');
                if (confirm(msg)) await deleteConversation(id);
            });
        });
    }

    function renderMessages(messages) {
        if (!messages || messages.length === 0) {
            messagesEl.innerHTML = `<div class="empty-state">${t('chat.start_chat')}</div>`;
            return;
        }
        // 建立 tool_call_id → tool 结果映射，并标记已合并的 tool 消息
        const toolResultsById = {};
        const mergedToolIds = new Set();
        messages.forEach((msg) => {
            if (msg.role === 'tool' && msg.tool_call_id) {
                toolResultsById[msg.tool_call_id] = msg.content;
            }
        });

        messagesEl.innerHTML = '';
        messages.forEach((msg) => {
            // assistant 消息含 thinking 内容（独立消息框）
            if (msg.role === 'assistant' && msg.thinking) {
                const wrapper = document.createElement('div');
                wrapper.className = 'thinking-row';
                wrapper.innerHTML = `
                    <div class="tool-row" data-expanded="true">
                        <div class="tool-row-header">
                            <span class="tool-row-icon">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/>
                                </svg>
                            </span>
                            <span class="tool-row-title">${escapeHtml(t('tool.thinking'))}</span>
                            <span class="tool-row-arrow">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <polyline points="9 18 15 12 9 6"></polyline>
                                </svg>
                            </span>
                        </div>
                        <div class="tool-row-details">
                            <pre class="tool-row-content">${escapeHtml(msg.thinking)}</pre>
                        </div>
                    </div>
                `;
                const thinkingRow = wrapper.querySelector('.tool-row');
                const header = thinkingRow.querySelector('.tool-row-header');
                header.addEventListener('click', () => {
                    const expanded = thinkingRow.dataset.expanded === 'true';
                    thinkingRow.dataset.expanded = expanded ? 'false' : 'true';
                    const details = thinkingRow.querySelector('.tool-row-details');
                    if (details) details.hidden = expanded;
                });
                messagesEl.appendChild(wrapper);
            }
            // 工具调用消息（assistant 含 tool_calls）— 每个 tool_call 独立消息框
            if (msg.role === 'assistant' && msg.tool_calls && msg.tool_calls.length > 0) {
                msg.tool_calls.forEach((tc) => {
                    const row = createToolCallRow(tc.name, tc.args, tc.id);
                    const result = toolResultsById[tc.id];
                    if (result !== undefined) {
                        const resultSection = row.querySelector('.tool-row-result-section');
                        const resultEl = row.querySelector('.tool-row-result');
                        if (resultSection) resultSection.style.display = '';
                        if (resultEl) resultEl.textContent = result;
                        mergedToolIds.add(tc.id);
                    }
                    messagesEl.appendChild(row);
                });
                // 不 return，继续渲染 content
            }
            // 跳过已被合并到 assistant 消息中的 tool 消息
            else if (msg.role === 'tool' && msg.tool_call_id && mergedToolIds.has(msg.tool_call_id)) {
                return;
            }
            // 孤立的 tool 角色消息（无对应 tool_call）— 仍单独渲染
            else if (msg.role === 'tool') {
                const row = createToolCallRow('tool_result', {}, '');
                const resultSection = row.querySelector('.tool-row-result-section');
                const resultEl = row.querySelector('.tool-row-result');
                if (resultSection) resultSection.style.display = '';
                if (resultEl) resultEl.textContent = msg.content;
                const titleEl = row.querySelector('.tool-row-title');
                if (titleEl) titleEl.textContent = t('tool.result');
                messagesEl.appendChild(row);
                return;
            }
            // 普通消息（assistant 的 content 单独渲染）
            if (msg.role === 'assistant' && msg.content) {
                const div = document.createElement('div');
                div.className = 'message assistant';
                div.innerHTML = `<div class="bubble">${formatContent(msg.content)}</div>`;
                messagesEl.appendChild(div);
            } else if (msg.role === 'user') {
                const div = document.createElement('div');
                div.className = 'message user';
                div.innerHTML = `<div class="bubble">${formatContent(msg.content)}</div>`;
                messagesEl.appendChild(div);
            }
        });
        scrollToBottom();
    }

    function appendMessage(role, content) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        // <div class="avatar">${role === 'user' ? 'U' : 'A'}</div>
        div.innerHTML = `
            <div class="bubble">${formatContent(content)}</div>`;
        messagesEl.appendChild(div);
        scrollToBottom();
    }

    function showTyping() {
        const div = document.createElement('div');
        div.className = 'message assistant';
        div.id = 'typing-indicator';
        div.innerHTML = `<div class="avatar">A</div><div class="bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
        messagesEl.appendChild(div);
        scrollToBottom();
    }
    function removeTyping() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }
    // 用户是否主动向上滚动（AI 回答时不自动滚到底部）
    let _userScrolledUp = false;

    function scrollToBottom() {
        // 如果用户主动向上滚动过，不自动滚动
        if (_userScrolledUp) return;
        setTimeout(() => { messagesEl.scrollTop = messagesEl.scrollHeight; }, 50);
    }

    // 监听滚动事件，判断用户是否在底部
    messagesEl.addEventListener('scroll', () => {
        const threshold = 50;  // 距离底部 50px 以内视为"在底部"
        const atBottom = messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < threshold;
        _userScrolledUp = !atBottom;
    });

    // ===== Skills =====
    async function loadSkills() {
        if (!panelSkills) return;
        try {
            const res = await fetch('/api/skills');
            const data = await res.json();
            const skills = data.skills || [];
            const inner = panelSkills.querySelector('.side-panel-inner');
            if (!inner) return;
            if (skills.length === 0) {
                inner.innerHTML = `<h2>${t('sidebar.skills')}</h2><p>${t('skills.select_hint')}</p>`;
                return;
            }
            inner.innerHTML = `
                <h2>${t('sidebar.skills')}</h2>
                <div class="skills-grid">${skills.map((s) => `
                    <div class="skill-card" data-skill="${escapeHtml(s.name)}">
                        <div class="skill-icon">${s.icon || '🧩'}</div>
                        <div class="skill-info">
                            <div class="skill-name">${escapeHtml(s.name)}</div>
                            <div class="skill-desc">${escapeHtml(s.description)}</div>
                        </div>
                        <div class="skill-category">${escapeHtml(s.category)}</div>
                    </div>
                `).join('')}</div>
                <p class="skills-hint">在聊天中输入 <code>/技能名</code> 调用技能</p>
            `;
        } catch (_) {
            const inner = panelSkills.querySelector('.side-panel-inner');
            if (inner) inner.innerHTML = `<h2>${t('sidebar.skills')}</h2><p>${t('common.request_failed')}</p>`;
        }
    }

    // ===== Views =====
    function hideAllMainViews() {
        if (welcome) welcome.style.display = 'none';
        if (chatArea) chatArea.style.display = 'none';
        if (newTaskPage) newTaskPage.style.display = 'none';
        if (panelSkills) panelSkills.style.display = 'none';
        if (panelAutomation) panelAutomation.style.display = 'none';
    }

    function setView(view) {
        currentView = view;
        hideAllMainViews();
        const isNewTask = view === 'new-task';
        const isSkills = view === 'skills';
        const isAuto = view === 'automation';
        const isWelcome = view === 'welcome';
        const isChat = view === 'chat';
        if (isNewTask && newTaskPage) newTaskPage.style.display = 'flex';
        else if (isSkills && panelSkills) panelSkills.style.display = 'flex';
        else if (isAuto && panelAutomation) panelAutomation.style.display = 'flex';
        else if (isWelcome && welcome) welcome.style.display = 'flex';
        else if (isChat && chatArea) chatArea.style.display = 'flex';
        if (newTaskBtn) newTaskBtn.classList.toggle('active', isNewTask);
        if (skillsBtn) skillsBtn.classList.toggle('active', isSkills);
        if (automationBtn) automationBtn.classList.toggle('active', isAuto);
    }

    function showWelcome() {
        currentConversationId = null;
        renderConversationList(searchInput ? searchInput.value : '');
        setView('welcome');
    }

    function showChatArea(title) {
        setView('chat');
        if (chatTitle) chatTitle.textContent = title;
    }

    function openNewTaskPage() {
        resetTaskComposer();
        loadModels();
        setView('new-task');
        currentConversationId = null;
        renderConversationList(searchInput ? searchInput.value : '');
        if (taskInput) setTimeout(() => taskInput.focus(), 50);
    }

    function closeNewTaskPage() {
        resetTaskComposer();
        if (conversations.length > 0) switchToConversation(conversations[0].id);
        else showWelcome();
    }

    function setStatus(state, text) {
        statusDot.className = 'status-dot';
        if (state === 'busy') statusDot.classList.add('busy');
        else if (state === 'error') statusDot.classList.add('error');
        statusText.textContent = text;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function formatContent(content) {
        if (!content) return '';
        let escaped = escapeHtml(content);
        escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        escaped = escaped.replace(/\n/g, '<br>');
        return escaped;
    }

    // ===== Task composer =====
    function resetTaskComposer() {
        taskAttachments = [];
        if (taskInput) {
            taskInput.value = '';
            taskInput.style.height = 'auto';
        }
        document.querySelectorAll('.capability-chip').forEach((c) => c.classList.remove('active'));
        renderTaskAttachments();
        updateTaskSendState();
        if (taskFileInput) taskFileInput.value = '';
        closeAllDropdowns();
    }

    function updateTaskSendState() {
        if (!taskSendBtn) return;
        const hasText = taskInput && taskInput.value.trim().length > 0;
        const hasFiles = taskAttachments.length > 0;
        taskSendBtn.disabled = !(hasText || hasFiles) || isLoading;
    }

    function renderTaskAttachments() {
        if (!taskAttachmentsEl) return;
        if (taskAttachments.length === 0) {
            taskAttachmentsEl.hidden = true;
            taskAttachmentsEl.innerHTML = '';
            return;
        }
        taskAttachmentsEl.hidden = false;
        taskAttachmentsEl.innerHTML = taskAttachments.map((a) => `
            <div class="task-attach-chip" data-id="${a.id}">
                <span class="name" title="${escapeHtml(a.name)}">${escapeHtml(a.name)}</span>
                <button type="button" class="remove-attach" data-id="${a.id}" aria-label="remove">×</button>
            </div>
        `).join('');
        taskAttachmentsEl.querySelectorAll('.remove-attach').forEach((btn) => {
            btn.addEventListener('click', () => {
                taskAttachments = taskAttachments.filter((x) => x.id !== btn.dataset.id);
                renderTaskAttachments();
                updateTaskSendState();
            });
        });
    }

    function addFilesToAttachments(fileList) {
        Array.from(fileList || []).forEach((file) => {
            taskAttachments.push({
                id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                name: file.name,
                type: file.type.startsWith('image/') ? 'image' : 'file',
                file,
            });
        });
        renderTaskAttachments();
        updateTaskSendState();
    }

    function buildTaskMessage(text) {
        // 首条用户消息只保留正文（及附件提示），不把 workspace/permission/model 元数据拼进对话
        const parts = [text.trim()];
        if (taskAttachments.length > 0) {
            parts.push(`[attachments: ${taskAttachments.map((a) => a.name).join(', ')}]`);
        }
        return parts.filter(Boolean).join('\n');
    }

    async function submitNewTask() {
        const text = taskInput ? taskInput.value.trim() : '';
        if (!text && taskAttachments.length === 0) {
            showToast(t('task.empty_task'), true);
            return;
        }
        if (isLoading) return;
        const title = (text || t('sidebar.new_task')).slice(0, 20);
        const message = buildTaskMessage(text || t('sidebar.new_task'));
        try {
            const id = await createConversation(title);
            if (!id) return;
            currentConversationId = id;
            showChatArea(title);
            messagesEl.innerHTML = '';
            appendMessage('user', message);
            showTyping();

            // 切换为停止按钮（对话页 sendBtn）
            setSendBtnToStop();
            updateTaskSendState();

            // 流式输出
            await new Promise((resolve) => {
                sendMessageStream(id, message, selectedModelId,
                    makeStreamCallbacks(messagesEl, () => {
                        setSendBtnToSend();
                        resolve();
                    })
                );
            });
            await loadConversations();
            const conv = conversations.find((c) => c.id === id);
            if (conv && chatTitle) chatTitle.textContent = conv.title;
            renderConversationList(searchInput ? searchInput.value : '');
            resetTaskComposer();
        } finally {
            isLoading = false;
            updateTaskSendState();
            setSendBtnToSend();
        }
    }

    function createToolCallRow(toolName, args, callId) {
        // 工具调用行：可折叠，默认合并状态
        // bash 工具特殊处理，标题显示为"运行命令"
        const isBash = toolName.toLowerCase() === 'bash';
        const title = isBash ? t('tool.running_command') : `${t('tool.calling')}:${toolName}`;

        const wrapper = document.createElement('div');
        wrapper.className = 'tool-row';
        wrapper.dataset.callId = callId || '';
        wrapper.dataset.expanded = 'false';

        // 头部：图标 + 标题 + 箭头
        const header = document.createElement('div');
        header.className = 'tool-row-header';
        header.innerHTML = `
            <span class="tool-row-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="4 17 10 11 4 5"></polyline>
                    <line x1="12" y1="19" x2="20" y2="19"></line>
                </svg>
            </span>
            <span class="tool-row-title">${escapeHtml(title)}</span>
            <span class="tool-row-arrow">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"></polyline>
                </svg>
            </span>
        `;

        // 详情：参数 + 结果
        const details = document.createElement('div');
        details.className = 'tool-row-details';
        details.hidden = true;
        details.innerHTML = `
            <div class="tool-row-section">
                <div class="tool-row-label">${t('tool.arguments')}</div>
                <pre class="tool-row-args">${escapeHtml(JSON.stringify(args, null, 2))}</pre>
            </div>
            <div class="tool-row-section tool-row-result-section" style="display:none;">
                <div class="tool-row-label">${t('tool.result')}</div>
                <pre class="tool-row-result"></pre>
            </div>
        `;

        header.addEventListener('click', () => {
            const expanded = wrapper.dataset.expanded === 'true';
            wrapper.dataset.expanded = expanded ? 'false' : 'true';
            details.hidden = expanded;
        });

        wrapper.appendChild(header);
        wrapper.appendChild(details);

        // 包裹在 message assistant 中以保持消息布局一致
        const msg = document.createElement('div');
        msg.className = 'message assistant tool-message';
        msg.appendChild(wrapper);
        return msg;
    }

    function updateToolResult(messagesEl, callId, content) {
        const row = messagesEl.querySelector(`.tool-row[data-call-id="${callId}"]`);
        if (!row) return;
        const resultSection = row.querySelector('.tool-row-result-section');
        const resultEl = row.querySelector('.tool-row-result');
        if (resultSection && resultEl) {
            resultSection.style.display = '';
            resultEl.textContent = content;
        }
    }

    async function switchToConversation(id) {
        if (isLoading) return;
        isLoading = true;
        currentConversationId = id;
        renderConversationList(searchInput ? searchInput.value : '');
        const conv = conversations.find((c) => c.id === id);
        showChatArea(conv ? conv.title : t('sidebar.new_task'));
        messagesEl.innerHTML = `<div class="empty-state">${t('common.loading')}</div>`;
        const messages = await loadMessages(id);
        renderMessages(messages);
        isLoading = false;
        sendBtn.disabled = !messageInput.value.trim() || !currentConversationId;
        await updateContextIndicator();
    }

    async function handleSend() {
        const text = messageInput.value.trim();
        if (!text || !currentConversationId || isLoading) return;
        messageInput.value = '';
        messageInput.style.height = 'auto';
        appendMessage('user', text);
        showTyping();

        // 切换为停止按钮
        setSendBtnToStop();

        sendMessageStream(currentConversationId, text, selectedModelId,
            makeStreamCallbacks(messagesEl, () => {
                // 恢复为发送按钮
                setSendBtnToSend();
                loadConversations();
                const conv = conversations.find((c) => c.id === currentConversationId);
                if (conv) chatTitle.textContent = conv.title;
                renderConversationList(searchInput ? searchInput.value : '');
                updateContextIndicator();
            })
        );
    }

    function setSendBtnToStop() {
        isLoading = true;
        sendBtn.disabled = false;
        sendBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`;
        sendBtn.classList.add('stop');
        // 停止按钮点击时中断流式请求
        sendBtn.onclick = (e) => {
            e.preventDefault();
            if (_streamAbortController) {
                _streamAbortController.abort();
            }
            setSendBtnToSend();
        };
    }

    function setSendBtnToSend() {
        isLoading = false;
        sendBtn.disabled = !messageInput.value.trim() || !currentConversationId;
        sendBtn.innerHTML = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
        sendBtn.classList.remove('stop');
        // 恢复为发送按钮的点击事件
        sendBtn.onclick = handleSend;
    }

    // ===== Dropdowns =====
    function closeAllDropdowns() {
        [taskPlusMenu, taskModelMenu, chatModelMenu, workspaceMenu, permissionMenu].forEach((el) => {
            if (el) el.hidden = true;
        });
        [taskPlusBtn, taskModelBtn, chatModelBtn, workspaceBtn, permissionBtn].forEach((el) => {
            if (el) el.classList.remove('open');
        });
    }

    function toggleDropdown(btn, menu) {
        const willOpen = menu.hidden;
        closeAllDropdowns();
        if (willOpen) {
            menu.hidden = false;
            btn.classList.add('open');
        }
    }

    function updateWorkspaceLabel() {
        if (!workspaceLabel) return;
        workspaceLabel.textContent = workspaceMode === 'none'
            ? t('task.ws_none')
            : t('task.ws_select');
    }

    function updatePermissionLabel() {
        if (!permissionLabel) return;
        permissionLabel.textContent = permissionMode === 'full'
            ? t('task.perm_full')
            : t('task.perm_default');
    }

    // ===== User menu / settings =====
    function openUserMenu() {
        userMenu.hidden = false;
        userBar.classList.add('open');
        userBar.setAttribute('aria-expanded', 'true');
    }
    function closeUserMenu() {
        userMenu.hidden = true;
        userBar.classList.remove('open');
        userBar.setAttribute('aria-expanded', 'false');
        const submenu = userMenu.querySelector('.has-submenu');
        if (submenu) submenu.classList.remove('open');
    }
    function toggleUserMenu() {
        if (userMenu.hidden) openUserMenu();
        else closeUserMenu();
    }

    async function openHomeDir() {
        try {
            const data = await api('/api/open-home', { method: 'POST' });
            showToast(data.path ? `${t('sidebar.open_home')}: ${data.path}` : t('sidebar.open_home_ok'));
        } catch (e) {
            showToast(e.message || t('sidebar.open_home_failed'), true);
        }
    }

    function showSettingsTab(tab) {
        settingsTab = tab;
        document.querySelectorAll('.settings-nav-item').forEach((el) => {
            el.classList.toggle('active', el.dataset.settingsTab === tab);
        });
        const map = {
            system: 'settings-panel-system',
            memory: 'settings-panel-memory',
            models: 'settings-panel-models',
            'model-edit': 'settings-panel-model-edit',
        };
        Object.entries(map).forEach(([key, id]) => {
            const panel = $(id);
            if (panel) panel.hidden = key !== tab;
        });
        // 导航高亮：编辑页时仍高亮模型
        if (tab === 'model-edit') {
            document.querySelectorAll('.settings-nav-item').forEach((el) => {
                el.classList.toggle('active', el.dataset.settingsTab === 'models');
            });
        }
    }

    async function loadSettingsSummary() {
        try {
            const data = await api('/api/config');
            if (settingsModel) settingsModel.textContent = data.model_name || '-';
            if (settingsEndpoint) settingsEndpoint.textContent = data.api_endpoint || '-';
        } catch (e) {
            if (settingsModel) settingsModel.textContent = '-';
            if (settingsEndpoint) settingsEndpoint.textContent = '-';
        }
        updateThemeLabels();
    }

    function openSettings(tab = 'system') {
        closeUserMenu();
        settingsModal.hidden = false;
        showSettingsTab(tab);
        loadSettingsSummary();
        if (tab === 'models' || tab === 'model-edit') loadModels();
    }

    function closeSettings() {
        settingsModal.hidden = true;
        editingModelId = null;
    }

    // 模型高级配置：与后端字段一一对应；档位顺序与 UI 渲染强绑定
    const THINKING_LEVELS = ['high', 'max'];
    const ADV_FIELDS = [
        'model-adv-tool',
        'model-adv-image',
        'model-adv-thinking',
        'model-adv-thinking-only',
        'model-adv-allow-disable',
    ];

    function resetAdvancedForm() {
        ADV_FIELDS.forEach((id) => {
            const el = $(id);
            if (el) el.checked = false;
        });
        // 渲染默认思考强度下拉
        const sel = $('model-adv-default-intensity');
        if (sel) {
            sel.innerHTML = THINKING_LEVELS.map(
                (lv) => `<option value="${lv}">${lv}</option>`
            ).join('');
            sel.value = 'high';
        }
        // 渲染支持的思考强度（单选 radio）
        const wrap = $('model-adv-supported-wrap');
        if (wrap) {
            wrap.innerHTML = THINKING_LEVELS.map(
                (lv) => `<label class="form-check"><input type="radio" name="model-adv-supported" value="${lv}"><span>${lv}</span></label>`
            ).join('');
            // 默认选中第一项
            const first = wrap.querySelector('input[type=radio]');
            if (first) first.checked = true;
        }
        const inEl = $('model-adv-input');
        const outEl = $('model-adv-output');
        if (inEl) inEl.value = '';
        if (outEl) outEl.value = '';
        syncThinkingVisibility();
    }

    // "默认/支持的思考强度"两项只在勾选"思考模式"时显示
    function syncThinkingVisibility() {
        const thinkingOn = !!$('model-adv-thinking')?.checked;
        const a = $('model-adv-intensity-group');
        const b = $('model-adv-supported-group');
        if (a) a.style.display = thinkingOn ? '' : 'none';
        if (b) b.style.display = thinkingOn ? '' : 'none';
    }

    function fillAdvancedForm(adv) {
        const a = adv || {};
        const map = {
            'model-adv-tool': a.tool_calling,
            'model-adv-image': a.image_input,
            'model-adv-thinking': a.thinking_mode,
            'model-adv-thinking-only': a.thinking_only,
            'model-adv-allow-disable': a.allow_disable_thinking,
        };
        Object.keys(map).forEach((id) => {
            const el = $(id);
            if (el) el.checked = !!map[id];
        });
        const sel = $('model-adv-default-intensity');
        if (sel) {
            sel.value = THINKING_LEVELS.includes(a.default_thinking_intensity)
                ? a.default_thinking_intensity
                : 'high';
        }
        const wrap = $('model-adv-supported-wrap');
        if (wrap) {
            const supported = Array.isArray(a.supported_thinking_intensities)
                ? a.supported_thinking_intensities
                : ['high'];
            const targetVal = supported.length > 0 ? supported[0] : 'high';
            const radio = wrap.querySelector(`input[type=radio][value="${targetVal}"]`);
            if (radio) radio.checked = true;
        }
        const ctxEl = $('model-adv-context');
        if (ctxEl) ctxEl.value = a.context_size || '';
        syncThinkingVisibility();
    }

    function readAdvancedForm() {
        const thinkingOn = !!$('model-adv-thinking')?.checked;
        let supported = [];
        if (thinkingOn) {
            const checked = document.querySelector('#model-adv-supported-wrap input[type=radio]:checked');
            supported = checked ? [checked.value] : ['high'];
        }
        const ctxEl = $('model-adv-context');
        return {
            tool_calling: !!$('model-adv-tool')?.checked,
            image_input: !!$('model-adv-image')?.checked,
            thinking_mode: thinkingOn,
            thinking_only: !!$('model-adv-thinking-only')?.checked,
            allow_disable_thinking: !!$('model-adv-allow-disable')?.checked,
            default_thinking_intensity: thinkingOn
                ? ($('model-adv-default-intensity')?.value || 'high')
                : '',
            supported_thinking_intensities: supported,
            context_size: Number(ctxEl?.value || 0),
        };
    }

    function openModelEdit(modelUid) {
        editingModelId = modelUid || null;
        showSettingsTab('model-edit');
        const title = $('model-edit-title');
        const delBtn = $('model-edit-delete');
        if (title) title.textContent = modelUid ? t('settings.edit_model') : t('settings.add_model');
        if (delBtn) delBtn.hidden = !modelUid;
        $('model-edit-id').value = modelUid || '';
        $('model-edit-name').value = '';
        $('model-edit-endpoint').value = '';
        $('model-edit-key').value = '';
        $('model-edit-key').placeholder = modelUid ? t('settings.key_keep') : '';
        $('model-edit-modelid').value = '';
        $('model-edit-default').checked = false;
        resetAdvancedForm();

        if (!modelUid) return;
        const m = models.find((x) => x.id === modelUid);
        if (m) {
            $('model-edit-name').value = m.name || '';
            $('model-edit-endpoint').value = m.api_endpoint || '';
            $('model-edit-modelid').value = m.model_id || '';
            $('model-edit-default').checked = !!m.is_default;
            if (m.has_api_key) $('model-edit-key').placeholder = t('settings.key_keep');
            fillAdvancedForm(m.advanced);
        }
    }

    async function saveModelForm(e) {
        e.preventDefault();
        const id = $('model-edit-id').value;
        const payload = {
            name: $('model-edit-name').value.trim(),
            api_endpoint: $('model-edit-endpoint').value.trim(),
            model_id: $('model-edit-modelid').value.trim(),
            set_default: $('model-edit-default').checked,
            advanced: readAdvancedForm(),
        };
        const key = $('model-edit-key').value;
        if (key) payload.api_key = key;
        if (!payload.api_endpoint || !payload.model_id) {
            showToast(t('settings.required_fields'), true);
            return;
        }
        try {
            if (id) {
                await api(`/api/models/${id}`, { method: 'PUT', body: JSON.stringify(payload) });
            } else {
                if (!payload.api_key) payload.api_key = '';
                await api('/api/models', { method: 'POST', body: JSON.stringify(payload) });
            }
            showToast(t('settings.saved'));
            await loadModels();
            await loadSettingsSummary();
            showSettingsTab('models');
        } catch (err) {
            showToast(err.message, true);
        }
    }

    async function deleteCurrentModel() {
        const id = $('model-edit-id').value;
        if (!id) return;
        if (!confirm(t('settings.confirm_delete_model'))) return;
        try {
            await api(`/api/models/${id}`, { method: 'DELETE' });
            if (selectedModelId === id) {
                selectedModelId = null;
                localStorage.removeItem('maxagent-model-id');
            }
            await loadModels();
            showSettingsTab('models');
            showToast(t('settings.deleted'));
        } catch (err) {
            showToast(err.message, true);
        }
    }

    // ===== Events =====
    if (newTaskBtn) newTaskBtn.addEventListener('click', () => { closeUserMenu(); openNewTaskPage(); });
    if (welcomeNewTaskBtn) welcomeNewTaskBtn.addEventListener('click', () => openNewTaskPage());
    if (closeNewTaskBtn) closeNewTaskBtn.addEventListener('click', () => closeNewTaskPage());

    if (taskInput) {
        taskInput.addEventListener('input', () => {
            taskInput.style.height = 'auto';
            taskInput.style.height = Math.min(taskInput.scrollHeight, 280) + 'px';
            updateTaskSendState();
        });
        taskInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitNewTask();
            }
        });
    }
    if (taskSendBtn) taskSendBtn.addEventListener('click', () => submitNewTask());

    // capability chips
    document.querySelectorAll('.capability-chip[data-prompt]').forEach((chip) => {
        chip.addEventListener('click', () => {
            document.querySelectorAll('.capability-chip').forEach((c) => c.classList.remove('active'));
            chip.classList.add('active');
            const prompt = chip.dataset.prompt || '';
            if (taskInput) {
                if (!taskInput.value.trim()) taskInput.value = prompt;
                else if (!taskInput.value.includes(prompt.trim())) {
                    taskInput.value = prompt + taskInput.value;
                }
                taskInput.focus();
                updateTaskSendState();
            }
        });
    });
    const moreBtn = $('capability-more-btn');
    if (moreBtn) {
        moreBtn.addEventListener('click', () => showToast(t('task.more_todo')));
    }

    // plus menu
    if (taskPlusBtn && taskPlusMenu) {
        taskPlusBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDropdown(taskPlusBtn, taskPlusMenu);
        });
        taskPlusMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            const item = e.target.closest('[data-plus]');
            if (!item) return;
            const action = item.dataset.plus;
            closeAllDropdowns();
            if (action === 'file') {
                if (taskFileInput) taskFileInput.click();
            } else if (action === 'ref') {
                showToast(t('task.ref_todo'));
            } else if (action === 'skill') {
                setView('skills');
            } else if (action === 'mcp') {
                showToast(t('task.mcp_todo'));
            }
        });
    }
    if (taskFileInput) {
        taskFileInput.addEventListener('change', () => {
            addFilesToAttachments(taskFileInput.files);
            taskFileInput.value = '';
        });
    }

    // model picker
    if (taskModelBtn && taskModelMenu) {
        taskModelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            renderModelMenu();
            toggleDropdown(taskModelBtn, taskModelMenu);
        });
        taskModelMenu.addEventListener('click', (e) => e.stopPropagation());
    }
    if (chatModelBtn && chatModelMenu) {
        chatModelBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            renderModelMenu();
            toggleDropdown(chatModelBtn, chatModelMenu);
        });
        chatModelMenu.addEventListener('click', (e) => e.stopPropagation());
    }

    // workspace / permission
    if (workspaceBtn && workspaceMenu) {
        workspaceBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDropdown(workspaceBtn, workspaceMenu);
        });
        workspaceMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            const item = e.target.closest('[data-workspace]');
            if (!item) return;
            workspaceMode = item.dataset.workspace;
            localStorage.setItem('maxagent-workspace', workspaceMode);
            updateWorkspaceLabel();
            closeAllDropdowns();
        });
    }
    if (permissionBtn && permissionMenu) {
        permissionBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleDropdown(permissionBtn, permissionMenu);
        });
        permissionMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            const item = e.target.closest('[data-permission]');
            if (!item) return;
            permissionMode = item.dataset.permission;
            localStorage.setItem('maxagent-permission', permissionMode);
            updatePermissionLabel();
            closeAllDropdowns();
        });
    }

    if (newTaskPage) {
        newTaskPage.addEventListener('dragover', (e) => e.preventDefault());
        newTaskPage.addEventListener('drop', (e) => {
            e.preventDefault();
            if (e.dataTransfer && e.dataTransfer.files.length) {
                addFilesToAttachments(e.dataTransfer.files);
            }
        });
    }

    if (skillsBtn) skillsBtn.addEventListener('click', () => { setView('skills'); closeUserMenu(); loadSkills(); });
    if (automationBtn) automationBtn.addEventListener('click', () => { setView('automation'); closeUserMenu(); });

    if (userBar) {
        userBar.addEventListener('click', (e) => {
            e.stopPropagation();
            toggleUserMenu();
        });
    }
    if (userMenu) {
        userMenu.addEventListener('click', (e) => {
            e.stopPropagation();
            const item = e.target.closest('[data-action]');
            if (!item) return;
            const action = item.dataset.action;
            if (action === 'settings') openSettings('system');
            else if (action === 'appearance') toggleTheme();
            else if (action === 'language') {
                if (!e.target.closest('.lang-option')) item.classList.toggle('open');
            } else if (action === 'open-home') {
                closeUserMenu();
                openHomeDir();
            }
        });
    }

    document.addEventListener('click', (e) => {
        if (!userMenu.hidden && !e.target.closest('.user-bar-wrap')) closeUserMenu();
        if (!e.target.closest('.plus-menu-wrap') && !e.target.closest('.model-picker-wrap') && !e.target.closest('.config-dropdown-wrap')) {
            closeAllDropdowns();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeUserMenu();
            closeSettings();
            closeAllDropdowns();
            if (currentView === 'new-task') closeNewTaskPage();
        }
    });

    document.querySelectorAll('.lang-option').forEach((btn) => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const lang = btn.dataset.lang;
            if (lang) {
                setLang(lang);
                localStorage.setItem('maxagent-lang', lang);
                applyI18n();
                closeUserMenu();
            }
        });
    });

    if (settingsThemeBtn) settingsThemeBtn.addEventListener('click', () => toggleTheme());
    document.querySelectorAll('[data-close-modal]').forEach((el) => {
        el.addEventListener('click', closeSettings);
    });
    document.querySelectorAll('[data-settings-tab]').forEach((btn) => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.settingsTab;
            showSettingsTab(tab);
            if (tab === 'models') loadModels();
            if (tab === 'system') loadSettingsSummary();
        });
    });
    const modelAddBtn = $('model-add-btn');
    if (modelAddBtn) modelAddBtn.addEventListener('click', () => openModelEdit(null));
    const modelEditBack = $('model-edit-back');
    if (modelEditBack) modelEditBack.addEventListener('click', () => showSettingsTab('models'));
    const modelEditForm = $('model-edit-form');
    if (modelEditForm) modelEditForm.addEventListener('submit', saveModelForm);
    const modelEditDelete = $('model-edit-delete');
    if (modelEditDelete) modelEditDelete.addEventListener('click', deleteCurrentModel);
    // 勾选"思考模式"时联动显示/隐藏强度配置
    const advThinking = $('model-adv-thinking');
    if (advThinking) advThinking.addEventListener('change', syncThinkingVisibility);
    // K 快捷值（输入/输出 token 长度）
    document.querySelectorAll('.quick-values').forEach((box) => {
        const targetId = box.dataset.target;
        const mult = Number(box.dataset.multiplier || 1024);
        const target = targetId ? $(targetId) : null;
        if (!target) return;
        box.querySelectorAll('button[data-val]').forEach((btn) => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                const v = Number(btn.dataset.val || 0) * mult;
                target.value = String(v);
            });
        });
    });
    // 首次加载时把高级配置的"档位选项"渲染好（解决新建模型打开表单时未渲染的问题）
    resetAdvancedForm();
    const openMemoryBtn = $('open-memory-btn');
    if (openMemoryBtn) openMemoryBtn.addEventListener('click', openHomeDir);

    // sendBtn 使用 onclick 属性动态切换（发送/停止），不再用 addEventListener
    sendBtn.onclick = handleSend;

    // context indicator
    const contextIndicator = $('context-indicator');
    const contextTooltip = $('context-tooltip');
    if (contextIndicator && contextTooltip) {
        contextIndicator.addEventListener('mouseenter', () => { contextTooltip.hidden = false; });
        contextIndicator.addEventListener('mouseleave', () => { contextTooltip.hidden = true; });
    }
    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 200) + 'px';
        sendBtn.disabled = !messageInput.value.trim() || !currentConversationId;
    });
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });
    searchInput.addEventListener('input', () => renderConversationList(searchInput.value));
    window.addEventListener('language-changed', applyI18n);

    // ===== Init =====
    async function init() {
        const savedLang = localStorage.getItem('maxagent-lang');
        if (savedLang) setLang(savedLang);
        applyTheme(theme);
        applyI18n();
        setStatus('idle', t('status.ready'));
        updateWorkspaceLabel();
        updatePermissionLabel();
        await loadModels();
        await loadConversations();
        if (conversations.length > 0) await switchToConversation(conversations[0].id);
        else showWelcome();
        // 启动热更新轮询
        startHotReload();
    }

    // ===== Hot Reload =====
    let _reloadVersion = parseInt(localStorage.getItem('maxagent-reload-v') || '0', 10);

    function startHotReload() {
        setInterval(async () => {
            try {
                const res = await fetch('/api/poll-reload');
                const data = await res.json();
                if (data.reload) {
                    _reloadVersion++;
                    localStorage.setItem('maxagent-reload-v', String(_reloadVersion));
                    // 加时间戳强制刷新静态资源缓存
                    const links = document.querySelectorAll('link[rel=stylesheet]');
                    links.forEach((el) => {
                        const href = el.getAttribute('href') || '';
                        el.setAttribute('href', href.replace(/\?v=[^&]*|$/, `?v=${_reloadVersion}`));
                    });
                    location.reload();
                }
            } catch (_) {}
        }, 1000);
    }

    init();
})();
