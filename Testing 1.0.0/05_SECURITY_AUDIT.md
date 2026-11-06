# 05 — Comprehensive Security Audit

**Audit Version:** 1.0.0  
**Target Architecture:** AI Desktop Friend (AI Friend A1)  
**Security Standard:** OWASP Top 10 (2021) / CWE / CVSS v3.1  
**Audit Scope:** Local Network Boundaries, API & WebSocket Security, WebEngine Sandbox Integrity, Zero-Cloud Data Privacy, and Operating System Process Isolation.

---

## 1. Threat Model & Security Boundaries

```mermaid
flowchart LR
    subgraph External_Untrusted ["External / Internet (Untrusted)"]
        Internet["Public Internet\n(Blocked - No Cloud Outbound)"]
        Browser["Third-Party Web Browser\n(Malicious Websites)"]
    end

    subgraph Host_Boundary ["Local Windows Host (127.0.0.1)"]
        subgraph AI_Friend ["AI Desktop Friend Process Tree"]
            App["main.py (PySide6 / Qt6)"]
            FastAPI["FastAPI / Starlette\n(Port 8765)"]
            WebEngine["Chromium WebEngine View\n(Chat UI)"]
            SQLite["%APPDATA%/AIDesktopFriend/\nconversations.db"]
        end
        OllamaDaemon["Ollama Daemon\n(Port 11434)"]
        OtherProcesses["Other Local Applications\n(User Space)"]
    end

    Browser -- "Cross-Origin HTTP / WS\n(Blocked by CORS/Origin)" -.-x FastAPI
    FastAPI <--> WebEngine
    App --> SQLite
    App --> OllamaDaemon
    App -- "Zero External Calls\n(100% Offline)" -.-x Internet
    OtherProcesses -- "Local Unauthenticated REST\n(Vulnerability SEC-002)" --> FastAPI
```

### Trust Boundary Definitions
1. **Loopback Network Boundary (`127.0.0.1:8765`):** Exposes REST routes and WebSocket channels to the embedded chat UI.
2. **Chromium WebEngine View:** Renders HTML/CSS/JS frontend inside a QtWebEngine container. Must not execute arbitrary external JavaScript or navigate to external URLs.
3. **Local Inference Interface (`127.0.0.1:11434`):** Local Ollama REST daemon.
4. **Data at Rest (`%APPDATA%\AIDesktopFriend`):** Stores unencrypted SQLite conversation logs, application settings, and audio cache.

---

## 2. Zero-Cloud Privacy Verification

An exhaustive network inspection was conducted across all modules to verify whether user prompts, audio samples, or conversational data leak to cloud AI endpoints.

### Traffic & Code Inspection Results
- **LLM Inference:** [`app/ai/ollama_client.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/ai/ollama_client.py) connects exclusively to `http://127.0.0.1:11434`. No API keys, Anthropic endpoints, OpenAI endpoints, or Google Gemini cloud endpoints are referenced or queried.
- **Speech Recognition:** [`app/voice/whisper_engine.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/voice/whisper_engine.py) uses local Faster-Whisper models executing on host CPU/GPU via CTranslate2. Zero audio data is transmitted over the network.
- **Speech Synthesis:** Kokoro ONNX, Piper, and Windows SAPI5 run 100% locally on device.
- **Finding:** **100% Zero-Cloud Compliance Confirmed.** The application operates cleanly in air-gapped / disconnected network environments.

---

## 3. Vulnerability Register & Impact Analysis

### `SEC-001`: FastAPI Middleware Origin Header Bypass
- **Vulnerability Type:** CWE-346: Origin Validation Error
- **CVSS v3.1 Score:** **5.3** (CVSS:3.1/AV:L/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N)
- **Affected File:** [`app/api/server.py:172-176`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py#L172-L176)
- **Detailed Finding:**
  ```python
  def is_allowed_origin(origin: Optional[str]) -> bool:
      if not origin:
          return True  # Allows requests without Origin header
  ```
  Web browsers emit the `Origin` header during CORS requests. However, command-line tools (curl, PowerShell `Invoke-RestMethod`), desktop scripts, or applications that forge requests without an `Origin` header are granted unrestricted access to the REST endpoints.
- **Impact:** Malicious non-browser software executing on the local machine can query, insert, or clear messages without origin restrictions.
- **Remediation:** Enforce strict inspection: if `Origin` is absent, verify that the request's `Host` header and client socket address strictly match `127.0.0.1:8765`.

---

### `SEC-002`: Unauthenticated Local Control REST & WebSocket Endpoints
- **Vulnerability Type:** CWE-306: Missing Authentication for Critical Function
- **CVSS v3.1 Score:** **5.5** (CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:L/I:L/A:L)
- **Affected Files:** [`app/api/server.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py), [`app/api/websocket.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/websocket.py)
- **Detailed Finding:**
  Endpoints exposing sensitive capabilities (`/api/conversations`, `/api/conversations/{id}/messages`, `/api/voice/stop`, and `/ws`) do not require authentication tokens, HTTP basic auth, or session cookies.
- **Impact:** Any unprivileged process or background malware running on the same workstation can read user conversations, trigger unwanted TTS speech, or disrupt ongoing audio conversations.
- **Remediation:** Generate an ephemeral 256-bit cryptographic token during boot in `main.py`. Pass this token to `ModernChatWindow` and require an `X-Local-Token` or `Authorization: Bearer <token>` header on all REST and WebSocket connections.

---

### `SEC-003`: Deprecated FastAPI Startup Lifecycle Hook
- **Vulnerability Type:** CWE-477: Use of Obsolete Functions
- **CVSS v3.1 Score:** **2.0** (Informational / Code Quality)
- **Affected File:** [`app/api/server.py:227`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py#L227)
- **Detailed Finding:**
  Uses `@app.on_event("startup")` which triggers `DeprecationWarning: on_event is deprecated, use lifespan event handlers instead.` in Starlette/FastAPI.
- **Remediation:** Replace with `@asynccontextmanager async def lifespan(app: FastAPI):`.

---

## 4. WebEngine Sandbox & Link Interception Verification

- **Chromium Sandbox Integrity:**
  - Audited `main.py` and `app/desktop/modern_chat_window.py`.
  - Confirmed that `--no-sandbox` is **NOT** present or enabled, preserving Chromium's multi-process security sandbox.
- **External URL Delegation:**
  - In [`app/desktop/modern_chat_window.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/modern_chat_window.py), `CustomWebPage.acceptNavigationRequest` intercepts all hyperlinks clicked in the chat window:
  ```python
  if url.scheme() in ("http", "https") and not is_local_origin(url):
      QDesktopServices.openUrl(url)
      return False
  ```
  - Confirmed via unit tests in `tests/test_security_fixes.py`: External links are safely routed to the user's default Windows browser (Edge/Chrome/Firefox), preventing the internal WebEngine view from loading untrusted third-party web content.

---

## 5. Operating System Process Isolation & Data Security

1. **Windows Job Object Termination:**
   - [`app/core/lifecycle.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/core/lifecycle.py#L93-L177) assigns the primary process to a Win32 Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000`.
   - Verified: If `main.py` is forcefully terminated or killed via Task Manager, all child processes spawned by the companion are immediately reaped by the Windows kernel, preventing rogue background daemon accumulation.
2. **Data-at-Rest Security:**
   - Conversations are stored unencrypted in `%APPDATA%\AIDesktopFriend\conversations.db`.
   - Default Windows NTFS file system permissions restrict access to the logged-in user account.
   - For enterprise or high-privacy deployments, implementing optional SQLCipher database encryption is recommended.
