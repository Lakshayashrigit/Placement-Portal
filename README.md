# Placement Portal

A comprehensive placement portal built with Flask and SQLite to manage job drives, applications, and student profiles.

## Features

- **Admin Dashboard**: Manage students, companies, and placement drives.
- **Company Dashboard**: Create drives, view applicants, and update application status.
- **Student Dashboard**: View available drives and track application history.
- **Resume Management**: Students can upload and update their resumes (PDF).
- **CGPA Eligibility**: Automated eligibility check based on drive-specific requirements.

## How to Run:

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialize Database**:
   ```bash
   python models.py
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```

4. **Access the Portal**:
   Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

## Credentials for Testing:

- **Admin**: `admin@portal.com` / `admin123`
- **Student/Company**: Register via the signup page.
