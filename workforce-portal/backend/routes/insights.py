"""Module 7 (dashboards & reports), Module 8 (notifications) and admin/settings."""
import csv, io, json
from datetime import date, timedelta
from flask import Blueprint, request, jsonify, g, Response
from werkzeug.security import generate_password_hash
from auth import need, emp_scope, audit, notify_users, notify_employee, notify_hr, EMAIL, HR
from db import q, one, ex, settings

bp = Blueprint('insights', __name__)


def rng():
    t = date.today(); a = request.args.get('from') or (t - timedelta(days=13)).isoformat(); b = request.args.get('to') or t.isoformat()
    date.fromisoformat(a); date.fromisoformat(b); return a, b


@bp.get('/dashboard')
@need()
def dashboard():
    u = g.user; a, b = rng(); eid = u['employee_id']
    if u['role'] == 'employee' or request.args.get('me'):
        month = date.today().strftime('%Y-%m')
        return jsonify(kind='employee',
            profile=one('SELECT e.full_name,e.emp_code,e.designation,e.joining_date,d.name department,m.full_name manager FROM employees e JOIN departments d ON d.id=e.department_id LEFT JOIN employees m ON m.id=e.manager_id WHERE e.id=%s', (eid,)),
            attendance=one("SELECT COALESCE(SUM(status IN ('Present','Late','Half Day')),0) present,COALESCE(SUM(status='Late'),0) late,ROUND(COALESCE(SUM(hours),0),1) hours FROM attendance WHERE employee_id=%s AND LEFT(att_date,7)=%s", (eid, month)),
            today=one('SELECT check_in,check_out FROM attendance WHERE employee_id=%s AND att_date=CURDATE()', (eid,)),
            balances=q('SELECT leave_type,balance FROM leave_balances WHERE employee_id=%s', (eid,)),
            pending_leaves=q("SELECT leave_type,start_date,end_date,status FROM leave_requests WHERE employee_id=%s AND status IN ('Pending','Pending HR') ORDER BY id DESC", (eid,)),
            projects=q('SELECT p.id,p.name,p.status FROM projects p JOIN project_members m ON m.project_id=p.id WHERE m.employee_id=%s', (eid,)),
            task_status=q('SELECT status,COUNT(*) n FROM tasks WHERE assignee_id=%s GROUP BY status', (eid,)),
            feedback=one("SELECT period,overall,rating,feedback,created_at FROM performance_reviews WHERE employee_id=%s AND kind='manager' ORDER BY id DESC LIMIT 1", (eid,)))
    w, p = emp_scope(); p = tuple(p); mgr = u['role'] == 'manager'
    tasks_scope = 'pr.department_id=%s' if mgr else '1=1'; tp = (u['dept'],) if mgr else ()
    tk = one(f"SELECT COUNT(*) n,COALESCE(SUM(t.status='Completed'),0) c,COALESCE(SUM(t.status<>'Completed' AND t.deadline<CURDATE()),0) od FROM tasks t JOIN projects pr ON pr.id=t.project_id WHERE {tasks_scope}", tp)
    return jsonify(kind='manager' if mgr else 'hr', range={'from': a, 'to': b},
        total=one(f'SELECT COUNT(*) n FROM employees e WHERE {w}', p)['n'],
        active=one(f"SELECT COUNT(*) n FROM employees e WHERE {w} AND e.status='Active'", p)['n'],
        present_today=one(f'SELECT COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE {w} AND a.att_date=CURDATE()', p)['n'],
        late_today=one(f"SELECT COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE {w} AND a.att_date=CURDATE() AND a.status='Late'", p)['n'],
        on_leave=one(f"SELECT COUNT(DISTINCT l.employee_id) n FROM leave_requests l JOIN employees e ON e.id=l.employee_id WHERE {w} AND l.status='Approved' AND CURDATE() BETWEEN l.start_date AND l.end_date", p)['n'],
        pending_leaves=one(f"SELECT COUNT(*) n FROM leave_requests l JOIN employees e ON e.id=l.employee_id WHERE {w} AND l.status IN ('Pending','Pending HR')", p)['n'],
        by_department=q(f"SELECT d.name label,COUNT(*) n FROM employees e JOIN departments d ON d.id=e.department_id WHERE {w} AND e.status IN ('Active','Onboarding') GROUP BY d.name ORDER BY d.name", p),
        new_joiners=q(f'SELECT e.full_name,e.designation,e.joining_date FROM employees e WHERE {w} AND e.joining_date>=DATE_SUB(CURDATE(),INTERVAL 30 DAY) ORDER BY e.joining_date DESC', p),
        attrition={'exited_90d': one(f"SELECT COUNT(*) n FROM offboarding_records o JOIN employees e ON e.id=o.employee_id WHERE {w} AND o.status='Completed' AND o.exit_date>=DATE_SUB(CURDATE(),INTERVAL 90 DAY)", p)['n'],
                   'in_notice': one(f"SELECT COUNT(*) n FROM offboarding_records o JOIN employees e ON e.id=o.employee_id WHERE {w} AND o.status<>'Completed'", p)['n']},
        attendance_trend=q(f'SELECT a.att_date label,COUNT(*) n FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE {w} AND a.att_date BETWEEN %s AND %s GROUP BY a.att_date ORDER BY a.att_date', p + (a, b)),
        task_completion_rate=round(100 * tk['c'] / tk['n'], 1) if tk['n'] else 0, overdue_tasks=tk['od'],
        performance=q(f"""SELECT e.full_name,(SELECT overall FROM performance_reviews r WHERE r.employee_id=e.id AND r.kind='manager' ORDER BY r.id DESC LIMIT 1) overall FROM employees e WHERE {w} AND e.status='Active' ORDER BY e.full_name""", p))


REPORTS = {
    'headcount': ("SELECT d.name department,COUNT(*) employees,SUM(e.status='Active') active FROM employees e JOIN departments d ON d.id=e.department_id WHERE {w} GROUP BY d.name ORDER BY d.name", 0),
    'attendance': ("SELECT d.name department,e.full_name,COUNT(a.id) days_present,SUM(a.status='Late') late_days,ROUND(COALESCE(SUM(a.hours),0),1) total_hours FROM employees e JOIN departments d ON d.id=e.department_id LEFT JOIN attendance a ON a.employee_id=e.id AND a.att_date BETWEEN %s AND %s WHERE {w} AND e.status='Active' GROUP BY d.name,e.full_name ORDER BY d.name,e.full_name", 2),
    'leave': ("SELECT d.name department,l.leave_type,COUNT(*) requests,SUM(l.days) days FROM leave_requests l JOIN employees e ON e.id=l.employee_id JOIN departments d ON d.id=e.department_id WHERE {w} AND l.status='Approved' AND l.start_date BETWEEN %s AND %s GROUP BY d.name,l.leave_type ORDER BY d.name", 1),
    'performance': ("SELECT d.name department,e.full_name,r.period,r.overall,r.rating FROM performance_reviews r JOIN employees e ON e.id=r.employee_id JOIN departments d ON d.id=e.department_id WHERE {w} AND r.kind='manager' ORDER BY d.name,r.id DESC", 0),
    'tasks': ("SELECT d.name department,e.full_name,COUNT(t.id) tasks,SUM(t.status='Completed') completed,SUM(t.status<>'Completed' AND t.deadline<CURDATE()) overdue FROM tasks t JOIN employees e ON e.id=t.assignee_id JOIN departments d ON d.id=e.department_id WHERE {w} GROUP BY d.name,e.full_name ORDER BY d.name", 0),
}


@bp.get('/reports/<kind>')
@need('super_admin', 'hr_admin', 'manager')
def report(kind):
    if kind not in REPORTS: return jsonify(error='Unknown report.'), 404
    t = date.today(); a = request.args.get('from') or t.replace(day=1).isoformat(); b = request.args.get('to') or t.isoformat()
    w, p = emp_scope(); sql, uses_range = REPORTS[kind]
    params = {0: tuple(p), 1: tuple(p) + (a, b), 2: (a, b) + tuple(p)}[uses_range]
    rows = q(sql.format(w=w), params)
    if request.args.get('format') == 'csv':
        buf = io.StringIO(); wr = csv.writer(buf)
        if rows: wr.writerow(rows[0].keys()); [wr.writerow(r.values()) for r in rows]
        audit('REPORT_EXPORT', kind)
        return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment; filename={kind}-report.csv'})
    return jsonify(kind=kind, rows=rows)


# ---------------- Notifications ----------------
@bp.get('/notifications')
@need()
def notifications():
    rows = q('SELECT id,message,is_read,created_at FROM notifications WHERE user_id=%s ORDER BY id DESC LIMIT 50', (g.user['id'],))
    return jsonify(items=rows, unread=sum(1 for r in rows if not r['is_read']))


@bp.post('/notifications/<int:nid>/read')
@need()
def read_one(nid):
    ex('UPDATE notifications SET is_read=1 WHERE id=%s AND user_id=%s', (nid, g.user['id'])); return jsonify(ok=True)


@bp.post('/notifications/read-all')
@need()
def read_all():
    ex('UPDATE notifications SET is_read=1 WHERE user_id=%s', (g.user['id'],)); return jsonify(ok=True)


@bp.post('/notifications/run-reminders')
@need(*HR)
def reminders():
    n = 0
    for t in q("SELECT t.title,t.deadline,t.assignee_id FROM tasks t WHERE t.status<>'Completed' AND t.deadline BETWEEN CURDATE() AND DATE_ADD(CURDATE(),INTERVAL 2 DAY)"):
        msg = f"Reminder: task '{t['title']}' is due {t['deadline']}."
        if not one('SELECT n.id FROM notifications n JOIN users u ON u.id=n.user_id WHERE u.employee_id=%s AND n.message=%s AND DATE(n.created_at)=CURDATE()', (t['assignee_id'], msg)): notify_employee(t['assignee_id'], msg); n += 1
    for r in q("SELECT e.id,e.full_name,a.att_date FROM attendance a JOIN employees e ON e.id=a.employee_id WHERE a.check_out IS NULL AND a.att_date=DATE_SUB(CURDATE(),INTERVAL 1 DAY)"):
        notify_employee(r['id'], f"Attendance alert: no check-out recorded on {r['att_date']}."); n += 1
    inc = one("SELECT COUNT(DISTINCT employee_id) n FROM onboarding_records WHERE done=0")['n']
    if inc: notify_hr(f'{inc} employee(s) have incomplete onboarding records.'); n += 1
    audit('REMINDERS_RUN', f'{n} notifications'); return jsonify(sent=n)


# ---------------- Admin ----------------
@bp.get('/admin/users')
@need('super_admin')
def users():
    return jsonify(q('SELECT u.id,u.email,u.role,u.active,e.full_name,e.emp_code FROM users u JOIN employees e ON e.id=u.employee_id ORDER BY u.id'))


@bp.put('/admin/users/<int:uid>')
@need('super_admin')
def update_user(uid):
    d = request.get_json(silent=True) or {}; u = one('SELECT * FROM users WHERE id=%s', (uid,))
    if not u: return jsonify(error='User not found.'), 404
    if uid == g.user['id'] and (d.get('active') is False or d.get('role', u['role']) != 'super_admin'): return jsonify(error='You cannot demote or disable your own account.'), 400
    if 'role' in d:
        if d['role'] not in ('super_admin', 'hr_admin', 'manager', 'employee'): return jsonify(error='Invalid role.'), 400
        ex('UPDATE users SET role=%s WHERE id=%s', (d['role'], uid))
    if 'active' in d: ex('UPDATE users SET active=%s WHERE id=%s', (bool(d['active']), uid))
    if d.get('password'):
        if len(d['password']) < 8: return jsonify(error='Password must be at least 8 characters.'), 400
        ex('UPDATE users SET password_hash=%s WHERE id=%s', (generate_password_hash(d['password']), uid))
    audit('USER_UPDATE', f"user {uid}: {', '.join(k for k in d if k != 'password')}{' password-reset' if d.get('password') else ''}"); return jsonify(message='User updated.')


@bp.get('/admin/settings')
@need(*HR)
def get_settings():
    return jsonify(settings())


@bp.put('/admin/settings')
@need('super_admin')
def put_settings():
    d = request.get_json(silent=True) or {}; allowed = set(settings().keys())
    for k, v in d.items():
        if k not in allowed: return jsonify(error=f'Unknown setting: {k}'), 400
        if k in ('leave_defaults', 'perf_weights'):
            try: json.loads(v)
            except ValueError: return jsonify(error=f'{k} must be valid JSON.'), 400
        ex('UPDATE settings SET v=%s WHERE k=%s', (str(v), k))
    audit('SETTINGS_UPDATE', ', '.join(d.keys())); return jsonify(message='Settings saved.')


@bp.get('/admin/audit')
@need(*HR)
def audit_log():
    return jsonify(q('SELECT a.id,a.action,a.details,a.created_at,e.full_name user FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id LEFT JOIN employees e ON e.id=u.employee_id ORDER BY a.id DESC LIMIT 200'))


@bp.get('/admin/logins')
@need('super_admin')
def login_log():
    return jsonify(q('SELECT email,success,created_at FROM login_logs ORDER BY id DESC LIMIT 100'))
