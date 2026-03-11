import os

# Lấy thông tin database từ biến môi trường (Railway / Render)
DB_HOST = os.getenv("MYSQLHOST", "localhost")
DB_PORT = int(os.getenv("MYSQLPORT", 3306))
DB_USER = os.getenv("MYSQLUSER", "root")
DB_PASSWORD = os.getenv("MYSQLPASSWORD", "123456")
DB_NAME = os.getenv("MYSQLDATABASE", "Mymusic")

DB_CONFIG = {
    "host": DB_HOST,
    "port": DB_PORT,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_NAME,
    "charset": "utf8mb4"
}

# SQLAlchemy connection string
SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

SQLALCHEMY_TRACK_MODIFICATIONS = False

# API Key AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
