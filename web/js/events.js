// web/js/events.js - 完整修复版

/**
 * 键盘事件处理
 */
function handleKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

/**
 * 设置所有事件监听器
 */
function setupEventListeners() {
    // 主要按钮
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);
    if (messageInput) messageInput.addEventListener('keydown', handleKeydown);
    if (newChatBtn) newChatBtn.addEventListener('click', handleNewChat);
    if (clearAllBtn) clearAllBtn.addEventListener('click', clearAllSessions);
    if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
    if (menuBtn) menuBtn.addEventListener('click', toggleMobileSidebar);
    if (copySessionBtn) copySessionBtn.addEventListener('click', copySessionId);
    if (knowledgeBtn) knowledgeBtn.addEventListener('click', openKnowledgeModal);
    if (statsBtn) statsBtn.addEventListener('click', openStatsModal);
    if (settingsBtn) settingsBtn.addEventListener('click', openSettingsModal);

    // 登出按钮
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (confirm('确定要退出登录吗？')) {
                // 清除本地存储
                localStorage.removeItem('agent_token');
                localStorage.removeItem('agent_user_id');
                localStorage.removeItem('agent_username');
                localStorage.removeItem('agent_current_session_id');
                localStorage.removeItem('sessions');

                // 清除所有会话相关的缓存
                if (window.sessionFirstMessages) {
                    window.sessionFirstMessages = {};
                }

                // 跳转到登录页
                window.location.href = '/login.html';
            }
        });
    }

    // 设置开关
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

    // 快捷提问
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
        btn.addEventListener('click', closeAllModals);
    });

    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });

    // 点击模态框外部关闭（备用）
    document.addEventListener('click', (e) => {
        if (e.target.classList && e.target.classList.contains('modal')) {
            e.target.classList.remove('active');
        }
    });

    // ESC 键关闭模态框
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAllModals();
        }
    });
    if (knowledgeSearchBtn) {
    knowledgeSearchBtn.addEventListener('click', () => {
        // 专家模式下不允许切换搜索按钮
        if (isExpertMode) {
            showToast('专家模式下，搜索将由 AI 自动决策', 'info');
            return;
        }

        if (currentSearchMode === SearchMode.KNOWLEDGE) {
            currentSearchMode = SearchMode.NONE;
        } else {
            currentSearchMode = SearchMode.KNOWLEDGE;
            // 如果联网搜索是激活的，先关闭（二选一）
            if (webSearchBtn && webSearchBtn.classList.contains('active')) {
                webSearchBtn.classList.remove('active');
            }
        }
        updateModeButtons();
        saveModeSettings();
        showToast(currentSearchMode === SearchMode.KNOWLEDGE ? '✅ 知识库搜索已开启，联网搜索已关闭' : '知识库搜索已关闭', 'info');
    });
}

// 联网搜索按钮
if (webSearchBtn) {
    webSearchBtn.addEventListener('click', () => {
        // 专家模式下不允许切换搜索按钮
        if (isExpertMode) {
            showToast('专家模式下，搜索将由 AI 自动决策', 'info');
            return;
        }

        if (currentSearchMode === SearchMode.WEB) {
            currentSearchMode = SearchMode.NONE;
        } else {
            currentSearchMode = SearchMode.WEB;
            // 如果知识库搜索是激活的，先关闭（二选一）
            if (knowledgeSearchBtn && knowledgeSearchBtn.classList.contains('active')) {
                knowledgeSearchBtn.classList.remove('active');
            }
        }
        updateModeButtons();
        saveModeSettings();
        showToast(currentSearchMode === SearchMode.WEB ? '🌐 联网搜索已开启，知识库搜索已关闭' : '联网搜索已关闭', 'info');
    });
}

// 专家模式按钮
if (expertModeBtn) {
    expertModeBtn.addEventListener('click', () => {
        isExpertMode = !isExpertMode;
        updateModeButtons();
        saveModeSettings();

        if (isExpertMode) {
            showToast('🧠 专家模式已开启，AI 将自主决定是否使用知识库和联网搜索', 'success');
        } else {
            showToast('专家模式已关闭，搜索模式恢复为手动选择', 'info');
        }
    });}
}

/**
 * 创建新对话（用于侧边栏按钮）
 */
function createNewChat() {
    handleNewChat();
}

/**
 * 清空所有会话
 */
function clearAllSessions() {
    if (confirm('确定要清空所有会话吗？此操作不可恢复。')) {
        // 清除 localStorage 中的所有会话数据
        const sessions = JSON.parse(localStorage.getItem('sessions') || '[]');
        sessions.forEach(session => {
            localStorage.removeItem(`chat_history_${session}`);
        });
        localStorage.removeItem('sessions');

        // 清除当前会话
        clearSavedSession();

        // 清除缓存
        if (window.sessionFirstMessages) {
            window.sessionFirstMessages = {};
        }

        // 创建新会话
        handleNewChat();

        showToast('所有会话已清空', 'info');
    }
}