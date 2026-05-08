// models.js - 模态框逻辑（知识库、状态、设置）

/**
 * 打开知识库模态框
 */
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

/**
 * 加载知识库统计
 */
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

/**
 * 添加知识
 */
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

/**
 * 搜索知识
 */
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

/**
 * 打开系统状态模态框
 */
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

/**
 * 打开设置模态框
 */
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

/**
 * 关闭所有模态框
 */
function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('active');
    });
}