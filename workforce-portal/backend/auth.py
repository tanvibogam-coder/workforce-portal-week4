"""Authentication, role-based access control, scoping, audit and notification helpers."""
import os, re
from functools import wraps
from flask import Blueprint, request, jsonify, g
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import check_password_hash, generate_password_hash
from db import q, one, ex

SESSION_MINUTES = 120
HR = ('super_admin', 'hr_admin')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
bp = Blueprint('auth', __name__)


def serializer():
    return URLSafeTimedSerializer(os.getenv('SECRET_KEY', 'dev-secret'))


def user_by_id(uid):
    return one("""SELECT u.id,u.email,u.role,u.active,u.employee_id,e.full_name name,e.department_id dept
                  FROM users u JOIN employees e ON e.id=u.employee_id WHERE u.id=%s""", (uid,))


def need(*roles):
    """Auth middleware: valid token + active user (+ one of `roles` if given)."""
    def deco(fn):
        @wraps(fn)
        def w(*a, **k):
            h = request.headers.get('Authorization', ''); u = None
            if h.startswith('Bearer '):
                try: u = user_by_id(serializer().loads(h[7:], max_age=SESSION_MINUTES * 60)['sub'])
                except (BadSignature, SignatureExpired): u = None
            if not u or not u['active']: return jsonify(error='Authentication required.'), 401
            if roles and u['role'] not in roles: return jsonify(error='You are not authorized for this action.'), 403
            g.user = u
            return fn(*a, **k)
        return w
    return deco


def emp_scope(alias='e'):
    """SQL fragment limiting which employees the current user may see."""
    u = g.user
    if u['role'] in HR: return '1=1', ()
    if u['role'] == 'manager': return f'{alias}.department_id=%s', (u['dept'],)
    return f'{alias}.id=%s', (u['employee_id'],)


def can_see(emp_id):
    w, p = emp_scope()
    return bool(one(f'SELECT e.id FROM employees e WHERE e.id=%s AND {w}', (emp_id,) + tuple(p)))


def audit(action, details=''):
    uid = g.user['id'] if getattr(g, 'user', None) else None
    ex('INSERT INTO audit_logs(user_id,action,details) VALUES(%s,%s,%s)', (uid, action, str(details)[:500]))


def notify_users(user_ids, msg):
    for uid in set(user_ids):
        if uid: ex('INSERT INTO notifications(user_id,message) VALUES(%s,%s)', (uid, msg[:300]))


def notify_employee(emp_id, msg):
    notify_users([r['id'] for r in q('SELECT id FROM users WHERE employee_id=%s AND active=1', (emp_id,))], msg)


def notify_hr(msg):
    notify_users([r['id'] for r in q("SELECT id FROM users WHERE role IN ('hr_admin','super_admin') AND active=1")], msg)


def notify_managers(dept_id, msg):
    notify_users([r['id'] for r in q("SELECT u.id FROM users u JOIN employees e ON e.id=u.employee_id WHERE u.role='manager' AND u.active=1 AND e.department_id=%s", (dept_id,))], msg)


def public(u):
    return {'id': u['id'], 'name': u['name'], 'email': u['email'], 'role': u['role'], 'employee_id': u['employee_id'], 'dept': u['dept']}


@bp.post('/auth/login')
def login():
    d = request.get_json(silent=True) or {}
    email, pw = (d.get('email') or '').strip(), d.get('password') or ''
    if not email or not pw: return jsonify(error='Email and password are required.'), 400
    if not EMAIL.match(email): return jsonify(error='Enter a valid email address.'), 400
    u = one('SELECT id,password_hash,active FROM users WHERE LOWER(email)=LOWER(%s)', (email,))
    ok = bool(u and u['active'] and check_password_hash(u['password_hash'], pw))
    ex('INSERT INTO login_logs(email,success) VALUES(%s,%s)', (email, ok))
    if not ok: return jsonify(error='Invalid email or password.'), 401
    full = user_by_id(u['id']); g.user = full; audit('LOGIN', full['email'])
    return jsonify(token=serializer().dumps({'sub': u['id']}), user=public(full), expires_in_minutes=SESSION_MINUTES)


@bp.post('/auth/logout')
@need()
def logout():
    audit('LOGOUT', g.user['email']); return jsonify(message='Logged out.')


@bp.get('/auth/me')
@need()
def me():
    return jsonify(public(g.user))


@bp.put('/auth/password')
@need()
def change_password():
    d = request.get_json(silent=True) or {}
    row = one('SELECT password_hash FROM users WHERE id=%s', (g.user['id'],))
    if not check_password_hash(row['password_hash'], d.get('current') or ''): return jsonify(error='Current password is incorrect.'), 400
    new = d.get('new') or ''
    if len(new) < 8 or not re.search(r'\d', new) or not re.search(r'[A-Za-z]', new):
        return jsonify(error='New password needs 8+ characters with letters and numbers.'), 400
    ex('UPDATE users SET password_hash=%s WHERE id=%s', (generate_password_hash(new), g.user['id']))
    audit('PASSWORD_CHANGE', g.user['email']); return jsonify(message='Password updated.')
