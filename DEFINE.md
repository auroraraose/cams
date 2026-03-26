# DEFINE: Chat Persistence & Optimization

**Goal:** Enable persistent chat across pages and prevent UI blocking.

## Frontend (`src/frontend/chat.js`)
- [ ] **Persistence:**
    - [ ] Use `localStorage` to store:
        - `chat_session_id`
        - `chat_user_id`
        - `chat_history` (JSON array of messages)
        - `chat_is_open` (boolean)
    - [ ] On load, restore state from `localStorage`.
- [ ] **Optimization (Non-blocking):**
    - [ ] Debounce/Throttle Markdown rendering during streaming (e.g., update DOM only every 100ms or use `requestAnimationFrame`).
    - [ ] Ensure navigation links work even while streaming (the browser might stop the stream on unload, which is expected in MPA).
- [ ] **UI Changes:**
    - [ ] Change "Close" button behavior to just "Hide/Minimize" (which is what it effectively did, but now state persists).
    - [ ] Add explicit "Minimize" icon `_`? Or keep `X` but clarify it saves state? The user asked for "Minimize". Let's change icon to `−` (minus) for minimize.
    - [ ] Add a way to "Clear Session" (Trash icon).

## Backend
- [ ] No changes required for persistence (handled by Vertex session referencing).
- [ ] (Optional) Add check for session validity if getting 404.

## Verification
- [ ] Reload page -> Chat history should appear.
- [ ] Navigate to `entity.html` -> Chat should persist.
- [ ] Stream long message -> UI should remain responsive.
