"""Module 5 (performance) and Module 6 (projects & tasks)."""
from datetime import date
from flask import Blueprint, request, jsonify, g
from auth import need, emp_scope, can_see, audit, notify_employee, HR
from db import q, one, ex, jsetting

bp = Blueprint('work', __name__)
MGR = ('super_admin', 'hr_admin', 'manager')
STATUSES = ['Not Started', 'In Progress', 'Under Review', 'Completed', 'On Hold']


def rating(score):
    return 'Outstanding' if score >= 85 else 'Good' if score >= 70 else 'Needs Improvement' if score >= 50 else 'At Risk'


def pct(v):
    try: v = float(v)
    except (TypeError, ValueError): return None
    return v if 0 <= v <= 100 else None


# ---------------- Performance ----------------
@bp.get('/performance/goals')
@need()
def goals():
    eid = int(request.args.get('employee_id') or g.user['employee_id'])
    if not can_see(eid): return jsonify(error='Not authorized.'), 403
    return jsonify(q('SELECT * FROM performance_goals WHERE employee_id=%s ORDER BY id DESC', (eid,)))


@bp.post('/performance/goals')
@need(*MGR)
def add_goal():
    d = request.get_json(silent=True) or {}
    if not d.get('employee_id') or not (d.get('title') or '').strip(): return jsonify(error='Employee and goal title are required.'), 400
    if not can_see(d['employee_id']): return jsonify(error='Not authorized for this employee.'), 403
    gid = ex('INSERT INTO performance_goals(employee_id,title,kpi,target,due_date,created_by) VALUES(%s,%s,%s,%s,%s,%s)',
             (d['employee_id'], d['title'].strip(), d.get('kpi'), d.get('target'), d.get('due_date') or None, g.user['id']))
    notify_employee(d['employee_id'], f"New goal assigned: {d['title']}"); audit('GOAL_CREATE', f'goal {gid}'); return jsonify(id=gid), 201


@bp.put('/performance/goals/<int:gid>')
@need()
def goal_progress(gid):
    gl = one('SELECT * FROM performance_goals WHERE id=%s', (gid,))
    if not gl or not can_see(gl['employee_id']): return jsonify(error='Goal not found.'), 404
    p = request.get_json(silent=True) or {}; v = pct(p.get('progress'))
    if v is None: return jsonify(error='Progress must be between 0 and 100.'), 400
    ex('UPDATE performance_goals SET progress=%s WHERE id=%s', (int(v), gid)); return jsonify(progress=int(v))


@bp.post('/performance/reviews')
@need(*MGR)
def add_review():
    d = request.get_json(silent=True) or {}; eid = d.get('employee_id')
    if not eid or not (d.get('period') or '').strip(): return jsonify(error='Employee and evaluation period are required.'), 400
    if not can_see(eid) or eid == g.user['employee_id']: return jsonify(error='You cannot review this employee.'), 403
    qs, pr, go = pct(d.get('quality_score')), pct(d.get('productivity')), pct(d.get('goal_achievement'))
    if None in (qs, pr, go): return jsonify(error='Quality, productivity and goal achievement must be 0-100.'), 400
    t = one("SELECT COUNT(*) n, COALESCE(SUM(status='Completed'),0) c FROM tasks WHERE assignee_id=%s", (eid,))
    tc = round(100 * t['c'] / t['n'], 1) if t['n'] else 0.0
    att = one("SELECT COUNT(*) n FROM attendance WHERE employee_id=%s AND att_date>=DATE_SUB(CURDATE(),INTERVAL 30 DAY)", (eid,))['n']
    ats = min(100.0, round(att / 22 * 100, 1))
    w = jsetting('perf_weights', {'task': 25, 'quality': 20, 'productivity': 20, 'attendance': 15, 'goals': 20}); tot = sum(w.values()) or 100
    overall = round((tc * w['task'] + qs * w['quality'] + pr * w['productivity'] + ats * w['attendance'] + go * w['goals']) / tot, 1)
    rid = ex("""INSERT INTO performance_reviews(employee_id,reviewer_id,kind,period,task_completion,quality_score,productivity,attendance_score,goal_achievement,overall,rating,feedback)
                VALUES(%s,%s,'manager',%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (eid, g.user['id'], d['period'].strip(), tc, qs, pr, ats, go, overall, rating(overall), d.get('feedback')))
    notify_employee(eid, f"New performance review for {d['period']}: {overall} ({rating(overall)})."); audit('REVIEW_CREATE', f'review {rid}')
    return jsonify(id=rid, overall=overall, rating=rating(overall)), 201


@bp.post('/performance/self')
@need()
def self_assess():
    d = request.get_json(silent=True) or {}; s = pct(d.get('score'))
    if s is None or not (d.get('period') or '').strip(): return jsonify(error='Period and a 0-100 score are required.'), 400
    rid = ex("INSERT INTO performance_reviews(employee_id,kind,period,overall,rating,feedback) VALUES(%s,'self',%s,%s,%s,%s)", (g.user['employee_id'], d['period'].strip(), s, rating(s), d.get('comment')))
    return jsonify(id=rid), 201


@bp.get('/performance/reviews')
@need()
def reviews():
    eid = int(request.args.get('employee_id') or g.user['employee_id'])
    if not can_see(eid): return jsonify(error='Not authorized.'), 403
    return jsonify(q("""SELECT r.*, e.full_name reviewer FROM performance_reviews r LEFT JOIN users u ON u.id=r.reviewer_id
                        LEFT JOIN employees e ON e.id=u.employee_id WHERE r.employee_id=%s ORDER BY r.id DESC""", (eid,)))


@bp.get('/performance/overview')
@need(*MGR)
def overview():
    w, p = emp_scope()
    return jsonify(q(f"""SELECT e.id,e.emp_code,e.full_name,d.name department,
        (SELECT overall FROM performance_reviews r WHERE r.employee_id=e.id AND r.kind='manager' ORDER BY r.id DESC LIMIT 1) overall,
        (SELECT rating FROM performance_reviews r WHERE r.employee_id=e.id AND r.kind='manager' ORDER BY r.id DESC LIMIT 1) rating,
        (SELECT ROUND(AVG(progress)) FROM performance_goals gl WHERE gl.employee_id=e.id) goal_progress
        FROM employees e JOIN departments d ON d.id=e.department_id WHERE {w} AND e.status='Active' ORDER BY d.name,e.full_name""", p))


# ---------------- Projects ----------------
@bp.get('/projects')
@need()
def projects():
    u = g.user; cond, p = '1=1', ()
    if u['role'] == 'manager': cond, p = 'p.department_id=%s', (u['dept'],)
    elif u['role'] == 'employee': cond, p = 'p.id IN (SELECT project_id FROM project_members WHERE employee_id=%s)', (u['employee_id'],)
    return jsonify(q(f"""SELECT p.*,d.name department,(SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) tasks,
        (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='Completed') done,
        (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status<>'Completed' AND t.deadline<CURDATE()) overdue,
        (SELECT GROUP_CONCAT(e.full_name SEPARATOR ', ') FROM project_members m JOIN employees e ON e.id=m.employee_id WHERE m.project_id=p.id) members
        FROM projects p JOIN departments d ON d.id=p.department_id WHERE {cond} ORDER BY p.id DESC""", p))


@bp.post('/projects')
@need(*MGR)
def add_project():
    d = request.get_json(silent=True) or {}; dept = g.user['dept'] if g.user['role'] == 'manager' else d.get('department_id')
    if not (d.get('name') or '').strip() or not dept: return jsonify(error='Project name and department are required.'), 400
    if d.get('start_date') and d.get('end_date') and d['end_date'] < d['start_date']: return jsonify(error='End date cannot be before start date.'), 400
    pid = ex('INSERT INTO projects(name,department_id,description,start_date,end_date,created_by) VALUES(%s,%s,%s,%s,%s,%s)',
             (d['name'].strip(), dept, d.get('description'), d.get('start_date') or None, d.get('end_date') or None, g.user['id']))
    audit('PROJECT_CREATE', d['name']); return jsonify(id=pid), 201


@bp.post('/projects/<int:pid>/members')
@need(*MGR)
def add_member(pid):
    d = request.get_json(silent=True) or {}; pr = one('SELECT department_id FROM projects WHERE id=%s', (pid,))
    if not pr: return jsonify(error='Project not found.'), 404
    if g.user['role'] == 'manager' and pr['department_id'] != g.user['dept']: return jsonify(error='Not your department project.'), 403
    if not d.get('employee_id') or not one('SELECT id FROM employees WHERE id=%s', (d['employee_id'],)): return jsonify(error='Choose an employee.'), 400
    ex('INSERT IGNORE INTO project_members VALUES(%s,%s)', (pid, d['employee_id'])); notify_employee(d['employee_id'], 'You were added to a project.')
    return jsonify(message='Member added.'), 201


# ---------------- Tasks ----------------
@bp.get('/tasks')
@need()
def tasks():
    u = g.user; conds, p = [], []
    if u['role'] == 'employee': conds.append('t.assignee_id=%s'); p.append(u['employee_id'])
    elif u['role'] == 'manager': conds.append('pr.department_id=%s'); p.append(u['dept'])
    if request.args.get('mine'): conds.append('t.assignee_id=%s'); p.append(u['employee_id'])
    if request.args.get('project_id'): conds.append('t.project_id=%s'); p.append(request.args['project_id'])
    if request.args.get('status'): conds.append('t.status=%s'); p.append(request.args['status'])
    return jsonify(q(f"""SELECT t.*,pr.name project,e.full_name assignee,(t.status<>'Completed' AND t.deadline<CURDATE()) overdue
        FROM tasks t JOIN projects pr ON pr.id=t.project_id JOIN employees e ON e.id=t.assignee_id
        WHERE {' AND '.join(conds) or '1=1'} ORDER BY overdue DESC,t.deadline,t.id DESC""", p))


@bp.post('/tasks')
@need(*MGR)
def add_task():
    d = request.get_json(silent=True) or {}
    if not (d.get('title') or '').strip() or not d.get('project_id') or not d.get('assignee_id'): return jsonify(error='Title, project and assignee are required.'), 400
    pr = one('SELECT department_id FROM projects WHERE id=%s', (d['project_id'],))
    if not pr: return jsonify(error='Project not found.'), 404
    if g.user['role'] == 'manager' and (pr['department_id'] != g.user['dept'] or not can_see(d['assignee_id'])): return jsonify(error='You can only assign tasks within your department.'), 403
    if d.get('priority', 'Medium') not in ('Low', 'Medium', 'High'): return jsonify(error='Invalid priority.'), 400
    tid = ex('INSERT INTO tasks(project_id,assignee_id,title,priority,deadline) VALUES(%s,%s,%s,%s,%s)', (d['project_id'], d['assignee_id'], d['title'].strip(), d.get('priority', 'Medium'), d.get('deadline') or None))
    ex('INSERT IGNORE INTO project_members VALUES(%s,%s)', (d['project_id'], d['assignee_id']))
    notify_employee(d['assignee_id'], f"New task assigned: {d['title']} (due {d.get('deadline') or 'n/a'})."); audit('TASK_CREATE', f'task {tid}')
    return jsonify(id=tid), 201


@bp.put('/tasks/<int:tid>')
@need()
def update_task(tid):
    t = one('SELECT t.*,pr.department_id dept FROM tasks t JOIN projects pr ON pr.id=t.project_id WHERE t.id=%s', (tid,)); u = g.user
    if not t: return jsonify(error='Task not found.'), 404
    d = request.get_json(silent=True) or {}
    owner = t['assignee_id'] == u['employee_id']; mgr = u['role'] in HR or (u['role'] == 'manager' and t['dept'] == u['dept'])
    if not owner and not mgr: return jsonify(error='Not authorized to update this task.'), 403
    if 'status' in d:
        if d['status'] not in STATUSES: return jsonify(error='Invalid status.'), 400
        ex('UPDATE tasks SET status=%s WHERE id=%s', (d['status'], tid))
    if mgr:
        for f in ('priority', 'deadline', 'title'):
            if f in d: ex(f'UPDATE tasks SET {f}=%s WHERE id=%s', (d[f] or None, tid))
    audit('TASK_UPDATE', f"task {tid} -> {d.get('status', 'edited')}"); return jsonify(message='Task updated.')
