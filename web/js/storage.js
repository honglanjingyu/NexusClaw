// web/js/storage.js - 只从 Redis 加载历史

/**
 * 保存设置到本地存储
 */
function saveSettings() {
    localStorage.setItem('api_url', API_BASE);
    localStorage.setItem('stream_enabled', isStreaming);
    localStorage.setItem('auto_scroll', autoScroll);
}

/**
 * 加载设置
 */
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

/**
 * 保存会话ID到本地存储（只保存ID，不保存消息）
 */
function saveSessionIdToStorage(sessionId) {
    if (sessionId && sessionId !== 'null' && sessionId !== 'undefined') {
        currentSessionId = sessionId;
        try {
            localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
            console.log('会话ID已保存到 localStorage:', sessionId);
        } catch (e) {
            console.warn('保存会话失败:', e);
        }
        updateURLWithSessionId(sessionId);
        updateSessionDisplay();
    }
}

/**
 * 更新会话列表（只保存会话ID列表）
 */
function updateSessionList() {
    if (!currentSessionId || currentSessionId === 'null' || currentSessionId === 'undefined') {
        return;
    }

    let sessions = [];
    try {
        sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    } catch (e) {
        sessions = [];
    }

    if (!sessions.includes(currentSessionId)) {
        sessions.unshift(currentSessionId);
        if (sessions.length > 50) sessions.pop();
        localStorage.setItem('sessions', JSON.stringify(sessions));
    }
}

/**
 * 删除会话的本地存储
 */
function deleteSessionFromStorage(sessionId) {
    let sessions = [];
    try {
        sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    } catch (e) {
        sessions = [];
    }
    const newSessions = sessions.filter(s => s !== sessionId);
    localStorage.setItem('sessions', JSON.stringify(newSessions));
    // 不删除 chat_history_* 数据
}

/**
 * 从 Redis 加载会话历史
 */
async function loadHistoryFromRedis(sessionId) {
    if (!sessionId) return [];

    try {
        const response = await fetch(`${API_BASE}/session/${sessionId}/history?limit=100`);
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.messages) {
                console.log(`从 Redis 加载历史: ${data.messages.length} 条消息`);
                return data.messages;
            }
        }
        return [];
    } catch (error) {
        console.warn('从 Redis 加载历史失败:', error);
        return [];
    }
}

/**
 * 更新历史列表 UI（只显示会话ID）
 */
function updateHistoryList() {
    let sessions = [];
    try {
        sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
    } catch (e) {
        sessions = [];
    }

    const historyList = document.getElementById('chatHistoryList');
    if (!historyList) return;

    if (sessions.length === 0) {
        historyList.innerHTML = '<div class="empty-history">暂无历史对话</div>';
        return;
    }

    historyList.innerHTML = sessions.map(sessionId => {
        const shortId = sessionId.length > 12 ? sessionId.substring(0, 12) + '...' : sessionId;
        const isActive = (sessionId === currentSessionId);

        return `
            <div class="history-item ${isActive ? 'active' : ''}" data-session-id="${sessionId}">
                <div class="history-item-content">
                    <i class="fas fa-comment"></i>
                    <span>会话: ${escapeHtml(shortId)}</span>
                </div>
                <button class="history-item-delete" data-session-id="${sessionId}" title="删除会话">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
    }).join('');

    // 绑定历史列表事件
    document.querySelectorAll('.history-item').forEach(item => {
        const sessionId = item.dataset.sessionId;
        if (!sessionId) return;

        item.addEventListener('click', (e) => {
            if (e.target.closest('.history-item-delete')) return;
            e.stopPropagation();
            if (sessionId) switchSession(sessionId);
        });

        const deleteBtn = item.querySelector('.history-item-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (sessionId) deleteSession(sessionId);
            });
        }
    });
}

/**
 * 切换会话（从 Redis 加载）
 */
async function switchSession(sessionId) {
    if (!sessionId) return;
    if (isSending) {
        showToast('请等待当前回答完成', 'warning');
        return;
    }

    if (sessionId === currentSessionId) {
        console.log('已经是当前会话，跳过切换');
        return;
    }

    console.log('切换会话:', sessionId);
    isSwitchingSession = true;

    currentSessionId = sessionId;

    // 更新显示
    updateSessionDisplay();
    updateURLWithSessionId(sessionId);

    // 保存到 localStorage（只保存会话ID）
    try {
        localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
    } catch (e) {}

    // 清空消息区域
    if (messagesArea) {
        const existingMessages = messagesArea.querySelectorAll('.message');
        existingMessages.forEach(msg => msg.remove());
    }

    // 从 Redis 加载历史
    const history = await loadHistoryFromRedis(sessionId);

    if (history.length > 0) {
        chatHistory = history.map(msg => ({
            role: msg.role,
            content: msg.content
        }));
        renderMessages();
        showToast(`已切换到会话 ${sessionId.substring(0, 8)}... (${history.length} 条消息)`, 'success');
    } else {
        chatHistory = [];
        renderWelcomeMessage();
        showToast(`已切换到会话 ${sessionId.substring(0, 8)}...`, 'info');
    }

    updateHistoryList();
    isSwitchingSession = false;
}

/**
 * 删除会话
 */
async function deleteSession(sessionId) {
    if (!sessionId) return;

    if (confirm('确定要删除这个会话吗？此操作不可恢复。')) {
        console.log('删除会话:', sessionId);

        // 调用后端删除
        try {
            await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
        } catch (e) {
            console.warn('后端删除失败:', e);
        }

        // 从会话列表中移除
        let sessions = [];
        try {
            sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        } catch (e) {}

        const newSessions = sessions.filter(s => s !== sessionId);
        localStorage.setItem('sessions', JSON.stringify(newSessions));

        // 如果删除的是当前会话
        if (sessionId === currentSessionId) {
            if (newSessions.length > 0) {
                await switchSession(newSessions[0]);
            } else {
                await handleNewChat();
            }
        } else {
            updateHistoryList();
        }

        showToast('会话已删除', 'success');
    }
}

/**
 * 清空所有会话
 */
async function clearAllSessions() {
    if (confirm('确定要清空所有会话吗？此操作不可恢复。')) {
        let sessions = [];
        try {
            sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        } catch (e) {}

        // 删除所有会话
        for (const sessionId of sessions) {
            try {
                await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
            } catch (e) {
                console.warn('删除会话失败:', sessionId, e);
            }
        }

        localStorage.removeItem('sessions');
        localStorage.removeItem(STORAGE_KEY_SESSION);

        await handleNewChat();
        showToast('所有会话已清空', 'info');
    }
}