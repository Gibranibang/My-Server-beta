---
phase: 06-public-share-link-backend-bundled-zerotier-one-auto-install
plan: 04
subsystem: companion-ui, metrics
tags: [route-pill, disk-telemetry, smb-source]
requires: []
provides: [dynamic route pill icon, Option A DISK telemetry isolation]
affects: [zima_metrics_manager.py, myserver_core_service.py, HomeView.tsx]
key-files:
  created:
    - MyServer Desktop Companion UI/src/companion/__tests__/HomeView.routePill.test.tsx
    - tests/test_disk_telemetry_isolation.py
  modified:
    - MyServer Desktop Companion UI/src/companion/views/HomeView.tsx
    - zima_metrics_manager.py
    - myserver_core_service.py
status: complete
requirements: [RPI-01, DSK-01]
commits: 2
plan_head_before: 829756a
plan_head_after: 7a502174a64c6be7c4221217291cc02ad4059c46
actuals:
  tasks: 2
  commits: 2
---

# Phase 06 Plan 04: Route Pill Icon & DISK Telemetry Isolation Summary

Footer route pill now renders `<currentRouteMeta.icon` (1-line change, CRLF preserved), and `ZimaMetricsClient` skips Windows SMB drive scanning and purges stale network-drive entries when `smb_source == "backend"`, with `fetch_metrics(self, on_online_callback=None)` unchanged.

## Commits
- Task 1: `61b7e9f` — HomeView line 327 + routePill vitest suite
- Task 2: `7a50217` — smb_source guard, core-service sync, unit tests

## Deviations from Plan

**1. [Rule 1 - Bug] Plan line count wrong (640 vs 639)**
- HomeView.tsx has 639 lines at HEAD (file ends with CRLF; plan assumed 640). Test 4 asserts 639 — the edit changes zero line counts.
- **2. [Rule 1 - Bug]** Existing test queried badge text "Active"; test language is "id" so badge renders "Aktif". Fixed in test.

## Verification
- Vitest routePill: 2 passed. Python unittest (disk isolation + smb toggle + no_hardcoding): 23 OK.
- Acceptance greps: self.smb_source=1, is_backend_smb=2, srv_smb_source=5; signature intact. No version bump. STATE/ROADMAP untouched; `.gitignore` not staged.
- Note: commits made on `main` (sequential mode, same as plan 06-03).

## Known Stubs
None.

## Self-Check: PASSED
