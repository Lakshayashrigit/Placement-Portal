import sqlite3
import os

DB_PATH = "database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # TABLE users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL, -- admin, company, student
            approved BOOLEAN DEFAULT 0,
            active BOOLEAN DEFAULT 1,
            resume_path TEXT,
            cgpa REAL
        )
    """)

    # Check for cgpa column in users if it exists (for existing DBs)
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'cgpa' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN cgpa REAL")

    # TABLE companies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            hr_contact TEXT,
            website TEXT,
            company_code TEXT UNIQUE,
            approval_status TEXT DEFAULT 'Pending', -- Pending, Approved, Rejected
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)

    # TABLE placement_drives
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS placement_drives (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER NOT NULL,
            job_title TEXT NOT NULL,
            job_description TEXT,
            eligibility TEXT,
            deadline DATE,
            status TEXT DEFAULT 'Pending', -- Pending, Approved, Closed
            min_cgpa REAL DEFAULT 0,
            FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
        )
    """)

    # Check for min_cgpa column in placement_drives if it exists (for existing DBs)
    cursor.execute("PRAGMA table_info(placement_drives)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'min_cgpa' not in columns:
        cursor.execute("ALTER TABLE placement_drives ADD COLUMN min_cgpa REAL DEFAULT 0")

    # TABLE applications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            application_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            drive_id INTEGER NOT NULL,
            application_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Applied', -- Applied, Shortlisted, Selected, Rejected
            FOREIGN KEY (student_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (drive_id) REFERENCES placement_drives (id) ON DELETE CASCADE,
            UNIQUE(student_id, drive_id)
        )
    """)

    # Create default Admin if not exists
    cursor.execute("SELECT * FROM users WHERE role='admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (name, email, password, role, approved, active) VALUES (?, ?, ?, ?, ?, ?)",
            ("System Admin", "admin@portal.com", "admin123", "admin", 1, 1)
        )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
