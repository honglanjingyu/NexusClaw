// API 配置
let API_BASE = '/api/v1';
let currentSessionId = null;
let chatHistory = [];
let isStreaming = true;
let autoScroll = true;
let isSending = false;  // 防止重复发送
let thinkingAnimationInterval = null;  // 思考动画定时器

// DOM 元素
const messagesArea = document.getElementById('messagesArea');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const newChatBtn = document.getElementById('newChatBtn');
const clearAllBtn = document.getElementById('clearAllBtn');
const sidebarToggle = document.getElementById('sidebarToggle');
const menuBtn = document.getElementById('menuBtn');
const sidebar = document.getElementById('sidebar');
const sessionIdDisplay = document.getElementById('sessionIdDisplay');
const copySessionBtn = document.getElementById('copySessionBtn');
const knowledgeBtn = document.getElementById('knowledgeBtn');
const statsBtn = document.getElementById('statsBtn');
const settingsBtn = document.getElementById('settingsBtn');
const streamToggle = document.getElementById('streamToggle');
const autoScrollToggle = document.getElementById('autoScrollToggle');
const apiUrlInput = document.getElementById('apiUrl');
const charCountSpan = document.getElementById('charCount');
const statusIcon = document.getElementById('statusIcon');
const statusText = document.getElementById('statusText');

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
    loadSettings();
    await initSession();
    await checkHealth();
    setupEventListeners();
    setupAutoResize();
    loadChatHistoryFromStorage();
});

// 加载设置
function loadSettings() {
    const savedApiUrl = localStorage.getItem('api_url');
    if (savedApiUrl) {
        API_BASE = savedApiUrl;
        if (apiUrlInput) apiUrlInput.value = savedApiUrl;
    }

    const savedStream = localStorage.getItem('stream_enabled');
    if (savedStream !== null) {
        isStreaming = savedStream === 'true';
        if (streamToggle) streamToggle.checked = isStreaming;
    }

    const savedAutoScroll = localStorage.getItem('auto_scroll');
    if (savedAutoScroll !== null) {
        autoScroll = savedAutoScroll === 'true';
        if (autoScrollToggle) autoScrollToggle.checked = autoScroll;
    }
}

// 保存设置
function saveSettings() {
    localStorage.setItem('api_url', API_BASE);
    localStorage.setItem('stream_enabled', isStreaming);
    localStorage.setItem('auto_scroll', autoScroll);
}

// 初始化会话
async function initSession() {
    try {
        const response = await fetch(`${API_BASE}/session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_name: 'web_user' })
        });

        if (response.ok) {
            const data = await response.json();
            currentSessionId = data.session_id;
            sessionIdDisplay.textContent = `会话: ${currentSessionId.slice(0, 8)}...`;
            updateSessionId();
        } else {
            currentSessionId = generateSessionId();
            sessionIdDisplay.textContent = `会话: ${currentSessionId.slice(0, 8)}...`;
        }
    } catch (error) {
        console.warn('API 不可用，使用本地会话:', error);
        currentSessionId = generateSessionId();
        sessionIdDisplay.textContent = `会话: ${currentSessionId.slice(0, 8)}...`;
    }
}

function generateSessionId() {
    return 'local_' + Math.random().toString(36).substring(2, 10);
}

function updateSessionId() {
    const sessionKey = `chat_history_${currentSessionId}`;
    const saved = localStorage.getItem(sessionKey);
    if (saved) {
        try {
            chatHistory = JSON.parse(saved);
            renderMessages();
        } catch (e) {}
    } else {
        chatHistory = [];
        renderMessages();
    }
    saveChatHistoryToStorage();
    updateHistoryList();
}

// 保存对话历史到本地存储
function saveChatHistoryToStorage() {
    const sessionKey = `chat_history_${currentSessionId}`;
    localStorage.setItem(sessionKey, JSON.stringify(chatHistory));

    const sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    if (!sessions.includes(currentSessionId)) {
        sessions.unshift(currentSessionId);
        if (sessions.length > 20) sessions.pop();
        localStorage.setItem('sessions', JSON.stringify(sessions));
    }
}

// 加载会话列表
function loadChatHistoryFromStorage() {
    updateHistoryList();
}

function updateHistoryList() {
    const sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    const historyList = document.getElementById('chatHistoryList');

    if (!historyList) return;

    if (sessions.length === 0) {
        historyList.innerHTML = '<div class="empty-history">暂无历史对话</div>';
        return;
    }

    historyList.innerHTML = sessions.map(sessionId => {
        const sessionKey = `chat_history_${sessionId}`;
        const history = JSON.parse(localStorage.getItem(sessionKey) || '[]');
        const firstMsg = history.find(m => m.role === 'user')?.content || '新对话';
        const preview = firstMsg.length > 20 ? firstMsg.slice(0, 20) + '...' : firstMsg;

        return `
            <div class="history-item ${sessionId === currentSessionId ? 'active' : ''}" data-session-id="${sessionId}">
                <div class="history-item-content">
                    <i class="fas fa-comment"></i>
                    <span>${escapeHtml(preview)}</span>
                </div>
                <button class="history-item-delete" data-session-id="${sessionId}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
    }).join('');

    document.querySelectorAll('.history-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.closest('.history-item-delete')) return;
            const sessionId = item.dataset.sessionId;
            if (sessionId) switchSession(sessionId);
        });
    });

    document.querySelectorAll('.history-item-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const sessionId = btn.dataset.sessionId;
            if (sessionId) deleteSession(sessionId);
        });
    });
}

function switchSession(sessionId) {
    currentSessionId = sessionId;
    sessionIdDisplay.textContent = `会话: ${sessionId.slice(0, 8)}...`;

    const sessionKey = `chat_history_${sessionId}`;
    const saved = localStorage.getItem(sessionKey);
    if (saved) {
        try {
            chatHistory = JSON.parse(saved);
        } catch (e) {
            chatHistory = [];
        }
    } else {
        chatHistory = [];
    }

    renderMessages();
    updateHistoryList();
}

function deleteSession(sessionId) {
    const sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    const newSessions = sessions.filter(s => s !== sessionId);
    localStorage.setItem('sessions', JSON.stringify(newSessions));
    localStorage.removeItem(`chat_history_${sessionId}`);

    if (sessionId === currentSessionId) {
        if (newSessions.length > 0) {
            switchSession(newSessions[0]);
        } else {
            createNewChat();
        }
    } else {
        updateHistoryList();
    }
}

// 健康检查
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        if (response.ok) {
            statusIcon.className = 'fas fa-circle online';
            statusText.textContent = '已连接';
        } else {
            throw new Error('API 响应错误');
        }
    } catch (error) {
        statusIcon.className = 'fas fa-circle offline';
        statusText.textContent = '离线';
    }
}

// 设置事件监听
function setupEventListeners() {
    sendBtn.addEventListener('click', sendMessage);
    messageInput.addEventListener('keydown', handleKeydown);
    newChatBtn.addEventListener('click', createNewChat);
    clearAllBtn.addEventListener('click', clearAllSessions);
    sidebarToggle.addEventListener('click', toggleSidebar);
    menuBtn.addEventListener('click', toggleMobileSidebar);
    copySessionBtn.addEventListener('click', copySessionId);
    knowledgeBtn.addEventListener('click', openKnowledgeModal);
    statsBtn.addEventListener('click', openStatsModal);
    settingsBtn.addEventListener('click', openSettingsModal);

    if (streamToggle) {
        streamToggle.addEventListener('change', (e) => {
            isStreaming = e.target.checked;
            saveSettings();
        });
    }

    if (autoScrollToggle) {
        autoScrollToggle.addEventListener('change', (e) => {
            autoScroll = e.target.checked;
            saveSettings();
        });
    }

    if (apiUrlInput) {
        apiUrlInput.addEventListener('change', (e) => {
            API_BASE = e.target.value;
            saveSettings();
            checkHealth();
        });
    }

    // 建议芯片点击 - 使用事件委托
    document.addEventListener('click', (e) => {
        const chip = e.target.closest('.suggestion-chip');
        if (chip) {
            const msg = chip.dataset.msg;
            if (msg) {
                messageInput.value = msg;
                sendMessage();
            }
        }
    });

    // 模态框关闭
    document.querySelectorAll('.modal-close').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.classList.remove('active');
            });
        });
    });

    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
}

function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
}

function toggleMobileSidebar() {
    sidebar.classList.toggle('mobile-open');
}

function copySessionId() {
    navigator.clipboard.writeText(currentSessionId);
    showToast('会话ID已复制', 'success');
}

function createNewChat() {
    currentSessionId = generateSessionId();
    sessionIdDisplay.textContent = `会话: ${currentSessionId.slice(0, 8)}...`;
    chatHistory = [];
    renderMessages();
    saveChatHistoryToStorage();
    updateHistoryList();
    sidebar.classList.remove('mobile-open');
}

function clearAllSessions() {
    if (confirm('确定要清空所有会话吗？此操作不可恢复。')) {
        const sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        sessions.forEach(session => {
            localStorage.removeItem(`chat_history_${session}`);
        });
        localStorage.removeItem('sessions');
        createNewChat();
        showToast('所有会话已清空', 'info');
    }
}

// ========== 思考动画相关函数 ==========

/**
 * 添加带思考动画的等待消息
 * @returns {string} 消息元素ID
 */
function addThinkingMessage() {
    const messageId = `thinking_${Date.now()}_${nextMessageId++}`;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant thinking';
    messageDiv.id = messageId;

    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="message-text">
                <span class="thinking-text">正在思考</span>
                <span class="thinking-dots">...</span>
            </div>
            <div class="message-meta"></div>
        </div>
    `;

    messagesArea.appendChild(messageDiv);

    // 启动点动画
    startThinkingAnimation(messageId);

    if (autoScroll) scrollToBottom();
    return messageId;
}

/**
 * 启动思考动画（... 循环闪烁）
 * @param {string} messageId 消息元素ID
 */
function startThinkingAnimation(messageId) {
    // 清除之前的动画
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
    }

    const messageDiv = document.getElementById(messageId);
    if (!messageDiv) return;

    const dotsSpan = messageDiv.querySelector('.thinking-dots');
    if (!dotsSpan) return;

    let dotCount = 3;
    let increasing = false; // true: 增加点数, false: 减少点数

    thinkingAnimationInterval = setInterval(() => {
        const currentDiv = document.getElementById(messageId);
        if (!currentDiv) {
            // 消息已被替换，清除动画
            if (thinkingAnimationInterval) {
                clearInterval(thinkingAnimationInterval);
                thinkingAnimationInterval = null;
            }
            return;
        }

        const currentDotsSpan = currentDiv.querySelector('.thinking-dots');
        if (!currentDotsSpan) return;

        // 更新点数
        if (increasing) {
            dotCount++;
            if (dotCount >= 3) {
                dotCount = 3;
                increasing = false;
            }
        } else {
            dotCount--;
            if (dotCount <= 0) {
                dotCount = 0;
                increasing = true;
            }
        }

        // 显示对应的点
        currentDotsSpan.textContent = '.'.repeat(Math.max(1, dotCount));

    }, 400); // 每400毫秒变化一次
}

/**
 * 停止思考动画并替换为实际内容
 * @param {string} thinkingMessageId 思考消息ID
 * @param {string} content 实际内容
 * @returns {string} 新消息ID
 */
function replaceThinkingWithContent(thinkingMessageId, content) {
    // 停止动画
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
        thinkingAnimationInterval = null;
    }

    const thinkingDiv = document.getElementById(thinkingMessageId);
    if (!thinkingDiv) {
        // 如果思考消息不存在，直接创建新消息
        return addMessageToUI('assistant', content);
    }

    // 更新消息内容
    const textDiv = thinkingDiv.querySelector('.message-text');
    if (textDiv) {
        // 移除思考动画相关类
        thinkingDiv.classList.remove('thinking');
        textDiv.innerHTML = formatMarkdown(content);
    }

    // 更新ID
    const newId = `msg_${Date.now()}_${nextMessageId++}`;
    thinkingDiv.id = newId;

    // 更新时间
    const metaSpan = thinkingDiv.querySelector('.message-meta');
    if (metaSpan) {
        metaSpan.textContent = new Date().toLocaleTimeString();
    }

    return newId;
}

/**
 * 添加空助手消息（用于流式响应）
 * @returns {string} 消息ID
 */
function addEmptyAssistantMessage() {
    // 停止之前的思考动画（如果有）
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
        thinkingAnimationInterval = null;
    }

    const messageId = `msg_${Date.now()}_${nextMessageId++}`;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = messageId;

    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="message-text"></div>
            <div class="message-meta"></div>
        </div>
    `;

    messagesArea.appendChild(messageDiv);
    return messageId;
}

// 发送消息（主入口，带防重复）
async function sendMessage() {
    if (isSending) {
        showToast('请等待上一消息完成', 'warning');
        return;
    }

    const message = messageInput.value.trim();
    if (!message) return;

    isSending = true;
    sendBtn.disabled = true;

    try {
        if (isStreaming) {
            await sendMessageStream(message);
        } else {
            await sendMessageNormal(message);
        }
    } catch (error) {
        console.error('发送消息失败:', error);
        showToast('发送失败: ' + error.message, 'error');
    } finally {
        isSending = false;
        sendBtn.disabled = false;
        messageInput.focus();
    }
}

// 普通模式发送
async function sendMessageNormal(message) {
    addMessageToUI('user', message);
    messageInput.value = '';
    updateCharCount();

    // 添加思考动画
    const thinkingId = addThinkingMessage();

    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            })
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                // 替换思考动画为实际内容
                replaceThinkingWithContent(thinkingId, data.response);
                chatHistory.push({ role: 'user', content: message });
                chatHistory.push({ role: 'assistant', content: data.response });
                saveChatHistoryToStorage();
                updateHistoryList();
            } else {
                replaceThinkingWithContent(thinkingId, `错误: ${data.error || data.response || '未知错误'}`);
            }
        } else {
            const errorText = await response.text();
            replaceThinkingWithContent(thinkingId, `API 错误 (${response.status}): ${errorText.slice(0, 200)}`);
        }
    } catch (error) {
        replaceThinkingWithContent(thinkingId, `网络错误: ${error.message}`);
    } finally {
        if (autoScroll) scrollToBottom();
    }
}

let nextMessageId = 0;
let hasReceivedFirstChunk = false;  // 标记是否已收到第一个字符

// 流式模式发送
async function sendMessageStream(message) {
    // 重置标记
    hasReceivedFirstChunk = false;

    addMessageToUI('user', message);
    messageInput.value = '';
    updateCharCount();

    // 添加思考动画（不是空消息）
    const thinkingId = addThinkingMessage();

    let fullResponse = '';
    let hasError = false;

    try {
        const response = await fetch(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId,
                stream: true
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.type === 'chunk') {
                            const chunk = data.data;
                            if (chunk) {
                                // 收到第一个字符，停止思考动画并创建真实消息
                                if (!hasReceivedFirstChunk) {
                                    hasReceivedFirstChunk = true;
                                    // 停止动画，替换为真实消息容器
                                    stopThinkingAnimation(thinkingId);
                                    // 创建新的空消息用于流式追加
                                    const newMsgId = createStreamingMessage(thinkingId);
                                    // 更新 assistantMessageId 为新的消息ID
                                    window.currentStreamingMsgId = newMsgId;
                                    // 添加第一个字符
                                    fullResponse += chunk;
                                    updateStreamingMessage(newMsgId, fullResponse);
                                } else {
                                    fullResponse += chunk;
                                    if (window.currentStreamingMsgId) {
                                        updateStreamingMessage(window.currentStreamingMsgId, fullResponse);
                                    }
                                }
                                if (autoScroll) scrollToBottom();
                            }
                        } else if (data.type === 'session') {
                            if (data.data.session_id && data.data.session_id !== currentSessionId) {
                                currentSessionId = data.data.session_id;
                                sessionIdDisplay.textContent = `会话: ${currentSessionId.slice(0, 8)}...`;
                            }
                        } else if (data.type === 'error') {
                            hasError = true;
                            fullResponse = `错误: ${data.data}`;
                            if (hasReceivedFirstChunk && window.currentStreamingMsgId) {
                                updateStreamingMessage(window.currentStreamingMsgId, fullResponse);
                            } else {
                                replaceThinkingWithContent(thinkingId, fullResponse);
                            }
                        } else if (data.type === 'complete') {
                            console.log('Stream complete', data);
                        }
                    } catch (e) {
                        console.warn('解析 SSE 数据失败:', e, line);
                    }
                }
            }
        }

        // 如果从未收到任何字符（可能是空响应）
        if (!hasReceivedFirstChunk && !hasError) {
            replaceThinkingWithContent(thinkingId, '收到空响应，请稍后重试。');
        }

        // 保存到历史（仅当没有错误且有内容时）
        if (!hasError && fullResponse && !fullResponse.startsWith('错误:')) {
            chatHistory.push({ role: 'user', content: message });
            chatHistory.push({ role: 'assistant', content: fullResponse });
            saveChatHistoryToStorage();
            updateHistoryList();
        }

    } catch (error) {
        console.error('流式请求失败:', error);
        if (hasReceivedFirstChunk && window.currentStreamingMsgId) {
            updateStreamingMessage(window.currentStreamingMsgId, `网络错误: ${error.message}`);
        } else {
            replaceThinkingWithContent(thinkingId, `网络错误: ${error.message}`);
        }
    }
}

/**
 * 停止思考动画（不替换内容，准备创建新消息）
 * @param {string} thinkingMessageId 思考消息ID
 */
function stopThinkingAnimation(thinkingMessageId) {
    // 停止动画
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
        thinkingAnimationInterval = null;
    }

    const thinkingDiv = document.getElementById(thinkingMessageId);
    if (thinkingDiv) {
        // 隐藏思考消息（稍后会被替换或移除）
        thinkingDiv.style.display = 'none';
    }
}

/**
 * 创建用于流式输出的消息（替换思考消息的位置）
 * @param {string} oldThinkingId 旧的思考消息ID
 * @returns {string} 新消息ID
 */
function createStreamingMessage(oldThinkingId) {
    const oldDiv = document.getElementById(oldThinkingId);
    if (!oldDiv) {
        // 回退：直接创建新消息
        return addEmptyAssistantMessage();
    }

    // 创建新消息元素
    const messageId = `msg_${Date.now()}_${nextMessageId++}`;
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = messageId;

    messageDiv.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="message-text"></div>
            <div class="message-meta">${new Date().toLocaleTimeString()}</div>
        </div>
    `;

    // 替换旧消息
    oldDiv.parentNode.replaceChild(messageDiv, oldDiv);

    if (autoScroll) scrollToBottom();
    return messageId;
}

/**
 * 更新流式消息内容
 * @param {string} messageId 消息ID
 * @param {string} content 内容
 */
function updateStreamingMessage(messageId, content) {
    const messageDiv = document.getElementById(messageId);
    if (messageDiv) {
        const textDiv = messageDiv.querySelector('.message-text');
        if (textDiv) {
            textDiv.innerHTML = formatMarkdown(content);
        }
    }
}

function addMessageToUI(role, content) {
    const messageId = `msg_${Date.now()}_${nextMessageId++}`;
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.id = messageId;

    const avatar = role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
    const formattedContent = formatMarkdown(content);

    messageDiv.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-text">${formattedContent}</div>
            <div class="message-meta">${new Date().toLocaleTimeString()}</div>
        </div>
    `;

    messagesArea.appendChild(messageDiv);

    if (autoScroll) scrollToBottom();
    return messageId;
}

function updateAssistantMessage(messageId, content) {
    const messageDiv = document.getElementById(messageId);
    if (messageDiv) {
        const textDiv = messageDiv.querySelector('.message-text');
        if (textDiv) {
            textDiv.innerHTML = formatMarkdown(content);
        }
    }
}

function addTypingIndicator() {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.className = 'message assistant';
    indicatorDiv.id = 'typingIndicator';
    indicatorDiv.innerHTML = `
        <div class="message-avatar"><i class="fas fa-robot"></i></div>
        <div class="message-content">
            <div class="message-text">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        </div>
    `;
    messagesArea.appendChild(indicatorDiv);
    if (autoScroll) scrollToBottom();
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

function renderMessages() {
    if (!messagesArea) return;

    if (chatHistory.length === 0) {
        messagesArea.innerHTML = `
            <div class="welcome-message">
                <div class="welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h2>你好！我是 AI Agent</h2>
                <p>我可以帮你回答问题、搜索知识、处理任务。试试问我：</p>
                <div class="suggestion-chips">
                    <button class="suggestion-chip" data-msg="现在几点了？">
                        <i class="fas fa-clock"></i> 现在几点了？
                    </button>
                    <button class="suggestion-chip" data-msg="介绍一下 RAG 技术">
                        <i class="fas fa-brain"></i> 介绍一下 RAG 技术
                    </button>
                    <button class="suggestion-chip" data-msg="如何排查 CPU 告警问题？">
                        <i class="fas fa-chart-line"></i> 如何排查 CPU 告警？
                    </button>
                    <button class="suggestion-chip" data-msg="知识库里有什么内容？">
                        <i class="fas fa-database"></i> 知识库里有什么？
                    </button>
                </div>
            </div>
        `;
        return;
    }

    messagesArea.innerHTML = '';
    chatHistory.forEach(msg => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role}`;
        const avatar = msg.role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        const formattedContent = formatMarkdown(msg.content);

        messageDiv.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                <div class="message-text">${formattedContent}</div>
                <div class="message-meta">${new Date().toLocaleTimeString()}</div>
            </div>
        `;
        messagesArea.appendChild(messageDiv);
    });

    scrollToBottom();
}

function formatMarkdown(text) {
    if (!text) return '';

    let formatted = escapeHtml(text);

    // 代码块
    formatted = formatted.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
    // 行内代码
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
    // 粗体
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    // 斜体
    formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    // 标题
    formatted = formatted.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    formatted = formatted.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    formatted = formatted.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    // 列表
    formatted = formatted.replace(/^- (.*$)/gm, '<li>$1</li>');
    formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    // 换行
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function scrollToBottom() {
    if (autoScroll && messagesArea) {
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }
}

function updateCharCount() {
    const count = messageInput.value.length;
    charCountSpan.textContent = `${count} 字符`;
}

function setupAutoResize() {
    messageInput.addEventListener('input', () => {
        updateCharCount();
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });
}

// 知识库模态框
async function openKnowledgeModal() {
    const modal = document.getElementById('knowledgeModal');
    if (modal) modal.classList.add('active');

    await loadKnowledgeStats();

    const addBtn = document.getElementById('addKnowledgeBtn');
    const searchBtn = document.getElementById('searchKnowledgeBtn');

    if (addBtn) {
        addBtn.onclick = addKnowledge;
    }
    if (searchBtn) {
        searchBtn.onclick = searchKnowledge;
    }
}

async function loadKnowledgeStats() {
    try {
        const response = await fetch(`${API_BASE}/knowledge/stats`);
        if (response.ok) {
            const data = await response.json();
            const docCountSpan = document.getElementById('docCount');
            if (docCountSpan) {
                const match = data.message?.match(/\d+/);
                docCountSpan.textContent = match ? match[0] : '0';
            }
        }
    } catch (error) {
        console.error('加载知识库统计失败:', error);
    }
}

async function addKnowledge() {
    const content = document.getElementById('knowledgeContent')?.value.trim();
    const category = document.getElementById('knowledgeCategory')?.value.trim() || 'general';

    if (!content) {
        showToast('请输入知识内容', 'warning');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/knowledge`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, category })
        });

        if (response.ok) {
            const data = await response.json();
            showToast(data.message, data.success ? 'success' : 'error');
            if (data.success) {
                const textarea = document.getElementById('knowledgeContent');
                if (textarea) textarea.value = '';
                await loadKnowledgeStats();
            }
        } else {
            showToast('添加失败: HTTP ' + response.status, 'error');
        }
    } catch (error) {
        showToast('添加失败: ' + error.message, 'error');
    }
}

async function searchKnowledge() {
    const query = document.getElementById('knowledgeQuery')?.value.trim();
    if (!query) return;

    const resultsDiv = document.getElementById('knowledgeResults');
    if (resultsDiv) resultsDiv.innerHTML = '<div class="loading">搜索中...</div>';

    try {
        const response = await fetch(`${API_BASE}/knowledge/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query, top_k: 5 })
        });

        if (response.ok && resultsDiv) {
            const data = await response.json();
            if (data.success && data.message) {
                resultsDiv.innerHTML = `<div class="knowledge-result-item">
                    <div class="content">${escapeHtml(data.message)}</div>
                </div>`;
            } else {
                resultsDiv.innerHTML = `<div class="knowledge-result-item">${escapeHtml(data.message || '无结果')}</div>`;
            }
        } else if (resultsDiv) {
            resultsDiv.innerHTML = '<div class="knowledge-result-item">搜索失败</div>';
        }
    } catch (error) {
        if (resultsDiv) {
            resultsDiv.innerHTML = `<div class="knowledge-result-item">搜索失败: ${escapeHtml(error.message)}</div>`;
        }
    }
}

// 状态模态框
async function openStatsModal() {
    const modal = document.getElementById('statsModal');
    if (modal) modal.classList.add('active');

    try {
        const [statusRes, memoryRes, toolsRes] = await Promise.all([
            fetch(`${API_BASE}/status`),
            fetch(`${API_BASE}/memory/stats`),
            fetch(`${API_BASE}/tools`)
        ]);

        if (statusRes.ok) {
            const status = await statusRes.json();
            const initStatusSpan = document.getElementById('initStatus');
            if (initStatusSpan) {
                initStatusSpan.innerHTML = status.initialized ?
                    '<span style="color: #10b981">✅ 已初始化</span>' :
                    '<span style="color: #ef4444">❌ 未初始化</span>';
            }
            const statSessionSpan = document.getElementById('statSessionId');
            if (statSessionSpan) statSessionSpan.textContent = status.session_id?.slice(0, 12) + '...' || '--';
            const toolCountSpan = document.getElementById('toolCount');
            if (toolCountSpan) toolCountSpan.textContent = status.tools?.length || 0;
        }

        if (memoryRes.ok) {
            const memory = await memoryRes.json();
            const shortTermSpan = document.getElementById('shortTermCount');
            const workingSpan = document.getElementById('workingCount');
            const longTermSpan = document.getElementById('longTermCount');
            if (shortTermSpan) shortTermSpan.textContent = memory.short_term || 0;
            if (workingSpan) workingSpan.textContent = memory.working || 0;
            if (longTermSpan) longTermSpan.textContent = memory.long_term || 0;
        }

        if (toolsRes.ok) {
            const tools = await toolsRes.json();
            const toolsContainer = document.getElementById('toolsContainer');
            if (toolsContainer) {
                if (tools.tools && tools.tools.length > 0) {
                    toolsContainer.innerHTML = tools.tools.map(tool =>
                        `<span class="tool-badge">${escapeHtml(tool)}</span>`
                    ).join('');
                } else {
                    toolsContainer.innerHTML = '<span style="color: #64748b">暂无工具</span>';
                }
            }
        }
    } catch (error) {
        console.error('加载状态失败:', error);
        showToast('加载状态失败', 'error');
    }
}

function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.classList.add('active');

    const testBtn = document.getElementById('testConnectionBtn');
    if (testBtn) {
        testBtn.onclick = async () => {
            try {
                const response = await fetch(`${API_BASE}/health`);
                if (response.ok) {
                    showToast('连接成功', 'success');
                } else {
                    showToast('连接失败', 'error');
                }
            } catch (error) {
                showToast('连接失败: ' + error.message, 'error');
            }
        };
    }
}

// Toast 通知
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
        <span>${escapeHtml(message)}</span>
    `;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#6366f1'};
        color: white;
        padding: 10px 20px;
        border-radius: 8px;
        font-size: 0.85rem;
        z-index: 2000;
        display: flex;
        align-items: center;
        gap: 8px;
        animation: fadeIn 0.3s ease;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}