// web/js/app.js - 在 DOMContentLoaded 中添加

document.addEventListener('DOMContentLoaded', async () => {
    initDomElements();
    loadSettings();
    loadModeSettings();  // 确保这行存在，加载模式状态

    // 显示用户名
    const username = localStorage.getItem('agent_username');
    const userNameDisplay = document.getElementById('userNameDisplay');
    if (userNameDisplay && username) {
        userNameDisplay.textContent = username;
    } else if (userNameDisplay) {
        userNameDisplay.textContent = '用户';
    }

    // 初始化会话（会从 URL 或 localStorage 恢复）
    await initSession();

    await checkHealth();
    setupEventListeners();
    setupAutoResize();

    // 注意：不要调用 loadChatHistoryFromStorage()，因为 initSession 已经处理了历史消息
});