# System architecture & database design (Mermaid — renders on GitHub)

## Architecture
```mermaid
flowchart LR
  B[Browser<br/>HTML + CSS + vanilla JS<br/>Chart.js] -->|fetch /api + Bearer token| F[Flask app.py]
  F --> A[auth.py<br/>token check, RBAC, scoping, audit, notify]
  F --> R1[routes/employees.py]
  F --> R2[routes/time_off.py]
  F --> R3[routes/work.py]
  F --> R4[routes/insights.py]
  A & R1 & R2 & R3 & R4 --> D[db.py<br/>parameterised queries]
  D --> M[(MySQL workforce_portal)]
  F -->|serves static files| B
```

## Database relationships
```mermaid
erDiagram
  departments ||--o{ employees : has
  employees ||--o| users : "login"
  employees |o--o{ employees : "reports to"
  employees ||--o{ attendance : records
  employees ||--o{ leave_requests : applies
  employees ||--o{ leave_balances : holds
  employees ||--o{ performance_goals : has
  employees ||--o{ performance_reviews : receives
  employees ||--o{ tasks : assigned
  employees ||--o{ onboarding_records : checklist
  employees ||--o| offboarding_records : exit
  employees ||--o{ employee_history : changes
  departments ||--o{ projects : owns
  projects ||--o{ tasks : contains
  projects ||--o{ project_members : team
  employees ||--o{ project_members : member
  users ||--o{ notifications : receives
  users ||--o{ audit_logs : performs
  users ||--o{ leave_requests : "decides"
```
Extra tables beyond the brief's 14: `project_members`, `employee_history` (profile update history), `login_logs`, `settings`.
