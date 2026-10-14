"""Creates the MySQL schema and loads demo data.  Usage:  python init_db.py"""
import os, random
from datetime import date, datetime, timedelta
from pathlib import Path
import mysql.connector
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / '.env')
cfg = dict(host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', '3306')), user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''))
DB = os.getenv('DB_NAME', 'workforce_portal')


def run_schema(cur):
    cur.execute(f'DROP DATABASE IF EXISTS `{DB}`')
    sql = (ROOT.parent / 'database' / 'schema.sql').read_text().replace('workforce_portal', DB)
    for stmt in [s.strip() for s in sql.split(';') if s.strip()]: cur.execute(stmt)


def main():
    conn = mysql.connector.connect(**cfg); cur = conn.cursor(); run_schema(cur); cur.execute(f'USE `{DB}`')
    random.seed(7); today = date.today(); d = lambda n: (today - timedelta(days=n)).isoformat()
    for name in ['Administration', 'Human Resources', 'Engineering', 'Sales', 'Finance']: cur.execute('INSERT INTO departments(name) VALUES(%s)', (name,))
    # (name, email, dept_id, designation, manager_idx, join_days_ago, status, role, password)
    staff = [
        ('Aarav Mehta', 'admin@company.com', 1, 'System Administrator', None, 900, 'Active', 'super_admin', 'Admin@123'),
        ('Priya Sharma', 'hr@company.com', 2, 'HR Administrator', 1, 700, 'Active', 'hr_admin', 'Hr@12345'),
        ('Rahul Verma', 'manager@company.com', 3, 'Engineering Manager', 1, 800, 'Active', 'manager', 'Manager@123'),
        ('Neha Kulkarni', 'sales.manager@company.com', 4, 'Sales Manager', 1, 650, 'Active', 'manager', 'Manager@123'),
        ('Amit Patil', 'employee@company.com', 3, 'Software Engineer', 3, 400, 'Active', 'employee', 'Employee@123'),
        ('Sneha Joshi', 'sneha@company.com', 3, 'QA Engineer', 3, 300, 'Active', 'employee', 'Employee@123'),
        ('Karan Singh', 'karan@company.com', 3, 'Backend Developer', 3, 220, 'Active', 'employee', 'Employee@123'),
        ('Divya Nair', 'divya@company.com', 3, 'Frontend Developer', 3, 12, 'Onboarding', 'employee', 'Employee@123'),
        ('Rohan Desai', 'rohan@company.com', 4, 'Sales Executive', 4, 500, 'Active', 'employee', 'Employee@123'),
        ('Meera Iyer', 'meera@company.com', 4, 'Account Executive', 4, 260, 'Active', 'employee', 'Employee@123'),
        ('Vikram Bose', 'finance.manager@company.com', 5, 'Finance Manager', 1, 720, 'Active', 'manager', 'Manager@123'),
        ('Pooja Shah', 'pooja@company.com', 5, 'Accountant', 11, 340, 'Active', 'employee', 'Employee@123'),
        ('Sanjay Pawar', 'sanjay@company.com', 4, 'Sales Executive', 4, 600, 'Exited', 'employee', 'Employee@123'),
    ]
    defaults = {'Casual Leave': 12, 'Sick Leave': 10, 'Earned Leave': 15, 'Optional Holiday': 2}
    for i, (n, em, dept, des, mgr, jd, st, role, pw) in enumerate(staff, 1):
        cur.execute('INSERT INTO employees(emp_code,full_name,email,phone,department_id,designation,manager_id,joining_date,employment_type,work_location,status,salary_band) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (f'EMP{i:04d}', n, em, f'98{random.randint(10000000, 99999999)}', dept, des, mgr, d(jd), 'Full-time', random.choice(['Pune', 'Mumbai', 'Remote']), st, random.choice(['B2', 'B3', 'B4'])))
        cur.execute('INSERT INTO users(employee_id,email,password_hash,role,active) VALUES(%s,%s,%s,%s,%s)', (i, em, generate_password_hash(pw), role, st != 'Exited'))
        for t, b in defaults.items(): cur.execute('INSERT INTO leave_balances VALUES(%s,%s,%s)', (i, t, b))
    for k, v in {'work_start': '09:30', 'grace_minutes': '15', 'hr_approval_days': '5', 'leave_defaults': '{"Casual Leave":12,"Sick Leave":10,"Earned Leave":15,"Optional Holiday":2}',
                 'perf_weights': '{"task":25,"quality":20,"productivity":20,"attendance":15,"goals":20}'}.items(): cur.execute('INSERT INTO settings VALUES(%s,%s)', (k, v))
    # attendance for the last 14 weekdays
    for emp in [i for i, s in enumerate(staff, 1) if s[6] == 'Active']:
        for n in range(1, 21):
            day = today - timedelta(days=n)
            if day.weekday() >= 5 or random.random() < 0.06: continue
            ci = datetime.combine(day, datetime.min.time()) + timedelta(hours=9, minutes=random.randint(0, 55))
            co = None if random.random() < 0.04 else ci + timedelta(hours=random.choice([8, 8.5, 9, 4]), minutes=random.randint(0, 30))
            hrs = round((co - ci).total_seconds() / 3600, 2) if co else None
            st = 'Half Day' if hrs and hrs < 4.5 else ('Late' if ci.time() > datetime.strptime('09:45', '%H:%M').time() else 'Present')
            cur.execute('INSERT INTO attendance(employee_id,att_date,check_in,check_out,hours,status) VALUES(%s,%s,%s,%s,%s,%s)', (emp, day, ci, co, hrs, st))
        if emp % 2 == 1 and today.weekday() < 5:
            ci = datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=random.randint(0, 40))
            cur.execute("INSERT INTO attendance(employee_id,att_date,check_in,status) VALUES(%s,%s,%s,'Present')", (emp, today, ci))
    L = lambda e, t, a, b, days, st, r: cur.execute('INSERT INTO leave_requests(employee_id,leave_type,start_date,end_date,days,reason,status) VALUES(%s,%s,%s,%s,%s,%s,%s)', (e, t, a, b, days, r, st))
    L(5, 'Casual Leave', d(-3), d(-4), 2, 'Pending', 'Family function'); L(6, 'Sick Leave', d(2), d(1), 2, 'Approved', 'Fever')
    L(9, 'Earned Leave', d(-10), d(-17), 6, 'Pending', 'Vacation'); L(10, 'Casual Leave', d(20), d(19), 2, 'Rejected', 'Personal work')
    cur.execute('UPDATE leave_balances SET balance=balance-2 WHERE employee_id=6 AND leave_type="Sick Leave"')
    goals = [(5, 'Ship payroll API v2', 'Endpoints delivered', '12', 70), (5, 'Reduce bug backlog', 'Open bugs', '< 10', 40), (6, 'Automate regression suite', 'Coverage', '80%', 55), (7, 'Migrate reports to MySQL views', 'Reports migrated', '8', 30), (9, 'Close Q4 pipeline', 'Revenue (lakh)', '40', 65)]
    for e, t, k, tg, pr in goals: cur.execute('INSERT INTO performance_goals(employee_id,title,kpi,target,progress,due_date,created_by) VALUES(%s,%s,%s,%s,%s,%s,3)', (e, t, k, tg, pr, d(-30)))
    for e, ov, rt, fb in [(5, 82.5, 'Good', 'Reliable delivery; improve code review turnaround.'), (6, 74.0, 'Good', 'Strong testing discipline.'), (9, 88.0, 'Outstanding', 'Exceeded target.'), (7, 62.0, 'Needs Improvement', 'Needs to close overdue tasks.')]:
        cur.execute("INSERT INTO performance_reviews(employee_id,reviewer_id,kind,period,task_completion,quality_score,productivity,attendance_score,goal_achievement,overall,rating,feedback) VALUES(%s,3,'manager','Q2 2026',80,80,80,90,75,%s,%s,%s)", (e, ov, rt, fb))
    cur.execute("INSERT INTO projects(name,department_id,description,start_date,end_date,created_by) VALUES('Payroll Platform Upgrade',3,'Modernise payroll services',%s,%s,3),('Customer Onboarding Portal',3,'Self-service onboarding',%s,%s,3),('Q4 Sales Campaign',4,'Enterprise outreach',%s,%s,4)", (d(60), d(-30), d(40), d(-50), d(20), d(-40)))
    for pid, emps in {1: [5, 6, 7], 2: [5, 8], 3: [9, 10]}.items():
        for e in emps: cur.execute('INSERT INTO project_members VALUES(%s,%s)', (pid, e))
    T = [(1, 5, 'Design payroll REST endpoints', 'High', 'Completed', 20), (1, 5, 'Implement tax calculation', 'High', 'In Progress', -5), (1, 6, 'Write regression tests', 'Medium', 'Under Review', -2),
         (1, 7, 'Optimise payslip queries', 'Medium', 'Not Started', 3), (2, 8, 'Build signup form', 'Low', 'In Progress', -8), (2, 5, 'Integrate email service', 'Medium', 'On Hold', -15),
         (3, 9, 'Prepare outreach list', 'High', 'Completed', 10), (3, 10, 'Schedule client demos', 'Medium', 'In Progress', -4)]
    for p, e, t, pr, st, off in T: cur.execute('INSERT INTO tasks(project_id,assignee_id,title,priority,status,deadline) VALUES(%s,%s,%s,%s,%s,%s)', (p, e, t, pr, st, d(-off) if off < 0 else d(-off) if off > 0 else d(0)))
    for i, (item, owner) in enumerate([('Collect ID and address proof', 'HR'), ('Sign offer letter and NDA', 'HR'), ('Create email account', 'IT'), ('Issue laptop and access card', 'IT'), ('Orientation session', 'HR')]):
        cur.execute('INSERT INTO onboarding_records(employee_id,item,owner,done) VALUES(8,%s,%s,%s)', (item, owner, i < 2))
    cur.execute("INSERT INTO offboarding_records(employee_id,resignation_date,exit_date,approved,clearance,assets_returned,access_revoked,docs_done,status) VALUES(13,%s,%s,1,1,1,1,1,'Completed')", (d(50), d(20)))
    for uid, msg in [(5, 'Welcome to the Workforce Portal.'), (3, 'Amit Patil requested 2 day(s) of Casual Leave.'), (2, 'Onboarding in progress for Divya Nair - 3 items pending.')]: cur.execute('INSERT INTO notifications(user_id,message) VALUES(%s,%s)', (uid, msg))
    conn.commit(); cur.close(); conn.close()
    print('Database ready. Demo logins: admin@company.com / Admin@123, hr@company.com / Hr@12345, manager@company.com / Manager@123, employee@company.com / Employee@123')


if __name__ == '__main__':
    main()
