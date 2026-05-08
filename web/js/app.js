// web/js/app.js - 完整修复版

document.addEventListener('DOMContentLoaded', async () => {
    initDomElements();
    loadSettings();

    // 初始化会话（会从 URL 或 localStorage 恢复）
    await initSession();

    await checkHealth();
    setupEventListeners();
    setupAutoResize();

    // 注意：不要调用 loadChatHistoryFromStorage()，因为 initSession 已经处理了历史消息
});