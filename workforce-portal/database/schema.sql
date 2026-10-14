CREATE DATABASE IF NOT EXISTS workforce_portal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE workforce_portal;

CREATE TABLE IF NOT EXISTS departments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS employees (
  id INT AUTO_INCREMENT PRIMARY KEY,
  emp_code VARCHAR(20) UNIQUE,
  full_name VARCHAR(120) NOT NULL,
  email VARCHAR(160) NOT NULL UNIQUE,
  phone VARCHAR(20) NULL,
  department_id INT NOT NULL,
  designation VARCHAR(100) NOT NULL,
  manager_id INT NULL,
  joining_date DATE NOT NULL,
  employment_type ENUM('Full-time','Part-time','Contract','Intern') NOT NULL DEFAULT 'Full-time',
  work_location VARCHAR(100) NULL,
  status ENUM('Active','Inactive','Onboarding','Exited') NOT NULL DEFAULT 'Active',
  salary_band VARCHAR(20) NULL,
  photo_url VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_emp_dept(department_id), INDEX idx_emp_name(full_name),
  FOREIGN KEY (department_id) REFERENCES departments(id),
  FOREIGN KEY (manager_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL UNIQUE,
  email VARCHAR(160) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('super_admin','hr_admin','manager','employee') NOT NULL DEFAULT 'employee',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS attendance (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  att_date DATE NOT NULL,
  check_in DATETIME NULL,
  check_out DATETIME NULL,
  hours DECIMAL(5,2) NULL,
  status ENUM('Present','Late','Half Day') NOT NULL DEFAULT 'Present',
  UNIQUE KEY uq_att(employee_id, att_date),
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS leave_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  leave_type ENUM('Casual Leave','Sick Leave','Earned Leave','Unpaid Leave','Optional Holiday') NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  days DECIMAL(4,1) NOT NULL,
  reason VARCHAR(500) NOT NULL,
  status ENUM('Pending','Pending HR','Approved','Rejected') NOT NULL DEFAULT 'Pending',
  decided_by INT NULL,
  decided_at DATETIME NULL,
  comment VARCHAR(300) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_leave_emp(employee_id), INDEX idx_leave_status(status),
  FOREIGN KEY (employee_id) REFERENCES employees(id),
  FOREIGN KEY (decided_by) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS leave_balances (
  employee_id INT NOT NULL,
  leave_type VARCHAR(30) NOT NULL,
  balance DECIMAL(5,1) NOT NULL DEFAULT 0,
  PRIMARY KEY (employee_id, leave_type),
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS performance_goals (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  title VARCHAR(200) NOT NULL,
  kpi VARCHAR(200) NULL,
  target VARCHAR(100) NULL,
  progress INT NOT NULL DEFAULT 0,
  due_date DATE NULL,
  created_by INT NULL,
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS performance_reviews (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  reviewer_id INT NULL,
  kind ENUM('manager','self') NOT NULL DEFAULT 'manager',
  period VARCHAR(40) NOT NULL,
  task_completion DECIMAL(5,1) NULL,
  quality_score DECIMAL(5,1) NULL,
  productivity DECIMAL(5,1) NULL,
  attendance_score DECIMAL(5,1) NULL,
  goal_achievement DECIMAL(5,1) NULL,
  overall DECIMAL(5,1) NOT NULL,
  rating VARCHAR(30) NOT NULL,
  feedback TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS projects (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  department_id INT NOT NULL,
  description TEXT NULL,
  start_date DATE NULL,
  end_date DATE NULL,
  status ENUM('Planned','Active','On Hold','Completed') NOT NULL DEFAULT 'Active',
  created_by INT NULL,
  FOREIGN KEY (department_id) REFERENCES departments(id)
);
CREATE TABLE IF NOT EXISTS project_members (
  project_id INT NOT NULL,
  employee_id INT NOT NULL,
  PRIMARY KEY (project_id, employee_id),
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS tasks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  project_id INT NOT NULL,
  assignee_id INT NOT NULL,
  title VARCHAR(200) NOT NULL,
  priority ENUM('Low','Medium','High') NOT NULL DEFAULT 'Medium',
  status ENUM('Not Started','In Progress','Under Review','Completed','On Hold') NOT NULL DEFAULT 'Not Started',
  deadline DATE NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_assignee(assignee_id), INDEX idx_task_status(status),
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (assignee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  message VARCHAR(300) NOT NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_note_user(user_id, is_read),
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS onboarding_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  item VARCHAR(150) NOT NULL,
  owner ENUM('HR','IT') NOT NULL DEFAULT 'HR',
  done BOOLEAN NOT NULL DEFAULT FALSE,
  done_at DATETIME NULL,
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS offboarding_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL UNIQUE,
  resignation_date DATE NOT NULL,
  exit_date DATE NOT NULL,
  approved BOOLEAN NOT NULL DEFAULT FALSE,
  clearance BOOLEAN NOT NULL DEFAULT FALSE,
  assets_returned BOOLEAN NOT NULL DEFAULT FALSE,
  access_revoked BOOLEAN NOT NULL DEFAULT FALSE,
  docs_done BOOLEAN NOT NULL DEFAULT FALSE,
  status ENUM('Initiated','Approved','Completed') NOT NULL DEFAULT 'Initiated',
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS audit_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NULL,
  action VARCHAR(60) NOT NULL,
  details VARCHAR(500) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS login_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(160) NOT NULL,
  success BOOLEAN NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS employee_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  employee_id INT NOT NULL,
  changed_by INT NULL,
  field VARCHAR(40) NOT NULL,
  old_value VARCHAR(255) NULL,
  new_value VARCHAR(255) NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (employee_id) REFERENCES employees(id)
);
CREATE TABLE IF NOT EXISTS settings (
  k VARCHAR(40) PRIMARY KEY,
  v VARCHAR(500) NOT NULL
);
