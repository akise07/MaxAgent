// MaxAgent Frontend App
(function() {
    'use strict';

    // ===== State =====
    let currentConversationId = null;
    let conversations = [];
    let isLoading = false;
    let currentView = 'chat'; // chat | skills | automation
    let theme = localStorage.getItem('maxagent-theme') || 'dark';

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
        return response.json();
    }

    // ===== Toast =====
    let toastTimer = null;
    function showToast(msg, isError = false) {
        toastEl.textContent = msg;
        toastEl.classList.toggle('error', !!isError);
        toastEl.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => {
            toastEl.hidden = true;
        }, 2600);
    }

    // ===== Theme =====
    function applyTheme(next) {
        theme = next === 'light' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('maxagent-theme', theme);
        updateThemeLabels();
    }

    function toggleTheme() {
        applyTheme(theme === 'dark' ? 'light' : 'dark');
    }

    function updateThemeLabels() {
        const label = theme === 'light' ? t('sidebar.theme_light') : t('sidebar.theme_dark');
        if (themeLabel) themeLabel.textContent = label;
        if (settingsThemeBtn) {
            settingsThemeBtn.textContent = theme === 'light'
                ? t('sidebar.switch_to_dark')
                : t('sidebar.switch_to_light');
        }
    }

    // ===== i18n apply =====
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
        if (langLabel) {
            langLabel.textContent = currentLang === 'en' ? 'English' : '中文';
        }
        document.querySelectorAll('.lang-option').forEach((btn) => {
            btn.classList.toggle('active', btn.dataset.lang === currentLang);
        });
        updateThemeLabels();
        // re-render dynamic lists so empty states use current language
        renderConversationList(searchInput ? searchInput.value : '');
        if (statusDot && !statusDot.classList.contains('busy') && !statusDot.classList.contains('error')) {
            setStatus('idle', t('status.ready'));
        }
    }

    // ===== Conversation Management =====
    async function loadConversations() {
        try {
            const data = await api('/api/conversations');
            conversations = data.conversations || [];
            renderConversationList(searchInput ? searchInput.value : '');
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
            switchToConversation(data.conversation_id);
            return data.conversation_id;
        } catch (e) {
            console.error('创建会话失败:', e);
            showToast(e.message, true);
        }
    }

    async function deleteConversation(id) {
        try {
            await api(`/api/conversations/${id}`, { method: 'DELETE' });
            conversations = conversations.filter(c => c.id !== id);
            renderConversationList(searchInput ? searchInput.value : '');
            if (currentConversationId === id) {
                currentConversationId = null;
                if (conversations.length > 0) {
                    await switchToConversation(conversations[0].id);
                } else {
                    showWelcome();
                }
            }
        } catch (e) {
            console.error('删除会话失败:', e);
            showToast(e.message, true);
        }
    }

    async function loadMessages(conversationId) {
        try {
            const data = await api(`/api/conversations/${conversationId}`);
            return data.messages || [];
        } catch (e) {
            console.error('加载消息失败:', e);
            return [];
        }
    }

    async function sendMessage(conversationId, message) {
        try {
            setStatus('busy', t('chat.thinking'));
            const data = await api('/api/chat', {
                method: 'POST',
                body: JSON.stringify({ conversation_id: conversationId, message }),
            });
            return data.reply;
        } catch (e) {
            console.error('发送消息失败:', e);
            return `${t('common.request_failed')}: ${e.message}`;
        } finally {
            setStatus('idle', t('status.ready'));
        }
    }

    // ===== Rendering =====
    function renderConversationList(filter = '') {
        if (!conversationList) return;
        const filtered = filter
            ? conversations.filter(c => (c.title || '').includes(filter))
            : conversations;

        if (filtered.length === 0) {
            conversationList.innerHTML = `
                <div class="empty-state" style="padding: 40px 16px; text-align: center;">
                    ${filter ? t('sidebar.no_match') : t('sidebar.no_conversations')}
                </div>
            `;
            return;
        }

        conversationList.innerHTML = filtered.map(c => `
            <div class="conversation-item ${c.id === currentConversationId ? 'active' : ''}"
                 data-id="${c.id}">
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

        conversationList.querySelectorAll('.conversation-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete')) return;
                const id = el.dataset.id;
                setView('chat');
                switchToConversation(id);
            });
        });

        conversationList.querySelectorAll('.conv-delete').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const conv = conversations.find(c => c.id === id);
                const title = conv ? conv.title : '';
                const msg = t('sidebar.confirm_delete').replace('{title}', title);
                if (confirm(msg)) {
                    await deleteConversation(id);
                }
            });
        });
    }

    function renderMessages(messages) {
        if (!messages || messages.length === 0) {
            messagesEl.innerHTML = `<div class="empty-state">${t('chat.start_chat')}</div>`;
            return;
        }

        messagesEl.innerHTML = messages.map((msg) => `
            <div class="message ${msg.role}">
                <div class="avatar">
                    ${msg.role === 'user' ? 'U' : 'A'}
                </div>
                <div class="bubble">${formatContent(msg.content)}</div>
            </div>
        `).join('');

        scrollToBottom();
    }

    function appendMessage(role, content) {
        const div = document.createElement('div');
        div.className = `message ${role}`;
        div.innerHTML = `
            <div class="avatar">${role === 'user' ? 'U' : 'A'}</div>
            <div class="bubble">${formatContent(content)}</div>
        `;
        messagesEl.appendChild(div);
        scrollToBottom();
    }

    function showTyping() {
        const div = document.createElement('div');
        div.className = 'message assistant';
        div.id = 'typing-indicator';
        div.innerHTML = `
            <div class="avatar">A</div>
            <div class="bubble">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        messagesEl.appendChild(div);
        scrollToBottom();
    }

    function removeTyping() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    function scrollToBottom() {
        setTimeout(() => {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }, 50);
    }

    // ===== View switching =====
    function setView(view) {
        currentView = view;
        const isChat = view === 'chat';
        const isSkills = view === 'skills';
        const isAuto = view === 'automation';

        if (panelSkills) panelSkills.style.display = isSkills ? 'flex' : 'none';
        if (panelAutomation) panelAutomation.style.display = isAuto ? 'flex' : 'none';

        if (isChat) {
            // restore chat or welcome based on current conversation
            if (currentConversationId) {
                welcome.style.display = 'none';
                chatArea.style.display = 'flex';
            } else {
                welcome.style.display = 'flex';
                chatArea.style.display = 'none';
            }
        } else {
            welcome.style.display = 'none';
            chatArea.style.display = 'none';
        }

        if (newTaskBtn) newTaskBtn.classList.toggle('active', isChat);
        if (skillsBtn) skillsBtn.classList.toggle('active', isSkills);
        if (automationBtn) automationBtn.classList.toggle('active', isAuto);
    }

    // ===== UI Helpers =====
    function showWelcome() {
        setView('chat');
        welcome.style.display = 'flex';
        chatArea.style.display = 'none';
    }

    function showChatArea(title) {
        setView('chat');
        welcome.style.display = 'none';
        chatArea.style.display = 'flex';
        chatTitle.textContent = title;
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

    // ===== Conversation Switching =====
    async function switchToConversation(id) {
        if (isLoading) return;
        isLoading = true;

        currentConversationId = id;
        renderConversationList(searchInput ? searchInput.value : '');

        const conv = conversations.find(c => c.id === id);
        showChatArea(conv ? conv.title : t('sidebar.new_task'));

        messagesEl.innerHTML = `<div class="empty-state">${t('common.loading')}</div>`;

        const messages = await loadMessages(id);
        renderMessages(messages);

        isLoading = false;
        sendBtn.disabled = !messageInput.value.trim() || !currentConversationId;
    }

    // ===== Send Message =====
    async function handleSend() {
        const text = messageInput.value.trim();
        if (!text || !currentConversationId || isLoading) return;

        messageInput.value = '';
        sendBtn.disabled = true;
        messageInput.style.height = 'auto';

        appendMessage('user', text);
        showTyping();

        const reply = await sendMessage(currentConversationId, text);

        removeTyping();
        appendMessage('assistant', reply);

        await loadConversations();
        const conv = conversations.find(c => c.id === currentConversationId);
        if (conv) {
            chatTitle.textContent = conv.title;
        }
        renderConversationList(searchInput ? searchInput.value : '');
    }

    // ===== User menu =====
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
            console.error(e);
            showToast(e.message || t('sidebar.open_home_failed'), true);
        }
    }

    async function loadSettings() {
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

    function openSettings() {
        closeUserMenu();
        settingsModal.hidden = false;
        loadSettings();
    }

    function closeSettings() {
        settingsModal.hidden = true;
    }

    // ===== Event Listeners =====
    if (newTaskBtn) {
        newTaskBtn.addEventListener('click', () => {
            setView('chat');
            createConversation();
        });
    }

    if (skillsBtn) {
        skillsBtn.addEventListener('click', () => {
            setView('skills');
            closeUserMenu();
        });
    }

    if (automationBtn) {
        automationBtn.addEventListener('click', () => {
            setView('automation');
            closeUserMenu();
        });
    }

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

            if (action === 'settings') {
                openSettings();
            } else if (action === 'appearance') {
                toggleTheme();
            } else if (action === 'language') {
                // 点击语言行本身时展开/收起子菜单（点语言选项由下方单独处理）
                if (!e.target.closest('.lang-option')) {
                    item.classList.toggle('open');
                }
            } else if (action === 'open-home') {
                closeUserMenu();
                openHomeDir();
            }
        });
    }

    document.addEventListener('click', (e) => {
        if (!userMenu.hidden && !e.target.closest('.user-bar-wrap')) {
            closeUserMenu();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeUserMenu();
            closeSettings();
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

    if (settingsThemeBtn) {
        settingsThemeBtn.addEventListener('click', () => toggleTheme());
    }

    document.querySelectorAll('[data-close-modal]').forEach((el) => {
        el.addEventListener('click', closeSettings);
    });

    sendBtn.addEventListener('click', handleSend);

    messageInput.addEventListener('input', () => {
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
        sendBtn.disabled = !messageInput.value.trim() || !currentConversationId;
    });

    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
    });

    searchInput.addEventListener('input', () => {
        renderConversationList(searchInput.value);
    });

    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', async () => {
            const text = chip.dataset.text;
            setView('chat');
            if (!currentConversationId) {
                await createConversation();
            }
            if (currentConversationId) {
                messageInput.value = text;
                sendBtn.disabled = false;
                handleSend();
            }
        });
    });

    window.addEventListener('language-changed', applyI18n);

    // ===== Init =====
    async function init() {
        // language from localStorage or default
        const savedLang = localStorage.getItem('maxagent-lang');
        if (savedLang) setLang(savedLang);

        applyTheme(theme);
        applyI18n();
        setStatus('idle', t('status.ready'));
        setView('chat');

        await loadConversations();

        if (conversations.length > 0) {
            await switchToConversation(conversations[0].id);
        } else {
            await createConversation();
        }
    }

    init();
})();
