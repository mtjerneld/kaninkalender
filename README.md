# Kaninkalendern

En kalenderapplikation för att hantera återkommande aktiviteter.

## 🚀 Funktioner

- Skapa och hantera scheman för kaniner
- Automatisk generering av uppgifter baserat på scheman
- Markera uppgifter som slutförda eller missade
- Flytta uppgifter inom 7 dagar från originaldatumet
- Responsiv design som fungerar på alla enheter

## 💻 Lokal utveckling

### Förutsättningar

- Python 3.9 eller senare
- pip (Python package manager)

### Installation

1. Klona repot
2. Skapa en `.env` fil med följande variabler:
   ```
   DATABASE_URL=din_postgres_url
   SECRET_KEY=ett_hemligt_värde
   PASSWORD_HASH=hash_av_lösenord
   API_KEY=din_api_nyckel
   CALENDAR_TITLE=Kaninkalendern
   ```
3. Installera beroenden: `pip install -r requirements.txt`
4. Kör migreringar: `flask db upgrade`
5. Starta servern: `flask run`

## 🚢 Deployment på Render

Applikationen är konfigurerad för deployment på Render med följande egenskaper:

- Använder Python 3.9
- Databasen sparas i `instance/`-mappen
- Automatisk databasinitialisering vid första körning
- Migreringar körs endast om databasen inte finns

### Miljövariabler

- `FLASK_ENV`: Satt till "production"
- `RENDER`: Satt till "true" för att detektera Render-miljön

## 📁 Projektstruktur

```
kaninkalender/
├── app.py              # Huvudapplikation
├── migrate.py          # Databasinitialisering
├── requirements.txt    # Python-beroenden
├── render.yaml         # Render-konfiguration
├── static/            # Statiska filer (CSS, JS)
├── templates/         # HTML-mallar
└── instance/         # Databas och konfiguration
```

## 🔧 Teknisk information

- **Backend**: Flask med SQLAlchemy för databashantering
- **Databas**: SQLite med Flask-Migrate för migrations
- **Frontend**: HTML, CSS, JavaScript
- **Deployment**: Render med gunicorn som WSGI-server

## 📝 Databasmigrationer

För att hantera databasändringar:

1. Uppdatera modellerna i `app.py`
2. Generera en ny migration:
   ```bash
   flask db migrate -m "beskrivning av ändringen"
   ```
3. Tillämpa migrationen:
   ```bash
   flask db upgrade
   ```

## 🔐 Säkerhet

- Databasen sparas i `instance/`-mappen som är skyddad från Git
- Migreringar körs endast om databasen inte finns
- Produktionsmiljön använder gunicorn med säkra inställningar
- Lösenord hashas med SHA-256 innan lagring
- Alla API-anrop sker över HTTPS
- Känsliga uppgifter lagras i miljövariabler

### Miljövariabler

Följande miljövariabler behöver konfigureras:

- `DATABASE_URL`: Connection string för PostgreSQL-databasen
- `API_KEY`: API-nyckel för externa anrop
- `SECRET_KEY`: Hemlig nyckel för sessionshantering
- `PASSWORD_HASH`: SHA-256 hash av lösenordet (utan default i produktion)

#### Lokal utveckling
1. Skapa en `.env`-fil i projektets rotmapp
2. Lägg till följande rader:
```
DATABASE_URL=din_neon_connection_string
API_KEY=din_api_nyckel
SECRET_KEY=ett_säkert_slumpmässigt_värde
PASSWORD_HASH=din_lösenordshash  # Använd sha256 för att generera hash
```

#### Produktion (Render)
1. Gå till Render Dashboard
2. Välj ditt projekt
3. Gå till "Environment"
4. Lägg till alla miljövariabler med säkra värden
5. Se till att använda en stark PASSWORD_HASH i produktion

### Säkerhetsrekommendationer

1. Använd starka, unika lösenord för alla tjänster
2. Rotera API-nycklar regelbundet
3. Använd en stark SECRET_KEY i produktion
4. Aktivera HTTPS i produktion
5. Håll alla beroenden uppdaterade
6. Använd en stark lösenordshash i produktion (ingen default)

## API

Appen tillhandahåller följande API-endpoints. Alla endpoints kräver API-nyckel som skickas i `X-API-Key` headern.

### Endpoints

#### Scheman
- `GET /api/schedules` - Hämta alla scheman
- `POST /api/schedules` - Skapa nytt schema
- `PUT /api/schedules/<id>` - Uppdatera schema
- `DELETE /api/schedules/<id>` - Ta bort schema

#### Uppgifter
- `GET /api/tasks` - Hämta uppgifter (med valfria parametrar `start_date` och `end_date`)
- `POST /api/tasks/<id>/toggle` - Växla uppgift mellan slutförd/ej slutförd
- `POST /api/tasks/<id>/reschedule` - Flytta uppgift till nytt datum
- `POST /api/tasks/<id>/missed` - Markera uppgift som missad

#### Påminnelser
- `GET /api/reminder-check` - Hämta dagens uppgifter

## Beroenden

- Flask==3.0.2
- Flask-SQLAlchemy==3.1.1
- Flask-Migrate==4.0.5
- psycopg2-binary==2.9.9
- python-dotenv>=1.0.0
- gunicorn==21.2.0

## Databasmigrationer

För att köra databasmigrationer:

```bash
# Initiera migrations (endast första gången)
python -m flask db init

# Skapa ny migration
python -m flask db migrate -m "beskrivning av ändringar"

# Kör migrationer
python -m flask db upgrade
```

## API-dokumentation

### Autentisering

API:et stödjer två autentiseringsmetoder:

1. **Session-baserad autentisering**
   - Logga in via `/api/login` med lösenord
   - Använd session-cookien för efterföljande anrop
   - Exempel:
     ```bash
     # Logga in
     curl -X POST http://localhost:5000/api/login \
       -H "Content-Type: application/json" \
       -d '{"password": "ditt_lösenord"}'
     
     # Använd API:et (cookien skickas automatiskt)
     curl http://localhost:5000/api/tasks
     ```

2. **API-nyckel autentisering**
   - Skicka API-nyckeln i `X-API-Key` headern
   - Fungerar utan session
   - Exempel:
     ```bash
     curl http://localhost:5000/api/tasks \
       -H "X-API-Key: din_api_nyckel"
     ```

### Endpoints

#### Scheman

- `GET /api/schedules`
  - Hämta alla scheman
  - Kräver autentisering

- `POST /api/schedules`
  - Skapa nytt schema
  - Body:
    ```json
    {
      "title": "Aktivitetsnamn",
      "description": "Beskrivning",
      "weekdays": [1, 3, 5],  // 0=Måndag, 6=Söndag
      "start_date": "2024-04-01",
      "end_date": "2024-12-31",
      "active": true
    }
    ```
  - Kräver autentisering

- `PUT /api/schedules/<id>`
  - Uppdatera schema
  - Samma body som POST
  - Kräver autentisering

- `DELETE /api/schedules/<id>`
  - Ta bort schema
  - Kräver autentisering

#### Uppgifter

- `GET /api/tasks`
  - Hämta uppgifter
  - Query-parametrar:
    - `start_date`: Startdatum (YYYY-MM-DD)
    - `end_date`: Slutdatum (YYYY-MM-DD)
  - Kräver autentisering

- `POST /api/tasks/<id>/toggle`
  - Växla uppgiftens status
  - Body:
    ```json
    {
      "status": "completed"  // eller "missed"
    }
    ```
  - Kräver autentisering

- `POST /api/tasks/<id>/reschedule`
  - Flytta uppgift till nytt datum
  - Body:
    ```json
    {
      "new_date": "2024-04-01"
    }
    ```
  - Kräver autentisering

### Exempel på API-anrop

```bash
# Hämta alla scheman med API-nyckel
curl http://localhost:5000/api/schedules \
  -H "X-API-Key: din_api_nyckel"

# Skapa nytt schema med API-nyckel
curl -X POST http://localhost:5000/api/schedules \
  -H "X-API-Key: din_api_nyckel" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Vattna blommor",
    "description": "Vattna alla blommor i vardagsrummet",
    "weekdays": [1, 3, 5],
    "start_date": "2024-04-01",
    "end_date": "2024-12-31",
    "active": true
  }'

# Hämta uppgifter för en period med API-nyckel
curl "http://localhost:5000/api/tasks?start_date=2024-04-01&end_date=2024-04-30" \
  -H "X-API-Key: din_api_nyckel"
```

## Utveckling

### Databas

- Använd PostgreSQL
- Migreringar hanteras med Flask-Migrate
- Kör `flask db migrate` för att skapa nya migreringar
- Kör `flask db upgrade` för att applicera migreringar

### Miljövariabler

- `DATABASE_URL`: PostgreSQL-anslutningssträng
- `SECRET_KEY`: Hemlig nyckel för sessions
- `PASSWORD_HASH`: SHA-256 hash av lösenordet
- `API_KEY`: API-nyckel för externa anrop
- `CALENDAR_TITLE`: Titel som visas i kalendern 