import os

DB_CONFIG = {
    'host': 'localhost',  # tên server
    'user': 'root',  # Khớp với MYSQL_USER trong docker-compose.yml
    'password': '123456',  # Khớp với MYSQL_PASSWORD trong docker-compose.yml
    'database': 'Mymusic'  # Khớp với MYSQL_DATABASE trong docker-compose.yml
}

# Hoặc nếu dùng Flask-SQLAlchemy:
SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
SQLALCHEMY_TRACK_MODIFICATIONS = False
# Cấu hình AI lấy từ .env
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')