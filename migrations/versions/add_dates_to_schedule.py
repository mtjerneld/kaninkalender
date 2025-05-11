"""add dates to schedule

Revision ID: add_dates_to_schedule
Revises: 
Create Date: 2024-03-19

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta

# revision identifiers, used by Alembic.
revision = 'add_dates_to_schedule'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Lägg till nya kolumner med NULL som default
    op.add_column('schedule', sa.Column('start_date', sa.Date(), nullable=True))
    op.add_column('schedule', sa.Column('end_date', sa.Date(), nullable=True))
    
    # Sätt start_date till dagens datum för alla befintliga poster
    today = datetime.now().date()
    op.execute(f"UPDATE schedule SET start_date = '{today}' WHERE start_date IS NULL")
    
    # Sätt end_date till ett år fram i tiden för alla befintliga poster
    one_year = today + timedelta(days=365)
    op.execute(f"UPDATE schedule SET end_date = '{one_year}' WHERE end_date IS NULL")

def downgrade():
    # Ta bort kolumnerna
    op.drop_column('schedule', 'end_date')
    op.drop_column('schedule', 'start_date') 