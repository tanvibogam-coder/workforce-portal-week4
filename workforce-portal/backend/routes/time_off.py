"""Module 3 (attendance) and Module 4 (leave & approval workflow)."""
from datetime import date, datetime, timedelta
from flask import Blueprint, request, jsonify, g
from auth import need, emp_scope, can_see, audit, notify_hr, notify_employee, notify_managers, HR
from db import q, one, ex, settings, jsetting

bp = Blueprint('timeoff', __name__)
LEAVE_TYPES = ['Casual Leave', 'Sick Leave', 'Earned Leave', 'Unpaid Leave', 'Optional Holiday']


def classify(ci, co, s):
    """Attendance classification: Late (after start+grace) / Half Day (<4h) / Present."""
    start = datetime.combine(ci.date(), datetime.strptime(s['work_start'], '%H:%M').time()) + timedelta(minutes=int(s['grace_minutes']))
    hours = round((co - ci).total_seconds() / 3600, 2) if co else None
    status = 'Late' if ci > start else 'Present'
    if hours is not None and hours < 4: status = 'Half Day'
    return hours, status


def month_arg():
    m = request.args.get('month') or date.today().strftime('%Y-%m')
    datetime.strptime(m, '%Y-%m'); return m


@bp.post('/attendance/check-in')
@need()
def check_in():
    now = datetime.now(); eid = g.user['employee_id']
    if one('SELECT id FROM attendance WHERE employee_id=%s AND att_date=%s', (eid, now.date())): return jsonify(error='You have already checked in today.'), 409
    _, status = classify(now, None, settings())
    ex('INSERT INTO attendance(employee_id,att_date,check_in,status) VALUES(%s,%s,%s,%s)', (eid, now.date(), now, status))
    return jsonify(message=f'Checked in ({status}).', status=status), 201


@bp.post('/attendance/check-out')
@need()
def check_out():
    now = datetime.now(); r = one('SELECT id,check_out FROM attendance WHERE employee_id=%s AND att_date=%s', (g.user['employee_id'], now.date()))
    if not r: return jsonify(error='Check in first.'), 400
    if r['check_out']: return jsonify(error='You have already checked out today.'), 409
    ex("""UPDATE attendance SET check_out=%s, hours=ROUND(TIMESTAMPDIFF(MINUTE,check_in,%s)/60,2),
          status=IF(TIMESTAMPDIFF(MINUTE,check_in,%s)<240,'Half Day',status) WHERE id=%s""", (now, now, now, r['id']))
    return jsonify(message='Checked out.')


@bp.get('/attendance')
@need()
def attendance():
    eid = int(request.args.get('employee_id') or g.user['employee_id'])
    if not can_see(eid): return jsonify(error='You are not authorized to view this attendance.'), 403
    rows = q("SELECT * FROM attendance WHERE employee_id=%s AND LEFT(att_date,7)=%s ORDER BY att_date DESC", (eid, month_arg()))
    today = date.today().isoformat()
    for r in rows:
        if not r['check_out'] and r['att_date'] < today: r['status'] = 'Missing Checkout'
    return jsonify(rows)


@bp.get('/attendance/summary')
@need('super_admin', 'hr_admin', 'manager')
def summary():
    w, p = emp_scope()
    return jsonify(q(f"""SELECT e.id,e.emp_code,e.full_name,d.name department,
        COALESCE(SUM(a.status IN ('Present','Late','Half Day')),0) present, COALESCE(SUM(a.status='Late'),0) late,
        COALESCE(SUM(a.check_out IS NULL AND a.att_date<CURDATE()),0) missing, ROUND(COALESCE(SUM(a.hours),0),1) hours
        FROM employees e JOIN departments d ON d.id=e.department_id
        LEFT JOIN attendance a ON a.employee_id=e.id AND LEFT(a.att_date,7)=%s
        WHERE {w} AND e.status='Active' GROUP BY e.id,e.emp_code,e.full_name,d.name ORDER BY d.name,e.full_name""", (month_arg(),) + tuple(p)))


@bp.get('/attendance/exceptions')
@need('super_admin', 'hr_admin', 'manager')
def exceptions():
    w, p = emp_scope()
    rows = q(f"""SELECT a.id,a.att_date,a.check_in,a.check_out,a.status,e.full_name,e.emp_code FROM attendance a JOIN employees e ON e.id=a.employee_id
        WHERE {w} AND a.att_date>=DATE_SUB(CURDATE(),INTERVAL 30 DAY) AND (a.status='Late' OR (a.check_out IS NULL AND a.att_date<CURDATE())) ORDER BY a.att_date DESC""", p)
    for r in rows:
        if not r['check_out'] and r['att_date'] < date.today().isoformat(): r['status'] = 'Missing Checkout'
    return jsonify(rows)


@bp.put('/attendance/<int:aid>')
@need(*HR)
def correct(aid):
    d = request.get_json(silent=True) or {}; a = one('SELECT * FROM attendance WHERE id=%s', (aid,))
    if not a: return jsonify(error='Attendance record not found.'), 404
    if not (d.get('reason') or '').strip(): return jsonify(error='A reason is required for corrections.'), 400
    try:
        ci = datetime.fromisoformat(d.get('check_in') or a['check_in'])
        co = datetime.fromisoformat(d['check_out']) if d.get('check_out') else (datetime.fromisoformat(a['check_out']) if a['check_out'] else None)
    except ValueError: return jsonify(error='Use a valid date-time (YYYY-MM-DDTHH:MM).'), 400
    if co and co <= ci: return jsonify(error='Check-out must be after check-in.'), 400
    hours, status = classify(ci, co, settings())
    ex('UPDATE attendance SET check_in=%s,check_out=%s,hours=%s,status=%s WHERE id=%s', (ci, co, hours, status, aid))
    audit('ATTENDANCE_CORRECTION', f"record {aid}: {a['check_in']}/{a['check_out']} -> {ci.isoformat()}/{co.isoformat() if co else None}; reason: {d['reason']}")
    notify_employee(a['employee_id'], f"HR corrected your attendance for {a['att_date']}."); return jsonify(message='Attendance corrected and logged.')


# ---------------- Leave ----------------
def weekdays(a, b):
    n, d = 0, a
    while d <= b:
        n += d.weekday() < 5; d += timedelta(days=1)
    return n


@bp.get('/leave/balances')
@need()
def balances():
    eid = int(request.args.get('employee_id') or g.user['employee_id'])
    if not can_see(eid): return jsonify(error='Not authorized.'), 403
    return jsonify(q('SELECT leave_type,balance FROM leave_balances WHERE employee_id=%s ORDER BY leave_type', (eid,)))


@bp.post('/leave')
@need()
def apply_leave():
    d = request.get_json(silent=True) or {}; eid = g.user['employee_id']
    if d.get('leave_type') not in LEAVE_TYPES: return jsonify(error='Select a valid leave type.'), 400
    if not (d.get('reason') or '').strip(): return jsonify(error='Please give a reason for the leave.'), 400
    try: a = date.fromisoformat(d['start_date']); b = date.fromisoformat(d['end_date'])
    except (KeyError, ValueError, TypeError): return jsonify(error='Enter valid start and end dates.'), 400
    if b < a: return jsonify(error='End date cannot be before start date.'), 400
    days = weekdays(a, b)
    if days == 0: return jsonify(error='Selected dates fall only on weekends.'), 400
    if one("SELECT id FROM leave_requests WHERE employee_id=%s AND status IN ('Pending','Pending HR','Approved') AND start_date<=%s AND end_date>=%s", (eid, b, a)):
        return jsonify(error='These dates overlap with an existing leave request.'), 409
    if d['leave_type'] != 'Unpaid Leave':
        bal = one('SELECT balance FROM leave_balances WHERE employee_id=%s AND leave_type=%s', (eid, d['leave_type']))
        if not bal or bal['balance'] < days: return jsonify(error=f"Insufficient balance: {bal['balance'] if bal else 0} day(s) left, {days} requested."), 400
    lid = ex('INSERT INTO leave_requests(employee_id,leave_type,start_date,end_date,days,reason) VALUES(%s,%s,%s,%s,%s,%s)', (eid, d['leave_type'], a, b, days, d['reason'].strip()[:500]))
    msg = f"{g.user['name']} requested {days} day(s) of {d['leave_type']} ({a} to {b})."
    notify_managers(g.user['dept'], msg); notify_employee(eid, 'Your leave request was submitted.'); audit('LEAVE_APPLY', f'request {lid}')
    return jsonify(id=lid, days=days), 201


@bp.get('/leave')
@need()
def list_leave():
    w, p = emp_scope(); conds = [w]; p = list(p)
    if request.args.get('status'): conds.append('l.status=%s'); p.append(request.args['status'])
    if request.args.get('mine'): conds.append('l.employee_id=%s'); p.append(g.user['employee_id'])
    return jsonify(q(f"""SELECT l.*,e.full_name,e.emp_code,d.name department FROM leave_requests l JOIN employees e ON e.id=l.employee_id
        JOIN departments d ON d.id=e.department_id WHERE {' AND '.join(conds)} ORDER BY l.id DESC LIMIT 200""", p))


@bp.get('/leave/calendar')
@need()
def calendar():
    m = month_arg(); w, p = emp_scope()
    if g.user['role'] == 'employee': w, p = 'e.department_id=%s', (g.user['dept'],)  # employees see their team calendar
    return jsonify(q(f"""SELECT l.start_date,l.end_date,l.leave_type,e.full_name FROM leave_requests l JOIN employees e ON e.id=l.employee_id
        WHERE {w} AND l.status='Approved' AND LEFT(l.start_date,7)<=%s AND LEFT(l.end_date,7)>=%s ORDER BY l.start_date""", tuple(p) + (m, m)))


@bp.post('/leave/<int:lid>/decide')
@need('super_admin', 'hr_admin', 'manager')
def decide(lid):
    d = request.get_json(silent=True) or {}; u = g.user; hr = u['role'] in HR
    r = one('SELECT l.*,e.department_id dept,e.full_name FROM leave_requests l JOIN employees e ON e.id=l.employee_id WHERE l.id=%s', (lid,))
    if not r: return jsonify(error='Leave request not found.'), 404
    if r['employee_id'] == u['employee_id']: return jsonify(error='You cannot decide your own leave request.'), 403
    if not hr and not (u['role'] == 'manager' and u['dept'] == r['dept']): return jsonify(error='Not authorized for this request.'), 403
    if r['status'] not in ('Pending', 'Pending HR'): return jsonify(error=f"Request already {r['status']}."), 409
    if r['status'] == 'Pending HR' and not hr: return jsonify(error='This request awaits HR approval.'), 403
    if d.get('decision') not in ('approve', 'reject'): return jsonify(error="decision must be 'approve' or 'reject'."), 400
    threshold = float(settings().get('hr_approval_days', 5))
    if d['decision'] == 'reject': status = 'Rejected'
    elif r['status'] == 'Pending' and not hr and r['days'] > threshold: status = 'Pending HR'
    else: status = 'Approved'
    if status == 'Approved' and r['leave_type'] != 'Unpaid Leave':
        ex('UPDATE leave_balances SET balance=balance-%s WHERE employee_id=%s AND leave_type=%s', (r['days'], r['employee_id'], r['leave_type']))
    ex('UPDATE leave_requests SET status=%s,decided_by=%s,decided_at=%s,comment=%s WHERE id=%s', (status, u['id'], datetime.now(), (d.get('comment') or '')[:300], lid))
    if status == 'Pending HR': notify_hr(f"{r['full_name']}'s {r['days']}-day leave needs HR approval.")
    notify_employee(r['employee_id'], f"Your {r['leave_type']} request ({r['start_date']} to {r['end_date']}) is now: {status}.")
    audit('LEAVE_DECISION', f'request {lid} -> {status}'); return jsonify(status=status)
