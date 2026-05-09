// web/js/config.js (修改版)

// API 配置
let API_BASE = '/api/v1';
let currentSessionId = null;
let chatHistory = [];
let isStreaming = true;
let autoScroll = true;
let isSending = false;
let thinkingAnimationInterval = null;
let hasReceivedFirstChunk = false;
let nextMessageId = 0;

// 搜索模式枚举
const SearchMode = {
    KNOWLEDGE: 'knowledge',  // 知识库搜索
    WEB: 'web',              // 网络搜索
    NONE: 'none'             // 不搜索
};

// 全局模式状态
let currentSearchMode = SearchMode.NONE;  // 当前搜索模式
let isExpertMode = false;                 // 是否专家模式

// DOM 元素引用
let knowledgeSearchBtn, webSearchBtn, expertModeBtn;

// 从 URL 获取 session_id
function getSessionIdFromURL() {
    const urlParams = new URLSearchParams(window.location.search);
    const session = urlParams.get('session');
    console.log('从 URL 获取 session_id:', session);
    return session;
}

// 更新 URL 中的 session_id（不刷新页面）
function updateURLWithSessionId(sessionId) {
    if (!sessionId || sessionId === 'null' || sessionId === 'undefined') {
        console.log('跳过更新 URL: session_id 无效', sessionId);
        return;
    }

    const url = new URL(window.location.href);
    const currentSession = url.searchParams.get('session');

    if (currentSession !== sessionId) {
        url.searchParams.set('session', sessionId);
        window.history.replaceState({}, '', url);
        console.log('URL 已更新:', url.toString());
    }
}

// 清除 URL 中的 session_id
function clearURLSessionId() {
    const url = new URL(window.location.href);
    url.searchParams.delete('session');
    window.history.replaceState({}, '', url);
    console.log('已清除 URL 中的 session 参数');
}

// 更新会话显示
function updateSessionDisplay() {
    if (sessionIdDisplay) {
        if (currentSessionId && currentSessionId !== 'null' && currentSessionId !== 'undefined') {
            const shortId = currentSessionId.substring(0, 8) + '...';
            sessionIdDisplay.textContent = `会话: ${shortId}`;
            sessionIdDisplay.title = `会话ID: ${currentSessionId}`;
        } else {
            sessionIdDisplay.textContent = `会话: --`;
        }
    }
}

// 本地存储 key
const STORAGE_KEY_SESSION = 'agent_current_session_id';

// 保存会话ID到本地和 URL
function saveSessionIdToStorage(sessionId) {
    if (sessionId && sessionId !== 'null' && sessionId !== 'undefined') {
        currentSessionId = sessionId;
        try {
            localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
            console.log('会话已保存到 localStorage:', sessionId);
        } catch (e) {
            console.warn('保存会话失败:', e);
        }
        updateURLWithSessionId(sessionId);
        updateSessionDisplay();
    }
}

// 清除保存的会话
function clearSavedSession() {
    currentSessionId = null;
    try {
        localStorage.removeItem(STORAGE_KEY_SESSION);
        console.log('已清除 localStorage 中的会话');
    } catch (e) {
        console.warn('清除会话失败:', e);
    }
    clearURLSessionId();
    updateSessionDisplay();
}

// DOM 元素引用
let messagesArea, messageInput, sendBtn, newChatBtn, clearAllBtn;
let sidebarToggle, menuBtn, sidebar, sessionIdDisplay, copySessionBtn;
let knowledgeBtn, statsBtn, settingsBtn, streamToggle, autoScrollToggle;
let apiUrlInput, charCountSpan, statusIcon, statusText;

function initDomElements() {
    messagesArea = document.getElementById('messagesArea');
    messageInput = document.getElementById('messageInput');
    sendBtn = document.getElementById('sendBtn');
    newChatBtn = document.getElementById('newChatBtn');
    clearAllBtn = document.getElementById('clearAllBtn');
    sidebarToggle = document.getElementById('sidebarToggle');
    menuBtn = document.getElementById('menuBtn');
    sidebar = document.getElementById('sidebar');
    sessionIdDisplay = document.getElementById('sessionIdDisplay');
    copySessionBtn = document.getElementById('copySessionBtn');
    knowledgeBtn = document.getElementById('knowledgeBtn');
    statsBtn = document.getElementById('statsBtn');
    settingsBtn = document.getElementById('settingsBtn');
    streamToggle = document.getElementById('streamToggle');
    autoScrollToggle = document.getElementById('autoScrollToggle');
    apiUrlInput = document.getElementById('apiUrl');
    charCountSpan = document.getElementById('charCount');
    statusIcon = document.getElementById('statusIcon');
    statusText = document.getElementById('statusText');
    knowledgeSearchBtn = document.getElementById('knowledgeSearchBtn');
    webSearchBtn = document.getElementById('webSearchBtn');
    expertModeBtn = document.getElementById('expertModeBtn');
}

// 保存模式设置到 localStorage
function saveModeSettings() {
    localStorage.setItem('search_mode', currentSearchMode);
    localStorage.setItem('expert_mode', isExpertMode);
}

// 加载模式设置
function loadModeSettings() {
    const savedMode = localStorage.getItem('search_mode');
    if (savedMode && Object.values(SearchMode).includes(savedMode)) {
        currentSearchMode = savedMode;
    }

    const savedExpert = localStorage.getItem('expert_mode');
    if (savedExpert !== null) {
        isExpertMode = savedExpert === 'true';
    }

    // 更新按钮状态
    updateModeButtons();
}

function updateModeButtons() {
    if (knowledgeSearchBtn) {
        if (currentSearchMode === SearchMode.KNOWLEDGE) {
            knowledgeSearchBtn.classList.add('active');
        } else {
            knowledgeSearchBtn.classList.remove('active');
        }
        // 专家模式下禁用搜索按钮（视觉上半透明）
        if (isExpertMode) {
            knowledgeSearchBtn.style.opacity = '0.5';
            knowledgeSearchBtn.style.cursor = 'not-allowed';
        } else {
            knowledgeSearchBtn.style.opacity = '1';
            knowledgeSearchBtn.style.cursor = 'pointer';
        }
    }

    if (webSearchBtn) {
        if (currentSearchMode === SearchMode.WEB) {
            webSearchBtn.classList.add('active');
        } else {
            webSearchBtn.classList.remove('active');
        }
        if (isExpertMode) {
            webSearchBtn.style.opacity = '0.5';
            webSearchBtn.style.cursor = 'not-allowed';
        } else {
            webSearchBtn.style.opacity = '1';
            webSearchBtn.style.cursor = 'pointer';
        }
    }

    if (expertModeBtn) {
        if (isExpertMode) {
            expertModeBtn.classList.add('active');
        } else {
            expertModeBtn.classList.remove('active');
        }
    }
}

// 获取当前请求的搜索模式（用于发送到后端）
function getRequestSearchMode() {
    if (isExpertMode) return 'none';  // 专家模式不使用搜索按钮
    return currentSearchMode;
}

// 获取是否专家模式
function getIsExpertMode() {
    return isExpertMode;
}

function forceNewSession() {
    // 清除 localStorage 中的会话数据
    try {
        localStorage.removeItem(STORAGE_KEY_SESSION);
        localStorage.removeItem('sessions');
        // 清除所有以 chat_history_ 开头的 key
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith('chat_history_')) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log('已清除所有会话数据');
    } catch (e) {
        console.warn('清除会话数据失败:', e);
    }

    // 清除 URL 参数
    clearURLSessionId();

    // 重置全局变量
    currentSessionId = null;
    chatHistory = [];

    // 刷新页面
    window.location.href = window.location.pathname;
}