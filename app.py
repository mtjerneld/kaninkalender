from flask import Flask, render_template, jsonify, request, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
from functools import wraps
from hashlib import sha256
import logging

# Ladda miljövariabler från .env
load_dotenv()

# Skapa Flask-appen
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-secret-key')  # Lägg till en hemlig nyckel för sessions
app.config['SESSION_COOKIE_SECURE'] = False  # Tillåt sessions över HTTP i utvecklingsmiljö
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Skydda mot XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Skydda mot CSRF
app.config['SESSION_TYPE'] = 'filesystem'  # Använd filsystem för sessions
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Sätt sessionens livstid till 7 dagar

# Konfigurera databasen
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.json.ensure_ascii = False  # Tillåt icke-ASCII tecken i JSON

# API-nyckel från miljövariabel
API_KEY = os.getenv('API_KEY')

# Lösenordshash från miljövariabel
PASSWORD_HASH = os.getenv('PASSWORD_HASH', '8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92')  # Default: "123456"

# Konfigurera logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Login attempts tracking
login_attempts = {}
MAX_LOGIN_ATTEMPTS = 3
BLOCK_DURATION = 0.5  # minutes (30 seconds)

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def is_ip_blocked(ip):
    if ip in login_attempts:
        attempts = login_attempts[ip]
        if attempts['count'] >= MAX_LOGIN_ATTEMPTS:
            block_time = attempts['last_attempt'] + timedelta(minutes=BLOCK_DURATION)
            if datetime.now() < block_time:
                return True
            else:
                # Reset attempts if block duration has passed
                login_attempts[ip] = {'count': 0, 'last_attempt': datetime.now()}
    return False

def record_login_attempt(ip, success):
    if ip not in login_attempts:
        login_attempts[ip] = {'count': 0, 'last_attempt': datetime.now()}
    
    if not success:
        login_attempts[ip]['count'] += 1
    else:
        login_attempts[ip]['count'] = 0
    
    login_attempts[ip]['last_attempt'] = datetime.now()

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Tillåt API-nyckel som alternativ till session
        api_key = request.headers.get('X-API-Key')
        if API_KEY and api_key == API_KEY:
            print("Authenticated via API key")  # Debug-utskrift
            return f(*args, **kwargs)

        # Alternativt: kontrollera session
        is_logged_in = session.get('is_logged_in', False)
        if is_logged_in:
            print("Authenticated via session")  # Debug-utskrift
            return f(*args, **kwargs)

        print("Authentication failed - no valid API key or session")  # Debug-utskrift
        return jsonify({"error": "Unauthorized"}), 401
    return decorated_function

# Initiera databasen och migrations
db = SQLAlchemy(app)
migrate = Migrate(app, db)

def run_migrations():
    with app.app_context():
        from flask_migrate import upgrade
        print("🔄 Running database migrations...")
        try:
            upgrade()
            print("✅ Migrations completed successfully!")
        except Exception as e:
            print(f"❌ Error during migrations: {str(e)}")
            raise

# Hämta titel från miljövariabel eller använd default
CALENDAR_TITLE = os.getenv('CALENDAR_TITLE', 'Calendar')

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Ny kolumn för beskrivning
    weekdays = db.Column(db.String(100), nullable=False)  # Stored as JSON string
    active = db.Column(db.Boolean, default=True)
    end_date = db.Column(db.Date, nullable=True)  # Slutdatum
    start_date = db.Column(db.Date, nullable=True)  # Startdatum

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,  # Lägg till beskrivning i JSON-svaret
            'weekdays': json.loads(self.weekdays),
            'active': self.active,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'start_date': self.start_date.isoformat() if self.start_date else None
        }

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    task_type = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Lägg till beskrivningsfält
    completed = db.Column(db.Boolean, default=False)
    missed = db.Column(db.Boolean, default=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=True)

def create_future_tasks():
    # Hämta alla aktiva scheman
    schedules = Schedule.query.filter_by(active=True).all()
    today = datetime.now().date()
    max_end_date = today + timedelta(days=365*10)  # 10 år fram i tiden
    
    # Samla alla uppgifter som ska skapas
    all_tasks_to_create = []
    
    # För varje schema, skapa uppgifter fram till dess slutdatum
    for schedule in schedules:
        # Bestäm hur långt fram vi ska skapa uppgifter
        if schedule.end_date:
            end_date = min(schedule.end_date, max_end_date)
        else:
            end_date = today + timedelta(days=60)
        
        # Bestäm startdatum
        if schedule.start_date:
            start_date = schedule.start_date
        else:
            start_date = today
        
        # Skapa uppgifter för varje dag från startdatum till slutdatumet
        current_date = max(today, start_date)
        weekdays = json.loads(schedule.weekdays)
        tasks_for_schedule = 0
        
        while current_date <= end_date:
            weekday = current_date.weekday()
            
            if weekday in weekdays:
                # Kontrollera om det redan finns en uppgift för detta datum och schema
                existing_task = Task.query.filter_by(
                    date=current_date,
                    schedule_id=schedule.id
                ).first()
                
                if not existing_task:
                    all_tasks_to_create.append(Task(
                        date=current_date,
                        task_type=schedule.title,
                        description=schedule.description,  # Kopiera beskrivningen från schemat
                        completed=False,
                        schedule_id=schedule.id
                    ))
                    tasks_for_schedule += 1
            
            current_date += timedelta(days=1)
        
        if tasks_for_schedule > 0:
            print(f"Prepared {tasks_for_schedule} tasks for schedule '{schedule.title}'")
    
    # Skapa alla uppgifter i ett enda batch
    if all_tasks_to_create:
        print(f"Creating {len(all_tasks_to_create)} tasks in bulk")
        db.session.bulk_save_objects(all_tasks_to_create)
        db.session.commit()
        print("Bulk insert completed")

@app.route('/')
def index():
    today = datetime.now().date()
    today_tasks = Task.query.filter_by(date=today).all()
    return render_template('index.html', 
                         today_tasks=today_tasks, 
                         calendar_title=CALENDAR_TITLE)

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    password = data.get('password', '')
    client_ip = get_client_ip()
    
    # Check if IP is blocked
    if is_ip_blocked(client_ip):
        remaining_time = (login_attempts[client_ip]['last_attempt'] + 
                         timedelta(minutes=BLOCK_DURATION) - datetime.now())
        seconds = int(remaining_time.total_seconds())
        return jsonify({
            'error': f'För många misslyckade inloggningsförsök. Försök igen om {seconds} sekunder.'
        }), 429

    # Hash the password
    hashed_password = sha256(password.encode()).hexdigest()

    if hashed_password == PASSWORD_HASH:
        session.clear()  # Rensa eventuella gamla sessionsdata
        session['is_logged_in'] = True
        session.permanent = True  # Gör sessionen permanent
        record_login_attempt(client_ip, True)
        print("Session created:", dict(session))  # Debug-utskrift
        return jsonify({'message': 'Login successful'})
    else:
        record_login_attempt(client_ip, False)
        return jsonify({'error': 'Felaktigt lösenord'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    print("Logging out, session before:", dict(session))  # Debug-utskrift
    session.clear()  # Rensa hela sessionen
    print("Session after logout:", dict(session))  # Debug-utskrift
    return jsonify({'message': 'Logged out successfully'})

@app.route('/api/check-session')
def check_session():
    print("Checking session:", dict(session))  # Debug-utskrift
    is_logged_in = session.get('is_logged_in', False)
    print("Is logged in:", is_logged_in)  # Debug-utskrift
    return jsonify({'logged_in': is_logged_in})

@app.route('/api/schedules', methods=['GET'])
@require_auth
def get_schedules():
    try:
        schedules = Schedule.query.all()
        return jsonify([s.to_dict() for s in schedules])
    except Exception as e:
        logging.exception("Fel vid hämtning av scheman:")
        return jsonify({'error': str(e)}), 500

@app.route('/api/schedules', methods=['POST'])
@require_auth
def create_schedule():
    data = request.json
    title = data.get('title')
    description = data.get('description')  # Hämta beskrivning
    weekdays = data.get('weekdays', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    active = data.get('active', True)

    logger.info(f"Creating schedule with description: {description}")  # Logga beskrivningen

    if not title or not weekdays or not start_date:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        # Validera datum
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date()
        max_end_date = datetime.now().date() + timedelta(days=365*10)  # 10 år fram i tiden
        
        if end_date:
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
            if end_date_obj > max_end_date:
                return jsonify({'error': 'Slutdatum kan inte vara mer än 10 år fram i tiden'}), 400
        else:
            end_date_obj = None

        # Skapa schemat
        schedule = Schedule(
            title=title,
            description=description,  # Lägg till beskrivning
            weekdays=json.dumps(weekdays),
            start_date=start_date_obj,
            end_date=end_date_obj,
            active=active
        )
        logger.info(f"Created schedule object with description: {schedule.description}")  # Logga beskrivningen
        db.session.add(schedule)
        db.session.flush()  # Flush för att få schedule.id

        # Skapa alla uppgifter i ett enda batch
        tasks_to_create = []
        current_date = start_date_obj

        while True:
            if end_date_obj and current_date > end_date_obj:
                break

            weekday = current_date.weekday()
            if weekday in weekdays:
                tasks_to_create.append(Task(
                    schedule_id=schedule.id,
                    date=current_date,
                    task_type=title,
                    description=description,  # Kopiera beskrivningen från schemat
                    completed=False,
                    missed=False
                ))

            current_date += timedelta(days=1)
            if not end_date and current_date > max_end_date:
                break

        if tasks_to_create:
            db.session.bulk_save_objects(tasks_to_create)

        db.session.commit()
        return jsonify(schedule.to_dict()), 201

    except ValueError as e:
        db.session.rollback()
        return jsonify({'error': f'Ogiltigt datumformat: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating schedule: {str(e)}")
        return jsonify({'error': 'Ett fel uppstod när schemat skulle skapas'}), 500

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
@require_auth
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    data = request.json
    logger.info(f"Updating schedule {schedule_id} with data: {data}")  # Logga inkommande data
    
    schedule.title = data['title']
    schedule.description = data.get('description')  # Uppdatera beskrivning
    logger.info(f"Updated schedule description to: {schedule.description}")  # Logga beskrivningen
    
    schedule.weekdays = json.dumps(data['weekdays'])
    schedule.active = data['active']
    
    if data.get('end_date'):
        try:
            schedule.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            print(f"Updated schedule end date to: {schedule.end_date}")
        except ValueError as e:
            print(f"Error parsing end date: {e}")
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        schedule.end_date = None
        print("Removed end date from schedule")
    if data.get('start_date'):
        try:
            schedule.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            print(f"Updated schedule start date to: {schedule.start_date}")
        except ValueError as e:
            print(f"Error parsing start date: {e}")
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        schedule.start_date = None
        print("Removed start date from schedule")
    
    db.session.commit()
    
    # Ta bort framtida uppgifter för detta schema
    today = datetime.now().date()
    Task.query.filter(
        Task.schedule_id == schedule_id,
        Task.date >= today
    ).delete()
    
    # Skapa nya framtida uppgifter
    create_future_tasks()
    
    return jsonify(schedule.to_dict())

@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
@require_auth
def delete_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    
    # Ta bort framtida uppgifter för detta schema
    today = datetime.now().date()
    Task.query.filter(
        Task.schedule_id == schedule_id,
        Task.date >= today
    ).delete()
    
    db.session.delete(schedule)
    db.session.commit()
    return '', 204

@app.route('/api/tasks', methods=['GET'])
@require_auth
def get_tasks():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    query = Task.query
    
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        query = query.filter(Task.date >= start_date)
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        query = query.filter(Task.date <= end_date)
    
    tasks = query.all()
    print(f"Returning {len(tasks)} tasks from {start_date} to {end_date}")
    
    return jsonify([{
        'id': task.id,
        'date': task.date.strftime('%Y-%m-%d'),
        'task_type': task.task_type,
        'description': task.description,  # Lägg till beskrivning i API-svaret
        'completed': task.completed,
        'missed': task.missed,
        'schedule_id': task.schedule_id
    } for task in tasks])

@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
@require_auth
def toggle_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json()
    status = data.get('status')
    
    if status == 'completed':
        task.completed = not task.completed
        if task.completed:
            task.missed = False
    elif status == 'missed':
        task.missed = not task.missed
        if task.missed:
            task.completed = False
    
    db.session.commit()
    return jsonify({
        'id': task.id,
        'date': task.date.isoformat(),
        'task_type': task.task_type,
        'completed': task.completed,
        'missed': task.missed
    })

@app.route('/api/tasks/<int:task_id>/reschedule', methods=['POST'])
@require_auth
def reschedule_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.json
    new_date = datetime.strptime(data['new_date'], '%Y-%m-%d').date()
    
    # Kontrollera att det nya datumet är inom 7 dagar från originaldatumet
    if abs((new_date - task.date).days) > 7:
        return jsonify({'error': 'Kan bara flytta aktiviteten inom 7 dagar från originaldatumet'}), 400
    
    task.date = new_date
    db.session.commit()
    return jsonify({
        'id': task.id,
        'date': task.date.strftime('%Y-%m-%d'),
        'task_type': task.task_type,
        'completed': task.completed,
        'schedule_id': task.schedule_id
    })

@app.route('/api/tasks/<int:task_id>/missed', methods=['POST'])
@require_auth
def mark_task_missed(task_id):
    task = Task.query.get_or_404(task_id)
    task.missed = True
    task.completed = False  # Återställ completed om uppgiften markeras som missad
    db.session.commit()
    return jsonify({
        'id': task.id,
        'date': task.date.strftime('%Y-%m-%d'),
        'task_type': task.task_type,
        'completed': task.completed,
        'missed': task.missed,
        'schedule_id': task.schedule_id
    })

@app.route('/api/reminder-check')
@require_auth
def check_reminders():
    today = datetime.now().date()
    
    # Hämta endast dagens uppgifter
    tasks = Task.query.filter_by(date=today).all()
    
    reminders = [{
        'title': task.task_type,
        'date': task.date.strftime('%Y-%m-%d')
    } for task in tasks]
    
    return jsonify(reminders)

if __name__ == "__main__":
    # Kör migreringar i produktion eller om RENDER=true
    if os.getenv('RENDER') == 'true' or os.getenv('FLASK_ENV') == 'production':
        run_migrations()
    app.run(debug=True) 