// web/js/api.js - 完整修复版（添加认证头和会话权限验证）

// ========== 认证相关 ==========

/**
 * 获取认证头
 */
function getAuthHeaders() {
    const token = localStorage.getItem('agent_token');
    if (token && token !== 'null' && token !== 'undefined') {
        return { 'Authorization': `Bearer ${token}` };
    }
    return {};
}

/**
 * 检查是否已登录
 */
function isLoggedIn() {
    const token = localStorage.getItem('agent_token');
    return token && token !== 'null' && token !== 'undefined';
}

/**
 * 登出
 */
function logout() {
    localStorage.removeItem('agent_token');
    localStorage.removeItem('agent_user_id');
    localStorage.removeItem('agent_username');
    window.location.href = '/login.html';
}

/**
 * 验证会话访问权限
 */
async function verifySessionAccess(sessionId) {
    const token = localStorage.getItem('agent_token');
    if (!token || token === 'null' || token === 'undefined') return true; // 未登录用户允许访问

    try {
        const response = await fetch(`${API_BASE}/auth/session/verify`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await response.json();
        return data.authorized === true;
    } catch (error) {
        console.warn('验证会话权限失败:', error);
        return false;
    }
}

// ========== 会话管理 ==========

/**
 * 验证会话是否存在
 */
async function verifySessionExists(sessionId) {
    if (!sessionId || sessionId === 'null' || sessionId === 'undefined') return false;

    try {
        console.log('验证会话:', sessionId);
        const headers = getAuthHeaders();
        const response = await fetch(`${API_BASE}/session/${sessionId}/info`, { headers });
        if (response.ok) {
            const data = await response.json();
            const exists = data.success === true && data.info !== null;
            console.log('会话验证结果:', exists ? '存在' : '不存在');
            return exists;
        }
        return false;
    } catch (error) {
        console.warn('验证会话失败:', error);
        return false;
    }
}

/**
 * 格式化时间
 */
function formatTime(isoString) {
    if (!isoString) return new Date().toLocaleTimeString();
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString();
    } catch (e) {
        return new Date().toLocaleTimeString();
    }
}

// 渲染锁，防止重复渲染
let isRenderingHistory = false;
let isLoadingHistory = false;
let loadedSessionId = null;

/**
 * 加载会话历史消息 - 从 Redis 加载
 */
async function loadSessionHistory(sessionId) {
    if (!sessionId || sessionId === 'null' || sessionId === 'undefined') return [];

    // 防止重复加载同一个会话
    if (isLoadingHistory && loadedSessionId === sessionId) {
        console.log('正在加载历史，跳过');
        return [];
    }

    isLoadingHistory = true;
    loadedSessionId = sessionId;

    console.log('从 Redis 加载会话历史:', sessionId);
    try {
        const headers = getAuthHeaders();
        const response = await fetch(`${API_BASE}/session/${sessionId}/history?limit=100`, { headers });
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.messages) {
                console.log(`从 Redis 加载会话历史成功: ${data.messages.length} 条消息`);
                return data.messages;
            }
        }
        return [];
    } catch (error) {
        console.warn('加载会话历史失败:', error);
        return [];
    } finally {
        isLoadingHistory = false;
    }
}

/**
 * 渲染加载的会话历史
 */
function renderSessionHistory(messages) {
    if (!messages || messages.length === 0) {
        console.log('没有历史消息可渲染');
        return false;
    }

    // 防止重复渲染
    if (isRenderingHistory) {
        console.log('已经在渲染历史消息，跳过');
        return false;
    }

    // 检查是否已经渲染过相同数量的消息
    const existingCount = messagesArea.querySelectorAll('.message:not(.welcome-message)').length;
    if (existingCount >= messages.length) {
        console.log('历史消息已存在，跳过渲染');
        return true;
    }

    isRenderingHistory = true;

    console.log('渲染会话历史:', messages.length, '条消息');

    // 清空当前消息
    const existingMessages = messagesArea.querySelectorAll('.message');
    existingMessages.forEach(msg => {
        if (!msg.classList.contains('welcome-message')) {
            msg.remove();
        }
    });

    // 移除欢迎消息（如果有历史消息）
    const welcomeMsg = messagesArea.querySelector('.welcome-message');
    if (welcomeMsg && messages.length > 0) {
        welcomeMsg.remove();
    }

    let hasUserMessages = false;

    for (const msg of messages) {
        if (msg.role === 'system') continue;

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${msg.role}`;
        const avatar = msg.role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        const formattedContent = formatMarkdown(msg.content);

        messageDiv.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">
                <div class="message-text">${formattedContent}</div>
                <div class="message-meta">${formatTime(msg.created_at)}</div>
            </div>
        `;

        messagesArea.appendChild(messageDiv);
        if (msg.role === 'user') hasUserMessages = true;
    }

    if (hasUserMessages && autoScroll) {
        scrollToBottom();
    }

    isRenderingHistory = false;
    return hasUserMessages;
}

/**
 * 创建新会话
 */
async function createNewSession() {
    try {
        console.log('创建新会话...');
        const headers = getAuthHeaders();
        const response = await fetch(`${API_BASE}/session/create?user_id=web_user`, { headers });
        if (response.ok) {
            const data = await response.json();
            if (data.session_id) {
                console.log('创建新会话成功:', data.session_id);
                return data.session_id;
            }
        }
        console.error('创建会话响应失败:', response.status);
    } catch (e) {
        console.error('创建会话失败:', e);
    }

    // 降级：生成本地会话ID
    const localId = 'local_' + Math.random().toString(36).substring(2, 10);
    console.log('使用本地会话ID:', localId);
    return localId;
}

// 初始化锁，防止重复初始化
let isInitializing = false;

/**
 * 初始化会话（只从 Redis 加载）
 */
async function initSession() {
    // 防止重复初始化
    if (isInitializing) {
        console.log('已经在初始化中，跳过');
        return currentSessionId;
    }

    isInitializing = true;
    console.log('开始初始化会话...');

    let sessionId = getSessionIdFromURL();

    if (!sessionId) {
        const saved = localStorage.getItem(STORAGE_KEY_SESSION);
        if (saved && saved !== 'null' && saved !== 'undefined') {
            sessionId = saved;
            console.log('从 localStorage 获取会话ID:', sessionId);
        }
    }

    if (sessionId && sessionId !== 'null' && sessionId !== 'undefined') {
        console.log('找到会话 ID:', sessionId);
        const isValid = await verifySessionExists(sessionId);
        if (isValid) {
            currentSessionId = sessionId;
            updateURLWithSessionId(sessionId);
            updateSessionDisplay();

            // 从 Redis 加载历史消息
            const history = await loadSessionHistory(sessionId);

            if (history.length > 0) {
                // 清空 chatHistory 避免重复
                chatHistory = [];
                const hasMessages = renderSessionHistory(history);
                if (hasMessages) {
                    chatHistory = history.map(msg => ({
                        role: msg.role,
                        content: msg.content
                    }));
                }
                showToast(`✅ 已恢复会话 (${history.length} 条消息)`, 'success');
            } else {
                chatHistory = [];
                if (messagesArea && messagesArea.children.length === 0) {
                    renderWelcomeMessage();
                }
                showToast('✅ 已恢复会话', 'success');
            }

            // 更新会话列表
            updateSessionList();
            updateHistoryList();

            console.log('初始化会话成功:', sessionId);
            isInitializing = false;
            return sessionId;
        } else {
            console.log('保存的会话已失效，清除');
            clearSavedSession();
        }
    }

    console.log('没有有效会话，创建新会话...');
    sessionId = await createNewSession();
    currentSessionId = sessionId;
    saveSessionIdToStorage(sessionId);
    updateSessionDisplay();

    chatHistory = [];

    if (messagesArea && messagesArea.children.length === 0) {
        renderWelcomeMessage();
    }

    updateSessionList();
    updateHistoryList();

    isInitializing = false;
    return sessionId;
}

/**
 * 渲染欢迎消息
 */
function renderWelcomeMessage() {
    if (!messagesArea) return;
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
}

/**
 * 检查后端健康状态
 */
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

/**
 * 新建会话按钮处理
 */
async function handleNewChat() {
    if (isSending) {
        showToast('请等待当前回答完成', 'warning');
        return;
    }

    console.log('新建会话...');

    try {
        const headers = getAuthHeaders();
        // 调用后端创建新会话
        const response = await fetch(`${API_BASE}/session/create?user_id=web_user`, { headers });
        if (response.ok) {
            const data = await response.json();
            if (data.session_id) {
                const newSessionId = data.session_id;

                // 更新全局变量
                currentSessionId = newSessionId;

                // 保存到 localStorage（只保存会话ID）
                try {
                    localStorage.setItem(STORAGE_KEY_SESSION, newSessionId);
                } catch (e) {}

                // 更新 URL
                updateURLWithSessionId(newSessionId);
                updateSessionDisplay();

                // 清空聊天历史
                chatHistory = [];

                // 清空消息区域并显示欢迎消息
                if (messagesArea) {
                    const existingMessages = messagesArea.querySelectorAll('.message');
                    existingMessages.forEach(msg => msg.remove());
                    renderWelcomeMessage();
                }

                // 更新会话列表
                updateSessionList();
                updateHistoryList();

                showToast('✨ 已创建新会话', 'success');

                if (messageInput) messageInput.focus();
                return;
            }
        }

        // 降级方案
        const localId = 'local_' + Math.random().toString(36).substring(2, 10);
        currentSessionId = localId;
        try {
            localStorage.setItem(STORAGE_KEY_SESSION, localId);
        } catch (e) {}
        updateURLWithSessionId(localId);
        updateSessionDisplay();
        chatHistory = [];
        renderWelcomeMessage();
        updateSessionList();
        updateHistoryList();
        showToast('✨ 已创建新会话', 'success');

    } catch (error) {
        console.error('创建新会话失败:', error);
        showToast('创建新会话失败: ' + error.message, 'error');
    }
}

/**
 * 非流式发送消息
 */
async function sendMessageNormal(message) {
    // 更新会话第一条消息缓存（如果是第一条消息）
    if (chatHistory.length === 0 && message) {
        await updateSessionFirstMessage(currentSessionId, message);
    }

    addMessageToUI('user', message);
    messageInput.value = '';
    updateCharCount();

    const thinkingId = addThinkingMessage();

    try {
        const headers = {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        };

        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId
            })
        });

        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                replaceThinkingWithContent(thinkingId, data.response);
                // 更新本地 chatHistory 用于显示（不保存到 localStorage）
                chatHistory.push({ role: 'user', content: message });
                chatHistory.push({ role: 'assistant', content: data.response });
                // 只更新会话列表
                updateSessionList();
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

/**
 * 流式发送消息
 */
// web/js/api.js - 修改发送消息函数

/**
 * 流式发送消息（传递模式参数）
 */
async function sendMessageStream(message) {
    hasReceivedFirstChunk = false;

    // 更新会话第一条消息缓存
    if (chatHistory.length === 0 && message) {
        await updateSessionFirstMessage(currentSessionId, message);
    }

    // 添加用户消息到 UI
    addMessageToUI('user', message);
    messageInput.value = '';
    updateCharCount();

    const thinkingId = addThinkingMessage();

    let fullResponse = '';
    let newSessionId = null;
    let hasError = false;

    try {
        const headers = {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
        };

        // 获取当前模式状态
        const requestSearchMode = getRequestSearchMode();
        const requestIsExpert = getIsExpertMode();

        console.log('发送请求 - 搜索模式:', requestSearchMode, '专家模式:', requestIsExpert);

        const response = await fetch(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                message: message,
                session_id: currentSessionId,
                stream: true,
                search_mode: requestSearchMode,  // 新增：搜索模式
                is_expert: requestIsExpert       // 新增：是否专家模式
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
                                if (!hasReceivedFirstChunk) {
                                    hasReceivedFirstChunk = true;
                                    stopThinkingAnimation(thinkingId);
                                    const newMsgId = createStreamingMessage(thinkingId);
                                    window.currentStreamingMsgId = newMsgId;
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
                                newSessionId = data.data.session_id;
                                saveSessionIdToStorage(newSessionId);
                                currentSessionId = newSessionId;
                                updateSessionDisplay();
                                updateSessionList();
                            }
                        } else if (data.type === 'end') {
                            if (data.session_id && data.session_id !== currentSessionId) {
                                saveSessionIdToStorage(data.session_id);
                                currentSessionId = data.session_id;
                                updateSessionDisplay();
                                updateSessionList();
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

        if (!hasReceivedFirstChunk && !hasError) {
            replaceThinkingWithContent(thinkingId, '收到空响应，请稍后重试。');
        }

        // 更新本地 chatHistory
        if (!hasError && fullResponse && !fullResponse.startsWith('错误:')) {
            chatHistory.push({ role: 'user', content: message });
            chatHistory.push({ role: 'assistant', content: fullResponse });
            updateSessionList();
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
 * 发送消息入口
 */
async function sendMessage() {
    if (isSending) {
        showToast('请等待上一消息完成', 'warning');
        return;
    }

    const message = messageInput.value.trim();
    if (!message) return;

    if (!currentSessionId || currentSessionId === 'null' || currentSessionId === 'undefined') {
        await initSession();
    }

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