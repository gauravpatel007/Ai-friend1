DO not implement by yourself user will give instruction - then only then implement this file - or else say you didn't get any instructions
# AI FRIEND — MOVIE HUB

## MASTER IMPLEMENTATION PLAN | PHASE 0–12

### PROJECT OVERVIEW

I am developing an existing desktop application called AI Friend.

The application currently includes:

* An AI companion interface.
* A conversation sidebar and chat history.
* Local Ollama model integration.
* Voice interaction features.
* A desktop UI with a dark theme.
* Existing application settings and other project functionality.

I want to introduce a completely new feature called **Movie Hub**.

Movie Hub will be a dedicated, full-screen second tab inside the existing application. It will provide movie and television-series discovery, regional and language filters, movie details, watchlists, and AI-powered recommendations.

This is an extension of the existing AI Friend project, not a replacement or a standalone application.

The implementation must follow the actual architecture, programming language, UI framework, storage system, and coding conventions discovered in the repository.

Do not assume that the proposed architecture or file names in this document already exist.

---

# PHASE EXECUTION POLICY — MANDATORY

THIS IS THE MOST IMPORTANT RULE IN THIS DOCUMENT.

You must follow the phases sequentially and implement ONLY the phase I explicitly authorize.

The complete roadmap is provided for planning and architectural consistency. It does NOT authorize implementing all phases at once.

## Phase 0 — Introduction and Planning

Phase 0 introduces the project, defines the feature, establishes boundaries, and creates a detailed implementation plan.

Phase 0 must not implement Movie Hub.

## Phase 1 onward — Actual Implementation

Actual implementation begins at Phase 1.

I will explicitly instruct you when to begin each phase.

For example:

* "Execute Phase 1."
* "Execute Phase 2."
* "Execute Phase 3."

When I authorize a phase, execute only that phase.

Do not automatically continue to the next phase after finishing the current one.

Do not implement future-phase functionality just because you believe it is useful.

You may make minimal preparatory decisions necessary to keep the current phase compatible with the roadmap, but do not prematurely implement future features.

## Required Behavior

1. Read this complete master plan before executing any phase.
2. Determine which phase I explicitly authorized in my latest instruction.
3. If I have not authorized a phase, do not start implementation.
4. If I authorize Phase 0, perform planning only.
5. If I authorize Phase 1, execute Phase 1 only.
6. After completing a phase, run its applicable verification steps.
7. Report the actual outcome.
8. Stop and wait for my next instruction.

Never automatically advance to another phase.

If I request a phase that depends on incomplete work from an earlier phase, inspect the actual project state, explain the dependency, and ask me how to proceed instead of silently skipping prerequisites.

Do not interpret "continue," "finish," or "complete the project" as authorization to execute every remaining phase at once. Clarify the specific next phase if necessary.

---

# PHASE 0 — INTRODUCTION, REQUIREMENTS, AND IMPLEMENTATION PLAN

## Objective

Understand the Movie Hub concept, document the requirements, inspect the existing project at a high level, and establish a safe phase-by-phase implementation strategy.

Phase 0 is planning only.

## Tasks

### 0.1 Introduce Movie Hub

Document the proposed Movie Hub feature and how it will fit into the existing AI Friend application.

The intended navigation is:

* AI Companion: existing chat and companion functionality.
* Movie Hub: a new, full-screen movie and series discovery workspace.

Movie Hub must not replace or damage the existing chat interface.

### 0.2 Define Functional Requirements

Document the intended functionality:

* Full-screen Movie Hub workspace.
* Movie and series discovery.
* ALL, ONLY MOVIES, and ONLY SERIES filters.
* Indian cinema categories.
* South Indian cinema categories.
* Bollywood/Hindi cinema.
* Hollywood.
* International cinema.
* Language and genre filters.
* Search.
* Sorting and pagination.
* Movie and series details.
* Posters and backdrops.
* Cast and crew information.
* Similar titles.
* Watchlist and favorites.
* Persistent user preferences.
* Optional AI-powered recommendations using existing Ollama integration.
* Optional trailer discovery.
* Appropriate caching and offline behavior.

Distinguish required functionality from optional enhancements.

### 0.3 Establish Architectural Boundaries

Define which existing application capabilities must remain untouched unless integration is genuinely necessary.

Examples:

* Existing chat and conversation history.
* Ollama model configuration.
* Voice processing.
* Existing settings.
* Existing navigation infrastructure.
* Existing logging and error handling.

Identify possible integration points without modifying application code.

### 0.4 Define the Data Strategy

Evaluate the suitability of TMDB as the primary source for movie and series metadata.

Documentation:
https://developer.themoviedb.org/docs/getting-started

Investigate:

* Authentication requirements.
* Search and discovery endpoints.
* Movie and television endpoints.
* Regional and language filters.
* Genre metadata.
* Credits.
* Image URLs.
* Similar titles and recommendations.
* Rate limits.
* Attribution requirements.
* Applicable usage and caching restrictions.

Do not assume that every desired filter or data field is directly available through one endpoint.

Document any fields that must be derived from multiple responses or handled by application code.

Do not request or expose API credentials during planning.

### 0.5 Define the AI Strategy

Explain the intended separation between deterministic application logic and LLM reasoning.

Application code should handle:

* Search.
* Filtering.
* Sorting.
* Pagination.
* Basic validation.
* Watchlist operations.
* Database access.

The existing Ollama integration may handle:

* Natural-language recommendation requests.
* Preference extraction.
* Recommendation explanations.
* Comparing retrieved titles.
* Optional reranking of verified candidate titles.

The AI must not invent movie metadata.

### 0.6 Define the Phase Dependencies

Produce a phase dependency map.

Explain why the phases must run in order and which later phases depend on earlier functionality.

### 0.7 Define Acceptance Criteria

Establish measurable criteria for:

* Functional correctness.
* UI consistency.
* Performance.
* Error handling.
* Data integrity.
* API reliability.
* Offline behavior.
* Regression prevention.

### 0.8 Deliver the Phase 0 Report

Provide:

1. Feature introduction.
2. Requirements summary.
3. Architecture assumptions that still need verification.
4. Data-provider evaluation.
5. Proposed architecture.
6. Phase dependency map.
7. Major risks.
8. Testing strategy.
9. Detailed implementation roadmap.

## Phase 0 Restrictions

* Do not implement Movie Hub.
* Do not create its UI.
* Do not modify application code.
* Do not install dependencies.
* Do not modify configuration.
* Do not create a database.
* Do not call external APIs requiring credentials.
* Do not begin Phase 1 automatically.

If repository inspection is necessary, perform read-only inspection only.

## Completion Criteria

Phase 0 is complete when the plan is documented, dependencies are understood, major risks are identified, and the implementation roadmap is ready.

Then stop and wait for explicit authorization to execute Phase 1.

---

# PHASE 1 — REPOSITORY AUDIT AND ARCHITECTURE DISCOVERY

## Objective

Inspect the existing AI Friend codebase in detail and determine how Movie Hub should be integrated without disrupting existing functionality.

This is the first implementation-stage phase, but it is primarily an investigation and preparation phase.

## 1.1 Inspect the Repository

Inspect:

* Project directory structure.
* Application entry points.
* UI framework and version.
* Navigation implementation.
* Main window and layout.
* Existing shared components.
* Theme and styling system.
* State-management patterns.
* Threading and asynchronous operations.
* API clients.
* Ollama integration.
* Storage and persistence.
* Configuration management.
* Logging.
* Error handling.
* Existing tests.
* Build and packaging process.

Follow existing project conventions.

Do not invent architectural details before examining the actual source code.

## 1.2 Map Existing Functionality

Identify the files and components responsible for:

* Main application startup.
* Chat interface.
* Conversation sidebar.
* Message input.
* Voice controls.
* Ollama requests.
* Settings.
* Application navigation.
* Local data storage.
* Existing caching mechanisms.

Record dependencies between these components.

## 1.3 Inspect Current UI Constraints

Determine:

* How the current main workspace is rendered.
* How navigation changes the displayed page.
* Whether the UI uses a stacked-page architecture, tabs, routes, or another mechanism.
* How window resizing is handled.
* How theme styling is shared.
* How existing components are reused.
* Whether the current application has an established pattern for adding new feature pages.

## 1.4 Assess API and Configuration Patterns

Inspect how existing external services are configured.

Determine how a new movie API key could be stored without exposing it in source code or logs.

Do not modify credentials or configuration during this phase.

## 1.5 Assess Existing Performance and Reliability

Identify relevant issues that could affect Movie Hub:

* UI-thread blocking.
* Slow synchronous API calls.
* Missing timeouts.
* Poor error handling.
* Unbounded image loading.
* Inconsistent state management.
* Existing test failures.

Record pre-existing defects separately from Movie Hub issues.

Do not undertake unrelated repairs.

## 1.6 Prepare the Integration Design

Document:

* Proposed navigation integration point.
* Proposed Movie Hub page/component boundary.
* Proposed service boundaries.
* Proposed model/data structures.
* Proposed local persistence strategy.
* Proposed API integration strategy.
* Proposed test locations.

Adapt the design to the real project.

Do not create speculative folders or unnecessary abstractions.

## 1.7 Establish the Baseline

Run appropriate existing tests when practical.

Record:

* Tests executed.
* Tests passed.
* Tests failed.
* Tests that could not run.
* Existing failures.
* Relevant startup or UI errors.

Do not claim that tests passed if they were not executed.

## Deliverables

Produce an architecture audit report containing:

1. Actual project architecture.
2. Important files and their responsibilities.
3. Existing navigation flow.
4. Existing API and Ollama integration patterns.
5. Storage and configuration patterns.
6. Testing baseline.
7. Identified integration risks.
8. Recommended implementation design.
9. Exact files likely to change in Phase 2.

## Restrictions

* Do not implement Movie Hub.
* Do not change the existing UI.
* Do not add dependencies.
* Do not refactor unrelated modules.
* Do not continue to Phase 2.

## Completion Criteria

The project architecture is understood, the integration design is documented, and the baseline results are recorded.

Stop and wait for explicit authorization to execute Phase 2.

---

# PHASE 2 — NAVIGATION FOUNDATION AND MOVIE HUB PAGE SHELL

## Objective

Introduce the new Movie Hub navigation destination and a structurally correct full-screen workspace.

This phase establishes the foundation. It does not implement the complete movie discovery experience.

## 2.1 Implement Navigation

Add Movie Hub to the existing application navigation.

Requirements:

* Keep the AI Companion accessible.
* Add a clearly identifiable Movie Hub destination.
* Use existing navigation conventions.
* Indicate which destination is active.
* Support switching between destinations.
* Preserve existing conversation state.
* Preserve voice settings and model configuration.
* Avoid duplicate main windows or application instances.

## 2.2 Create the Movie Hub Page Shell

Create the appropriate page or view component using the existing UI framework.

Include:

* Page header.
* Page title.
* Main content container.
* Search-bar placeholder or structural component.
* Content-type filter container.
* Regional-filter container.
* Main discovery-section containers.

These elements are structural placeholders only when their functionality belongs to a later phase.

Do not add fake movie results.

## 2.3 Apply Existing Design Conventions

Use:

* Existing theme tokens.
* Existing typography.
* Existing spacing.
* Existing buttons.
* Existing icons or icon libraries.
* Existing card and layout conventions.

If a design-system component exists, reuse it instead of creating an unnecessary duplicate.

## 2.4 Handle Navigation State

Ensure that:

* Returning to chat preserves the existing experience.
* Opening Movie Hub displays the correct page.
* Switching pages does not trigger unnecessary application restarts.
* Navigation works with the application's supported window dimensions.

## 2.5 Test the Foundation

Verify:

* Application startup.
* Navigation between the two destinations.
* Existing chat functionality.
* Page resizing.
* Theme consistency.
* No new startup errors.
* No regressions in existing tests.

## Deliverables

* Functional Movie Hub navigation.
* Full-screen page shell.
* List of changed files.
* Screenshots or a description of the resulting UI, where practical.
* Test results.

## Restrictions

* Do not integrate the movie API.
* Do not implement real movie searches.
* Do not add AI recommendations.
* Do not create the watchlist database.
* Do not implement future phases.

Stop and wait for authorization to execute Phase 3.

---

# PHASE 3 — MOVIE HUB UI AND INTERACTION DESIGN

## Objective

Build the actual Movie Hub interface and implement its local UI interactions using the existing design system.

The page may use controlled loading and empty states until real data integration is introduced.

## 3.1 Build the Page Layout

Implement:

* Header.
* Search input.
* Primary content-type controls.
* Regional and language filter controls.
* Genre selector.
* Sorting controls.
* Featured-section layout.
* Recommendation-section layout.
* Movie poster grid.
* Loading states.
* Empty states.
* Error-state presentation.

Do not use fabricated movie records as if they were real data.

## 3.2 Implement Primary Content-Type Controls

Create:

* ALL.
* ONLY MOVIES.
* ONLY SERIES.

For this phase, implement the local selection state and correct active-state styling.

If real results are not yet connected, do not pretend that the selection filters a real catalog.

The filtering of actual API results belongs to later phases.

## 3.3 Implement Filter Controls

Build UI controls for:

* Region.
* Language.
* Genre.
* Release year.
* Sorting.

Use a clear visual distinction between selected and unselected values.

Avoid excessively large filter panels.

## 3.4 Build Reusable Components

Create reusable components appropriate to the project's architecture.

Potential components include:

* MovieCard.
* MovieGrid.
* ContentTypeSelector.
* RegionFilter.
* GenreSelector.
* SearchBar.
* LoadingSkeleton.
* EmptyState.
* ErrorState.

Do not create a separate component for every tiny visual element without a reason.

## 3.5 Add Basic Interaction Polish

Implement:

* Hover states.
* Focus states.
* Keyboard-accessible controls.
* Clear filter actions.
* Responsive layout behavior.
* Consistent spacing.
* Appropriate scrolling.

## 3.6 Validate the UI

Test:

* Narrow and wide window sizes.
* Filter selection.
* Search-input behavior.
* Empty states.
* Navigation back to chat.
* Existing theme consistency.

## Deliverables

* Completed primary Movie Hub UI.
* Reusable UI components.
* Documented interactions.
* Test results.

## Restrictions

* Do not connect real movie API data.
* Do not implement Ollama recommendations.
* Do not implement persistent watchlists.
* Do not proceed to Phase 4.

Stop and wait for authorization to execute Phase 4.

---

# PHASE 4 — MOVIE DATA PROVIDER AND API SERVICE

## Objective

Create a reliable integration layer for retrieving real movie and television metadata.

## 4.1 Verify Provider Requirements

Use current official provider documentation.

If using TMDB, verify:

* Authentication.
* Search endpoints.
* Movie discovery.
* Television discovery.
* Genre endpoints.
* Detail endpoints.
* Credits endpoints.
* Image URL construction.
* Pagination.
* Supported filters.
* Error response formats.
* Rate limits.
* Attribution requirements.
* Applicable caching restrictions.

Do not assume endpoint parameters without verifying them.

## 4.2 Create the API Service

Implement a dedicated provider client using the existing networking conventions.

Responsibilities:

* Authentication.
* Request construction.
* Query parameter validation.
* Timeouts.
* Response parsing.
* Error normalization.
* Rate-limit handling.
* Logging without exposing secrets.

Keep API-specific details out of UI components.

## 4.3 Define Data Models

Create suitable models for:

* Movie.
* Television series.
* Genre.
* Cast and crew.
* Search result.
* Paged result.
* Movie details.
* Series details.

Use the project's established modeling approach.

Handle optional fields and incomplete responses safely.

## 4.4 Implement Essential Retrieval Operations

Implement the API operations required for:

* Movie search.
* Series search.
* Movie discovery.
* Series discovery.
* Genre retrieval.
* Movie details.
* Series details.
* Credits, where supported.

Do not implement every optional endpoint simply because it exists.

## 4.5 Handle API Failures

Handle:

* Missing credentials.
* Invalid credentials.
* Rate limits.
* Network disconnection.
* Request timeout.
* Server errors.
* Invalid JSON.
* Missing fields.
* Empty results.

Display user-friendly errors and preserve the application's responsiveness.

## 4.6 Add Configuration

Follow existing configuration conventions.

Do not hardcode real credentials.

Document how to configure the provider.

Do not print secrets in logs.

## 4.7 Test the Service

Use mocked responses for automated tests.

Test valid results, empty results, invalid responses, errors, and timeouts.

## Deliverables

* Working API service.
* Validated data models.
* Configuration instructions.
* API service tests.
* List of verified endpoints.

## Restrictions

* Do not implement the full discovery experience.
* Do not add AI recommendation logic.
* Do not proceed to Phase 5.

Stop and wait for authorization to execute Phase 5.

---

# PHASE 5 — REAL MOVIE DATA AND CONTENT-TYPE FILTERS

## Objective

Connect Movie Hub to real metadata and implement correct filtering for movies, series, and combined results.

## 5.1 Connect UI to the API

Replace applicable structural placeholders with real data from the API service.

Use proper loading and error states.

Do not load the complete catalog into memory.

## 5.2 Implement ALL

Display supported movie and series content together.

Use the provider's supported discovery endpoints and combine results through a clearly defined application-level strategy when necessary.

Preserve accurate content-type labels.

## 5.3 Implement ONLY MOVIES

Retrieve and display movie results only.

Ensure that television series cannot appear in this view.

## 5.4 Implement ONLY SERIES

Retrieve and display television-series results only.

Ensure that movies cannot appear in this view.

## 5.5 Implement Pagination

Support the provider's pagination model.

Avoid repeated requests for the same page.

Prevent stale responses from overwriting newer results.

## 5.6 Implement Sorting

Where supported, provide useful sorting options, such as:

* Popularity.
* Rating.
* Release date.
* Title.

Document the difference between provider-side sorting and local sorting.

Do not present unsupported sorting options as if they were functional.

## 5.7 Test Data Integrity

Verify:

* Correct content types.
* Correct titles.
* Correct poster paths.
* Correct release dates.
* Correct pagination.
* Correct sorting.
* Empty results.
* API failure handling.

## Deliverables

* Real movie and series results.
* Functional content-type filters.
* Pagination.
* Supported sorting.
* Automated tests.

## Restrictions

* Do not implement regional classification beyond the requirements needed for basic API integration.
* Do not implement watchlists or AI recommendations.
* Do not proceed to Phase 6.

Stop and wait for authorization to execute Phase 6.

---

# PHASE 6 — REGIONAL, LANGUAGE, GENRE, AND ADVANCED SEARCH FILTERS

## Objective

Implement reliable regional and content filters using actual metadata.

## 6.1 Implement Regional Categories

Support:

* Indian Cinema.
* South Indian Cinema.
* Bollywood/Hindi Cinema.
* Hollywood.
* International Cinema.

Define how each category is classified.

Do not assume that one country code or one language field perfectly represents an entire film industry.

Where classification requires multiple signals, document the logic and limitations.

## 6.2 Implement Language Filters

Support available languages such as:

* Hindi.
* Telugu.
* Tamil.
* Malayalam.
* Kannada.
* Bengali.
* Marathi.
* Punjabi.
* English.
* Other available languages.

Use provider-supported language identifiers rather than assuming display labels are accepted API parameters.

## 6.3 Implement Genre Filters

Load available genres from the provider.

Allow supported single-genre and multiple-genre combinations.

Handle differences between movie genres and television genres.

## 6.4 Implement Release-Year Filters

Support useful release-year selection.

Validate input and use provider-supported release-date parameters when available.

## 6.5 Implement Combined Filtering

Examples:

* ONLY MOVIES + Telugu + Action.
* ONLY SERIES + Hindi + Crime.
* ALL + English + Science Fiction.
* ONLY MOVIES + Indian Cinema + Comedy.

Verify that combined filters are applied consistently.

## 6.6 Implement Search

Support:

* Movie title search.
* Series title search.
* Person search where supported.
* Clear search.
* Debounced input.
* Enter-to-search.
* Search combined with compatible filters.

Do not promise that the provider can directly interpret arbitrary natural-language prompts. Natural-language interpretation belongs to the AI integration phase.

## 6.7 Test Classification Accuracy

Use representative titles from different Indian film industries and international cinema.

Verify that:

* The categories are not treated as mutually exclusive when they overlap.
* Movies and series remain correctly separated.
* Language and country are not confused.
* Unsupported classifications are handled honestly.

## Deliverables

* Functional regional filters.
* Functional language and genre filters.
* Release-year filtering.
* Advanced search.
* Combined-filter tests.
* Documented classification rules.

## Restrictions

* Do not implement AI recommendations.
* Do not implement the watchlist.
* Do not proceed to Phase 7.

Stop and wait for authorization to execute Phase 7.

---

# PHASE 7 — MOVIE DETAILS, POSTERS, AND RELATED TITLES

## Objective

Create detailed views for movies and series and make the discovery experience visually complete.

## 7.1 Implement Movie Details

Display available verified fields:

* Title.
* Overview.
* Release date.
* Genres.
* Runtime.
* Rating and source.
* Poster.
* Backdrop.
* Cast.
* Director.
* Similar titles.
* Trailer information, where available.

Do not fabricate unavailable fields.

## 7.2 Implement Series Details

Display supported information:

* Series title.
* Overview.
* First-air date.
* Genres.
* Rating and source.
* Cast and creators.
* Seasons.
* Episodes.
* Current status, where available.
* Related series.

Handle incomplete data.

## 7.3 Implement Poster Loading

Requirements:

* Use provider-approved image paths.
* Support multiple image sizes where available.
* Handle missing images.
* Avoid repeated downloads.
* Keep image loading off the UI thread.
* Prevent image failures from breaking the entire page.

## 7.4 Implement Related Titles

Use provider recommendations or similar-title endpoints where available.

Ensure that related titles use real provider identifiers and metadata.

## 7.5 Implement Trailer Discovery

Use supported provider metadata to identify trailer information.

Prefer official trailer sources where possible.

Do not assume that every title has a trailer.

Follow safe external-link handling conventions.

## 7.6 Test Details Views

Verify:

* Opening and closing details.
* Missing metadata.
* Long descriptions.
* Cast information.
* Poster failures.
* Related titles.
* Navigation and scrolling.

## Deliverables

* Movie details.
* Series details.
* Poster loading.
* Related titles.
* Optional trailer integration.
* Relevant tests.

## Restrictions

* Do not implement persistent user preferences or AI recommendation workflows.
* Do not proceed to Phase 8.

Stop and wait for authorization to execute Phase 8.

---

# PHASE 8 — LOCAL DATABASE, WATCHLIST, FAVORITES, AND USER PREFERENCES

## Objective

Provide persistent personal entertainment tracking.

## 8.1 Inspect Existing Storage

Reuse the existing database if it is suitable.

Otherwise, evaluate SQLite or the project's established persistence technology.

Do not create duplicate storage systems unnecessarily.

## 8.2 Define the Data Model

Store the minimum information necessary for:

* Watchlist entries.
* Favorites.
* Watched titles.
* Currently watching.
* User ratings.
* Preferred genres.
* Preferred languages.
* Preferred regions.
* Optional recommendation settings.

Use stable provider IDs and explicit content types.

## 8.3 Implement Watchlist Operations

Support:

* Add to watchlist.
* Remove from watchlist.
* Prevent duplicates.
* Mark as watched.
* Update status.
* View saved titles.
* Filter saved titles.

## 8.4 Implement Favorites and Ratings

Allow users to:

* Mark favorites.
* Remove favorites.
* Rate titles locally.
* View their ratings.

Keep local user ratings separate from provider ratings.

## 8.5 Implement Persistence

Verify that user data survives:

* Application restarts.
* Navigation changes.
* Temporary network failures.

Use appropriate database transactions and migrations.

Avoid storing unnecessary copies of large API responses.

## 8.6 Implement Preference Controls

Allow users to choose preferred genres, languages, and regions.

Provide sensible defaults and an easy way to reset preferences.

Do not infer sensitive personal characteristics from viewing preferences.

## 8.7 Test Persistence

Test duplicate prevention, updates, deletion, restart persistence, and data integrity.

## Deliverables

* Persistent local storage.
* Watchlist.
* Favorites.
* Watched status.
* Local ratings.
* User preferences.
* Database tests.

## Restrictions

* Do not implement AI recommendation ranking.
* Do not proceed to Phase 9.

Stop and wait for authorization to execute Phase 9.

---

# PHASE 9 — OLLAMA-POWERED AI RECOMMENDATIONS

## Objective

Integrate AI-assisted recommendations with the existing local Ollama infrastructure.

The recommendation system must complement real movie data rather than replace it.

## 9.1 Reuse the Existing Ollama Integration

Inspect and reuse the established client, configuration, model selection, timeout, and error-handling mechanisms.

Do not create a duplicate Ollama client without a demonstrated architectural need.

Do not change the application's default model configuration merely to implement Movie Hub.

## 9.2 Parse Natural-Language Requests

Support requests such as:

* Recommend an underrated Malayalam thriller.
* Find a Hindi comedy.
* Suggest a science-fiction series.
* Recommend movies similar to a selected title.
* Find a suspenseful movie from a particular period.
* Suggest titles matching selected preferences.

Convert requests into a structured representation containing applicable fields such as:

* Content type.
* Language.
* Region.
* Genres.
* Release period.
* Mood or descriptive preferences.
* Similar-title reference.
* Sorting preferences.

Validate the result before querying the provider.

## 9.3 Retrieve Real Candidate Titles

Use the existing API service to retrieve candidates.

Apply deterministic filtering and ranking where possible.

Do not ask the LLM to generate an unrestricted list of titles and present it as a verified catalog.

## 9.4 Add Recommendation Ranking

Develop a transparent ranking strategy using relevant signals such as:

* Match to selected genres.
* Language and region.
* Content type.
* User preferences.
* Release-period match.
* Provider metadata.
* Available popularity or rating signals.

Avoid treating missing ratings as zero-quality titles.

Do not claim that a recommendation is personalized based on preferences that have not been collected.

## 9.5 Generate Explanations

Where appropriate, use Ollama to explain why verified titles fit the user's request.

Provide the model with retrieved metadata.

Require explanations to stay grounded in supplied information.

Do not invent actors, plot points, ratings, awards, or release dates.

## 9.6 Add Recommendation UI

Provide a dedicated recommendation area.

Display:

* The user's interpreted preferences.
* Recommended titles.
* A concise explanation for each recommendation.
* Relevant metadata.
* An action to open details.
* An action to save a title.

Allow the user to adjust filters and try again.

## 9.7 Handle Slow or Unavailable AI

* Keep standard search responsive.
* Do not invoke Ollama for every filter click.
* Provide progress feedback for longer AI operations.
* Use reasonable timeouts.
* Handle unavailable models.
* Allow cancellation where supported.
* Avoid freezing the UI.
* Do not block access to ordinary discovery features.

## 9.8 Test Recommendation Quality

Use representative test requests.

Verify that structured filters are interpreted correctly, returned titles are real, and explanations use the supplied metadata.

Test behavior when the LLM is unavailable or returns invalid output.

## Deliverables

* Structured natural-language preference extraction.
* AI-assisted recommendations.
* Verified candidate retrieval.
* Grounded explanations.
* Graceful fallback.
* Relevant tests.

## Restrictions

* Do not proceed to Phase 10.

Stop and wait for authorization to execute Phase 10.

---

# PHASE 10 — CACHING, OFFLINE BEHAVIOR, AND PERFORMANCE

## Objective

Make Movie Hub responsive and useful during slow network conditions or temporary disconnection.

## 10.1 Implement Metadata Caching

Use the established storage and networking architecture.

Cache only information permitted under the data provider's applicable terms.

Define appropriate cache policies for:

* Search results.
* Movie details.
* Series details.
* Genres.
* Related titles.

Document cache expiration and refresh behavior.

## 10.2 Implement Image Caching

Use safe, bounded local image caching.

Requirements:

* Avoid downloading identical images repeatedly.
* Respect provider requirements.
* Avoid unbounded storage growth.
* Handle missing and corrupted cached images.
* Keep image operations off the UI thread.

## 10.3 Implement Offline States

When the network is unavailable:

* Keep saved watchlists accessible.
* Keep saved preferences accessible.
* Show cached titles when available.
* Clearly indicate when data may be stale.
* Provide a retry action.
* Avoid misleading success messages.

Do not promise access to uncached titles or live information offline.

## 10.4 Improve Request Efficiency

Implement appropriate:

* Debouncing.
* Request deduplication.
* Cancellation or stale-response protection.
* Bounded concurrency.
* Pagination.
* Cache reuse.
* Timeout handling.

## 10.5 Profile Performance

Measure relevant operations where practical:

* Page opening.
* Search response time.
* Filter changes.
* Poster loading.
* Database operations.
* UI responsiveness.

Identify regressions instead of guessing at performance.

## 10.6 Test Offline and Failure Scenarios

Test:

* No network.
* Slow network.
* API timeout.
* Rate limit.
* Cache hit.
* Cache miss.
* Corrupted cache.
* Missing image.
* Reconnection.

## Deliverables

* Cache implementation.
* Offline states.
* Performance improvements.
* Measurements and test results.

## Restrictions

* Do not proceed to Phase 11.

Stop and wait for authorization to execute Phase 11.

---

# PHASE 11 — UI POLISH, ACCESSIBILITY, AND OPTIONAL ENHANCEMENTS

## Objective

Polish the complete feature and implement approved enhancements without compromising stability.

## 11.1 Visual Refinement

Review:

* Spacing.
* Typography.
* Poster sizing.
* Card consistency.
* Filter layout.
* Scrolling.
* Loading states.
* Error messages.
* Empty states.
* Window resizing.
* Theme consistency.

Use the existing visual language.

## 11.2 Accessibility and Keyboard Interaction

Verify:

* Keyboard navigation.
* Focus indicators.
* Readable text.
* Accessible control labels.
* Reasonable contrast.
* Appropriate tab order.
* Usable keyboard shortcuts, where supported.

## 11.3 Voice-Powered Discovery

If supported by the existing voice architecture, add optional voice-driven search.

Example:
"Find me a Telugu action movie."

Convert recognized speech into structured preferences and display results in Movie Hub.

Do not break existing voice interactions or introduce a second independent microphone-processing pipeline unnecessarily.

Only implement this enhancement if it fits the project's architecture and the required functionality is available.

## 11.4 Mood-Based Recommendations

Optionally allow users to describe the type of experience they want.

Convert the request into appropriate search and ranking preferences.

Do not make unsupported claims about a movie's content.

## 11.5 Movie Comparison

Optionally support comparing two titles using verified metadata.

Do not fabricate missing facts.

## 11.6 Streaming Availability

If a supported provider offers relevant availability data, optionally show where a title can be watched in the user's selected region.

Verify regional and temporal accuracy.

Do not assume a streaming subscription or availability.

If a reliable data source is unavailable, omit this enhancement rather than inventing availability information.

## 11.7 Final UI Verification

Test the complete Movie Hub interface across supported window sizes and interaction states.

## Deliverables

* Visual polish.
* Accessibility improvements.
* Approved optional enhancements.
* Test results.

## Restrictions

* Do not begin Phase 12 automatically.

Stop and wait for authorization to execute Phase 12.

---

# PHASE 12 — FULL REGRESSION TESTING, BUG FIXES, AND RELEASE READINESS

## Objective

Verify the integrated Movie Hub and ensure that the existing AI Friend application continues to work.

This phase focuses on testing, fixing Movie Hub-related defects, and preparing a release report.

It is not permission to redesign or rewrite the entire application.

## 12.1 Audit the Completed Implementation

Inspect the files modified during the authorized phases.

Look for:

* Duplicate logic.
* Dead code.
* Unused imports.
* Incorrect error handling.
* Inconsistent models.
* Security issues.
* Hardcoded secrets.
* Memory leaks.
* Unbounded caching.
* Blocking UI operations.
* Inconsistent state.
* Inadequate validation.

Fix defects within the approved scope.

## 12.2 Run Automated Tests

Run applicable tests for:

* Navigation.
* Search.
* Content-type filters.
* Regional filters.
* Genre and language filters.
* API service.
* Movie details.
* Series details.
* Watchlist.
* Persistence.
* AI recommendations.
* Offline behavior.
* Error handling.
* Existing application functionality.

Report actual results.

## 12.3 Perform Regression Testing

Verify that the following still work:

* Existing chat.
* Conversation history.
* Ollama model configuration.
* Message input.
* Existing voice features.
* Settings.
* Application startup and shutdown.

Do not assume that a feature is working merely because its code was not intentionally changed.

## 12.4 Verify Security and Configuration

Check:

* API credentials are not hardcoded.
* Secrets are not committed.
* Logs do not reveal sensitive values.
* External links are handled safely.
* Database operations are robust.
* Error messages are understandable.

## 12.5 Perform Manual Verification

Provide a step-by-step checklist for manually verifying the desktop application.

Include:

* Opening Movie Hub.
* Searching for a movie.
* Switching content types.
* Applying regional filters.
* Opening a details page.
* Saving a title.
* Restarting the application.
* Testing offline behavior.
* Using AI recommendations.
* Returning to chat.

## 12.6 Prepare the Final Release Report

Provide:

1. Feature summary.
2. Architecture summary.
3. Files created and modified.
4. API and configuration instructions.
5. Database and caching behavior.
6. Automated test results.
7. Manual verification checklist.
8. Known limitations.
9. Remaining bugs.
10. Performance observations.
11. Security considerations.
12. Suggested next improvements.

Separate verified functionality from assumptions and untested behavior.

## Completion Criteria

The implementation is ready for review when:

* Movie Hub works as a separate main tab.
* Existing AI Friend functionality remains intact.
* Core discovery and filtering work correctly.
* Movie and series metadata is retrieved from the configured provider.
* User data persists correctly.
* AI recommendations use verified candidate titles.
* Errors and offline conditions are handled.
* Relevant tests have been executed.
* Known limitations are documented.

## Final Restriction

After producing the report, stop.

Do not implement additional features or begin another development phase without explicit authorization.

---

# GLOBAL ENGINEERING RULES

These rules apply to every phase.

## Rule 1 — One Phase at a Time

Execute only the phase I explicitly authorize.

## Rule 2 — Preserve Existing Functionality

Do not break or unnecessarily rewrite existing AI Friend features.

## Rule 3 — Inspect Before Editing

Use the real project architecture instead of assuming that files or components exist.

## Rule 4 — No Fake Completion

Do not use mock data as a substitute for a completed real-data integration unless the current phase explicitly calls for a visual-only placeholder.

Clearly label any test fixtures.

## Rule 5 — Test Before Reporting Success

Run appropriate tests and report actual results.

## Rule 6 — Keep Scope Controlled

Fix defects introduced by the current phase. Report unrelated pre-existing defects rather than silently expanding the scope.

## Rule 7 — Protect Credentials

Never hardcode or expose real API keys or secrets.

## Rule 8 — Respect Phase Dependencies

Do not skip prerequisite phases without my explicit decision.

## Rule 9 — Maintain Documentation

Update relevant documentation as each phase is completed, without creating unnecessary duplicate documents.

## Rule 10 — Wait for My Next Instruction

At the end of each phase, provide a completion report and wait.

Never begin the next phase automatically.

# STARTING BEHAVIOR

When you receive this master plan:

1. Read the complete plan.
2. Determine whether I explicitly authorized a particular phase.
3. If I authorized Phase 0, execute Phase 0 only.
4. If I authorized Phase 1 or a later phase, execute only that authorized phase, provided its prerequisites are satisfied.
5. If I have not authorized a phase, acknowledge the plan and wait for my phase-specific instruction.

**Do not implement all phases at once.**
