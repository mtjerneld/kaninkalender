from app import app, db
from flask_migrate import upgrade

print("🔄 Running database migrations...")
with app.app_context():
    upgrade()
print("✅ Database migrations completed!") 