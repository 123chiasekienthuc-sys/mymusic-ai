# config.py
import os
from dotenv import load_dotenv

# Load biến môi trường từ file .env
load_dotenv()

# Cấu hình database ONLINE từ thông tin Railway
DB_CONFIG = {
    'host': 'switchback.proxy.rlwy.net',  # Host từ database_online.txt
    'user': 'root',                          # User từ database_online.txt
    'password': 'PoiVDleqpbtntUyikBlJObQPXnKvrcsd',  # Password từ database_online.txt
    'database': 'railway',                    # Database name từ database_online.txt
    'port': 53475,                            # Port từ database_online.txt
    'charset': 'utf8mb4',
    'use_unicode': True,
    'connect_timeout': 10,                    # Timeout kết nối
    'autocommit': True
}

# Hoặc bạn có thể sử dụng biến môi trường (nếu có)
# DB_CONFIG = {
#     'host': os.getenv('DB_HOST', 'switchback.proxy.rlwy.net'),
#     'user': os.getenv('DB_USER', 'root'),
#     'password': os.getenv('DB_PASSWORD', 'PoiVDleqpbtntUyikBlJObQPXnKvrcsd'),
#     'database': os.getenv('DB_NAME', 'railway'),
#     'port': int(os.getenv('DB_PORT', 53475)),
#     'charset': 'utf8mb4',
#     'use_unicode': True,
#     'connect_timeout': 10,
#     'autocommit': True
# }

# Cấu hình cho connection pool (tối ưu cho production)
DB_POOL_CONFIG = {
    'pool_name': 'mypool',
    'pool_size': 5,
    'pool_reset_session': True
}

# Cấu hình khác
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')
    DEBUG = False
    TESTING = False
    
    # Cấu hình upload
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'mp3', 'wav', 'aac', 'jpg', 'jpeg', 'png', 'gif'}
    
    # Cấu hình session
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Tắt HTTPS cho development

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
# Chọn config dựa trên môi trường
ENV = os.getenv('FLASK_ENV', 'production')
if ENV == 'development':
    config = DevelopmentConfig
else:
    config = ProductionConfig

# Hàm kiểm tra kết nối database
def test_connection():
    """Kiểm tra kết nối database"""
    import mysql.connector
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("✅ Kết nối database ONLINE thành công!")
            conn.close()
            return True
    except Exception as e:
        print(f"❌ Lỗi kết nối database: {e}")
        return False

# Test connection khi import
if __name__ == "__main__":
    test_connection()