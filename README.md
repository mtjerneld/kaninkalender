# Kaninkalendern

En enkel kalenderapp för att hålla koll på återkommande aktiviteter.

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

1. Klona repot:
   ```bash
   git clone https://github.com/mtjerneld/kaninkalender.git
   cd kaninkalender
   ```

2. Installera beroenden:
   ```bash
   pip install -r requirements.txt
   ```

3. Starta applikationen:
   ```bash
   python app.py
   ```

4. Öppna webbläsaren och gå till `http://localhost:5000`

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