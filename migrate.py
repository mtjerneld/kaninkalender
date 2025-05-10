from app import db, app
from flask_migrate import upgrade
import os

with app.app_context():
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if os.path.exists(db_path):
        print(f"✅ Databas finns redan: {db_path} – migrering hoppas över")
    else:
        print(f"🆕 Skapar databas med migrering: {db_path}")
        upgrade() 