"""update tasks for dates

Revision ID: update_tasks_for_dates
Revises: add_dates_to_schedule
Create Date: 2024-03-19

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timedelta

# revision identifiers, used by Alembic.
revision = 'update_tasks_for_dates'
down_revision = 'add_dates_to_schedule'
branch_labels = None
depends_on = None

def upgrade():
    # Skapa en temporär tabell för att lagra uppdaterade uppgifter
    op.create_table(
        'task_temp',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('task_type', sa.String(length=100), nullable=False),
        sa.Column('completed', sa.Boolean(), default=False),
        sa.Column('missed', sa.Boolean(), default=False),
        sa.Column('schedule_id', sa.Integer(), nullable=True)
    )
    
    # Kopiera alla uppgifter som ligger inom schemats datumintervall
    op.execute("""
        INSERT INTO task_temp (id, date, task_type, completed, missed, schedule_id)
        SELECT t.id, t.date, t.task_type, t.completed, t.missed, t.schedule_id
        FROM task t
        JOIN schedule s ON t.schedule_id = s.id
        WHERE t.date >= s.start_date 
        AND (s.end_date IS NULL OR t.date <= s.end_date)
    """)
    
    # Ta bort den gamla tabellen och byt namn på den temporära
    op.drop_table('task')
    op.rename_table('task_temp', 'task')

def downgrade():
    # Detta är en enkel downgrade som bara behåller alla uppgifter
    pass 