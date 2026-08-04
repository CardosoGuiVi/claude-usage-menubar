<!--
Sync Impact Report
===================
Version change: [TEMPLATE] → 1.0.0 (initial ratification)
Rationale: First concrete constitution for this project, replacing all
template placeholders. Initial ratification of a project constitution is
treated as 1.0.0 regardless of section count, per the semantic versioning
governance rules defined below.

Modified principles: N/A (template placeholders → concrete principles)
  - [PRINCIPLE_1_NAME] → I. Minimal, Justified Stack
  - [PRINCIPLE_2_NAME] → II. Pure Core, Thin UI
  - [PRINCIPLE_3_NAME] → III. Quality Enforced, Not Suggested
  - [PRINCIPLE_4_NAME] → IV. No Polished Distribution for the MVP
  - [PRINCIPLE_5_NAME] → V. Simplicity Over Generality

Added sections:
  - Project Purpose (preamble)
  - Technical Constraints (was [SECTION_2_NAME])
  - Project Scope (was [SECTION_3_NAME])

Removed sections: none (template section slots retained, renamed and filled)

Templates requiring follow-up review:
  - .specify/templates/plan-template.md — ⚠ pending manual check that its
    Constitution Check gates reference these five principles by name
  - .specify/templates/spec-template.md — ⚠ pending manual check for scope
    alignment with Principle V (Simplicity Over Generality) and the
    macOS-only / no-network constraints
  - .specify/templates/tasks-template.md — ⚠ pending manual check that task
    categorization supports the pure-core/thin-UI module split (Principle II)
  - .specify/templates/checklist-template.md — no constitution-specific
    dependency detected; no change required

Deferred items / TODOs: none. Ratification date set to the date this
constitution was first adopted in this session (2026-08-04) since no prior
ratified version exists.
-->

# claude-usage-menubar Constitution

## Project Purpose

A macOS status bar app that displays Claude Code token usage information
(based on the data behind the `/usage` command). This is an open-source
project, and secondarily a Spec-Driven Development exercise using Claude
Code together with Spec Kit.

## Core Principles

### I. Minimal, Justified Stack
The project targets Python 3.11+. `rumps` is the only accepted UI
dependency. New dependencies MUST NOT be added unless they solve a problem
that the standard library and `rumps` cannot solve. Heavy frameworks
(Electron, alternative GUI toolkits, etc.) are prohibited. Rationale: a
small, well-understood dependency surface keeps the app easy to audit,
install, and maintain as a solo/open-source project.

### II. Pure Core, Thin UI
Usage data reading and aggregation logic (parsing Claude Code session logs)
MUST live in a module that is independent from `rumps` and performs no UI
I/O. The status bar layer MUST be a thin shell that only consumes that core
module. Rationale: this makes the core testable without running the UI and
keeps business logic decoupled from a specific UI toolkit choice.

### III. Quality Enforced, Not Suggested
No change is accepted unless it passes lint and automated tests. This rule
MUST be enforced by an automated hook (e.g., pre-commit or CI gate), not
merely documented as convention. Rationale: documented-only conventions
erode over time; automated enforcement makes quality non-optional.

### IV. No Polished Distribution for the MVP
py2app/pyinstaller packaging, code signing, Homebrew Cask/Formula, and
LaunchAgent autostart are out of scope for the MVP. "Done" means: someone
clones the repo, runs a simple install script (venv + pip), and the app
works. Autostart MAY be revisited as a future iteration but is explicitly
not part of the MVP. Rationale: keeps early effort focused on core value
(usage visibility) instead of distribution polish.

### V. Simplicity Over Generality
The scope is specifically a Claude Code status bar app — not a generic
monitoring framework. Complexity that would only serve hypothetical future
use cases (pluggable data sources, multi-tool support, configurable
backends, etc.) MUST be rejected. Rationale: generality has a real cost in
code and cognitive overhead that isn't justified by the project's actual,
narrow purpose.

## Technical Constraints

- Platform: macOS only. Linux/Windows compatibility is not a concern.
- Data source: local Claude Code session files at
  `~/.claude/projects/**/*.jsonl` only. No network calls and no external
  API dependencies are permitted.
- Persistence: the app MUST NOT maintain its own data store. All displayed
  state is recomputed from local logs on each read.

## Project Scope

This project's primary deliverable is a working macOS status bar app for
Claude Code token usage. Its secondary purpose is to serve as a worked
example of Spec-Driven Development using Claude Code and Spec Kit. Features
and design decisions should be evaluated against both purposes, but the
first (a working, minimal, trustworthy usage indicator) takes precedence
over the second when they conflict.

## Governance

This constitution takes precedence over plan and task decisions. Any
conflict between a task and a principle stated here MUST be resolved by
adjusting the task, not by ignoring the principle.

- **Amendment procedure**: Amendments are made by editing this file via the
  `/speckit-constitution` workflow (or an equivalent explicit, reviewed
  edit). Each amendment MUST update the Sync Impact Report at the top of
  this file and the version/date footer below.
- **Versioning policy**: This constitution follows semantic versioning:
  - MAJOR: backward-incompatible governance or principle removals/redefinitions.
  - MINOR: a new principle or section is added, or existing guidance is
    materially expanded.
  - PATCH: clarifications, wording, or typo fixes with no semantic change.
- **Compliance review**: Every `/speckit-plan` and `/speckit-tasks` run MUST
  verify its output against the principles above (in particular the
  pure-core/thin-UI split, dependency minimalism, and the no-network/local-only
  data constraint). Any deviation MUST be justified explicitly in the plan
  or rejected in favor of a compliant approach.

**Version**: 1.0.0 | **Ratified**: 2026-08-04 | **Last Amended**: 2026-08-04
