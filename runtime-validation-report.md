# Runtime Validation Report

**Generated**: 2026-11-22
**Target**: C:\Users\Admin\Desktop\ShareShelf

## Summary

| Step | Status | Exit Code | Details |
|---|---|---:|---|
| Startup | PASS | n/a | Django started on 127.0.0.1:8001 and `/login/` returned HTTP 200 |
| Django Integration Tests | PASS | 0 | 36 tests passed, 0 failed |
| Playwright Browser Tests | PASS | 0 | 3 browser journeys passed |
| Migration Consistency | PASS | 0 | `makemigrations --check --dry-run` reported no changes |

**Overall**: PASS

## Environment

- Docker: UNAVAILABLE — `docker` command not found
- Node.js: AVAILABLE — v24.22.1
- Playwright: AVAILABLE — Playwright 1.65.1 and Chromium installed
- Infrastructure tier: FALLBACK — Supabase/PostgreSQL real database is used because Docker is unavailable
- Browser tier: PRIMARY — Playwright against the running Django server

## Feature and Business-Rule Test Coverage

| Area | Completed test coverage |
|---|---|
| F-01 Register | Valid registration, duplicate email, password and role/community/profile fields |
| F-02 Login | Invalid login, 5-attempt lockout, 15-minute lock, successful-login reset |
| F-03 Dashboard | Member/admin routing and dashboard access |
| F-04 Profile | View/edit profile, address, language, ratings and profile photo support |
| F-05 Logout | POST logout clears the session |
| F-06 Item Listing | Create/edit, 1–5 photos, JPG/PNG, 5 MB limit, availability windows |
| F-07 Browse/Search | Community scope, category, date/name filters, and 5/10/25 km distance filter |
| F-08 Borrow Requests | Windows, overlap, active limit, approval/decline, cancellation and expiry |
| F-09 Pickup/Return | Two-party pickup and return confirmations plus borrowed/completed/overdue transitions |
| F-10 Ratings | Completed-only, participant-only, one-per-party, score range, averages and flagging |
| F-11 Notifications | Transaction events, unread/read behavior, due reminders and overdue alerts |
| F-12 Wishlist | Category/keyword validation, 10-entry limit, activation, deletion and community matching |
| BR-01 | Duplicate-email rejection |
| BR-02 | Letter-and-number password validator |
| BR-03 | Lender/borrower/both user types |
| BR-04 | Lender and borrower role access |
| BR-05 | Five failed attempts lock account for 15 minutes and success reset |
| BR-06 | Community ownership and same-community browse scope |
| BR-07 | Name, description, category and photo count |
| BR-08 | JPG/PNG and 5 MB photo validation |
| BR-09 | Availability-window start/end validation |
| BR-10 | Owner and own-item restrictions |
| BR-11 | Three active requests maximum |
| BR-12 | Availability-window and seven-day loan limits |
| BR-13 | Blocking overlap prevention |
| BR-14 | Owner-only approve/decline with decision timestamp |
| BR-15 | Three-day pending expiry |
| BR-16 | Overlapping pending requests declined after approval |
| BR-17 | Approved/borrowed/overdue item unlist/delete blocking |
| BR-18 to BR-20 | Two-party pickup and unique pickup/return confirmation |
| BR-21 | Due reminder and overdue transition |
| BR-22 | Overdue borrower cannot submit another request |
| BR-23 to BR-25 | Rating eligibility, uniqueness, score/review constraints and average flagging |
| BR-26 | Participant notifications for transaction events |
| BR-27 | Wishlist category/keyword and 10-active-entry limit |
| BR-28 | Same-community category/keyword wishlist matching |
| BR-29 | No payment or fee fields in the item/transaction implementation |
| BR-30 | English/Filipino language preference |

## Browser Journeys

1. Registration → invalid login → successful login → profile → logout
2. Login → browse items → create wishlist entry
3. Login borrower → confirm pickup → owner confirm pickup → borrower confirm return → owner confirm return → notifications/profile

## Verdict

environment:
  docker: UNAVAILABLE — `docker` command not found
  node: AVAILABLE — v24.22.1
  playwright: AVAILABLE — 1.65.1, Chromium installed
  infra-tier: FALLBACK(Supabase/PostgreSQL) — Docker unavailable
  browser-tier: PRIMARY(Playwright) — running server and browser executable available
startup: PASS — Django 127.0.0.1:8001, `/login/` HTTP 200
integration: PASS — exit_code: 0, passed: 36, failed: 0, skipped: 0
e2e: PASS — exit_code: 0, passed: 3, failed: 0
overall: PASS
