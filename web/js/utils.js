// utils.js - 工具函数

/**
 * 转义 HTML 特殊字符
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 格式化 Markdown 为 HTML
 * 支持：标题、粗体、斜体、代码块、行内代码、列表、链接
 */
function formatMarkdown(text) {
    if (!text) return '';

    // 第一步：提取代码块，避免内部内容被处理
    const codeBlocks = [];
    let processed = text.replace(/```(\w*)\n?([\s\S]*?)```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push({ lang: lang || 'text', code: code.trim() });
        return `__CODE_BLOCK_${index}__`;
    });

    // 提取行内代码，临时替换
    const inlineCodes = [];
    processed = processed.replace(/`([^`]+)`/g, (match, code) => {
        const index = inlineCodes.length;
        inlineCodes.push(code);
        return `__INLINE_CODE_${index}__`;
    });

    // 转义 HTML
    let formatted = escapeHtml(processed);

    // 恢复行内代码
    inlineCodes.forEach((code, index) => {
        const placeholder = `__INLINE_CODE_${index}__`;
        formatted = formatted.replace(placeholder, `<code>${escapeHtml(code)}</code>`);
    });

    // 处理标题
    formatted = formatted.replace(/^#### (.*?)$/gm, '<h4>$1</h4>');
    formatted = formatted.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
    formatted = formatted.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
    formatted = formatted.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

    // 处理粗体和斜体
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // 处理链接
    formatted = formatted.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');

    // 处理无序列表
    const listLines = formatted.split('\n');
    let inList = false;
    let listItems = [];
    const resultLines = [];

    for (let i = 0; i < listLines.length; i++) {
        const line = listLines[i];
        const isListItem = /^[-*]\s+(.*)$/.test(line);

        if (isListItem) {
            if (!inList) {
                inList = true;
                listItems = [];
            }
            const content = line.replace(/^[-*]\s+/, '');
            listItems.push(`<li>${content}</li>`);
        } else {
            if (inList) {
                resultLines.push('<ul>');
                resultLines.push(...listItems);
                resultLines.push('</ul>');
                inList = false;
                listItems = [];
            }
            resultLines.push(line);
        }
    }

    if (inList) {
        resultLines.push('<ul>');
        resultLines.push(...listItems);
        resultLines.push('</ul>');
    }

    formatted = resultLines.join('\n');

    // 处理换行
    formatted = formatted.replace(/\n\n/g, '</p><p>');
    formatted = formatted.replace(/\n/g, '<br>');

    // 包装段落
    if (!formatted.startsWith('<h') && !formatted.startsWith('<ul') && !formatted.startsWith('<pre')) {
        formatted = `<p>${formatted}</p>`;
    }

    // 恢复代码块
    codeBlocks.forEach((block, index) => {
        const placeholder = `__CODE_BLOCK_${index}__`;
        const langClass = block.lang !== 'text' ? ` class="language-${block.lang}"` : '';
        const escapedCode = escapeHtml(block.code);
        formatted = formatted.replace(
            placeholder,
            `<pre><code${langClass}>${escapedCode}</code></pre>`
        );
    });

    return formatted;
}

/**
 * Toast 通知
 */
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

/**
 * 生成会话 ID
 */
function generateSessionId() {
    return 'local_' + Math.random().toString(36).substring(2, 10);
}

/**
 * 滚动到底部
 */
function scrollToBottom() {
    if (autoScroll && messagesArea) {
        messagesArea.scrollTop = messagesArea.scrollHeight;
    }
}

/**
 * 更新字符计数
 */
function updateCharCount() {
    const count = messageInput.value.length;
    if (charCountSpan) charCountSpan.textContent = `${count} 字符`;
}

/**
 * 设置输入框自动调整高度
 */
function setupAutoResize() {
    messageInput.addEventListener('input', () => {
        updateCharCount();
        messageInput.style.height = 'auto';
        messageInput.style.height = Math.min(messageInput.scrollHeight, 150) + 'px';
    });
}