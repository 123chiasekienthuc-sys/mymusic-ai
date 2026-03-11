# auto_install.py
import subprocess
import sys

def install_requirements():
    """Tự động cài đặt các thư viện từ requirements.txt"""
    print("🔧 ĐANG CÀI ĐẶT CÁC THƯ VIỆN CẦN THIẾT...")
    print("=" * 50)
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("\n✅ CÀI ĐẶT THÀNH CÔNG!")
        print("🎉 Bạn có thể chạy ứng dụng ngay bây giờ!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ LỖI CÀI ĐẶT: {e}")
        return False

if __name__ == "__main__":
    install_requirements()