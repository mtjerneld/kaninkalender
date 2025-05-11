from flask import Flask, render_template, jsonify, request, session, Blueprint, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
from functools import wraps
from hashlib import sha256
import logging
from flask_wtf.csrf import CSRFProtect, CSRFError
import secrets  # Lägg till denna import överst

# Ladda miljövariabler från .env
load_dotenv()

# Skapa Flask-appen
app = Flask(__name__)

# Säkerhetskonfiguration
required_env_vars = ['SECRET_KEY', 'PASSWORD_HASH', 'API_KEY']
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

app.secret_key = os.getenv('SECRET_KEY')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'  # True i produktion
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Skydda mot XSS
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Balanserad säkerhet för kalender-app
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Aktivera CSRF-skydd
csrf = CSRFProtect(app)

# Skapa blueprint för API-nyckel-baserade endpoints
api_bp = Blueprint('api', __name__, url_prefix='/api')
csrf.exempt(api_bp)  # Undanta hela API-blueprinten från CSRF

# Undanta login från CSRF-skydd
csrf.exempt(app.route('/api/login'))

def csrf_exempt(view):
    """Dekorator för att undanta en vy från CSRF-skydd"""
    csrf.exempt(view)
    return view

def csrf_optional_for_api_key(view):
    if not hasattr(view, '_csrf_exempt'):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            api_key = request.headers.get("X-API-Key")
            if api_key and api_key == API_KEY:
                # Direktundanta funktionen (görs en gång)
                view._csrf_exempt = True
            return view(*args, **kwargs)
        return wrapped_view
    return view

# Hantera CSRF-fel
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    if request.path == '/api/login':
        return jsonify({'error': 'Felaktigt lösenord'}), 401
    return jsonify({'error': 'CSRF token missing or invalid'}), 400

def generate_nonce():
    """Generera en unik nonce för varje request"""
    return secrets.token_hex(16)

@app.before_request
def before_request():
    if not session.get('csrf_token'):
        session['csrf_token'] = csrf._get_csrf_token()
    
    # Lägg till CSP header med nonce
    nonce = generate_nonce()
    session['script_nonce'] = nonce
    
    # Strikt CSP policy
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-{nonce}' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "font-src 'self' data: https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ).format(nonce=nonce)
    
    # Lägg till headers på response
    response = make_response()
    response.headers['Content-Security-Policy'] = csp
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Returnera None för att fortsätta med request
    return None

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

# Konfigurera loggning
logging.basicConfig(
    level=logging.DEBUG if os.environ.get('FLASK_ENV') == 'development' else logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

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
    from flask_migrate import upgrade
    import traceback
    print("🔄 Running database migrations...")
    try:
        upgrade()
        print("✅ Migrations completed successfully!")
    except Exception as e:
        print("❌ Error during migrations:")
        traceback.print_exc()
        raise

# Hämta titel från miljövariabel eller använd default
CALENDAR_TITLE = os.getenv('CALENDAR_TITLE', 'Calendar')

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    weekdays = db.Column(db.String(100), nullable=False)  # Stored as JSON string
    active = db.Column(db.Boolean, default=True)
    end_date = db.Column(db.Date, nullable=True)
    start_date = db.Column(db.Date, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'weekdays': json.loads(self.weekdays),  # Konvertera från JSON-sträng till lista
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
        try:
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
            weekdays = json.loads(schedule.weekdays) if isinstance(schedule.weekdays, str) else schedule.weekdays
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
                            description=schedule.description,
                            completed=False,
                            schedule_id=schedule.id
                        ))
                        tasks_for_schedule += 1
                
                current_date += timedelta(days=1)
            
            if tasks_for_schedule > 0:
                logging.debug(f"Prepared {tasks_for_schedule} tasks for schedule '{schedule.title}'")
                
        except Exception as e:
            logging.error(f"Fel vid skapande av uppgifter för schema {schedule.id}: {str(e)}")
            continue
    
    # Skapa alla uppgifter i ett enda batch
    if all_tasks_to_create:
        try:
            logging.debug(f"Creating {len(all_tasks_to_create)} tasks in bulk")
            db.session.bulk_save_objects(all_tasks_to_create)
            db.session.commit()
            logging.debug("Bulk insert completed")
        except Exception as e:
            logging.error(f"Fel vid bulk insert av uppgifter: {str(e)}")
            db.session.rollback()

@app.route('/')
def index():
    today = datetime.now().date()
    today_tasks = Task.query.filter_by(date=today).all()
    return render_template('index.html', 
                         today_tasks=today_tasks, 
                         calendar_title=CALENDAR_TITLE,
                         csrf_token=session.get('csrf_token', csrf._get_csrf_token()),
                         script_nonce=session.get('script_nonce', generate_nonce()))

@app.route('/api/login', methods=['POST'])
@csrf.exempt
def login():
    try:
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
            session.clear()
            session['is_logged_in'] = True
            session['login_time'] = datetime.now().isoformat()
            session.permanent = True
            record_login_attempt(client_ip, True)
            logging.debug("Successful login from IP: %s", client_ip)  # Säker loggning
            return jsonify({'message': 'Login successful'})
        else:
            record_login_attempt(client_ip, False)
            logging.warning("Failed login attempt from IP: %s", client_ip)  # Säker loggning
            return jsonify({'error': 'Felaktigt lösenord'}), 401
    except Exception as e:
        return log_error(e, "Fel vid inloggning")

@app.route('/api/logout', methods=['POST'])
def logout():
    print("Logging out, session before:", dict(session))  # Debug-utskrift
    session.clear()  # Rensa hela sessionen
    print("Session after logout:", dict(session))  # Debug-utskrift
    return jsonify({'message': 'Logged out successfully'})

@app.route('/api/check-session')
def check_session():
    is_logged_in = session.get('is_logged_in', False)
    logging.debug("Session check - logged in: %s", is_logged_in)  # Säker loggning
    return jsonify({'logged_in': is_logged_in})

@app.route('/api/schedules', methods=['GET'])
@require_auth
def get_schedules():
    try:
        schedules = Schedule.query.all()
        # Returnera tom array om inga scheman finns
        if not schedules:
            return jsonify([])
            
        # Konvertera alla scheman till dictionaries
        schedule_list = []
        for schedule in schedules:
            try:
                schedule_dict = schedule.to_dict()
                schedule_list.append(schedule_dict)
            except Exception as e:
                logging.error(f"Fel vid konvertering av schema {schedule.id}: {str(e)}")
                continue
                
        return jsonify(schedule_list)
        
    except Exception as e:
        logging.exception("Fel vid hämtning av scheman:")
        return jsonify({'error': 'Ett fel uppstod när scheman skulle hämtas'}), 500

@api_bp.route('/schedules', methods=['POST'])
@require_auth
@csrf_optional_for_api_key
def create_schedule():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Ingen data skickades'}), 400
            
        logging.debug("Received schedule data: %s", data)
        
        # Validera weekdays
        weekdays = data.get('weekdays', [])
        if not isinstance(weekdays, list):
            return jsonify({'error': 'weekdays måste vara en lista'}), 400
        
        # Konvertera till set för att ta bort duplicerade dagar och validera värden
        try:
            weekdays_set = {int(day) for day in weekdays}
            if not all(0 <= day <= 6 for day in weekdays_set):
                return jsonify({'error': 'weekdays måste vara värden mellan 0 och 6'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'weekdays måste innehålla giltiga nummer'}), 400
        
        # Validera start_date
        start_date = data.get('start_date')
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                if start_date < datetime.now().date():
                    return jsonify({'error': 'start_date kan inte vara i det förflutna'}), 400
            except ValueError:
                return jsonify({'error': 'ogiltigt start_date format'}), 400
        
        # Validera end_date
        end_date = data.get('end_date')
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                if start_date and end_date < start_date:
                    return jsonify({'error': 'end_date kan inte vara före start_date'}), 400
            except ValueError:
                return jsonify({'error': 'ogiltigt end_date format'}), 400
        
        # Skapa schemat
        schedule = Schedule(
            title=data['title'],
            description=data.get('description'),
            weekdays=json.dumps(list(weekdays_set)),  # Konvertera till JSON-sträng
            start_date=start_date,
            end_date=end_date,
            active=data.get('active', True)
        )
        
        db.session.add(schedule)
        db.session.commit()
        
        # Skapa framtida uppgifter
        create_future_tasks()
        
        return jsonify(schedule.to_dict()), 201
        
    except KeyError as e:
        logging.error("Missing required field: %s", str(e))
        return jsonify({'error': f'Saknar obligatoriskt fält: {str(e)}'}), 400
    except Exception as e:
        logging.exception("Fel vid skapande av schema:")
        return jsonify({'error': 'Ett fel uppstod när schemat skulle skapas'}), 500

@api_bp.route('/schedules/<int:schedule_id>', methods=['PUT'])
@require_auth
@csrf_optional_for_api_key
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    data = request.get_json()
    
    # Validera weekdays
    if 'weekdays' in data:
        weekdays = data['weekdays']
        if not isinstance(weekdays, list):
            return jsonify({'error': 'weekdays måste vara en lista'}), 400
        
        # Konvertera till set för att ta bort duplicerade dagar och validera värden
        try:
            weekdays_set = {int(day) for day in weekdays}
            if not all(0 <= day <= 6 for day in weekdays_set):
                return jsonify({'error': 'weekdays måste vara värden mellan 0 och 6'}), 400
            schedule.weekdays = json.dumps(list(weekdays_set))  # Konvertera tillbaka till JSON-sträng för lagring
        except (ValueError, TypeError):
            return jsonify({'error': 'weekdays måste innehålla giltiga nummer'}), 400
    
    # Uppdatera övriga fält
    if 'title' in data:
        schedule.title = data['title']
    if 'description' in data:
        schedule.description = data['description']
    if 'start_date' in data:
        schedule.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
    if 'end_date' in data:
        schedule.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data['end_date'] else None
    if 'active' in data:
        schedule.active = data['active']
    
    db.session.commit()
    
    # Uppdatera tasks om schemat ändrats
    if any(key in data for key in ['weekdays', 'start_date', 'end_date', 'active']):
        update_schedule_tasks(schedule)
    
    return jsonify(schedule.to_dict())

@api_bp.route('/schedules/<int:schedule_id>', methods=['DELETE'])
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
    try:
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
        logging.debug("Retrieved %d tasks from %s to %s", len(tasks), start_date, end_date)  # Säker loggning
        
        return jsonify([{
            'id': task.id,
            'date': task.date.strftime('%Y-%m-%d'),
            'task_type': task.task_type,
            'description': task.description,
            'completed': task.completed,
            'missed': task.missed,
            'schedule_id': task.schedule_id
        } for task in tasks])
    except Exception as e:
        return log_error(e, "Fel vid hämtning av uppgifter")

@api_bp.route('/tasks/<int:task_id>/toggle', methods=['POST'])
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

@api_bp.route('/tasks/<int:task_id>/reschedule', methods=['POST'])
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

@api_bp.route('/tasks/<int:task_id>/missed', methods=['POST'])
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

# Registrera blueprinten
app.register_blueprint(api_bp)

# Kör migreringar även när Render kör 'gunicorn app:app'
if os.getenv('RENDER') == 'true' or os.getenv('FLASK_ENV') == 'production':
    with app.app_context():
        run_migrations()

def log_error(error, message="Ett fel uppstod"):
    """Loggar fel internt men returnerar ett säkert meddelande till användaren"""
    if os.environ.get('FLASK_ENV') == 'development':
        logging.error(f"Detaljerat fel: {str(error)}")
    else:
        logging.error(message)
    return message

if __name__ == "__main__":
    app.run(debug=True) 