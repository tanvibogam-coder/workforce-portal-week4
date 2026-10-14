# API documentation
Base URL `http://127.0.0.1:5000/api` · JSON in/out · send `Authorization: Bearer <token>` (from `/auth/login`, valid 120 min).
Success → the resource or `{message,...}`. Errors always → `{"error": "readable message"}` with 400 validation, 401 not logged in, 403 not allowed, 404 not found, 409 conflict, 500 server.
Roles: **SA** super_admin · **HR** hr_admin · **MGR** manager (own department) · **EMP** employee (own data). "Any" = every logged-in user.

| Method & path | Who | Purpose |
|---|---|---|
| POST `/auth/login` · `/auth/logout` · GET `/auth/me` · PUT `/auth/password` | public / any | Session handling, change own password |
| GET `/meta/departments` | any | Department list |
| GET `/employees` `?q&dept&status&page&per` | SA HR MGR | Search / filter / paginate |
| GET `/employees/lookup` | any | Employee picker (scoped to what you may see) |
| GET `/employees/<id>` | scoped | Profile + update history + documents |
| POST `/employees` · PUT `/employees/<id>` · POST `/employees/<id>/deactivate` | SA HR | Create (auto login, leave balances, onboarding checklist) · edit (history logged) · deactivate |
| GET `/employees/export` | SA HR | CSV export |
| POST `/employees/<id>/documents` | SA HR | Upload (pdf/png/jpg/doc/docx/txt, ≤5 MB) |
| POST `/attendance/check-in` · `/attendance/check-out` | any | Own attendance |
| GET `/attendance` `?employee_id&month=YYYY-MM` | scoped | Daily records (late / half-day / missing check-out classified) |
| GET `/attendance/summary` · `/attendance/exceptions` | SA HR MGR | Monthly summary · exception report |
| PUT `/attendance/<id>` | SA HR | Correct record (reason required → audit log + notification) |
| GET `/leave/balances` · GET `/leave` `?status&mine` · GET `/leave/calendar?month` | scoped | Balances, requests, team calendar |
| POST `/leave` | any | Apply (validates dates, overlap, balance; weekends excluded) |
| POST `/leave/<id>/decide` `{decision: approve\|reject, comment}` | SA HR MGR | Manager approves → HR stage if longer than `hr_approval_days` |
| GET/POST `/performance/goals` · PUT `/performance/goals/<id>` | scoped / MGR+ / scoped | Goals & KPIs, progress |
| POST `/performance/reviews` · GET `/performance/reviews` · GET `/performance/overview` | MGR+ / scoped / MGR+ | Review (task completion & attendance auto-calculated, weighted score) |
| POST `/performance/self` | any | Self-assessment |
| GET/POST `/projects` · POST `/projects/<id>/members` | scoped / MGR+ | Projects & allocation |
| GET/POST `/tasks` · PUT `/tasks/<id>` | scoped / MGR+ / assignee or MGR | Tasks (overdue flag), status updates |
| GET `/dashboard` `?from&to&me=1` | any | HR / manager / employee dashboard payload |
| GET `/reports/<headcount\|attendance\|leave\|performance\|tasks>` `?from&to&format=csv` | SA HR MGR | Reports |
| GET `/notifications` · POST `/notifications/<id>/read` · `/notifications/read-all` | any | In-app notifications |
| POST `/notifications/run-reminders` | SA HR | Task-deadline, missing-check-out and onboarding reminders |
| GET `/onboarding` · `/onboarding/<emp_id>` · POST `/onboarding/<item_id>/toggle` | SA HR | Checklists (all done → employee becomes Active) |
| GET/POST `/offboarding` · PUT `/offboarding/<id>` | MGR+ / HR for updates | Exit workflow (all steps + approval → Exited, login disabled) |
| GET/PUT `/admin/users[/<id>]` | SA | Roles, enable/disable, password reset |
| GET `/admin/settings` (HR) · PUT (SA) · GET `/admin/audit` (HR) · GET `/admin/logins` (SA) | | Settings, audit log, login activity |
