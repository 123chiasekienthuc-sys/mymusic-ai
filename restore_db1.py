import os
import pymysql
from pymysql.constants import CLIENT
from pathlib import Path
import getpass
from dotenv import load_dotenv
import sys

# --- CẤU HÌNH --- #
load_dotenv()  # Load biến môi trường từ file .env

BACKUP_PATH = Path("data/mymusic.sql")  # Đường dẫn mặc định
DEFAULT_PASSWORD = "123456"  # Password mặc định

# --- HÀM CHÍNH --- #
def get_db_config():
    """Lấy thông tin kết nối database từ người dùng"""
    print("\n🔧 NHẬP THÔNG TIN DATABASE (ấn Enter để dùng giá trị mặc định)")
    
    config = {
        'host': input("MySQL Host [localhost]: ").strip() or "localhost",
        'user': input("Username [root]: ").strip() or "root",
        'database': input("Tên Database [mymusic]: ").strip() or "mymusic",
        'charset': 'utf8mb4',
        'client_flag': CLIENT.MULTI_STATEMENTS
    }
    
    # Xử lý password với giá trị mặc định
    password = getpass.getpass(f"Password [mặc định: '{DEFAULT_PASSWORD}']: ").strip()
    config['password'] = password or DEFAULT_PASSWORD
    
    return config

def restore_database(config, backup_file):
    """Thực hiện khôi phục database"""
    try:
        print(f"\n🔗 Đang kết nối tới MySQL server tại {config['host']}...")
        
        # Kết nối không chọn database trước
        conn = pymysql.connect(
            host=config['host'],
            user=config['user'],
            password=config['password'],
            charset=config['charset'],
            client_flag=config['client_flag']
        )
        
        with conn.cursor() as cursor:
            # Kiểm tra phiên bản MySQL
            cursor.execute("SELECT VERSION()")
            print(f"⚙️ MySQL Version: {cursor.fetchone()[0]}")
            
            print(f"\n♻️ Đang tạo database '{config['database']}'...")
            cursor.execute(f"DROP DATABASE IF EXISTS `{config['database']}`")
            cursor.execute(f"""
                CREATE DATABASE `{config['database']}` 
                CHARACTER SET utf8mb4 
                COLLATE utf8mb4_unicode_ci
            """)
            
            print(f"📥 Đang import dữ liệu từ {backup_file}...")
            cursor.execute(f"USE `{config['database']}`")
            
            # Đọc và thực thi file SQL
            with open(backup_file, 'r', encoding='utf-8') as f:
                sql = f.read()
                for statement in sql.split(';'):
                    if statement.strip():
                        cursor.execute(statement)
            
            conn.commit()
            print("\n✅ KHÔI PHỤC THÀNH CÔNG!")
            print(f"🔑 Thông tin kết nối:")
            print(f"- Host: {config['host']}")
            print(f"- Database: {config['database']}")
            print(f"- Username: {config['user']}")
            print(f"- Password: {'*' * len(config['password'])}")
            
    except pymysql.Error as e:
        print(f"\n❌ LỖI MySQL ({e.args[0]}): {e.args[1]}")
        if e.args[0] == 1049:  # Database không tồn tại
            print("👉 Gợi ý: Kiểm tra lại tên database hoặc quyền truy cập")
    except FileNotFoundError:
        print(f"\n❌ KHÔNG TÌM THẤY FILE BACKUP: {backup_file}")
        print(f"👉 Đảm bảo file tồn tại trong thư mục 'data'")
    except Exception as e:
        print(f"\n❌ LỖI KHÔNG XÁC ĐỊNH: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

# --- THỰC THI --- #
if __name__ == "__main__":
    print("""
    ================================
    🎵 MYMUSIC DATABASE RESTORE TOOL
    ================================
    """)
    
    # Kiểm tra file backup
    if not BACKUP_PATH.exists():
        print(f"❌ Không tìm thấy file backup tại: {BACKUP_PATH}")
        print(f"👉 Vui lòng đảm bảo:")
        print(f"- File 'mymusic.sql' tồn tại trong thư mục 'data'")
        print(f"- Đường dẫn đúng: {BACKUP_PATH.absolute()}")
        input("\nNhấn Enter để thoát...")
        sys.exit(1)
    
    # Lấy thông tin cấu hình
    db_config = get_db_config()
    
    # Xác nhận
    print(f"\n⚠️ BẠN SẮP KHÔI PHỤC:")
    print(f"- Host: {db_config['host']}")
    print(f"- Database: {db_config['database']}")
    print(f"- Username: {db_config['user']}")
    print(f"- Password: {'*' * len(db_config['password'])}")
    print(f"- Từ file: {BACKUP_PATH}")
    
    if input("\nTiếp tục? (y/N): ").lower() != 'y':
        print("🛑 Đã hủy thao tác!")
        sys.exit(0)
    
    # Thực hiện khôi phục
    restore_database(db_config, BACKUP_PATH)
    input("\nNhấn Enter để thoát...")