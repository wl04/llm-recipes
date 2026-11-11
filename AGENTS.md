# Agent development rules

## Applying these rules

- General rules define the intent of the requirements; language-specific sections clarify implementation. Explicit project conventions take precedence over default recommendations.
- Apply language-specific guidance only to languages used in the affected code. If a language has no section, follow its standard conventions and the project configuration; this does not block work.
- Add language-specific sections as needed: naming, errors and resources, asynchronous code, documentation, and checks. Do not repeat general rules.

## General principles

- Preserve public contracts unless the task requires changing them; consider the language, framework, and project conventions.
- KISS, YAGNI: choose a simple solution for the current task; add layers and dependencies only for a concrete need. DRY: consolidate repeated rules, not merely similar domain concepts.
- Apply SOLID according to its intent: separate responsibilities, preserve contracts, and use narrow interfaces at real boundaries. Do not automatically create abstractions for every type; consider the language's programming model.
- Refactoring preserves behavior; optimization requires a demonstrated need. Explain review feedback and take responses into account.

## Production code

### Commands and queries

- Apply CQS to domain operations; it does not require separate stores or a message bus.
- **Commands:** change state and use action verbs in their names. They usually return no useful data, but may report completion or failure through the language's established mechanisms.
- **Queries:** return data without observable side effects. Explicitly define behavior when data is absent; logical checks return a boolean. Choose names and access patterns according to language conventions.
- Do not add hidden mutations or notifications to queries. Do not expose mutable internal state in ways that bypass domain operations: use safe borrowing, a copy, or a read-only view.
- Commands must check their own preconditions: state may change between an earlier check and execution.
- Allow justified combinations of mutation and returned data for atomic operations (dequeueing, creation that returns an ID), iterators, and external contracts. Preserve atomicity and explain non-obvious exceptions. Do not introduce unnecessary reads or adapters solely to satisfy CQS.

### Boundaries, errors, and state

- Separate business rules from HTTP, databases, files, and UI; pass external dependencies explicitly.
- Validate inputs at system boundaries and invariants within operations. Preserve consistency on failure; use transactions for related changes.
- Distinguish missing data from failure; do not disguise failures as empty or zero results. Do not ignore errors; add context without secrets or personal data.

## Tests

### Naming

Use the semantic order `Operation_Behavior_Context`: operation, expected observable behavior, conditions. Use English words separated by `_`, with casing appropriate to the language. Avoid vague names such as `Works` / `Correctly`.

This pattern also applies to scenario names expressed as strings. Add any mandatory framework prefix before the pattern; automatically named documentation tests are exempt.

### Behavior and robustness

- One test covers one behavior; several related assertions are acceptable. For commands, check observable effects and errors; for queries, check returned data and, where relevant to the risk, the absence of side effects.
- Test the contract, not private methods or internal call order. Do not duplicate the implementation in tests or test insignificant formatting.
- Choose scenarios based on risk: normal cases, boundaries, invalid input, dependency failures, and violated preconditions. Accompany bug fixes with a test that reproduces the bug.
- Isolate data and execution order; control time, randomness, and IDs where they matter. Substitute external services in unit tests and verify real connections through integration tests.
- For asynchronous behavior, wait for a specific condition with a timeout instead of an arbitrary delay.

## Code style

### Production code

- Choose PascalCase, camelCase, or snake_case according to the language and identifier type; maintain a consistent project style, including tests.
- Use the project's formatter and linter; otherwise follow language conventions and record formatting choices in configuration. Avoid mixing broad formatting changes with behavior changes unless necessary.
- English names should convey meaning, consistent domain terminology, and units; avoid vague names such as `data`, `tmp`, and double negatives.
- Reduce nesting with early exits; extract domain constants. Split methods by responsibility and level of detail, not by line-count limits.
- API documentation describes the contract: purpose, constraints, results, errors, and side effects. Comments explain non-obvious reasons and constraints. Do not restate code or discussion/change history; retain the current rationale. Remove outdated comments and commented-out code.

### Tests

- Arrange → Act → Assert; separate stages with blank lines and add labels when useful.
- Use meaningful names. Keep important data close to the scenario; factories should hide only incidental details.
- Specify explicit expectations rather than computing them with the function under test. Parameterize datasets for the same rule; test different behaviors separately.

## Language-specific guidance

### C#

- Tests: `ApplyDiscount_ReducesTotal_WhenCustomerIsEligible`.
- Types, methods, and properties use PascalCase; parameters and local variables use camelCase; private fields follow project conventions (usually `_camelCase`).
- Represent simple state reads as properties (`Balance`); use methods for read operations (`GetBalanceAsync()`). Use `Is*`, `Has*`, and `Can*` for logical checks where natural.
- Name asynchronous methods with the `Async` suffix; use `Task` (or a justified `ValueTask`) for completion without data, not `async void`, except for event handlers. Pass `CancellationToken` to long-running operations that support cancellation.
- Respect nullable contracts; do not suppress warnings with `!` without justification. Release resources owned by the current code through `using` / `await using`.
- Write API documentation as XML comments using `///`.
- Default checks: `dotnet build`, `dotnet test`, and configured analyzers.

### Rust

- Tests: `apply_discount_reduces_total_when_customer_is_eligible`; `_` also separates words within the semantic parts.
- Do not mechanically transfer class-based architecture; introduce traits for real boundaries and necessary behavioral abstractions.
- Functions, methods, and variables use snake_case; types and traits use UpperCamelCase; constants use SCREAMING_SNAKE_CASE. Ordinary getters omit `get_` (`balance()`); name conversions according to their meaning: `as_*`, `to_*`, `into_*`.
- Represent expected errors through `Result` (`Result<(), E>` for commands without data), and missing values through `Option`; propagate errors with `?` where appropriate. Do not use `unwrap()` / `expect()` in production code without a justified invariant; they are acceptable in tests.
- Choose ownership and borrowing according to the contract; do not add `clone()` merely to bypass an ownership error without assessing the need and copying cost.
- Prefer safe Rust. For necessary `unsafe` code, document the API's safety requirements and explain why the particular block satisfies them.
- Document code with rustdoc (`///`, `//!`); add `Errors`, `Panics`, `Safety`, and testable examples as needed.
- Default checks: `cargo fmt --check`, `cargo clippy`, and `cargo test`, including applicable doctests.

### Python

- Tests: `test_apply_discount_reduces_total_when_customer_is_eligible`; retain the `test_` prefix (the discovery convention shared by pytest and stdlib `unittest`) and the `Operation_Behavior_Context` order.
- Functions, methods, variables, and modules use `snake_case`; classes use `PascalCase`; constants use `UPPER_SNAKE_CASE`. Follow PEP 8 and project conventions.
- Add type annotations to public contracts and nontrivial boundaries; prefer precise types and avoid unjustified `Any`. Do not complicate code with annotations solely for completeness.
- Use meaningful exceptions for expected errors; catch specific types and preserve the cause with `raise ... from ...` when translating errors. Do not suppress exceptions without justification.
- Manage resources through `with` / `async with`; avoid mutable default argument values. Use `None` for absent values with explicit semantics.
- In `asyncio`, do not block the event loop; ensure created tasks finish and cancellation is handled correctly. Use `TaskGroup` for related tasks when supported by the Python version.
- Document public APIs with PEP 257 docstrings describing the contract rather than the implementation. Default checks: the project's configured test runner (pytest or stdlib `unittest`), formatter, linter, and type checker.

## Project-specific rules

- Determine tool versions, check commands, and architectural constraints from local instructions, configuration, and CI. Account for target platforms and enabled capabilities.
- The language commands above are guidance when project configuration is absent; do not run checks for unrelated languages. Record missing information in the relevant project's instructions, not in the general rules.

## Workflow

1. Study the affected code, tests, and project rules; identify applicable language guidance and checks.
2. When changing behavior, follow TDD: a test that fails for the expected reason → implementation → refactoring.
3. Run checks relevant to the change and mandatory project checks; review the final diff for errors and unrelated edits.
4. Report changes, checks performed, and limitations; do not claim successful testing without running it.
5. When commits are needed, keep them small and cohesive, following commit-message and branch conventions.

## Repository instructions

Read and follow [project instructions](docs/project-instructions.md). Project-specific instructions take precedence over these general guidelines.
