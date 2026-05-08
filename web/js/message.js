// web/js/message.js - 完整修复版

/**
 * 添加思考消息
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
                <span class="thinking-dots">.</span>
            </div>
            <div class="message-meta"></div>
        </div>
    `;

    messagesArea.appendChild(messageDiv);
    startThinkingAnimation(messageId);

    if (autoScroll) scrollToBottom();
    return messageId;
}

/**
 * 启动思考动画
 */
function startThinkingAnimation(messageId) {
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
    }

    const messageDiv = document.getElementById(messageId);
    if (!messageDiv) return;

    const dotsSpan = messageDiv.querySelector('.thinking-dots');
    if (!dotsSpan) return;

    let dotCount = 1;

    thinkingAnimationInterval = setInterval(() => {
        const currentDiv = document.getElementById(messageId);
        if (!currentDiv) {
            if (thinkingAnimationInterval) {
                clearInterval(thinkingAnimationInterval);
                thinkingAnimationInterval = null;
            }
            return;
        }

        const currentDotsSpan = currentDiv.querySelector('.thinking-dots');
        if (!currentDotsSpan) return;

        dotCount = (dotCount % 3) + 1;
        currentDotsSpan.textContent = '.'.repeat(dotCount);
    }, 500);
}

/**
 * 停止思考动画
 */
function stopThinkingAnimation(thinkingMessageId) {
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
        thinkingAnimationInterval = null;
    }

    const thinkingDiv = document.getElementById(thinkingMessageId);
    if (thinkingDiv) {
        thinkingDiv.style.display = 'none';
    }
}

/**
 * 创建用于流式输出的消息
 */
function createStreamingMessage(oldThinkingId) {
    const oldDiv = document.getElementById(oldThinkingId);
    if (!oldDiv) {
        return addEmptyAssistantMessage();
    }

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

    oldDiv.parentNode.replaceChild(messageDiv, oldDiv);

    if (autoScroll) scrollToBottom();
    return messageId;
}

/**
 * 添加空助手消息
 */
function addEmptyAssistantMessage() {
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
            <div class="message-meta">${new Date().toLocaleTimeString()}</div>
        </div>
    `;

    messagesArea.appendChild(messageDiv);
    return messageId;
}

/**
 * 更新流式消息内容
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

/**
 * 替换思考消息为实际内容
 */
function replaceThinkingWithContent(thinkingMessageId, content) {
    if (thinkingAnimationInterval) {
        clearInterval(thinkingAnimationInterval);
        thinkingAnimationInterval = null;
    }

    const thinkingDiv = document.getElementById(thinkingMessageId);
    if (!thinkingDiv) {
        return addMessageToUI('assistant', content);
    }

    const textDiv = thinkingDiv.querySelector('.message-text');
    if (textDiv) {
        thinkingDiv.classList.remove('thinking');
        textDiv.innerHTML = formatMarkdown(content);
    }

    const newId = `msg_${Date.now()}_${nextMessageId++}`;
    thinkingDiv.id = newId;

    const metaSpan = thinkingDiv.querySelector('.message-meta');
    if (metaSpan) {
        metaSpan.textContent = new Date().toLocaleTimeString();
    }

    return newId;
}

/**
 * 添加消息到 UI
 */
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

// 渲染锁，防止重复渲染
let isRenderingMessages = false;
let lastRenderedHash = '';

/**
 * 计算消息哈希，用于检测变化
 */
function getMessagesHash(messages) {
    if (!messages || messages.length === 0) return '';
    return messages.map(m => `${m.role}:${m.content.substring(0, 50)}`).join('|');
}

/**
 * 渲染所有消息
 */
function renderMessages() {
    if (!messagesArea) return;

    // 防止重复渲染
    if (isRenderingMessages) {
        console.log('已经在渲染消息，跳过');
        return;
    }

    // 检查消息是否真的变化了
    const currentHash = getMessagesHash(chatHistory);
    if (currentHash === lastRenderedHash && chatHistory.length > 0) {
        console.log('消息未变化，跳过渲染');
        return;
    }
    lastRenderedHash = currentHash;

    isRenderingMessages = true;

    if (chatHistory.length === 0) {
        // 只有在没有消息时才显示欢迎消息
        const existingMessages = messagesArea.querySelectorAll('.message:not(.welcome-message)');
        if (existingMessages.length === 0) {
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
        isRenderingMessages = false;
        return;
    }

    // 检查是否已经有相同数量的消息
    const existingCount = messagesArea.querySelectorAll('.message:not(.welcome-message)').length;
    if (existingCount === chatHistory.length) {
        console.log('消息数量相同，跳过渲染');
        isRenderingMessages = false;
        return;
    }

    // 移除欢迎消息
    const welcomeMsg = messagesArea.querySelector('.welcome-message');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    // 清空现有消息
    const existingMessages = messagesArea.querySelectorAll('.message');
    existingMessages.forEach(msg => msg.remove());

    // 渲染所有消息
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
    isRenderingMessages = false;
}

/**
 * 清空消息区域
 */
function clearMessagesArea() {
    if (!messagesArea) return;

    const messages = messagesArea.querySelectorAll('.message');
    messages.forEach(msg => msg.remove());

    renderWelcomeMessage();
}

/**
 * 获取最后一条用户消息
 */
function getLastUserMessage() {
    for (let i = chatHistory.length - 1; i >= 0; i--) {
        if (chatHistory[i].role === 'user') {
            return chatHistory[i].content;
        }
    }
    return null;
}

/**
 * 获取最后一条助手消息
 */
function getLastAssistantMessage() {
    for (let i = chatHistory.length - 1; i >= 0; i--) {
        if (chatHistory[i].role === 'assistant') {
            return chatHistory[i].content;
        }
    }
    return null;
}