import os
import json
from pathlib import Path

# Đường dẫn file cấu hình
CONFIG_FILE = Path("db_config.json")

class DatabaseConfig:
    """Lớp quản lý cấu hình database với khả năng tự động phát hiện môi trường"""
    
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self):
        """Tải cấu hình từ file hoặc biến môi trường"""
        # Ưu tiên sử dụng biến môi trường
        if os.getenv('DB_HOST'):
            return {
                'host': os.getenv('DB_HOST'),
                'user': os.getenv('DB_USER'),
                'password': os.getenv('DB_PASSWORD'),
                'database': os.getenv('DB_NAME')
            }
        
        # Nếu không có biến môi trường, đọc từ file
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
                
        # Trường hợp không có config
        raise RuntimeError(f"Không tìm thấy file cấu hình: {CONFIG_FILE}")

    @property
    def db_config(self):
        """Trả về cấu hình database dạng dict"""
        return {
            'host': self.config.get('host', 'localhost'),
            'user': self.config.get('user', 'root'),
            'password': self.config.get('password', '123456'),
            'database': self.config.get('database', 'Mymusic')
        }

    @property
    def sqlalchemy_uri(self):
        """Trả về connection string cho SQLAlchemy"""
        config = self.db_config
        return f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}/{config['database']}"

# Khởi tạo cấu hình toàn cục
try:
    DB_CONFIG = DatabaseConfig().db_config
    SQLALCHEMY_DATABASE_URI = DatabaseConfig().sqlalchemy_uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
except RuntimeError as e:
    print(f"⚠️ Cảnh báo: {str(e)}")
    print("👉 Sử dụng giá trị mặc định...")
    
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'root',
        'password': '123456',
        'database': 'Mymusic'
    }
    
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}/{DB_CONFIG['database']}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False