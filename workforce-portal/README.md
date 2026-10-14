# Workforce Portal

## 1. Project Overview
Workforce Portal is a web-based application designed to manage employee-related activities through different user roles, including Admin, HR, Manager, and Employee.

## 2. Technologies Used
- **Backend:** Python, Flask
- **Database:** MySQL
- **Frontend:** Refer to the HTML, CSS, JavaScript, and other frontend files included in the project.

## 3. Prerequisites
Install the following before running the project:
- Python
- MySQL Server
- Visual Studio Code

## 4. Project Setup

### Step 1: Extract and Open
Extract the project ZIP and open the `workforce-portal` folder in Visual Studio Code.

### Step 2: Create a Virtual Environment
Open the VS Code terminal and navigate to the `backend` folder.

Create a virtual environment:

```bash
python -m venv venv
```

Activate it in Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Create a `.env` file in the `backend` folder using `.env.example` as a reference.

Configure the following variables with the correct local settings:

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_NAME=workforce_portal
DB_USER=root
DB_PASSWORD=your_mysql_password
SECRET_KEY=replace_with_a_secret_key
PORT=5000
```

Replace the example password and secret key with your own values. Do not share real credentials publicly.

### Step 5: Initialize the Database
Ensure MySQL Server is running and the database credentials are correct.

Run:

```bash
python init_db.py
```

**Warning:** Database initialization may drop and recreate the existing `workforce_portal` database. Back up any important data before running this command.

### Step 6: Run the Application

```bash
python app.py
```

Open a browser and visit:

http://127.0.0.1:5000

## 5. Demo Login Accounts

The application setup provides these demo accounts:

| Role | Email | Password |
|---|---|---|
| Admin | admin@company.com | Admin@123 |
| HR | hr@company.com | Hr@12345 |
| Manager | manager@company.com | Manager@123 |
| Employee | employee@company.com | Employee@123 |

Change demo passwords before using the application in a real environment.

## 6. Project Structure

- `backend/` — Backend application and database setup files
- `app.py` — Application entry point
- `db.py` — Database-related functionality
- `init_db.py` — Database initialization
- `requirements.txt` — Python dependencies
- `.env.example` — Environment configuration template
- `database/schema.sql` — Database schema

Additional frontend folders and files are included according to the project structure.

## 7. Security Notes
- Do not upload the actual `.env` file or real database passwords to public repositories.
- Keep `.env.example` free of real credentials.
- Back up the database before reinitializing it.

## 8. Troubleshooting
- Ensure MySQL Server is running.
- Verify the database credentials in `.env`.
- Confirm that the required Python packages are installed.
- Check the terminal output for errors when starting the application.