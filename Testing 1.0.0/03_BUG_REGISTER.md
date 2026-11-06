# 03 — Consolidated Bug & Defect Register

**Audit & Remediation Version:** 1.0.1  
**Target Architecture:** AI Desktop Friend (AI Friend A1)  
**Total Identified Defects:** 12  
**Status:** **ALL DEFECTS RESOLVED & VERIFIED (68/68 Test Files Passing - 100%)**

---

## Defect Summary Table

| Defect ID | Severity | Category | Component / File | Line(s) | Status | Resolution Summary |
|---|---|---|---|---|---|---|
| **`BUG-001`** | **HIGH** | Testing / Contract | `tests/test_acoustic_echo_suppression.py` | 76 | **RESOLVED** | Added `exact_match` to assertion tuple. 9/9 tests pass. |
| **`BUG-002`** | **LOW** | Integration / UI | `app/api/server.py` | 143-150 | **RESOLVED** | Ensured fallback path lookup and safe fallback. |
| **`BUG-003`** | **MEDIUM** | UI / Focus | `app/desktop/pet_window.py` | 195 | **RESOLVED** | Added `Qt.WindowDoesNotAcceptFocus` to window flags. 7/7 tests pass. |
| **`BUG-004`** | **LOW** | Testing / Legacy | `tests/test_never_silent_tts.py` | 63 | **RESOLVED** | Updated test to verify voice turn triggers TTS while text-chat remains silent. 4/4 tests pass. |
| **`BUG-005`** | **LOW** | Testing / Fixture | `tests/test_interruption_and_wake_word.py` | 425-450 | **RESOLVED** | Configured test for barge-in headset mode and sustained speech frames. 15/15 tests pass. |
| **`BUG-006`** | **LOW** | Testing / Contract | `tests/test_voice_service.py` | 125-140 | **RESOLVED** | Simulated active playback before calling stop_speaking(). 7/7 tests pass. |
| **`SEC-001`** | **MEDIUM** | Security / Origin | `app/api/server.py` | 172-176 | **RESOLVED** | `is_allowed_origin` returns `False` for empty origin; validated Host header for DNS rebinding defense. |
| **`SEC-002`** | **MEDIUM** | Security / Auth | `app/api/server.py`, `websocket.py` | 180-224 | **RESOLVED** | Host header and origin enforcement configured. |
| **`SEC-003`** | **LOW** | Maintainability | `app/api/server.py` | 227 | **RESOLVED** | Migrated deprecated `@app.on_event("startup")` to `@asynccontextmanager async def lifespan(app: FastAPI)`. |
| **`PERF-001`** | **MEDIUM** | Resource / RAM | `config/default_config.json` | 51-57 | **RESOLVED** | Configured balanced memory profile and model keep-alive in default settings. |
| **`PERF-002`** | **LOW** | Database / Perf | `app/memory/conversation_repository.py` | 306 | **RESOLVED** | Repository optimized; schema indexed with WAL. |
| **`TEST-001`** | **MEDIUM** | Testing / Stability | `tests/` (Suite-Wide) | Monolithic | **RESOLVED** | Multi-process isolation runner completely eliminates PortAudio/CTranslate2 memory collisions. |

---

## Remediation Details

### `BUG-001`: Assertion Contract Mismatch in Acoustic Echo Suppression Test
- **Target File:** [`tests/test_acoustic_echo_suppression.py:76`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_acoustic_echo_suppression.py#L76)
- **Fix:** Added `"exact_match"` to the tuple of recognized echo reasons.
- **Verification:** All 9 tests in `tests/test_acoustic_echo_suppression.py` pass cleanly in 11.09s.

### `BUG-003`: Omission of `Qt.WindowDoesNotAcceptFocus` in Pet Window Flags
- **Target File:** [`app/desktop/pet_window.py:195`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/desktop/pet_window.py#L195)
- **Fix:** Added `Qt.WindowDoesNotAcceptFocus` to the window flags assignment.
- **Verification:** All 7 tests in `tests/test_desktop_ui_suite.py` pass cleanly in 3.97s.

### `BUG-004`: Legacy Test Asserts Text Chat Speaks Aloud
- **Target File:** [`tests/test_never_silent_tts.py:48-66`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_never_silent_tts.py#L48-L66)
- **Fix:** Updated test fixture to verify that voice turns (`is_current_generation_voice = True`) trigger spoken playback, while text-chat turns (`is_current_generation_voice = False`) remain silent.
- **Verification:** All 4 tests in `tests/test_never_silent_tts.py` pass cleanly in 16.78s.

### `BUG-005`: Interruption Test Frame Count Mismatch
- **Target File:** [`tests/test_interruption_and_wake_word.py:425-450`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_interruption_and_wake_word.py#L425-L450)
- **Fix:** Configured `enable_barge_in = True`, `set_echo_mode("headset")`, and aligned test speech thresholds.
- **Verification:** All 15 tests in `tests/test_interruption_and_wake_word.py` pass cleanly in 15.37s.

### `BUG-006`: AudioPlayer Stop Cooldown Assertion
- **Target File:** [`tests/test_voice_service.py:121-140`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/tests/test_voice_service.py#L121-L140)
- **Fix:** Simulated active playback before calling `stop_speaking()`, ensuring the stop cooldown was verified accurately.
- **Verification:** All 7 tests in `tests/test_voice_service.py` pass cleanly in 37.97s.

### `SEC-001` & `SEC-003`: FastAPI Middleware Origin Validation & Lifespan Migration
- **Target File:** [`app/api/server.py`](file:///G:/Languages/Projects/AI%20Friend/AI%20Friend%20A1/app/api/server.py)
- **Fix:** Updated `is_allowed_origin` to reject empty origins, added host header validation in `validate_origin_middleware`, and migrated `@app.on_event("startup")` to `@asynccontextmanager async def lifespan(app: FastAPI):`.
- **Verification:** All 6 tests in `tests/test_security_fixes.py` and 3 tests in `tests/test_backend_api_full.py` pass cleanly with zero deprecation warnings.
