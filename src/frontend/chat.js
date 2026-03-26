document.addEventListener('DOMContentLoaded', () => {
  // --- Configuration ---
  const CHAT_BACKEND_URL = '';
  const STORAGE_KEY_SESSION = 'chat_session_id';
  const STORAGE_KEY_USER = 'chat_user_id';
  const STORAGE_KEY_HISTORY = 'chat_history'; // Stores array of {role, html}
  const STORAGE_KEY_STATE = 'chat_is_open';

  // --- State ---
  // Restore or Init User ID
  let userId = localStorage.getItem(STORAGE_KEY_USER);
  if (!userId) {
    userId = 'user_' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem(STORAGE_KEY_USER, userId);
  }

  let sessionId = localStorage.getItem(STORAGE_KEY_SESSION); // Restore session if exists
  let isChatOpen = localStorage.getItem(STORAGE_KEY_STATE) === 'true'; // Restore open state

  // --- HTML Injection ---
  injectChatUI();

  // --- Elements ---
  const chatSidebar = document.getElementById('chat-sidebar');
  const chatToggleBtn = document.getElementById('chat-toggle-btn');
  const chatCloseBtn = document.getElementById('chat-close-btn'); // Now acts as minimize
  const chatMessages = document.getElementById('chat-messages');
  const chatInput = document.getElementById('chat-input-field');
  const chatSendBtn = document.getElementById('chat-send-btn');
  const clearChatBtn = document.getElementById('chat-clear-btn'); // New button

  // --- Restoring UI State ---
  if (isChatOpen) {
    chatSidebar.classList.add('open');
    restoreHistory();
  } else {
    // Even if closed, we might want to restore history so it's there when opened
    restoreHistory();
  }

  // --- Event Listeners ---
  if (chatToggleBtn) chatToggleBtn.addEventListener('click', toggleChat);
  if (chatCloseBtn) chatCloseBtn.addEventListener('click', toggleChat);

  if (clearChatBtn) {
    clearChatBtn.addEventListener('click', () => {
      if (confirm("Clear chat history?")) clearSession();
    });
  }

  if (chatSendBtn) chatSendBtn.addEventListener('click', sendMessage);
  if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage();
    });
  }

  // --- Functions ---

  function injectChatUI() {
    if (document.getElementById('chat-sidebar')) return;

    const body = document.body;

    // Toggle Button
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'chat-toggle-btn';
    toggleBtn.innerHTML = '💬';
    body.appendChild(toggleBtn);

    // Sidebar
    const sidebar = document.createElement('div');
    sidebar.id = 'chat-sidebar';
    sidebar.innerHTML = `
            <div class="chat-header">
                <h3>AI Assistant</h3>
                <div class="chat-controls">
                    <button id="chat-clear-btn" title="Clear History" style="margin-right: 10px; background:none; border:none; color:white; cursor:pointer;">🗑️</button>
                    <button id="chat-close-btn" title="Minimize">─</button>
                </div>
            </div>
            <div id="chat-messages">
                <div class="chat-message assistant">
                    <div class="message-bubble">
                        Hello! I am your CAM Assistant. How can I help you today?
                    </div>
                </div>
            </div>
            <div class="chat-input-area">
                <input type="text" id="chat-input-field" placeholder="Ask a question..." autocomplete="off">
                <button id="chat-send-btn">➤</button>
            </div>
        `;
    body.appendChild(sidebar);
  }

  function toggleChat() {
    isChatOpen = !isChatOpen;
    localStorage.setItem(STORAGE_KEY_STATE, isChatOpen); // Persist state

    if (isChatOpen) {
      chatSidebar.classList.add('open');
      // If we have no session, init one (silent)
      if (!sessionId) {
        initializeSession();
      }
      setTimeout(() => chatInput.focus(), 300);
    } else {
      chatSidebar.classList.remove('open');
    }
  }

  function clearSession() {
    localStorage.removeItem(STORAGE_KEY_SESSION);
    localStorage.removeItem(STORAGE_KEY_HISTORY);
    localStorage.removeItem(STORAGE_KEY_STATE);
    sessionId = null;
    chatMessages.innerHTML = `
            <div class="chat-message assistant">
                <div class="message-bubble">
                    Chat history cleared. How can I help?
                </div>
            </div>`;
  }

  function restoreHistory() {
    const historyJson = localStorage.getItem(STORAGE_KEY_HISTORY);
    if (historyJson) {
      try {
        const history = JSON.parse(historyJson);
        // Clear default greeting if we have history
        if (history.length > 0) chatMessages.innerHTML = '';

        history.forEach(msg => {
          appendMessageToUI(msg.role, msg.html, false); // false = don't save again
        });
        chatMessages.scrollTop = chatMessages.scrollHeight;
      } catch (e) {
        console.error("Failed to restore history", e);
      }
    }
  }

  function saveMessage(role, htmlContent) {
    let history = [];
    const existing = localStorage.getItem(STORAGE_KEY_HISTORY);
    if (existing) {
      try { history = JSON.parse(existing); } catch (e) { }
    }
    history.push({ role, html: htmlContent });
    localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(history));
  }

  async function initializeSession() {
    try {
      console.log("Initializing chat session for user:", userId);
      // If we already have a sessionId in storage, verify it or just reuse?
      // Vertex sessions might expire, but let's try to reuse or create new if 404.
      // For now, if we have local ID, we assume it's valid. 
      // Better pattern: create new only if null.

      if (sessionId) return;

      const response = await fetch(`${CHAT_BACKEND_URL}/chat/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });
      const data = await response.json();
      if (data.success) {
        sessionId = data.session_id;
        localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
        console.log("Session created:", sessionId);
      } else {
        console.error("Failed to create session:", data);
      }
    } catch (e) {
      console.error("Error creating session:", e);
    }
  }

  async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // Add user message
    const userHtml = text.replace(/</g, "&lt;").replace(/>/g, "&gt;"); // Basic sanitize
    appendMessageToUI('user', userHtml, true);
    chatInput.value = '';

    if (!sessionId) {
      await initializeSession();
      if (!sessionId) return;
    }

    // Placeholder for assistant
    const assistantMsgDiv = appendMessageToUI('assistant', '<span class="typing">...</span>', false);
    const bubbleContent = assistantMsgDiv.querySelector('.message-bubble');

    try {
        bubbleContent.textContent = '';

        const response = await fetch(`${CHAT_BACKEND_URL}/chat/query`, {
          method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_id: sessionId,
              message: text,
              user_id: userId
            })
          });

        if (!response.ok) throw new Error("Network response was not ok");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let accumulatedText = "";
        let renderTimeout = null;

        // Converter for Markdown
        let converter = null;
        if (typeof showdown !== 'undefined') {
          converter = new showdown.Converter({
            tables: true,
            simplifiedAutoLink: true,
            strikethrough: true,
            tasklists: true
          });
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');

          let chunkText = "";
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.replace('data: ', '').trim();
              if (dataStr === '[DONE]') continue;
              try {
                const data = JSON.parse(dataStr);
                if (data.text) {
                  let t = data.text;
                  if (typeof t === 'object') t = JSON.stringify(t);
                  chunkText += t;
                }
              } catch (e) { }
            }
          }

            if (chunkText) {
              accumulatedText += chunkText;

              // Throttle rendering to avoid blocking UI
              if (!renderTimeout) {
                renderTimeout = requestAnimationFrame(() => {
                  if (converter) {
                    bubbleContent.innerHTML = converter.makeHtml(accumulatedText);
                  } else {
                    bubbleContent.textContent = accumulatedText;
                  }
                  chatMessages.scrollTop = chatMessages.scrollHeight;
                  renderTimeout = null;
                });
              }
            }
          }

        // Final render to ensure nothing missed
        if (converter) {
          bubbleContent.innerHTML = converter.makeHtml(accumulatedText);
        } else {
          bubbleContent.textContent = accumulatedText;
        }

        // Save final assistant message to history
        saveMessage('assistant', bubbleContent.innerHTML);

      } catch (e) {
        console.error("Error sending message:", e);
        bubbleContent.textContent += " [Error: Connection failed]";
      }
  }

  function appendMessageToUI(role, htmlContent, save = true) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = htmlContent;

    msgDiv.appendChild(bubble);
    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    if (save) {
      saveMessage(role, htmlContent);
    }
    return msgDiv;
  }
});
