# PLAN: Chat Interface with Vertex AI Reasoning Engine

**Goal:** Enable a chat interface in both `index.html` and `entity.html` that connects to the specified Vertex AI Reasoning Engine.

## Backend (FastAPI)
1.  **Dependencies:** Add `google-cloud-aiplatform` to `requirements.txt`.
2.  **Service:** Create `src/chat_service.py` implementing the user's snippet:
    *   Initialize `vertexai` with `PROJECT_ID="studio-example"`, `LOCATION="us-central1"`.
    *   Connect to `reasoningEngines/36666832621*****304`.
    *   Function to create session.
    *   Function to stream query (using `async generator`).
3.  **API Endpoints (`src/backend.py`):**
    *   `POST /chat/session`: Creates a new session, returns `session_id`.
    *   `POST /chat/query`: Streams the response for a given `session_id` and `message`.

## Frontend (HTML/JS)
1.  **Shared Logic:** Create a reusable `chat.js` file (or append to existing if appropriate) to handle UI toggling, session creation, and message sending.
2.  **`index.html`:** Uncomment/Add Chat Sidebar HTML and include `chat.js`.
3.  **`entity.html`:** Add Chat Sidebar HTML and include `chat.js`.
4.  **`style.css`:** Ensure chat styles are globally available (they seem to be in `style.css` already).

## Verification
*   **Manual:**
    *   Test chat on `index.html` (Home).
    *   Test chat on `entity.html` (Entity View).
    *   Verify session persistence (optional: ideally session persists across navigation if stored in sessionStorage/localStorage, but plan is just to enable it per page for now).
