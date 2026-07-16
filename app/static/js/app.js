// MaxAgent Frontend App
(function() {
    'use strict';

    // ===== State =====
    let currentConversationId = null;
    let conversations = [];
    let isLoading = false;

    // ===== DOM refs =====
    const $ = (id) => document.getElementById(id);
    const welcome = $('welcome');
    const chatArea = $('chat-area');
    const chatTitle = $('chat-title');
    const messagesEl = $('messages');
    const messageInput = $('message-input');
    const sendBtn = $('send-btn');
    const conversationList = $('conversation-list');
    const newChatBtn = $('new-chat-btn');
    const searchInput = $('search-input');
    const statusDot = $('status-dot');
    const statusText = $('status-text');

    // ===== API Helpers =====
    async function api(url, options = {}) {
        const config = {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        };
        const response = await fetch(url, config);
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(err.detail || '请求失败');
        }
        return response.json();
    }

    // ===== Conversation Management =====
    async function loadConversations() {
        try {
            const data = await api('/api/conversations');
            conversations = data.conversations || [];
            renderConversationList();
        } catch (e) {
            console.error('加载会话列表失败:', e);
        }
    }

    async function createConversation(title = '新对话') {
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
        }
    }

    async function deleteConversation(id) {
        try {
            await api(`/api/conversations/${id}`, { method: 'DELETE' });
            conversations = conversations.filter(c => c.id !== id);
            renderConversationList();
            if (currentConversationId === id) {
                currentConversationId = null;
                showWelcome();
            }
        } catch (e) {
            console.error('删除会话失败:', e);
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
            setStatus('busy', '思考中...');
            const data = await api('/api/chat', {
                method: 'POST',
                body: JSON.stringify({ conversation_id: conversationId, message }),
            });
            return data.reply;
        } catch (e) {
            console.error('发送消息失败:', e);
            return `发送消息失败: ${e.message}`;
        } finally {
            setStatus('idle', '就绪');
        }
    }

    // ===== Rendering =====
    function renderConversationList(filter = '') {
        const filtered = filter
            ? conversations.filter(c => c.title.includes(filter))
            : conversations;

        if (filtered.length === 0) {
            conversationList.innerHTML = `
                <div class="empty-state" style="padding: 40px 16px; text-align: center;">
                    ${filter ? '没有匹配的对话' : '暂无对话，点击上方按钮开始新对话'}
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
                    <div class="conv-preview">${escapeHtml(c.preview || '暂无消息')}</div>
                </div>
                <button class="conv-delete" title="删除对话" data-id="${c.id}">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                    </svg>
                </button>
            </div>
        `).join('');

        // 绑定事件
        conversationList.querySelectorAll('.conversation-item').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.closest('.conv-delete')) return;
                const id = el.dataset.id;
                switchToConversation(id);
            });
        });

        conversationList.querySelectorAll('.conv-delete').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                if (confirm('确定要删除此对话吗？')) {
                    await deleteConversation(id);
                }
            });
        });
    }

    function renderMessages(messages) {
        if (!messages || messages.length === 0) {
            messagesEl.innerHTML = '<div class="empty-state">开始对话吧</div>';
            return;
        }

        messagesEl.innerHTML = messages.map((msg, index) => `
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

    // ===== UI Helpers =====
    function showWelcome() {
        welcome.style.display = 'flex';
        chatArea.style.display = 'none';
    }

    function showChatArea(title) {
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
        div.textContent = text;
        return div.innerHTML;
    }

    function formatContent(content) {
        if (!content) return '';
        // 简单处理代码块
        let escaped = escapeHtml(content);
        // 处理代码块 ```code```
        escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
        // 处理行内代码 `code`
        escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');
        // 处理换行
        escaped = escaped.replace(/\n/g, '<br>');
        return escaped;
    }

    // ===== Conversation Switching =====
    async function switchToConversation(id) {
        if (isLoading) return;
        isLoading = true;

        currentConversationId = id;
        renderConversationList(searchInput.value);

        const conv = conversations.find(c => c.id === id);
        showChatArea(conv ? conv.title : '对话');

        messagesEl.innerHTML = '<div class="empty-state">加载中...</div>';

        const messages = await loadMessages(id);
        renderMessages(messages);

        isLoading = false;
    }

    // ===== Send Message =====
    async function handleSend() {
        const text = messageInput.value.trim();
        if (!text || !currentConversationId || isLoading) return;

        // 清空输入
        messageInput.value = '';
        sendBtn.disabled = true;
        messageInput.style.height = 'auto';

        // 添加用户消息
        appendMessage('user', text);

        // 显示打字指示器
        showTyping();

        // 发送请求
        const reply = await sendMessage(currentConversationId, text);

        // 移除打字指示器
        removeTyping();

        // 添加回复
        appendMessage('assistant', reply);

        // 更新会话列表
        await loadConversations();

        // 高亮当前会话
        renderConversationList(searchInput.value);
    }

    // ===== Event Listeners =====
    newChatBtn.addEventListener('click', () => {
        createConversation();
    });

    sendBtn.addEventListener('click', handleSend);

    messageInput.addEventListener('input', () => {
        // 自动调整高度
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';

        // 启用/禁用发送按钮
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

    // 欢迎页建议词点击
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', async () => {
            const text = chip.dataset.text;
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

    // ===== Init =====
    async function init() {
        setStatus('idle', '就绪');
        await loadConversations();

        // 如果有会话，自动切换到第一个
        if (conversations.length > 0) {
            await switchToConversation(conversations[0].id);
        } else {
            // 自动创建一个新会话
            await createConversation();
        }
    }

    init();
})();
