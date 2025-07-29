from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date, time

# Initialize Flask application
app = Flask(__name__)

# --- Configuration ---
# IMPORTANT: For production, change this to a strong, randomly generated key
# and store it securely (e.g., in an environment variable).
app.secret_key = 'your_super_secret_key_here' # CHANGE THIS IN PRODUCTION!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///presenzo131.db' # SQLite database file
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disable tracking modifications for performance
app.permanent_session_lifetime = timedelta(minutes=30) # Session active for 30 minutes

# Initialize SQLAlchemy with the Flask app
db = SQLAlchemy(app)

# --- Database Models ---
# Define the structure of your database tables using SQLAlchemy ORM

class Teacher(db.Model):
    """Represents a teacher in the system."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # Hashed password
    branch = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    # Relationships
    students = db.relationship('Student', backref='teacher', lazy=True)
    schedules = db.relationship('Schedule', backref='teacher', lazy=True)

class Student(db.Model):
    """Represents a student in the system."""
    id = db.Column(db.Integer, primary_key=True)
    rollno = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # Hashed password
    branch = db.Column(db.String(50), nullable=False)
    section = db.Column(db.String(10), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False) # Link to their teacher
    # Relationships
    attendance_records = db.relationship('Attendance', backref='student', lazy=True)

class Schedule(db.Model):
    """Represents a daily schedule for a teacher, containing period slots."""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    # Relationships
    period_slots = db.relationship('PeriodSlot', backref='schedule', lazy=True, cascade="all, delete-orphan") # Cascade delete slots if schedule is deleted

    @property
    def total_periods(self):
        """Calculates the total number of periods for this schedule."""
        return sum(slot.period_count for slot in self.period_slots)

class PeriodSlot(db.Model):
    """Represents a specific time slot within a schedule, with an associated period count."""
    id = db.Column(db.Integer, primary_key=True)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    period_count = db.Column(db.Integer, nullable=False) # Number of periods this slot counts for

    # Ensure uniqueness for a period slot within a schedule
    __table_args__ = (
        db.UniqueConstraint('schedule_id', 'start_time', 'end_time', name='unique_period_slot'),
    )

class Attendance(db.Model):
    """Records a student's attendance status for a specific period slot on a given date."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    period_slot_id = db.Column(db.Integer, db.ForeignKey('period_slot.id'), nullable=False)
    status = db.Column(db.String(10), nullable=False) # e.g., 'Present', 'Absent', 'Leave'

    # --- FIX: Add relationship to PeriodSlot ---
    period_slot = db.relationship('PeriodSlot', backref='attendances', lazy=True)

    # Ensure uniqueness for an attendance record (one record per student per slot per day)
    __table_args__ = (
        db.UniqueConstraint('student_id', 'date', 'period_slot_id', name='unique_attendance'),
    )

# --- Routes ---

@app.route('/')
def index():
    """Renders the homepage with options to login/register."""
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handles user registration for both teachers and students."""
    # Determine role from query parameter (GET) or form data (POST)
    role = request.args.get('role') if request.method == 'GET' else request.form.get('role')

    if request.method == 'POST':
        email = request.form['email'].lower()
        name = request.form['name']
        password = generate_password_hash(request.form['password']) # Hash the password for security
        branch = request.form['branch']
        section = request.form['section']

        if role == 'teacher':
            # Check if teacher email already exists
            if Teacher.query.filter_by(email=email).first():
                flash("Email already registered as teacher.", 'error')
                return redirect(url_for('register', role=role))
            teacher = Teacher(name=name, email=email, password=password, branch=branch, section=section)
            db.session.add(teacher)

        elif role == 'student':
            rollno = request.form['rollno']
            # Check if student email or roll number already exists
            if Student.query.filter_by(email=email).first():
                flash("Email already registered as student.", 'error')
                return redirect(url_for('register', role=role))
            if Student.query.filter_by(rollno=rollno).first():
                flash("Roll number already exists.", 'error')
                return redirect(url_for('register', role=role))

            # Assign student to a teacher based on branch and section
            # NOTE: This assumes a 1:1 or N:1 relationship where a branch/section has one primary teacher.
            # For more complex scenarios (e.g., multiple teachers per section, subjects), this logic needs refinement.
            teacher = Teacher.query.filter_by(branch=branch, section=section).first()
            if not teacher:
                flash("No teacher found for this branch and section. Please ensure a teacher is registered first.", 'error')
                return redirect(url_for('register', role=role))
            student = Student(name=name, email=email, password=password, branch=branch, section=section, rollno=rollno, teacher_id=teacher.id)
            db.session.add(student)
        else:
            flash("Invalid role specified.", 'error')
            return redirect(url_for('register', role='student')) # Default to student if role is bad

        db.session.commit() # Commit changes to the database
        flash("Registration successful. Please login.", 'success')
        return redirect(url_for('login', role=role))

    return render_template('register.html', role=role)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user login for both teachers and students."""
    if request.method == "POST":
        role = request.form.get("role")

        if role == "student":
            rollno = request.form.get("rollno")
            password = request.form.get("password")

            if not rollno or not password:
                flash("Roll number and password are required.", 'error')
                return redirect(url_for("login", role=role))

            student = Student.query.filter_by(rollno=rollno).first()
            # Verify password hash
            if not student or not check_password_hash(student.password, password):
                flash("Invalid roll number or password.", 'error')
                return redirect(url_for("login", role=role))

            # Set session variables for logged-in user
            session["user_id"] = student.id
            session["role"] = "student"
            return redirect(url_for("dashboard"))

        elif role == "teacher":
            email = request.form.get("email")
            password = request.form.get("password")

            if not email or not password:
                flash("Email and password are required.", 'error')
                return redirect(url_for("login", role=role))

            teacher = Teacher.query.filter_by(email=email).first()
            # Verify password hash
            if not teacher or not check_password_hash(teacher.password, password):
                flash("Invalid email or password.", 'error')
                return redirect(url_for("login", role=role))

            # Set session variables for logged-in user
            session["user_id"] = teacher.id
            session["role"] = "teacher"
            return redirect(url_for("dashboard"))

        else:
            flash("Invalid role.", 'error')
            return redirect(url_for("login"))
    else:
        # Render login page, defaulting to student role if not specified
        role = request.args.get("role", "student")
        return render_template("login.html", role=role)

@app.route('/schedule', methods=['POST'])
def schedule():
    """Allows teachers to create or update their daily schedules with period slots."""
    # Ensure only logged-in teachers can access this route
    if 'user_id' not in session or session['role'] != 'teacher':
        flash("Unauthorized access.", 'error')
        return redirect(url_for('login'))

    date_str = request.form['date']
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'error')
        return redirect(url_for('dashboard'))

    # Prevent scheduling on Sunday
    if date_obj.weekday() == 6: # Monday is 0, Sunday is 6
        flash("Cannot schedule on Sunday.", 'warning')
        return redirect(url_for('dashboard'))

    start_times = request.form.getlist('start_time')
    end_times = request.form.getlist('end_time')

    # Find existing schedule or create a new one for the teacher on this date
    schedule = Schedule.query.filter_by(teacher_id=session['user_id'], date=date_obj).first()
    if not schedule:
        schedule = Schedule(teacher_id=session['user_id'], date=date_obj)
        db.session.add(schedule)
        db.session.flush() # Flush to get the schedule.id for period slots

    # Remove existing slots for this schedule to allow for a complete update
    # This ensures that if a teacher modifies a schedule, old slots are removed and new ones are added.
    PeriodSlot.query.filter_by(schedule_id=schedule.id).delete()

    for start_str, end_str in zip(start_times, end_times):
        try:
            start = datetime.strptime(start_str, "%H:%M").time()
            end = datetime.strptime(end_str, "%H:%M").time()
        except ValueError:
            flash(f"Invalid time format for a period slot: {start_str}-{end_str}. Please use HH:MM.", 'error')
            db.session.rollback() # Rollback any changes if there's an error
            return redirect(url_for('dashboard'))

        # Calculate duration in minutes
        duration = datetime.combine(date.min, end) - datetime.combine(date.min, start)
        minutes = duration.total_seconds() / 60

        # --- Corrected Period Calculation Logic ---
        # Based on user requirements:
        # <= 60 minutes: 1 period
        # > 60 minutes and <= 120 minutes: 2 periods
        # >= 180 minutes (3 hours): 3 periods (for labs)
        if minutes <= 0:
            flash(f"Invalid period duration ({minutes} minutes) for {start_str}-{end_str}. End time must be after start time.", 'error')
            db.session.rollback()
            return redirect(url_for('dashboard'))
        elif minutes <= 60:
            count = 1
        elif 60 < minutes <= 120:
            count = 2
        elif minutes >= 180: # Assuming 3 hours means 180 minutes for a lab
            count = 3
        else:
            # Handle durations that don't fit the clear definitions (e.g., 121-179 minutes)
            flash(f"Period duration of {minutes} minutes for {start_str}-{end_str} does not fit standard period definitions. Defaulting to 1 period.", 'warning')
            count = 1

        slot = PeriodSlot(schedule_id=schedule.id, start_time=start, end_time=end, period_count=count)
        db.session.add(slot)

    db.session.commit() # Commit all new period slots
    flash("Schedule created/updated successfully.", 'success')
    return redirect(url_for('dashboard'))

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    """Allows teachers to mark attendance for students for a specific date and period slots."""
    # Ensure only logged-in teachers can access this route
    if 'user_id' not in session or session['role'] != 'teacher':
        flash("Unauthorized access.", 'error')
        return redirect(url_for('login'))

    date_str = request.form['date']
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'error')
        return redirect(url_for('dashboard'))

    teacher_id = session['user_id']

    # Get the schedule for the given date for the current teacher
    schedule = Schedule.query.filter_by(teacher_id=teacher_id, date=date_obj).first()
    if not schedule:
        flash("No schedule found for this date. Please create a schedule first.", 'warning')
        return redirect(url_for('dashboard'))

    # Iterate through form data to find attendance statuses
    for key, value in request.form.items():
        if key.startswith('status_'):
            parts = key.split('_')
            if len(parts) != 3: # Expected format: status_student_id_slot_id
                continue
            _, student_id_str, slot_id_str = parts
            try:
                student_id = int(student_id_str)
                slot_id = int(slot_id_str)
            except ValueError:
                flash(f"Invalid student ID or slot ID in form data: {key}", 'error')
                continue

            # Check if an attendance record already exists for this student, date, and slot
            record = Attendance.query.filter_by(student_id=student_id, date=date_obj, period_slot_id=slot_id).first()
            if record:
                # Update existing record
                record.status = value
            else:
                # Create new record
                new_record = Attendance(student_id=student_id, date=date_obj, period_slot_id=slot_id, status=value)
                db.session.add(new_record)

    db.session.commit() # Commit all attendance changes
    flash("Attendance marked successfully.", 'success')
    return redirect(url_for('dashboard'))

# --- NEW API ENDPOINT FOR TEACHER DASHBOARD JAVASCRIPT ---
@app.route('/api/teacher/attendance_data', methods=['GET'])
def get_teacher_attendance_data():
    """
    API endpoint to fetch students, schedule, and current attendance for a given date.
    Used by JavaScript on the teacher dashboard to dynamically populate the attendance table.
    """
    if 'user_id' not in session or session['role'] != 'teacher':
        return jsonify({'error': 'Unauthorized access'}), 401

    teacher_id = session['user_id']
    date_str = request.args.get('date')

    if not date_str:
        return jsonify({'error': 'Date parameter is missing'}), 400

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Invalid date format. Please use YYYY-MM-DD.'}), 400

    teacher = Teacher.query.get(teacher_id)
    if not teacher:
        return jsonify({'error': 'Teacher not found.'}), 404

    # Get students associated with this teacher's branch and section
    students = Student.query.filter_by(teacher_id=teacher.id).all()

    # Get the schedule for the selected date
    schedule_obj = Schedule.query.filter_by(teacher_id=teacher.id, date=date_obj).first()

    # Prepare data for JSON response
    response_data = {
        'students': [],
        'schedule': [],
        'error': None
    }

    # Serialize student data and their attendance for the selected date
    for student in students:
        student_data = {
            'id': student.id,
            'rollno': student.rollno,
            'name': student.name,
            'attendance': {} # To store attendance status for each period slot
        }
        # Fetch attendance records for this student for the specific date
        student_attendances = Attendance.query.filter_by(student_id=student.id, date=date_obj).all()
        for att in student_attendances:
            student_data['attendance'][att.period_slot_id] = att.status
        response_data['students'].append(student_data)

    # Serialize schedule data (period slots)
    if schedule_obj:
        for slot in schedule_obj.period_slots:
            response_data['schedule'].append({
                'id': slot.id,
                'start_time': slot.start_time.strftime('%H:%M'),
                'end_time': slot.end_time.strftime('%H:%M'),
                'period_count': slot.period_count
            })
    
    return jsonify(response_data), 200


@app.route('/dashboard')
def dashboard():
    """Renders the appropriate dashboard based on user role."""
    if 'user_id' not in session:
        flash("Please log in to access the dashboard.", 'info')
        return redirect(url_for('login'))

    if session['role'] == 'teacher':
        teacher = Teacher.query.get(session['user_id'])
        # No need to fetch students or today's schedule here, as the JS will do it via API
        return render_template('teacher_dashboard.html', teacher=teacher)

    else: # Student role
        student = Student.query.get(session['user_id'])
        
        teacher_schedules = Schedule.query.filter_by(teacher_id=student.teacher_id).all()

        total_possible_periods = 0
        for sch in teacher_schedules:
            total_possible_periods += sch.total_periods

        present_period_count_sum = 0
        # Eagerly load period_slot for efficiency
        # The .join(PeriodSlot) here is important for the HTML template to access att.period_slot
        attendances = Attendance.query.filter_by(student_id=student.id).join(PeriodSlot).all()
        for att in attendances:
            # The 'and att.period_slot' check is good practice, though with the relationship it should always exist
            if att.status == 'Present' and att.period_slot:
                present_period_count_sum += att.period_slot.period_count

        percent = round((present_period_count_sum / total_possible_periods) * 100, 2) if total_possible_periods > 0 else 0

        def needed_classes(target_percent, current_present_periods, current_total_periods):
            """
            Calculates the number of additional periods a student needs to be present for
            to reach a target attendance percentage.
            Assumes each 'needed' period is a 1-period slot for simplicity in calculation.
            """
            if current_total_periods == 0:
                return 0 # Cannot calculate if no periods yet

            # If current percentage is already above or equal to target, no classes are needed.
            if (current_present_periods / current_total_periods * 100) >= target_percent:
                return 0

            target_decimal = target_percent / 100.0
            
            # Handle the case where target is 100% and it's currently impossible
            if target_decimal == 1.0:
                if current_present_periods == current_total_periods:
                    return 0
                else:
                    # Return a specific string to indicate infinity, as Jinja2 doesn't understand float('inf')
                    return "infinity_val" 

            # Formula derived from: (current_present_periods + X) / (current_total_periods + X) >= target_decimal
            # Where X is the number of additional periods needed (assuming they are all present).
            numerator = (target_decimal * current_total_periods) - current_present_periods
            denominator = 1 - target_decimal

            # Denominator should be positive if target_decimal < 1
            if denominator <= 0:
                return 0 # Should not happen if target_percent < 100

            needed = max(0, numerator / denominator)
            # Round up to the nearest whole period, as you can't attend a fraction of a period
            return int(round(needed))


        return render_template('student_dashboard.html',
                               student=student,
                               percent=percent,
                               total_possible_periods=total_possible_periods, # Passed now
                               present_period_count_sum=present_period_count_sum, # Passed now
                               attendances=attendances, # Pass all attendance records for detailed table
                               needed={
                                   75: needed_classes(75, present_period_count_sum, total_possible_periods),
                                   80: needed_classes(80, present_period_count_sum, total_possible_periods),
                                   85: needed_classes(85, present_period_count_sum, total_possible_periods),
                                   90: needed_classes(90, present_period_count_sum, total_possible_periods),
                               })


@app.route('/logout')
def logout():
    """Logs out the current user by clearing the session."""
    session.clear()
    flash("You have been logged out.", 'info')
    return redirect(url_for('login'))

@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """
    A mock route for password reset.
    In a real application, this would involve sending an email with a reset link.
    """
    role = request.args.get("role") or request.form.get("role")
    if request.method == "POST":
        # Here you would typically implement email sending logic
        # to send a password reset link to the user's email.
        flash("Password reset instructions sent (mock). Please check your email or contact admin.", 'info')
        return redirect(url_for("forgot_password", role=role))
    return render_template("forgot_password.html", role=role)

# --- Application Entry Point ---
if __name__ == '__main__':
    # This block ensures that the database tables are created
    # when you run the script directly.
    with app.app_context():
        db.create_all() # Creates tables based on defined models
    app.run(debug=True) # Runs the Flask development server
