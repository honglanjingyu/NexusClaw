// web/js/sidebar.js - 完整修复版（只从 Redis 加载）

/**
 * 切换侧边栏折叠状态
 */
function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
}

/**
 * 切换移动端侧边栏
 */
function toggleMobileSidebar() {
    sidebar.classList.toggle('mobile-open');
}

/**
 * 复制会话 ID
 */
function copySessionId() {
    if (currentSessionId && currentSessionId !== 'null' && currentSessionId !== 'undefined') {
        navigator.clipboard.writeText(currentSessionId);
        showToast('会话ID已复制', 'success');
    } else {
        showToast('暂无有效会话', 'warning');
    }
}

/**
 * 更新历史列表 UI - 只显示会话ID
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

        // 点击项目主体切换会话
        item.addEventListener('click', (e) => {
            if (e.target.closest('.history-item-delete')) return;
            e.stopPropagation();
            if (sessionId) switchSession(sessionId);
        });

        // 删除按钮
        const deleteBtn = item.querySelector('.history-item-delete');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (sessionId) deleteSession(sessionId);
            });
        }
    });
}

// 切换会话锁，防止重复切换
let isSwitchingSession = false;

/**
 * 切换会话 - 只从 Redis 加载
 */
async function switchSession(sessionId) {
    if (!sessionId) return;
    if (isSending) {
        showToast('请等待当前回答完成', 'warning');
        return;
    }

    // 防止重复切换
    if (isSwitchingSession) {
        console.log('已经在切换会话，跳过');
        return;
    }

    if (sessionId === currentSessionId) {
        console.log('已经是当前会话，跳过切换');
        return;
    }

    isSwitchingSession = true;

    console.log('切换会话:', sessionId);

    currentSessionId = sessionId;

    // 更新显示
    if (sessionIdDisplay) {
        const shortId = sessionId.length > 8 ? sessionId.substring(0, 8) + '...' : sessionId;
        sessionIdDisplay.textContent = `会话: ${shortId}`;
        sessionIdDisplay.title = `会话ID: ${sessionId}`;
    }

    // 更新 URL
    updateURLWithSessionId(sessionId);

    // 保存到 localStorage（只保存会话ID）
    try {
        localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
    } catch (e) {
        console.warn('保存会话失败:', e);
    }

    // 清空当前消息区
    if (messagesArea) {
        const existingMessages = messagesArea.querySelectorAll('.message');
        existingMessages.forEach(msg => msg.remove());
    }

    // 从 Redis 加载会话历史
    try {
        const response = await fetch(`${API_BASE}/session/${sessionId}/history?limit=100`);
        if (response.ok) {
            const data = await response.json();
            if (data.success && data.messages && data.messages.length > 0) {
                chatHistory = data.messages.map(msg => ({
                    role: msg.role,
                    content: msg.content
                }));
                renderMessages();
                showToast(`已切换到会话 ${sessionId.substring(0, 8)}... (${data.messages.length} 条消息)`, 'success');
            } else {
                chatHistory = [];
                renderWelcomeMessage();
                showToast(`已切换到会话 ${sessionId.substring(0, 8)}...`, 'info');
            }
        } else {
            chatHistory = [];
            renderWelcomeMessage();
            showToast(`已切换到会话 ${sessionId.substring(0, 8)}...`, 'info');
        }
    } catch (error) {
        console.error('加载会话历史失败:', error);
        chatHistory = [];
        renderWelcomeMessage();
        showToast(`切换到会话失败: ${error.message}`, 'error');
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
            const response = await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' });
            if (!response.ok) {
                console.warn('后端删除返回:', response.status);
            }
        } catch (e) {
            console.warn('后端删除失败:', e);
        }

        // 从会话列表中移除
        let sessions = [];
        try {
            sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        } catch (e) {
            sessions = [];
        }

        const newSessions = sessions.filter(s => s !== sessionId);
        localStorage.setItem('sessions', JSON.stringify(newSessions));

        // 如果删除的是当前会话
        if (sessionId === currentSessionId) {
            if (newSessions.length > 0) {
                // 切换到第一个会话
                await switchSession(newSessions[0]);
            } else {
                // 没有其他会话，创建新会话
                await handleNewChat();
            }
        } else {
            updateHistoryList();
        }

        showToast('会话已删除', 'success');
    }
}

/**
 * 创建新对话
 */
async function createNewChat() {
    if (isSending) {
        showToast('请等待当前回答完成', 'warning');
        return;
    }

    // 防止重复创建
    if (isSwitchingSession) {
        console.log('正在切换会话，跳过创建');
        return;
    }

    isSwitchingSession = true;

    console.log('创建新对话');

    // 调用后端创建新会话
    try {
        const response = await fetch(`${API_BASE}/session/create?user_id=web_user`);
        if (response.ok) {
            const data = await response.json();
            if (data.session_id) {
                currentSessionId = data.session_id;

                if (sessionIdDisplay) {
                    const shortId = currentSessionId.substring(0, 8) + '...';
                    sessionIdDisplay.textContent = `会话: ${shortId}`;
                }

                // 更新 URL
                updateURLWithSessionId(currentSessionId);

                // 保存到 localStorage
                try {
                    localStorage.setItem(STORAGE_KEY_SESSION, currentSessionId);
                } catch (e) {}

                // 更新会话列表
                updateSessionList();

                chatHistory = [];
                renderWelcomeMessage();
                updateHistoryList();

                showToast('✨ 已创建新会话', 'success');
            } else {
                throw new Error('No session_id returned');
            }
        } else {
            throw new Error(`HTTP ${response.status}`);
        }
    } catch (error) {
        console.error('创建新会话失败:', error);
        // 降级方案：生成本地会话ID
        currentSessionId = 'local_' + Math.random().toString(36).substring(2, 10);
        if (sessionIdDisplay) {
            const shortId = currentSessionId.substring(0, 8) + '...';
            sessionIdDisplay.textContent = `会话: ${shortId}`;
        }
        updateURLWithSessionId(currentSessionId);
        try {
            localStorage.setItem(STORAGE_KEY_SESSION, currentSessionId);
        } catch (e) {}
        updateSessionList();
        chatHistory = [];
        renderWelcomeMessage();
        updateHistoryList();
        showToast('✨ 已创建新会话（本地）', 'success');
    }

    // 关闭移动端侧边栏
    if (sidebar) {
        sidebar.classList.remove('mobile-open');
    }

    isSwitchingSession = false;
}

/**
 * 清空所有会话
 */
async function clearAllSessions() {
    if (confirm('确定要清空所有会话吗？此操作不可恢复。')) {
        let sessions = [];
        try {
            sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        } catch (e) {
            sessions = [];
        }

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

        // 创建新会话
        await handleNewChat();

        showToast('所有会话已清空', 'info');
    }
}