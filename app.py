from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import os

app = Flask(__name__)

# Konfigurera databasen baserat på miljö
db_filename = 'kaninkalender.db'

# Använd /data på Render, annars instance-mappen lokalt
if os.path.exists('/data'):
    db_path = os.path.join('/data', db_filename)
else:
    db_path = os.path.join(app.instance_path, db_filename)
    os.makedirs(app.instance_path, exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.json.ensure_ascii = False  # Tillåt icke-ASCII tecken i JSON
db = SQLAlchemy(app)

# Hämta titel från miljövariabel eller använd default
CALENDAR_TITLE = os.getenv('CALENDAR_TITLE', 'Calendar')

# Initiera databasen endast om filen saknas
if not os.path.exists(db_path):
    with app.app_context():
        db.create_all()
        print(f"✅ Databas skapades eftersom den inte fanns: {db_path}")

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    weekdays = db.Column(db.String(100), nullable=False)  # Stored as JSON string
    active = db.Column(db.Boolean, default=True)
    end_date = db.Column(db.Date, nullable=True)  # New column for end date

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'weekdays': json.loads(self.weekdays),
            'active': self.active,
            'end_date': self.end_date.isoformat() if self.end_date else None
        }

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    task_type = db.Column(db.String(100), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    missed = db.Column(db.Boolean, default=False)  # Ny kolumn för missade uppgifter
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedule.id'), nullable=True)

def create_future_tasks():
    # Hämta alla aktiva scheman
    schedules = Schedule.query.filter_by(active=True).all()
    today = datetime.now().date()
    
    # För varje schema, skapa uppgifter fram till dess slutdatum
    for schedule in schedules:
        # Bestäm hur långt fram vi ska skapa uppgifter
        if schedule.end_date:
            end_date = schedule.end_date
            print(f"Schedule '{schedule.title}' has end date: {end_date}")
        else:
            end_date = today + timedelta(days=60)  # Ändrat från 30 till 60 dagar
            print(f"Schedule '{schedule.title}' has no end date, using default 60 days")
        
        # Skapa uppgifter för varje dag fram till slutdatumet
        current_date = today
        while current_date <= end_date:
            weekday = current_date.weekday()
            weekdays = json.loads(schedule.weekdays)
            
            if weekday in weekdays:
                # Kontrollera om det redan finns en uppgift för detta datum och schema
                existing_task = Task.query.filter_by(
                    date=current_date,
                    schedule_id=schedule.id
                ).first()
                
                if not existing_task:
                    task = Task(
                        date=current_date,
                        task_type=schedule.title,
                        completed=False,
                        schedule_id=schedule.id
                    )
                    db.session.add(task)
                    print(f"Created task for {current_date}: {schedule.title}")
            
            current_date += timedelta(days=1)
    
    db.session.commit()

@app.route('/')
def index():
    today = datetime.now().date()
    today_tasks = Task.query.filter_by(date=today).all()
    return render_template('index.html', today_tasks=today_tasks, calendar_title=CALENDAR_TITLE)

@app.route('/api/schedules', methods=['GET'])
def get_schedules():
    schedules = Schedule.query.all()
    return jsonify([schedule.to_dict() for schedule in schedules])

@app.route('/api/schedules', methods=['POST'])
def create_schedule():
    data = request.json
    end_date = None
    if data.get('end_date'):
        try:
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            print(f"Creating schedule with end date: {end_date}")
        except ValueError as e:
            print(f"Error parsing end date: {e}")
            return jsonify({'error': 'Invalid date format'}), 400
    
    schedule = Schedule(
        title=data['title'],
        weekdays=json.dumps(data['weekdays']),
        active=data['active'],
        end_date=end_date
    )
    db.session.add(schedule)
    db.session.commit()
    
    # Skapa framtida uppgifter för det nya schemat
    create_future_tasks()
    
    return jsonify(schedule.to_dict())

@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    schedule = Schedule.query.get_or_404(schedule_id)
    data = request.json
    schedule.title = data['title']
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
        'completed': task.completed,
        'missed': task.missed,
        'schedule_id': task.schedule_id
    } for task in tasks])

@app.route('/api/tasks/<int:task_id>/toggle', methods=['POST'])
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
def check_reminders():
    today = datetime.now().date()
    
    # Hämta endast dagens uppgifter
    tasks = Task.query.filter_by(date=today).all()
    
    reminders = [{
        'title': task.task_type,
        'date': task.date.strftime('%Y-%m-%d')
    } for task in tasks]
    
    return jsonify(reminders)

def init_db():
    with app.app_context():
        # Kontrollera om databasen redan har tabeller
        inspector = db.inspect(db.engine)
        if not inspector.has_table('schedule'):
            print("Creating database tables...")
            db.create_all()
            print("Database tables created successfully!")
        else:
            print("Database tables already exist, skipping creation.")

if __name__ == '__main__':
    init_db()  # Initiera databasen vid start
    app.run(debug=True) 