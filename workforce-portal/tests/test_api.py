"""API integration tests. Run after `python init_db.py`:   cd backend && python -m pytest ../tests -v"""
import sys, uuid
from datetime import date, timedelta
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))
from app import app  # noqa: E402

CREDS = {'admin': ('admin@company.com', 'Admin@123'), 'hr': ('hr@company.com', 'Hr@12345'),
         'manager': ('manager@company.com', 'Manager@123'), 'employee': ('employee@company.com', 'Employee@123')}


@pytest.fixture(scope='module')
def c():
    return app.test_client()


def auth(c, who):
    r = c.post('/api/auth/login', json=dict(zip(('email', 'password'), CREDS[who])))
    assert r.status_code == 200, r.get_json()
    return {'Authorization': 'Bearer ' + r.get_json()['token']}


def monday(weeks_ahead):
    d = date.today() + timedelta(weeks=weeks_ahead)
    return d - timedelta(days=d.weekday())


# ---- Module 1: authentication & RBAC ----
def test_login_validation_and_failure(c):
    assert c.post('/api/auth/login', json={}).status_code == 400
    assert c.post('/api/auth/login', json={'email': 'bad', 'password': 'x'}).status_code == 400
    assert c.post('/api/auth/login', json={'email': 'hr@company.com', 'password': 'wrong'}).status_code == 401


def test_protected_routes_need_token(c):
    assert c.get('/api/employees').status_code == 401
    assert c.get('/api/employees', headers={'Authorization': 'Bearer garbage'}).status_code == 401


def test_role_based_access(c):
    e = auth(c, 'employee')
    assert c.get('/api/employees', headers=e).status_code == 403
    assert c.get('/api/admin/users', headers=e).status_code == 403
    assert c.get('/api/admin/users', headers=auth(c, 'hr')).status_code == 403   # super admin only
    assert c.get('/api/admin/users', headers=auth(c, 'admin')).status_code == 200


def test_employee_cannot_view_others(c):
    e = auth(c, 'employee')
    assert c.get('/api/employees/1', headers=e).status_code == 403
    assert c.get('/api/attendance?employee_id=1', headers=e).status_code == 403


def test_manager_scoped_to_department(c):
    m = c.get('/api/employees', headers=auth(c, 'manager')).get_json()
    assert m['total'] > 0 and all(x['department'] == 'Engineering' for x in m['items'])


# ---- Module 2: employee master data ----
def test_employee_crud_and_duplicate_prevention(c):
    h = auth(c, 'hr'); email = f'test.{uuid.uuid4().hex[:6]}@company.com'
    body = {'full_name': 'Test Person', 'email': email, 'department_id': 3, 'designation': 'Intern', 'joining_date': date.today().isoformat()}
    r = c.post('/api/employees', json=body, headers=h); assert r.status_code == 201
    eid = r.get_json()['id']
    assert c.post('/api/employees', json=body, headers=h).status_code == 409                       # duplicate email
    assert c.post('/api/employees', json={**body, 'email': 'nope'}, headers=h).status_code == 400  # invalid email
    assert c.post('/api/employees', json={'email': email}, headers=h).status_code == 400            # mandatory fields
    assert c.put(f'/api/employees/{eid}', json={'designation': 'Analyst'}, headers=h).get_json()['changed'] == ['designation']
    detail = c.get(f'/api/employees/{eid}', headers=h).get_json()
    assert detail['history'][0]['new_value'] == 'Analyst'                                           # update history
    assert c.get('/api/employees?q=Test Person', headers=h).get_json()['total'] >= 1                # search
    assert c.post(f'/api/employees/{eid}/deactivate', headers=h).status_code == 200


def test_upload_validation(c):
    import io
    h = auth(c, 'hr')
    bad = c.post('/api/employees/5/documents', data={'file': (io.BytesIO(b'x'), 'evil.exe')}, headers=h, content_type='multipart/form-data')
    assert bad.status_code == 400


def test_sql_injection_is_inert(c):
    r = c.get("/api/employees?q=' OR 1=1 --", headers=auth(c, 'hr')); assert r.status_code == 200 and r.get_json()['total'] == 0


# ---- Module 3: attendance ----
def test_attendance_flow(c):
    e = auth(c, 'manager')
    first = c.post('/api/attendance/check-in', headers=e)
    assert first.status_code in (201, 409)
    assert c.post('/api/attendance/check-in', headers=e).status_code == 409                          # no double check-in
    assert c.get('/api/attendance/summary', headers=auth(c, 'employee')).status_code == 403


def test_attendance_correction_needs_reason_and_logs(c):
    h = auth(c, 'hr'); prev = (date.today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m'); rec = c.get(f'/api/attendance?employee_id=5&month={prev}', headers=h).get_json()
    assert rec, 'seed data expected'
    assert c.put(f"/api/attendance/{rec[0]['id']}", json={'check_in': rec[0]['check_in']}, headers=h).status_code == 400
    ok = c.put(f"/api/attendance/{rec[0]['id']}", json={'check_in': rec[0]['check_in'], 'reason': 'Badge reader fault'}, headers=h)
    assert ok.status_code == 200
    assert any(a['action'] == 'ATTENDANCE_CORRECTION' for a in c.get('/api/admin/audit', headers=h).get_json())


# ---- Module 4: leave workflow ----
def test_leave_validation_overlap_balance_and_approval(c):
    e, m, h = auth(c, 'employee'), auth(c, 'manager'), auth(c, 'hr')
    start = monday(30); end = start + timedelta(days=1)
    payload = {'leave_type': 'Casual Leave', 'start_date': start.isoformat(), 'end_date': end.isoformat(), 'reason': 'Test leave'}
    assert c.post('/api/leave', json={**payload, 'end_date': (start - timedelta(days=1)).isoformat()}, headers=e).status_code == 400  # end<start
    assert c.post('/api/leave', json={**payload, 'reason': ''}, headers=e).status_code == 400
    r = c.post('/api/leave', json=payload, headers=e); assert r.status_code == 201, r.get_json()
    lid = r.get_json()['id']
    assert c.post('/api/leave', json=payload, headers=e).status_code == 409                           # overlap
    big = monday(40); assert c.post('/api/leave', json={**payload, 'leave_type': 'Sick Leave', 'start_date': big.isoformat(), 'end_date': (big + timedelta(days=30)).isoformat()}, headers=e).status_code == 400  # balance
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'approve'}, headers=e).status_code == 403  # employee can't approve
    before = {b['leave_type']: b['balance'] for b in c.get('/api/leave/balances', headers=e).get_json()}
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'approve'}, headers=m).get_json()['status'] == 'Approved'
    after = {b['leave_type']: b['balance'] for b in c.get('/api/leave/balances', headers=e).get_json()}
    assert after['Casual Leave'] == before['Casual Leave'] - 2                                          # balance deducted
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'reject'}, headers=m).status_code == 409  # already decided


def test_long_leave_needs_hr_approval(c):
    e, m, h = auth(c, 'employee'), auth(c, 'manager'), auth(c, 'hr')
    s = monday(50); r = c.post('/api/leave', json={'leave_type': 'Unpaid Leave', 'start_date': s.isoformat(), 'end_date': (s + timedelta(days=13)).isoformat(), 'reason': 'Long trip'}, headers=e)
    lid = r.get_json()['id']
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'approve'}, headers=m).get_json()['status'] == 'Pending HR'
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'approve'}, headers=m).status_code == 403
    assert c.post(f'/api/leave/{lid}/decide', json={'decision': 'approve'}, headers=h).get_json()['status'] == 'Approved'


# ---- Modules 5-6: performance, projects, tasks ----
def test_review_scoring_and_permissions(c):
    m, e = auth(c, 'manager'), auth(c, 'employee')
    body = {'employee_id': 6, 'period': 'Q3 2026', 'quality_score': 80, 'productivity': 75, 'goal_achievement': 70, 'feedback': 'ok'}
    r = c.post('/api/performance/reviews', json=body, headers=m); assert r.status_code == 201 and 0 <= r.get_json()['overall'] <= 100
    assert c.post('/api/performance/reviews', json={**body, 'quality_score': 150}, headers=m).status_code == 400
    assert c.post('/api/performance/reviews', json=body, headers=e).status_code == 403
    assert c.post('/api/performance/reviews', json={**body, 'employee_id': 9}, headers=m).status_code == 403  # other department


def test_task_permissions(c):
    e, m = auth(c, 'employee'), auth(c, 'manager')
    mine = c.get('/api/tasks?mine=1', headers=e).get_json(); assert mine
    tid = mine[0]['id']
    assert c.put(f'/api/tasks/{tid}', json={'status': 'In Progress'}, headers=e).status_code == 200
    assert c.put(f'/api/tasks/{tid}', json={'status': 'Bogus'}, headers=e).status_code == 400
    other = [t for t in c.get('/api/tasks', headers=auth(c, 'admin')).get_json() if t['assignee'] != 'Amit Patil'][0]['id']
    assert c.put(f'/api/tasks/{other}', json={'status': 'Completed'}, headers=e).status_code == 403
    assert c.post('/api/tasks', json={'title': 'x', 'project_id': 1, 'assignee_id': 5}, headers=e).status_code == 403


def test_overdue_tasks_flagged(c):
    assert any(t['overdue'] for t in c.get('/api/tasks', headers=auth(c, 'admin')).get_json())


# ---- Modules 7-9: dashboards, reports, notifications, lifecycle ----
def test_dashboards_per_role(c):
    assert c.get('/api/dashboard', headers=auth(c, 'hr')).get_json()['kind'] == 'hr'
    assert c.get('/api/dashboard', headers=auth(c, 'manager')).get_json()['kind'] == 'manager'
    d = c.get('/api/dashboard', headers=auth(c, 'employee')).get_json(); assert d['kind'] == 'employee' and d['balances']


def test_reports_and_csv(c):
    h = auth(c, 'hr')
    for kind in ('headcount', 'attendance', 'leave', 'performance', 'tasks'):
        assert c.get(f'/api/reports/{kind}', headers=h).status_code == 200, kind
    assert c.get('/api/reports/headcount?format=csv', headers=h).mimetype == 'text/csv'
    assert c.get('/api/reports/headcount', headers=auth(c, 'employee')).status_code == 403


def test_notifications(c):
    e = auth(c, 'employee'); n = c.get('/api/notifications', headers=e).get_json(); assert 'unread' in n
    assert c.post('/api/notifications/read-all', headers=e).status_code == 200
    assert c.get('/api/notifications', headers=e).get_json()['unread'] == 0


def test_onboarding_and_offboarding(c):
    h = auth(c, 'hr'); items = c.get('/api/onboarding/8', headers=h).get_json(); assert items
    assert c.post(f"/api/onboarding/{items[-1]['id']}/toggle", headers=h).status_code == 200
    assert c.get('/api/onboarding', headers=auth(c, 'employee')).status_code == 403
    assert c.post('/api/offboarding', json={'employee_id': 5, 'resignation_date': '2026-10-10', 'exit_date': '2026-10-01'}, headers=h).status_code == 400


def test_error_format_and_health(c):
    assert c.get('/api/nothing-here').get_json()['error']
    assert c.get('/api/health').get_json()['database'] == 'connected'
