"""Module 2 - Employee master data, plus onboarding/offboarding (Module 9)."""
import csv, io, os
from datetime import date, datetime
from flask import Blueprint, request, jsonify, g, Response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from auth import need, emp_scope, can_see, audit, notify_hr, notify_employee, notify_managers, EMAIL, HR
from db import q, one, ex, jsetting

bp = Blueprint('emp', __name__)
FIELDS = ['full_name', 'email', 'phone', 'department_id', 'designation', 'manager_id', 'joining_date',
          'employment_type', 'work_location', 'status', 'salary_band']
REQUIRED = ['full_name', 'email', 'department_id', 'designation', 'joining_date']
BASE = """SELECT e.*, d.name department, m.full_name manager, DATEDIFF(CURDATE(), e.joining_date) tenure_days
          FROM employees e JOIN departments d ON d.id=e.department_id LEFT JOIN employees m ON m.id=e.manager_id"""
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
ALLOWED = {'pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'txt'}
CHECKLIST = [('Collect ID and address proof', 'HR'), ('Sign offer letter and NDA', 'HR'), ('Create email account', 'IT'),
             ('Issue laptop and access card', 'IT'), ('Orientation session', 'HR')]


def validate(d):
    for f in REQUIRED:
        if not str(d.get(f) or '').strip(): return f"'{f.replace('_', ' ')}' is required."
    if not EMAIL.match(d['email']): return 'Enter a valid email address.'
    if d.get('phone') and not str(d['phone']).replace('+', '').replace(' ', '').replace('-', '').isdigit(): return 'Phone must contain digits only.'
    try: datetime.strptime(str(d['joining_date'])[:10], '%Y-%m-%d')
    except ValueError: return 'Joining date must be YYYY-MM-DD.'
    if not one('SELECT id FROM departments WHERE id=%s', (d['department_id'],)): return 'Unknown department.'
    return None


@bp.get('/meta/departments')
@need()
def departments():
    return jsonify(q('SELECT id,name FROM departments ORDER BY name'))


@bp.get('/employees/lookup')
@need()
def lookup():
    w, p = emp_scope()
    return jsonify(q(f"SELECT e.id,e.emp_code,e.full_name,e.department_id FROM employees e WHERE {w} AND e.status IN ('Active','Onboarding') ORDER BY e.full_name", p))


@bp.get('/employees')
@need('super_admin', 'hr_admin', 'manager')
def list_employees():
    w, p = emp_scope(); conds = [w]; p = list(p); a = request.args
    if a.get('q'):
        s = '%' + a['q'] + '%'; conds.append('(e.full_name LIKE %s OR e.emp_code LIKE %s)'); p += [s, s]
    if a.get('dept'): conds.append('e.department_id=%s'); p.append(a['dept'])
    if a.get('status'): conds.append('e.status=%s'); p.append(a['status'])
    page = max(int(a.get('page', 1)), 1); per = min(max(int(a.get('per', 10)), 1), 100); cond = ' AND '.join(conds)
    total = one(f'SELECT COUNT(*) n FROM employees e WHERE {cond}', p)['n']
    items = q(f'{BASE} WHERE {cond} ORDER BY e.id LIMIT %s OFFSET %s', p + [per, (page - 1) * per])
    return jsonify(items=items, total=total, page=page, per=per)


@bp.get('/employees/export')
@need(*HR)
def export():
    rows = q(f'{BASE} ORDER BY e.id'); buf = io.StringIO()
    cols = ['emp_code', 'full_name', 'email', 'phone', 'department', 'designation', 'manager', 'joining_date', 'employment_type', 'work_location', 'status', 'salary_band', 'tenure_days']
    w = csv.writer(buf); w.writerow(cols)
    for r in rows: w.writerow([r[c] for c in cols])
    audit('EXPORT', 'employees csv')
    return Response(buf.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=employees.csv'})


@bp.get('/employees/<int:eid>')
@need()
def get_employee(eid):
    if not can_see(eid): return jsonify(error='You are not authorized to view this record.'), 403
    e = one(f'{BASE} WHERE e.id=%s', (eid,))
    hist = q("""SELECT h.field,h.old_value,h.new_value,h.created_at,e.full_name changed_by FROM employee_history h
                LEFT JOIN users u ON u.id=h.changed_by LEFT JOIN employees e ON e.id=u.employee_id WHERE h.employee_id=%s ORDER BY h.id DESC LIMIT 50""", (eid,))
    folder = os.path.join(UPLOAD_DIR, str(eid))
    docs = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    return jsonify(employee=e, history=hist, documents=docs)


@bp.post('/employees')
@need(*HR)
def create():
    d = request.get_json(silent=True) or {}; err = validate(d)
    if err: return jsonify(error=err), 400
    if one('SELECT id FROM employees WHERE LOWER(email)=LOWER(%s)', (d['email'],)): return jsonify(error='An employee with this email already exists.'), 409
    d.setdefault('employment_type', 'Full-time'); d['status'] = d.get('status') or 'Onboarding'
    cols = [f for f in FIELDS if d.get(f) not in (None, '')]
    eid = ex(f"INSERT INTO employees({','.join(cols)}) VALUES({','.join(['%s'] * len(cols))})", [d[c] for c in cols])
    ex('UPDATE employees SET emp_code=%s WHERE id=%s', (f'EMP{eid:04d}', eid))
    uid = ex('INSERT INTO users(employee_id,email,password_hash,role) VALUES(%s,%s,%s,%s)', (eid, d['email'], generate_password_hash('Welcome@123'), 'employee'))
    for t, b in (jsetting('leave_defaults', {}) or {}).items(): ex('INSERT INTO leave_balances VALUES(%s,%s,%s)', (eid, t, b))
    for item, owner in CHECKLIST: ex('INSERT INTO onboarding_records(employee_id,item,owner) VALUES(%s,%s,%s)', (eid, item, owner))
    notify_hr(f"Onboarding started for {d['full_name']} - {len(CHECKLIST)} checklist items pending.")
    audit('EMPLOYEE_CREATE', f"EMP{eid:04d} {d['full_name']}")
    return jsonify(id=eid, emp_code=f'EMP{eid:04d}', message='Employee created. Default login password: Welcome@123'), 201


@bp.put('/employees/<int:eid>')
@need(*HR)
def update(eid):
    old = one('SELECT * FROM employees WHERE id=%s', (eid,))
    if not old: return jsonify(error='Employee not found.'), 404
    d = request.get_json(silent=True) or {}
    new = {**old, **{k: (v if v != '' else None) for k, v in d.items() if k in FIELDS}}
    err = validate(new)
    if err: return jsonify(error=err), 400
    if one('SELECT id FROM employees WHERE LOWER(email)=LOWER(%s) AND id<>%s', (new['email'], eid)): return jsonify(error='Another employee already uses this email.'), 409
    changes = [(f, old[f], new[f]) for f in FIELDS if str(old[f] or '') != str(new[f] or '')]
    for f, o, n in changes:
        ex(f'UPDATE employees SET {f}=%s WHERE id=%s', (n, eid))
        ex('INSERT INTO employee_history(employee_id,changed_by,field,old_value,new_value) VALUES(%s,%s,%s,%s,%s)', (eid, g.user['id'], f, o, n))
    if old['email'] != new['email']: ex('UPDATE users SET email=%s WHERE employee_id=%s', (new['email'], eid))
    audit('EMPLOYEE_UPDATE', f"{old['emp_code']}: {', '.join(c[0] for c in changes) or 'no change'}")
    return jsonify(message='Employee updated.', changed=[c[0] for c in changes])


@bp.post('/employees/<int:eid>/deactivate')
@need(*HR)
def deactivate(eid):
    e = one('SELECT emp_code,full_name FROM employees WHERE id=%s', (eid,))
    if not e: return jsonify(error='Employee not found.'), 404
    if eid == g.user['employee_id']: return jsonify(error='You cannot deactivate your own account.'), 400
    ex("UPDATE employees SET status='Inactive' WHERE id=%s", (eid,)); ex('UPDATE users SET active=0 WHERE employee_id=%s', (eid,))
    ex('INSERT INTO employee_history(employee_id,changed_by,field,old_value,new_value) VALUES(%s,%s,%s,%s,%s)', (eid, g.user['id'], 'status', 'Active', 'Inactive'))
    audit('EMPLOYEE_DEACTIVATE', e['emp_code']); return jsonify(message='Employee deactivated.')


@bp.post('/employees/<int:eid>/documents')
@need(*HR)
def upload(eid):
    f = request.files.get('file')
    if not f or not f.filename: return jsonify(error='Choose a file to upload.'), 400
    name = secure_filename(f.filename); ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if ext not in ALLOWED: return jsonify(error='File type not allowed. Use: ' + ', '.join(sorted(ALLOWED))), 400
    data = f.read()
    if len(data) > 5 * 1024 * 1024: return jsonify(error='File exceeds the 5 MB limit.'), 400
    folder = os.path.join(UPLOAD_DIR, str(eid)); os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), 'wb') as out: out.write(data)
    audit('DOCUMENT_UPLOAD', f'employee {eid}: {name}'); return jsonify(message='Document uploaded.', name=name), 201


# ---------------- Onboarding ----------------
@bp.get('/onboarding')
@need(*HR)
def onboarding():
    rows = q("""SELECT e.id,e.emp_code,e.full_name,e.joining_date,d.name department,e.status,
                COUNT(o.id) total, COALESCE(SUM(o.done),0) done FROM employees e JOIN departments d ON d.id=e.department_id
                JOIN onboarding_records o ON o.employee_id=e.id GROUP BY e.id,e.emp_code,e.full_name,e.joining_date,d.name,e.status ORDER BY e.id DESC""")
    return jsonify(rows)


@bp.get('/onboarding/<int:eid>')
@need(*HR)
def onboarding_items(eid):
    return jsonify(q('SELECT * FROM onboarding_records WHERE employee_id=%s ORDER BY id', (eid,)))


@bp.post('/onboarding/<int:oid>/toggle')
@need(*HR)
def toggle(oid):
    o = one('SELECT * FROM onboarding_records WHERE id=%s', (oid,))
    if not o: return jsonify(error='Checklist item not found.'), 404
    done = not o['done']
    ex('UPDATE onboarding_records SET done=%s, done_at=%s WHERE id=%s', (done, datetime.now() if done else None, oid))
    left = one('SELECT COUNT(*) n FROM onboarding_records WHERE employee_id=%s AND done=0', (o['employee_id'],))['n']
    if left == 0:
        ex("UPDATE employees SET status='Active' WHERE id=%s AND status='Onboarding'", (o['employee_id'],))
        notify_employee(o['employee_id'], 'Your onboarding is complete. Welcome aboard!')
    audit('ONBOARDING_TOGGLE', f"{o['item']} -> {'done' if done else 'pending'}")
    return jsonify(done=done, remaining=left)


# ---------------- Offboarding ----------------
@bp.get('/offboarding')
@need('super_admin', 'hr_admin', 'manager')
def offboarding():
    w, p = emp_scope()
    return jsonify(q(f"""SELECT o.*,e.emp_code,e.full_name,d.name department FROM offboarding_records o JOIN employees e ON e.id=o.employee_id
                         JOIN departments d ON d.id=e.department_id WHERE {w} ORDER BY o.id DESC""", p))


@bp.post('/offboarding')
@need('super_admin', 'hr_admin', 'manager')
def initiate():
    d = request.get_json(silent=True) or {}
    if not d.get('employee_id') or not d.get('resignation_date') or not d.get('exit_date'): return jsonify(error='Employee, resignation date and exit date are required.'), 400
    if d['exit_date'] < d['resignation_date']: return jsonify(error='Exit date cannot be before resignation date.'), 400
    if not can_see(d['employee_id']): return jsonify(error='You are not authorized for this employee.'), 403
    if one('SELECT id FROM offboarding_records WHERE employee_id=%s', (d['employee_id'],)): return jsonify(error='An exit request already exists for this employee.'), 409
    oid = ex('INSERT INTO offboarding_records(employee_id,resignation_date,exit_date) VALUES(%s,%s,%s)', (d['employee_id'], d['resignation_date'], d['exit_date']))
    notify_hr('Exit request initiated - approval needed.'); audit('OFFBOARDING_START', f"employee {d['employee_id']}")
    return jsonify(id=oid), 201


@bp.put('/offboarding/<int:oid>')
@need(*HR)
def update_exit(oid):
    o = one('SELECT * FROM offboarding_records WHERE id=%s', (oid,))
    if not o: return jsonify(error='Exit record not found.'), 404
    d = request.get_json(silent=True) or {}
    for f in ('approved', 'clearance', 'assets_returned', 'access_revoked', 'docs_done'):
        if f in d: ex(f'UPDATE offboarding_records SET {f}=%s WHERE id=%s', (bool(d[f]), oid))
    o = one('SELECT * FROM offboarding_records WHERE id=%s', (oid,)); status = 'Initiated'
    if o['approved']: status = 'Approved'
    if o['approved'] and all(o[f] for f in ('clearance', 'assets_returned', 'access_revoked', 'docs_done')):
        status = 'Completed'; ex("UPDATE employees SET status='Exited' WHERE id=%s", (o['employee_id'],)); ex('UPDATE users SET active=0 WHERE employee_id=%s', (o['employee_id'],))
    ex('UPDATE offboarding_records SET status=%s WHERE id=%s', (status, oid)); audit('OFFBOARDING_UPDATE', f'record {oid} -> {status}')
    return jsonify(status=status)
