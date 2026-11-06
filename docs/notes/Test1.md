# ROLE

Act as a Senior Python Backend Engineer, QA Automation Engineer, Software Architect, and Test Engineer.

Your task is to perform a comprehensive, evidence-based testing and code audit of my entire **AI Desktop Friend** project.

Do not limit your work to reviewing code. Inspect the repository, understand its architecture, execute appropriate tests, identify defects, create missing tests, and verify fixes.

The backend is the highest priority.

# 1. PROJECT CONTEXT

Project name: AI Desktop Friend

Application type: Windows desktop AI companion.

Core technologies:

* Python 3.11+
* PySide6 for the desktop GUI
* Ollama for local LLM inference
* SQLite for persistent conversation storage
* SQLite WAL mode for database concurrency
* pytest and pytest-qt for automated testing
* Local HTTP communication with Ollama at http://127.0.0.1:11434

Key features:

* Floating desktop pet with transparent, frameless window.
* Eight character states: IDLE, LISTENING, THINKING, SPEAKING, HAPPY, SLEEPING, ERROR, and DRAGGING.
* Streaming responses from locally hosted language models.
* Filtering of internal reasoning enclosed in <think>...</think> tags.
* Persistent conversations and message history.
* Conversation creation, renaming, clearing, deletion, and search.
* Text chat, push-to-talk, and continuous voice input modes.
* Floating chat window with streaming and cancellation.
* System tray controls and application visibility management.
* Remembered character position and desktop preferences.
* Two entry points:

  * run_desktop.py — modern desktop chat application.
  * main.py — original desktop pet application.
* Optional smoke test:

  * python main.py --test-run

Expected local models include qwen3:4b and llama3.2, but the application should handle unavailable models and Ollama service failures gracefully.

# 2. PRIMARY OBJECTIVE

Determine whether the entire project works correctly, especially its backend.

Investigate these questions:

1. Does the application behave according to its documented features?
2. Are backend components implemented correctly?
3. Does streaming work with real and simulated Ollama responses?
4. Is conversation history persisted correctly in SQLite?
5. Are database operations safe under concurrent access?
6. Are errors, timeouts, and cancelled requests handled properly?
7. Can background tasks terminate without leaking threads or resources?
8. Does the GUI correctly reflect backend state?
9. Do both application entry points work?
10. Are existing tests meaningful, comprehensive, and reliable?
11. Are important edge cases and failure scenarios untested?
12. Can the application recover from failures without restarting?
13. Are there security, privacy, data-integrity, or performance problems?
14. Does the README accurately describe the actual implementation?

Do not assume a feature works simply because its code exists.

# 3. IMPORTANT EXECUTION RULES

Follow these rules throughout the audit:

* Inspect the entire repository before making conclusions.
* Read the README, dependency files, application entry points, backend modules, UI modules, database code, configuration files, and existing tests.
* Identify the actual architecture and execution flow before designing tests.
* Follow imports and call chains across modules.
* Identify all public backend methods and their callers.
* Run existing tests before changing code to establish a baseline.
* Record failing tests, errors, warnings, and environmental limitations.
* Distinguish confirmed defects from potential risks.
* Never fabricate test results, execution logs, coverage percentages, or successful verifications.
* Do not mark tests as passed unless they actually passed.
* Do not silently skip failing tests.
* Do not delete existing tests merely to make the test suite pass.
* Do not replace real implementations with mocks in production code.
* Use mocks and fakes in tests when appropriate.
* Preserve existing functionality and public interfaces unless a change is necessary.
* Avoid unnecessary architectural rewrites.
* Never run destructive database tests against the user's real conversation database.
* Never delete user data, installed Ollama models, or project files.
* Do not make external API calls or transmit conversation data to cloud services.
* Do not download large language models merely to execute tests.
* Do not expose credentials, private conversation contents, or sensitive local information in reports.
* If a dependency or service is unavailable, explain the limitation and continue with independent tests.

You are authorized to create and modify test files and to fix verified defects in project code. Keep changes minimal, targeted, and explainable.

Do not stop after generating a checklist. Perform the audit and execute the tests that the environment permits.

# 4. PHASE ONE — REPOSITORY DISCOVERY

Inspect the complete project structure.

Identify:

* Application entry points.
* Backend services and their dependencies.
* Ollama integration modules.
* Streaming and response-processing logic.
* Database models, repositories, and connection management.
* Conversation and message lifecycle management.
* Background workers, threads, signals, and asynchronous operations.
* Voice input and audio-processing components.
* Character animation and state-management logic.
* GUI-to-backend communication.
* Configuration and settings persistence.
* Logging and exception handling.
* Existing unit, integration, GUI, and smoke tests.
* Dependency declarations and development tools.
* Unused modules, duplicated logic, circular imports, and suspicious dead code.

Create an architecture map showing:

1. Application entry point.
2. UI layer.
3. Backend/service layer.
4. Ollama client.
5. SQLite persistence layer.
6. Background processing.
7. Voice subsystem.
8. Configuration and state persistence.

Trace a typical message through the complete application:

User input
→ Input validation
→ Backend request
→ Ollama request
→ Response streaming
→ Thinking-tag filtering
→ UI updates
→ Conversation persistence
→ Completion or error handling.

Verify the real implementation instead of assuming this is the exact execution path.

Deliver:

* Repository inventory.
* Architecture summary.
* Important module responsibilities.
* Dependency and call-flow map.
* Initial list of potential defects.

# 5. PHASE TWO — ESTABLISH THE TEST BASELINE

Before modifying code:

1. Check the Python version.
2. Identify the active virtual environment.
3. Inspect installed dependencies.
4. Inspect requirements.txt, pyproject.toml, setup.cfg, or other dependency configuration files that actually exist.
5. Identify how pytest is configured.
6. Discover all existing tests.
7. Run the existing test suite.
8. Run the documented smoke test if safe and supported.
9. Check whether both application entry points can be imported or launched safely in the available environment.

Start with commands appropriate to the repository, such as:

python --version

python -m pytest -v

python -m pytest --collect-only -q

python -m pytest --cov --cov-report=term-missing

Only run the coverage command if pytest-cov is installed; otherwise report that it is unavailable and determine whether installing a development dependency is appropriate.

For the smoke test, inspect its implementation before execution to ensure it does not modify user data, hang indefinitely, or require an interactive desktop session.

Use the project's virtual environment when available.

Record:

* Commands executed.
* Total tests collected.
* Passed tests.
* Failed tests.
* Skipped tests.
* Errors during test collection.
* Execution time.
* Coverage, if actually measured.
* Environmental limitations.

If a command fails because of an environment problem, distinguish that from an application defect.

# 6. PHASE THREE — BACKEND TESTING (HIGHEST PRIORITY)

Inspect and test every backend module.

## A. Ollama Integration

Test:

* Detection of an available Ollama service.
* Handling of a service that is not running.
* Model discovery.
* Selection of an installed model.
* Handling of an explicitly configured model.
* Behavior when no models are installed.
* Behavior when the configured model is unavailable.
* HTTP connection failures.
* Request timeouts.
* HTTP error responses.
* Invalid JSON.
* Malformed streaming responses.
* Empty responses.
* Unexpected response schemas.
* Unicode and multiline responses.
* Long generated responses.
* Interrupted connections.
* Server shutdown during generation.
* Recovery after the service becomes available again.

Verify that the application does not freeze when Ollama is unavailable.

Do not assume that model discovery, model selection, and generation are implemented in the same module. Trace their actual implementation.

## B. Streaming Response Processing

Test realistic Ollama streaming behavior.

Verify:

* Each response chunk is processed correctly.
* Chunks are emitted in the correct order.
* Partial text is displayed without losing characters.
* Multiple chunks combine into the expected response.
* Empty chunks are handled safely.
* Unicode characters split across network reads are decoded correctly.
* Newlines and whitespace are preserved appropriately.
* Final completion markers are handled correctly.
* Stream termination is detected.
* Exceptions during iteration are handled correctly.
* UI updates are not emitted from unsafe threads.
* Final text matches the expected accumulated response.

Test the actual streaming parser and its interaction with the UI-facing backend API.

## C. Internal Reasoning / <think> Tag Filtering

The README promises filtering of internal reasoning enclosed in <think>...</think> tags.

Test at least these cases:

1. Ordinary text without reasoning tags.
2. A complete <think>...</think> block.
3. Reasoning followed by a final answer.
4. Multiple reasoning blocks.
5. An opening tag split across chunks.
6. A closing tag split across chunks.
7. Tags with surrounding whitespace.
8. Empty reasoning blocks.
9. An unfinished reasoning block at stream termination.
10. Malformed or nested tags.
11. Uppercase or otherwise unexpected tag variants, according to the intended contract.
12. Literal tag-like text appearing in an answer.
13. Cancellation while the filter is inside a reasoning block.
14. Streaming where the final answer begins in the same chunk that closes the reasoning block.

Verify that internal reasoning is never accidentally emitted to the UI or persisted as an assistant-visible answer when the application is supposed to suppress it.

Check both incremental output and final accumulated output.

Identify any ambiguity in the filtering contract and recommend an explicit, testable behavior.

Do not claim that text-based filtering can reliably identify all model-internal reasoning. Test only the application's documented filtering behavior.

## D. Request Cancellation and Concurrency

Test:

* Cancelling an active generation.
* Cancelling before the first token arrives.
* Cancelling during a streamed response.
* Cancelling after completion.
* Repeated cancellation requests.
* Starting a new request after cancellation.
* Closing the chat window during generation.
* Exiting the application during generation.
* Rapid consecutive messages.
* Multiple requests competing for shared state.
* Background worker cleanup.
* Signal delivery after a worker has finished.
* Exceptions during worker shutdown.

Verify that cancellation stops further output as promptly as the underlying HTTP client and Ollama API permit.

Ensure cancelled requests do not continue updating a closed UI or overwrite the result of a newer request.

Do not equate stopping UI updates with actually stopping network generation.

Check for deadlocks, leaked threads, unhandled exceptions, race conditions, and stale callbacks.

## E. Backend Error Handling

Inspect every major backend boundary.

Test failures in:

* HTTP communication.
* JSON parsing.
* SQLite operations.
* Filesystem access.
* Configuration loading.
* Voice initialization.
* Background task execution.
* UI-to-service communication.

Verify that:

* Exceptions are handled at appropriate boundaries.
* Errors are logged with useful diagnostic context.
* Users receive clear, safe error messages.
* Secrets and private conversation text are not unnecessarily logged.
* Errors do not leave the application in an invalid state.
* Recovery works when the failed dependency becomes available again.

Avoid broad exception handlers that silently hide defects.

## F. Backend Interface Contracts

For every service and repository, identify:

* Public methods.
* Required parameters.
* Return types.
* Exceptions that may be raised.
* Side effects.
* Threading assumptions.
* Resource ownership.
* Persistence guarantees.

Write tests for valid inputs, invalid inputs, boundary conditions, and failure conditions.

Verify that the UI calls the backend according to the actual interface contracts.

Look for mismatches in:

* Method names.
* Parameter names.
* Return types.
* Signal payloads.
* Optional values.
* Error representations.
* Conversation and message identifiers.

# 7. PHASE FOUR — SQLITE AND CONVERSATION HISTORY

Test the database using temporary directories and isolated temporary databases.

Never run destructive tests against the user's actual conversation database.

## A. Database Initialization

Verify:

* Database creation.
* Schema creation.
* Schema migration behavior, if implemented.
* WAL mode configuration.
* Database reopening.
* Initialization when tables already exist.
* Behavior when the database path is invalid.
* Handling of corrupted or incompatible databases.
* Correct use of transactions.

Inspect connection ownership and SQLite thread-safety assumptions.

## B. Conversation Lifecycle

Test:

* Creating a conversation.
* Listing conversations.
* Retrieving a conversation.
* Renaming a conversation.
* Clearing conversation messages.
* Deleting a conversation.
* Handling nonexistent conversation IDs.
* Handling invalid or empty titles.
* Timestamp creation and updates.
* Ordering of conversations.
* Preservation of unrelated conversations during mutations.

Verify whether clearing messages preserves the conversation record and whether deletion behaves according to the intended contract.

## C. Message Lifecycle

Test:

* Saving user messages.
* Saving assistant messages.
* Retrieving messages in chronological order.
* Empty messages.
* Long messages.
* Unicode and emoji.
* Newlines.
* Invalid conversation references.
* Timestamp consistency.
* Ordering when timestamps are identical.
* Failed writes.
* Transaction rollback.
* Consistency between displayed and stored messages.

Test what happens when a generation is cancelled or fails halfway through.

Ensure incomplete assistant responses are handled consistently with the product's intended behavior.

## D. Search

Test:

* Searching across multiple conversations.
* Matching user and assistant messages.
* Case-insensitive searches where intended.
* Empty queries.
* Whitespace-only queries.
* Unicode.
* Special SQL characters.
* SQL wildcard characters such as % and _.
* Apostrophes and quotation marks.
* Deleted conversations.
* Empty databases.
* Very long queries.

Use parameterized SQL queries and verify that user input cannot alter SQL query structure.

Verify that search results identify the correct conversation and message.

## E. WAL Mode and Concurrent Access

Test:

* Reading while another connection writes.
* Concurrent message insertions.
* Simultaneous conversation updates.
* Busy database behavior.
* Lock contention.
* Transaction rollback.
* Database reopening after writes.
* WAL checkpoint behavior where relevant.
* Graceful shutdown with active database operations.

Use bounded concurrency tests that cannot hang indefinitely.

Investigate SQLite connection reuse across threads and the application's actual connection policy.

Verify that concurrent operations do not corrupt data, lose messages, or leave partially applied mutations.

# 8. PHASE FIVE — CONVERSATION MEMORY AND MESSAGE FLOW

Test the complete interaction between the chat backend and the database.

Verify:

1. A new user message reaches the intended conversation.
2. The appropriate conversation context is retrieved.
3. The backend constructs the correct Ollama request.
4. Streaming begins.
5. Assistant output is processed correctly.
6. The completed response is saved.
7. The conversation view refreshes correctly.
8. Switching conversations does not mix their messages.
9. Clearing or deleting a conversation during generation is handled safely.
10. Restarting the application restores persisted conversations.
11. Search results remain consistent with stored data.
12. A failed generation does not silently corrupt conversation history.

Inspect whether conversation history is actually included in the Ollama prompt.

Do not assume that saving messages to SQLite automatically means the model remembers them.

If conversation context is sent to Ollama, test:

* Message ordering.
* Correct role assignment.
* Context truncation or limits.
* Empty history.
* Long histories.
* Conversation isolation.
* Prevention of messages from other conversations leaking into the request.

Test prompt construction separately from the live Ollama service.

# 9. PHASE SIX — VOICE INPUT AND AUDIO

First discover which voice components and dependencies are actually implemented.

Do not invent functionality that does not exist.

For every supported voice mode, test:

* Initialization.
* Device availability.
* Permission or access failures.
* Missing audio dependencies.
* Empty audio input.
* Invalid audio data.
* Speech-recognition failures.
* Silence and timeouts.
* Start and stop transitions.
* Repeated start and stop requests.
* Switching between text and voice modes.
* Cancellation during voice processing.
* Resource cleanup.
* Application shutdown during active audio capture.

Verify that unavailable audio hardware does not prevent text chat from working.

Mock audio hardware and external speech services where appropriate.

Do not require a physical microphone in automated tests.

If voice functionality depends on optional packages or local models, document those dependencies and the resulting testing limitations.

# 10. PHASE SEVEN — GUI AND STATE-MANAGEMENT TESTING

Backend correctness remains the priority, but verify critical UI-to-backend integration.

Test, where practical:

* Launching both entry points.
* Creating and opening the chat window.
* Sending a message.
* Streaming response updates.
* Stopping generation.
* Switching conversations.
* Renaming and deleting conversations.
* Searching history.
* Displaying backend errors.
* Closing windows during active tasks.
* System tray actions.
* Character visibility and window lifecycle.
* Correct worker cleanup on exit.

For the eight character states, inspect the state-transition logic.

Verify valid transitions between IDLE, LISTENING, THINKING, SPEAKING, HAPPY, SLEEPING, ERROR, and DRAGGING.

Check whether backend events update the character state appropriately.

Identify invalid or missing transitions, states that become stuck, and animations that continue after shutdown.

Use pytest-qt for testable Qt behavior.

Avoid brittle tests based on arbitrary sleep durations. Prefer Qt signals, event-loop-aware waits, and deterministic synchronization.

Clearly separate headless tests from tests that require a Windows desktop session.

# 11. PHASE EIGHT — CONFIGURATION AND WINDOWS INTEGRATION

Inspect configuration handling and Windows-specific behavior.

Test, where supported:

* Missing configuration files.
* Invalid configuration values.
* Missing settings.
* Default values.
* Persisting user preferences.
* Reloading saved preferences.
* Invalid saved character positions.
* Multiple monitor or display-coordinate edge cases.
* Missing icon or asset files.
* Invalid filesystem paths.
* Paths containing spaces or non-ASCII characters.
* Launching from a different working directory.
* Running through the documented batch file.
* Clean application shutdown.
* System tray initialization failures.

Verify that configuration failures produce safe defaults or understandable errors rather than unexplained crashes.

Do not modify real user settings during automated tests.

# 12. PHASE NINE — SECURITY AND PRIVACY AUDIT

Inspect the application for realistic security and privacy risks.

Check for:

* SQL injection.
* Unsafe shell command construction.
* Untrusted path handling.
* Unnecessary network exposure.
* Ollama endpoints bound or accessed in unexpected ways.
* Unsafe deserialization.
* Accidental cloud API usage.
* Credentials or API keys committed to the repository.
* Sensitive conversation contents written to logs.
* Sensitive data included in crash reports.
* Insecure temporary files.
* Excessive filesystem permissions.
* Dependency vulnerabilities, using available offline tools or installed scanners where possible.

Verify whether HTTP requests remain local as documented.

Do not infer that an application is completely offline simply because its primary model runs locally. Inspect all relevant dependencies and network calls.

Do not transmit private project data to external scanning services.

Report the severity, evidence, exploitability, and practical impact of confirmed findings.

Do not label hypothetical risks as confirmed vulnerabilities.

# 13. PHASE TEN — PERFORMANCE AND RESOURCE TESTING

Measure actual behavior instead of guessing.

Investigate:

* Time to launch.
* Backend initialization latency.
* Time to first streamed token when a local model is available.
* Streaming throughput where measurable.
* Database query performance.
* Search performance with synthetic datasets.
* Memory growth during long conversations.
* Handling of very long responses.
* Repeated creation and deletion of conversations.
* Repeated generation cancellation.
* Background thread growth.
* Resource cleanup after repeated window openings and closings.

Use synthetic data and bounded workloads.

Do not benchmark LLM generation speed without distinguishing model loading time, hardware limitations, and network/service latency.

Identify:

* Unbounded buffers.
* Repeated full-history loading.
* Inefficient SQL queries.
* Missing indexes.
* Excessive UI refreshes.
* Memory leaks.
* Thread or connection leaks.

Only recommend optimization when measurements or code evidence justify it.

# 14. PHASE ELEVEN — TEST QUALITY AND COVERAGE

Evaluate the existing test suite itself.

Check for:

* Missing backend tests.
* Weak assertions.
* Tests that pass without verifying meaningful behavior.
* Excessive mocking that hides integration defects.
* Flaky timing assumptions.
* Shared mutable state between tests.
* Tests that depend on the developer's machine.
* Tests that require Ollama unexpectedly.
* Tests that access real conversation databases.
* Tests that fail to clean up threads or temporary files.
* Duplicate tests.
* Tests that never exercise error paths.
* Incorrectly marked skips or expected failures.

Create a test coverage matrix with these columns:

| Component | Existing Tests | Missing Scenarios | New Tests Added | Results | Remaining Risks |
| --------- | -------------- | ----------------- | --------------- | ------- | --------------- |

Prioritize branch coverage and failure-path coverage for critical backend modules.

Measure coverage if the required tooling is available.

Do not invent a target percentage or claim complete coverage based solely on line coverage.

Explain which modules remain untested and why.

# 15. PHASE TWELVE — TEST ARCHITECTURE

If the repository lacks sufficient tests, add a maintainable automated test suite.

Use the existing framework and project conventions.

Prefer the following layers:

### Unit Tests

Test individual backend functions and classes in isolation.

### Integration Tests

Test real interactions between backend components and temporary SQLite databases.

### Contract Tests

Verify interfaces between the Ollama client, streaming parser, database layer, services, and GUI-facing APIs.

### GUI Tests

Test selected Qt behaviors using pytest-qt.

### Smoke Tests

Verify startup and shutdown without requiring lengthy model generation.

### Optional Local-Service Tests

Test against an already-installed Ollama instance only when explicitly enabled.

Default automated tests should not require:

* Internet access.
* A running Ollama server.
* Downloaded models.
* A physical microphone.
* A visible desktop session.
* Access to the user's real database.

Use deterministic fake HTTP responses or a local mock HTTP server to test streaming protocols.

Use temporary SQLite databases.

Use pytest fixtures for reusable setup and cleanup.

Use parametrized tests for related edge cases.

Use fake clocks or deterministic timestamps where helpful.

Mark tests requiring external services clearly and keep them excluded from the default offline test run.

Ensure that the test suite is repeatable and can be executed from the repository root.

# 16. PHASE THIRTEEN — DEFECT INVESTIGATION AND FIXES

For every confirmed defect:

1. Identify the affected module and function.
2. Reproduce the failure with a minimal test.
3. Record the expected behavior.
4. Record the actual behavior.
5. Identify the root cause.
6. Implement the smallest safe correction.
7. Add a regression test.
8. Rerun the relevant test.
9. Rerun the broader test suite.
10. Check for unintended side effects.

Prioritize defects in this order:

P0 — Critical:

* Data corruption or loss.
* Severe security vulnerabilities.
* Application-wide crashes caused by common workflows.

P1 — High:

* Broken conversation persistence.
* Streaming failures.
* Incorrect cancellation.
* Concurrency defects.
* Application deadlocks.
* Major backend functionality failing.

P2 — Medium:

* Incorrect edge-case behavior.
* Recovery failures.
* Search or configuration bugs.
* Resource leaks.
* Missing error handling.

P3 — Low:

* Minor usability problems.
* Noncritical logging issues.
* Cosmetic defects.
* Low-impact code-quality improvements.

Adjust severity based on demonstrated impact.

Do not change unrelated code just to improve style.

Do not make large refactors while investigating unrelated bugs.

# 17. PHASE FOURTEEN — FINAL VERIFICATION

After implementing any fixes:

1. Run the complete automated test suite.
2. Run the backend tests independently.
3. Run database integration tests independently.
4. Run the streaming and cancellation tests independently.
5. Run static checks that are available in the project.
6. Run the documented smoke test if safe.
7. Verify imports and application startup paths.
8. Verify that tests do not modify user data.
9. Compare results with the initial baseline.
10. Review every modified file.
11. Confirm that no test results were fabricated.
12. Record all tests that could not be executed.

If possible, run the tests in a clean virtual environment or a reproducible CI environment without modifying the user's existing environment.

Do not claim that both desktop interfaces were visually tested unless the required GUI environment was actually available.

# 18. REQUIRED DELIVERABLES

Produce the following results.

## A. Executive Summary

Include:

* Overall project health.
* Backend health.
* Most serious confirmed defects.
* Test-suite reliability.
* Data-integrity risks.
* Security and privacy findings.
* Whether the project is ready for normal use.

Explain the basis for each conclusion.

## B. Architecture Report

Document the actual modules, responsibilities, dependencies, and important execution flows.

## C. Test Execution Report

Include:

* Exact commands executed.
* Tests collected.
* Passed, failed, skipped, and errored counts.
* Coverage measurements, if available.
* Runtime.
* Environment limitations.
* Failures requiring manual investigation.

## D. Backend Audit Report

Give detailed findings for:

* Ollama integration.
* Streaming.
* Thinking-tag filtering.
* Cancellation.
* Error handling.
* Concurrency.
* SQLite.
* Conversation lifecycle.
* Search.
* Context management.
* Voice processing.
* Configuration.
* Resource cleanup.

## E. Defect Register

Use this table:

| ID | Severity | Module | Defect | Reproduction | Root Cause | Fix Applied | Regression Test |
| -- | -------- | ------ | ------ | ------------ | ---------- | ----------- | --------------- |

Only list confirmed defects as confirmed. Label unverified concerns as potential risks.

## F. Test Coverage Matrix

Map each critical module to existing tests, added tests, test outcomes, and remaining gaps.

## G. Changed Files

For each modified or created file, explain:

* Why it changed.
* What was added or corrected.
* Which test validates the change.

## H. Remaining Risks

Identify all important untested scenarios, environment-dependent behaviors, and unresolved defects.

## I. Final Readiness Assessment

Choose one:

* NOT READY — Critical defects remain.
* NOT READY — High-priority defects remain.
* CONDITIONALLY READY — Important limitations remain.
* READY FOR FURTHER REAL-WORLD VALIDATION — Automated checks pass, but environmental behavior still needs confirmation.
* READY — Required tests and validation criteria pass, with no known blocking defects.

Explain why the selected status is justified.

Do not declare the application production-ready simply because pytest passes.

## J. Recommended Next Steps

Give a prioritized list of remaining work.

Separate:

* Must fix.
* Should fix.
* Optional improvements.

# 19. FINAL OPERATING INSTRUCTION

Begin by inspecting the actual repository and running the existing test suite.

Then proceed through the audit phases in order, prioritizing backend testing, SQLite integrity, streaming correctness, cancellation, and concurrency.

Create missing tests and fix verified defects where safe.

Continue until the available environment has been fully tested or a genuine limitation prevents further progress.

If the project is too large to audit in one pass, maintain a checklist of completed and incomplete phases. Never claim the entire project has been audited while important modules remain unexamined.

At the end, provide the complete reports, list all modified files, summarize actual test results, and clearly distinguish verified behavior from assumptions.

**The objective is not to make the test report look good. The objective is to discover whether the application really works and to improve its reliability without risking the user's data.**
