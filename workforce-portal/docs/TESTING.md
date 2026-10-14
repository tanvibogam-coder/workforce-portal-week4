# Test cases & report
Automated API integration tests: `tests/test_api.py` (pytest, 20 tests, run against the seeded MySQL database). Result at submission: **20 passed**.

| Area | Test cases covered |
|---|---|
| Auth | missing/invalid credentials, invalid email format, wrong password, no/garbage token → 401 |
| RBAC | employee blocked from directory/admin (403), HR blocked from super-admin pages, employee cannot read others' records, manager limited to own department |
| Employees | create, duplicate email (409), invalid email, missing fields, edit + history entry, search, deactivate, bad upload type, SQL-injection string is inert |
| Attendance | check-in, double check-in blocked, summary restricted to managers+, correction needs reason and writes audit log |
| Leave | end<start, empty reason, overlap (409), insufficient balance, employee cannot approve, balance deducted on approval, double decision blocked, long leave → HR approval stage |
| Performance | score calculation 0-100, out-of-range rejected, employee/other-department review blocked |
| Tasks | assignee can update own task, invalid status, cannot touch others' tasks, employee cannot create tasks, overdue flag |
| Dashboards/reports | each role gets its dashboard, 5 reports + CSV, report access restricted |
| Notifications / lifecycle | read-all, onboarding toggle + access control, exit date validation |
| Errors | unknown API route returns JSON error, health check |

Frontend: every page was loaded under each role against the live API in a headless DOM (0 script errors) and the add-employee form validation + submit flow was exercised.

## Defects found and fixed during testing
1. `DATE_FORMAT(col,'%Y-%m')` returned the literal format string with mysql-connector parameter binding (monthly attendance was always empty) → replaced with `LEFT(col,7)`.
2. Report query parameter order for date-range reports → fixed with explicit parameter mapping.

## Manual checks still recommended
Session expiry after 120 min, mobile layout, Chart.js rendering (CDN needs internet), screenshots for the submission.
