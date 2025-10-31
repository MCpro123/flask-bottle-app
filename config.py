import os

POSTGRES_HOST = 'localhost'
POSTGRES_DB = 'water_bottle_db'
POSTGRES_USER = 'swamminhtun'
POSTGRES_PASSWORD = ''
POSTGRES_PORT = 5432  # default Postgres port
SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24))

