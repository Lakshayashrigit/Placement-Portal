import os
import sys

# Explicitly add current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import flask
from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
import models
from models import get_db_connection, init_db
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "placement_portal_secret"
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

# Initialize DB on start
with app.app_context():
    init_db()

# --- Helpers ---
def login_required(role=None):
    def decorator(f):
        from functools import wraps
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash("Please login first.", "warning")
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                flash("Unauthorized access.", "danger")
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Routes ---

@app.route("/")
@app.route("/home")
def home():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template("index.html")

@app.route("/select_role")
def select_role():
    return redirect(url_for('home'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        role = request.form.get("role")
        
        # Backend Validation
        if not name or not email or not password or not role:
            flash("All fields are required.", "danger")
            return redirect(url_for('register'))
        
        if "@" not in email or "." not in email:
            flash("Invalid email format.", "danger")
            return redirect(url_for('register'))

        if role == 'company':
            if not request.form.get("company_name") or not request.form.get("hr_contact"):
                flash("Company name and HR contact are required.", "danger")
                return redirect(url_for('register'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if user exists
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                flash("Email already registered!", "danger")
                return redirect(url_for('register'))

            # For students, approved by default, for companies, pending
            approved = 1 if role == 'student' else 0
            
            cursor.execute(
                "INSERT INTO users (name, email, password, role, approved) VALUES (?, ?, ?, ?, ?)",
                (name, email, password, role, approved)
            )
            user_id = cursor.lastrowid
            
            if role == 'company':
                company_name = request.form.get("company_name")
                hr_contact = request.form.get("hr_contact")
                website = request.form.get("website")
                
                # Generate unique Company ID (e.g., CMP001)
                cursor.execute("SELECT COUNT(*) FROM companies")
                count = cursor.fetchone()[0]
                company_code = f"CMP{str(count + 1).zfill(3)}"
                
                cursor.execute(
                    "INSERT INTO companies (user_id, company_name, hr_contact, website, company_code) VALUES (?, ?, ?, ?, ?)",
                    (user_id, company_name, hr_contact, website, company_code)
                )
            
            conn.commit()
            flash("Registration successful! " + ("Please wait for admin approval." if role == 'company' else "You can login now."), "success")
            return redirect(url_for('login'))
        except Exception as e:
            conn.rollback()
            flash(f"Error: {str(e)}", "danger")
        finally:
            conn.close()
            
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    selected_role = request.args.get('role')
    
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role_from_form = request.form.get("role") # Hidden field from form
        
        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for('login', role=role_from_form))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ? AND password = ?", (email, password))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            # Role Validation
            if role_from_form and user['role'] != role_from_form:
                flash(f"Invalid role selected for this account. This account is registered as a {user['role']}.", "danger")
                return redirect(url_for('login', role=role_from_form))
            
            if not user['active']:
                flash("Your account is deactivated.", "danger")
                return redirect(url_for('login', role=role_from_form))
            
            if user['role'] == 'company' and not user['approved']:
                flash("Your account is pending admin approval.", "warning")
                return redirect(url_for('login', role=role_from_form))
                
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "danger")
            return redirect(url_for('login', role=role_from_form))
            
    return render_template("login.html", selected_role=selected_role)

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'company':
        return redirect(url_for('company_dashboard'))
    else:
        return redirect(url_for('student_dashboard'))

# --- Admin Routes ---

@app.route("/admin/dashboard")
@login_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    stats = {
        'students': cursor.execute("SELECT COUNT(*) FROM users WHERE role='student'").fetchone()[0],
        'companies': cursor.execute("SELECT COUNT(*) FROM companies").fetchone()[0],
        'drives': cursor.execute("SELECT COUNT(*) FROM placement_drives").fetchone()[0],
        'applications': cursor.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    }
    
    pending_companies = cursor.execute("""
        SELECT c.*, u.email, u.active 
        FROM companies c 
        JOIN users u ON c.user_id = u.id 
        WHERE c.approval_status = 'Pending'
    """).fetchall()
    
    pending_drives = cursor.execute("""
        SELECT d.*, c.company_name, c.company_code 
        FROM placement_drives d 
        JOIN companies c ON d.company_id = c.id 
        WHERE d.status = 'Pending'
    """).fetchall()
    
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, pending_companies=pending_companies, pending_drives=pending_drives)

@app.route("/admin/approve_company/<int:id>/<action>")
@login_required('admin')
def approve_company(id, action):
    status = 'Approved' if action == 'approve' else 'Rejected'
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE companies SET approval_status = ? WHERE id = ?", (status, id))
    if status == 'Approved':
        cursor.execute("UPDATE users SET approved = 1 WHERE id = (SELECT user_id FROM companies WHERE id = ?)", (id,))
    
    conn.commit()
    conn.close()
    flash(f"Company {status.lower()} successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/approve_drive/<int:id>/<action>")
@login_required('admin')
def approve_drive(id, action):
    status = 'Approved' if action == 'approve' else 'Rejected'
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE placement_drives SET status = ? WHERE id = ?", (status, id))
    conn.commit()
    conn.close()
    flash(f"Drive {status.lower()} successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/manage_users")
@login_required('admin')
def manage_users():
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT u.*, c.company_name, c.id as company_id, c.company_code 
        FROM users u 
        LEFT JOIN companies c ON u.id = c.user_id 
        WHERE u.role != 'admin' AND (u.name LIKE ? OR u.email LIKE ? OR c.company_name LIKE ? OR c.company_code LIKE ? OR u.id LIKE ? OR c.id LIKE ?)
    """
    params = [f'%{search}%'] * 6
    users = cursor.execute(query, params).fetchall()
    
    conn.close()
    return render_template("manage_users.html", users=users)

@app.route("/admin/all_applications")
@login_required('admin')
def view_all_applications():
    conn = get_db_connection()
    cursor = conn.cursor()
    applications = cursor.execute("""
        SELECT a.*, u.name as student_name, d.job_title, c.company_name, d.company_id, c.company_code 
        FROM applications a 
        JOIN users u ON a.student_id = u.id 
        JOIN placement_drives d ON a.drive_id = d.id 
        JOIN companies c ON d.company_id = c.id
        ORDER BY a.application_date DESC
    """).fetchall()
    conn.close()
    return render_template("admin_applications.html", applications=applications)

@app.route("/admin/toggle_user/<int:id>")
@login_required('admin')
def toggle_user(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    user = cursor.execute("SELECT active FROM users WHERE id = ?", (id,)).fetchone()
    if user:
        new_status = 0 if user['active'] else 1
        cursor.execute("UPDATE users SET active = ? WHERE id = ?", (new_status, id))
        conn.commit()
    conn.close()
    return redirect(url_for('manage_users'))

# --- Company Routes ---

@app.route("/company/dashboard")
@login_required('company')
def company_dashboard():
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    company = cursor.execute("SELECT * FROM companies WHERE user_id = ?", (session['user_id'],)).fetchone()
    
    query = "SELECT * FROM placement_drives WHERE company_id = ?"
    params = [company['id']]
    
    if search:
        query += " AND (job_title LIKE ? OR job_description LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%'])
        
    drives = cursor.execute(query, params).fetchall()
    
    conn.close()
    return render_template("company_dashboard.html", drives=drives, company=company)

@app.route("/company/create_drive", methods=["GET", "POST"])
@login_required('company')
def create_drive():
    if request.method == "POST":
        job_title = request.form.get("job_title")
        job_description = request.form.get("job_description")
        eligibility = request.form.get("eligibility")
        deadline = request.form.get("deadline")
        
        if not job_title or not deadline:
            flash("Job title and deadline are required.", "danger")
            return redirect(url_for('create_drive'))
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Check if company is active
            user_status = cursor.execute("SELECT active FROM users WHERE id = ?", (session['user_id'],)).fetchone()
            if not user_status or not user_status['active']:
                flash("Your account is deactivated. You cannot create drives.", "danger")
                return redirect(url_for('company_dashboard'))

            company_data = cursor.execute("SELECT id FROM companies WHERE user_id = ?", (session['user_id'],)).fetchone()
            min_cgpa = request.form.get("min_cgpa", 0)
            
            if company_data:
                cursor.execute("""
                    INSERT INTO placement_drives (company_id, job_title, job_description, eligibility, deadline, status, min_cgpa)
                    VALUES (?, ?, ?, ?, ?, 'Pending', ?)
                """, (company_data['id'], job_title, job_description, eligibility, deadline, min_cgpa))
                
                conn.commit()
                flash("Drive created and pending admin approval.", "success")
            else:
                flash("Company profile not found.", "danger")
                
        except Exception as e:
            conn.rollback()
            flash(f"Error creating drive: {str(e)}", "danger")
        finally:
            conn.close()
            
        return redirect(url_for('company_dashboard'))
        
    return render_template("create_drive.html")

@app.route("/company/view_applicants", defaults={'drive_id': None})
@app.route("/company/view_applicants/<int:drive_id>")
@login_required('company')
def view_applicants(drive_id=None):
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get current company ID
    company = cursor.execute("SELECT id FROM companies WHERE user_id = ?", (session['user_id'],)).fetchone()
    if not company:
        conn.close()
        flash("Company profile not found.", "danger")
        return redirect(url_for('company_dashboard'))
    
    query = """
        SELECT a.application_id as app_id, a.status as app_status, a.application_date, 
               u.name, u.email, u.resume_path, d.job_title
        FROM applications a 
        JOIN users u ON a.student_id = u.id 
        JOIN placement_drives d ON a.drive_id = d.id 
        WHERE d.company_id = ?
    """
    params = [company['id']]
    
    if drive_id:
        query += " AND a.drive_id = ?"
        params.append(drive_id)
        
    if search:
        query += " AND (u.name LIKE ? OR u.email LIKE ? OR d.job_title LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    query += " ORDER BY a.application_date DESC"
    
    applicants = cursor.execute(query, params).fetchall()
    
    drive_info = None
    if drive_id:
        drive_info = cursor.execute("SELECT job_title FROM placement_drives WHERE id = ?", (drive_id,)).fetchone()
    
    conn.close()
    return render_template("view_applicants.html", applicants=applicants, drive=drive_info, drive_id=drive_id)

@app.route("/company/update_status/<int:app_id>/<status>")
@login_required('company')
def update_application_status(app_id, status):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status = ? WHERE application_id = ?", (status, app_id))
    conn.commit()
    conn.close()
    flash(f"Application status updated to {status}.", "success")
    return redirect(request.referrer or url_for('company_dashboard'))

@app.route("/company/close_drive/<int:id>")
@login_required('company')
def close_drive(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE placement_drives SET status = 'Closed' WHERE id = ? AND company_id = (SELECT id FROM companies WHERE user_id = ?)", (id, session['user_id']))
    conn.commit()
    conn.close()
    flash("Drive closed successfully.", "info")
    return redirect(url_for('company_dashboard'))

# --- Student Routes ---

@app.route("/student/dashboard")
@login_required('student')
def student_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    student = cursor.execute("SELECT * FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    applications = cursor.execute("""
        SELECT a.*, d.job_title, c.company_name 
        FROM applications a 
        JOIN placement_drives d ON a.drive_id = d.id 
        JOIN companies c ON d.company_id = c.id 
        WHERE a.student_id = ?
    """, (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template("student_dashboard.html", applications=applications, student=student)

@app.route("/student/history")
@login_required('student')
def student_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    applications = cursor.execute("""
        SELECT a.application_id, a.student_id, a.drive_id, d.job_title, c.company_name, a.application_date, a.status
        FROM applications a
        JOIN placement_drives d ON a.drive_id = d.id
        JOIN companies c ON d.company_id = c.id
        WHERE a.student_id = ?
        ORDER BY a.application_date DESC
    """, (session['user_id'],)).fetchall()
    
    conn.close()
    return render_template("student_history.html", applications=applications)

@app.route("/student/profile", methods=["GET", "POST"])
@login_required('student')
def student_profile():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session['user_id']
    
    if request.method == "POST":
        name = request.form.get("name")
        cgpa = request.form.get("cgpa")
        file = request.files.get("resume")

        if not name:
            flash("Name is required.", "danger")
            conn.close()
            return redirect(url_for('student_profile'))
        
        # Update name and CGPA
        cursor.execute("UPDATE users SET name = ?, cgpa = ? WHERE id = ?", (name, cgpa, user_id))
        session['user_name'] = name
        
        # Handle Resume Update
        if file and file.filename != '':
            if not file.filename.lower().endswith('.pdf'):
                flash("Invalid format. Only PDF files are allowed.", "danger")
                conn.close()
                return redirect(url_for('student_profile'))

            # Get existing resume path to delete old file
            user_data = cursor.execute("SELECT resume_path FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_data and user_data['resume_path']:
                old_file_path = os.path.join(app.config['UPLOAD_FOLDER'], user_data['resume_path'])
                if os.path.exists(old_file_path):
                    try:
                        os.remove(old_file_path)
                    except Exception as e:
                        print(f"Error deleting old resume: {e}")

            # Save new resume
            filename = secure_filename(f"resume_{user_id}.pdf")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Update database
            cursor.execute("UPDATE users SET resume_path = ? WHERE id = ?", (filename, user_id))
            flash("Profile and Resume updated successfully.", "success")
        else:
            flash("Profile updated successfully.", "success")
            
        conn.commit()

    user = cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return render_template("student_profile.html", user=user)

@app.route("/view_drives")
@login_required('student')
def view_drives():
    search = request.args.get('search', '')
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = """
        SELECT d.*, c.company_name 
        FROM placement_drives d 
        JOIN companies c ON d.company_id = c.id 
        JOIN users u ON c.user_id = u.id
        WHERE d.status = 'Approved' AND u.active = 1
    """
    params = []
    
    if search:
        query += " AND (d.job_title LIKE ? OR c.company_name LIKE ? OR d.job_description LIKE ?)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        
    drives = cursor.execute(query, params).fetchall()
    
    # Get user's applied drive IDs
    applied_ids = [a['drive_id'] for a in cursor.execute("SELECT drive_id FROM applications WHERE student_id = ?", (session['user_id'],)).fetchall()]
    
    # Get student CGPA
    student = cursor.execute("SELECT cgpa FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    student_cgpa = student['cgpa'] if student and student['cgpa'] else 0
    
    conn.close()
    return render_template("view_drives.html", drives=drives, applied_ids=applied_ids, student_cgpa=student_cgpa)

@app.route("/apply/<int:drive_id>")
@login_required('student')
def apply_drive(drive_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if resume is uploaded
    user = cursor.execute("SELECT resume_path FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    if not user['resume_path']:
        flash("Please upload your resume in profile before applying.", "warning")
        return redirect(url_for('student_profile'))
    
    # Check if drive is closed or company inactive, and get min_cgpa
    drive = cursor.execute("""
        SELECT d.status, u.active, d.min_cgpa, d.job_title 
        FROM placement_drives d 
        JOIN companies c ON d.company_id = c.id 
        JOIN users u ON c.user_id = u.id
        WHERE d.id = ?
    """, (drive_id,)).fetchone()
    
    if not drive or drive['status'] == 'Closed' or not drive['active']:
        conn.close()
        flash("This drive is no longer accepting applications.", "danger")
        return redirect(url_for('view_drives'))

    # CGPA Eligibility Check
    student = cursor.execute("SELECT cgpa FROM users WHERE id = ?", (session['user_id'],)).fetchone()
    student_cgpa = student['cgpa'] if student and student['cgpa'] else 0
    min_required = drive['min_cgpa'] if drive['min_cgpa'] else 0
    
    if student_cgpa < min_required:
        conn.close()
        flash(f"You are not eligible for this drive. Minimum CGPA required is {min_required}", "danger")
        return redirect(url_for('view_drives'))

    try:
        cursor.execute("INSERT INTO applications (student_id, drive_id) VALUES (?, ?)", (session['user_id'], drive_id))
        conn.commit()
        flash("Applied successfully!", "success")
    except sqlite3.IntegrityError:
        flash("Already applied for this drive.", "warning")
    finally:
        conn.close()
        
    return redirect(url_for('view_drives'))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == "__main__":
    app.run(debug=True)