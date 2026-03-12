# -*- coding: utf-8 -*-
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_paginate import Pagination, get_page_args
import mysql.connector
from mysql.connector import Error
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
import sys
from pathlib import Path
import pymysql
from pymysql.constants import CLIENT
from dotenv import load_dotenv
import json
import time
from functools import wraps
import random
import uuid
import logging
import argparse

# Load environment variables
load_dotenv()

# =============================
# CẤU HÌNH LOGGING
# =============================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================
# CẤU HÌNH DATABASE TỪ ENV (RAILWAY)
# =============================
DB_CONFIG = {
    'host': os.getenv('MYSQLHOST', 'localhost'),
    'port': int(os.getenv('MYSQLPORT', 3306)),
    'user': os.getenv('MYSQLUSER', 'root'),
    'password': os.getenv('MYSQLPASSWORD', ''),
    'database': os.getenv('MYSQLDATABASE', 'railway'),
    'charset': 'utf8mb4',
    'use_unicode': True,
    'connect_timeout': 10,
    'autocommit': True
}

# =============================
# CẤU HÌNH ĐƯỜNG DẪN
# =============================
if getattr(sys, 'frozen', False):
    base_path = Path(sys.executable).parent
else:
    base_path = Path(__file__).parent.absolute()

static_dir = base_path / 'static'
template_dir = base_path / 'templates'
data_dir = base_path / 'data'

# Tạo thư mục cần thiết
for dir_path in [static_dir, template_dir, data_dir, 
                 static_dir / 'images', 
                 static_dir / 'images/singers', 
                 static_dir / 'images/artists',
                 static_dir / 'recordings']:
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Cannot create {dir_path}: {e}")

# =============================
# KHỞI TẠO FLASK APP
# =============================
app = Flask(__name__, 
            template_folder=str(template_dir),
            static_folder=str(static_dir))

# Cấu hình Flask
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 giờ

# Cấu hình upload
app.config['SINGER_IMAGE_FOLDER'] = str(static_dir / 'images/singers')
app.config['ARTIST_IMAGE_FOLDER'] = str(static_dir / 'images/artists')
app.config['UPLOAD_FOLDER'] = str(static_dir / 'recordings')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB
app.config['MAX_IMAGE_SIZE'] = 5 * 1024 * 1024  # 5MB

# CORS và CSRF
CORS(app)
csrf = CSRFProtect(app)

# =============================
# HÀM TIỆN ÍCH
# =============================

def get_db_connection():
    """Kết nối database với xử lý lỗi"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        logger.error(f"Database connection error: {e}")
        return None

def execute_query(query, params=None, fetch_one=False):
    """Thực thi query an toàn"""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        if not conn:
            return None, "Không thể kết nối database"
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        
        if query.strip().upper().startswith('SELECT'):
            if fetch_one:
                result = cursor.fetchone()
            else:
                result = cursor.fetchall()
        else:
            conn.commit()
            result = {"affected_rows": cursor.rowcount}
        
        return result, None
    except Error as e:
        logger.error(f"Query error: {e}")
        return None, str(e)
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

def allowed_file(filename):
    """Kiểm tra file âm thanh hợp lệ"""
    ALLOWED_EXTENSIONS = {'mp3', 'wav', 'aac', 'm4a'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_image(filename):
    """Kiểm tra file ảnh hợp lệ"""
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

# Rate limiting
request_history = {}

def rate_limit(max_requests=60, time_window=60):
    """Giới hạn số request"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            
            if client_ip not in request_history:
                request_history[client_ip] = []
            
            request_history[client_ip] = [
                req_time for req_time in request_history[client_ip]
                if current_time - req_time < time_window
            ]
            
            if len(request_history[client_ip]) >= max_requests:
                return jsonify({
                    "status": "error",
                    "message": f"Quá {max_requests} request trong {time_window} giây"
                }), 429
            
            request_history[client_ip].append(current_time)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================
# GOOGLE AI 
# =============================
try:
    from google import genai
    from google.genai import types
    gemini_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
    logger.info("✅ Đã khởi tạo Gemini AI (phiên bản mới)")
    GEMINI_AVAILABLE = True
except (ImportError, AttributeError) as e:
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
        gemini_client = genai.GenerativeModel('gemini-1.5-flash')
        logger.info("✅ Đã khởi tạo Gemini AI (phiên bản cũ)")
        GEMINI_AVAILABLE = True
    except ImportError:
        logger.warning("⚠️ Không thể khởi tạo Google AI. Tiếp tục chạy ở chế độ offline.")
        gemini_client = None
        GEMINI_AVAILABLE = False

# =============================
# AI ASSISTANT 
# =============================
try:
    from ai_assistant import sql_assistant
except ImportError:
    class SQLAssistant:
        def __init__(self):
            self.sample_exercises = {
                '1': {
                    'title': 'Tìm tất cả bản nhạc',
                    'description': 'Viết câu lệnh SQL để lấy tất cả bản nhạc',
                    'solution': 'SELECT * FROM bannhac',
                    'hint': 'Sử dụng SELECT * FROM'
                },
                '2': {
                    'title': 'Đếm số ca sĩ',
                    'description': 'Đếm tổng số ca sĩ',
                    'solution': 'SELECT COUNT(*) FROM casi',
                    'hint': 'Dùng COUNT(*)'
                }
            }
        
        def evaluate_sql(self, sql_query, exercise_id):
            return {
                'status': 'success',
                'score': 10,
                'feedback': 'Câu lệnh SQL hợp lệ',
                'message': 'Đã đánh giá'
            }
        
        def execute_sql_safe(self, sql_query):
            result, error = execute_query(sql_query)
            if error:
                return {'success': False, 'error': error}
            return {'success': True, 'data': result, 'count': len(result) if result else 0}
        
        def chat_response(self, message, context):
            if not GEMINI_AVAILABLE:
                return "Xin lỗi, AI hiện không khả dụng. Vui lòng thử lại sau."
            try:
                prompt = f"Bạn là trợ lý SQL chuyên về database nhạc sĩ, ca sĩ, bản nhạc, bản thu âm.\n"
                prompt += f"Ngữ cảnh hiện tại: {context}\n"
                prompt += f"Câu hỏi của người dùng: {message}\n"
                prompt += "Hãy trả lời bằng tiếng Việt, thân thiện và hữu ích."
                
                response = gemini_client.generate_content(prompt)
                return response.text
            except Exception as e:
                logger.error(f"Gemini error: {e}")
                return f"Có lỗi xảy ra: {str(e)}"
        
        def generate_exercise(self, topic):
            if not GEMINI_AVAILABLE:
                return {
                    'title': f'Bài tập về {topic}',
                    'description': f'Thực hành SQL chủ đề {topic}',
                    'solution': 'SELECT * FROM bannhac',
                    'hint': 'Thử nghiệm với SELECT'
                }
            try:
                prompt = f"Hãy tạo một bài tập SQL ngắn về chủ đề '{topic}' cho database nhạc sĩ, ca sĩ. "
                prompt += "Trả về JSON với các trường: title, description, solution, hint"
                response = gemini_client.generate_content(prompt)
                return json.loads(response.text)
            except:
                return {
                    'title': f'Bài tập về {topic}',
                    'description': f'Thực hành SQL chủ đề {topic}',
                    'solution': 'SELECT * FROM bannhac',
                    'hint': 'Thử nghiệm với SELECT'
                }
    
    sql_assistant = SQLAssistant()
    logger.info("Using fallback SQL Assistant")

# =============================
# CONTEXT PROCESSOR
# =============================
@app.context_processor
def utility_processor():
    return {
        'now': datetime.now,
        'csrf_token': lambda: request.form.get('csrf_token') if request.method == 'POST' else ''
    }

# =============================
# ROUTES - TRANG CHÍNH
# =============================

@app.route('/')
def index():
    """Trang chủ"""
    # Lấy danh sách nhạc sĩ mới nhất
    latest_nhacsi, _ = execute_query("""
        SELECT idnhacsi, tennhacsi, tieusu, 
               DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them 
        FROM nhacsi 
        ORDER BY created_at DESC 
        LIMIT 5
    """)
    
    return render_template('index.html', latest_nhacsi=latest_nhacsi or [])

@app.route('/health')
def health():
    """Health check cho Railway"""
    conn = get_db_connection()
    db_status = 'connected' if conn and conn.is_connected() else 'disconnected'
    if conn:
        conn.close()
    
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'database': db_status,
        'environment': os.getenv('FLASK_ENV', 'production')
    })

# =============================
# ROUTES - NHẠC SĨ
# =============================

@app.route('/nhacsi')
def nhacsi_list():
    """Danh sách nhạc sĩ"""
    result, error = execute_query("SELECT * FROM nhacsi ORDER BY tennhacsi")
    if error:
        flash(f'Lỗi: {error}', 'danger')
        return render_template('nhacsi/nhacsi_list.html', nhacsi_list=[])
    
    return render_template('nhacsi/nhacsi_list.html', nhacsi_list=result or [])

@app.route('/nhacsi/<int:id>')
def nhacsi_detail(id):
    """Chi tiết nhạc sĩ"""
    return render_template('nhacsi/nhacsi_detail.html', idnhacsi=id)

@app.route('/nhacsi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_nhacsi():
    """Thêm nhạc sĩ mới"""
    if request.method == 'GET':
        return render_template('nhacsi/nhacsi_add.html')
    
    try:
        tennhacsi = request.form.get('tennhacsi', '').strip()
        if not tennhacsi:
            flash('Tên nhạc sĩ không được để trống', 'danger')
            return redirect(url_for('add_nhacsi'))
        
        avatar_path = None
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ', 'danger')
                    return redirect(url_for('add_nhacsi'))
                
                filename = secure_filename(f"ns_{int(time.time())}_{file.filename}")
                save_path = os.path.join(app.config['ARTIST_IMAGE_FOLDER'], filename)
                file.save(save_path)
                avatar_path = f"images/artists/{filename}"
        
        query = """
            INSERT INTO nhacsi (tennhacsi, ngaysinh, gioitinh, quequan, tieusu, avatar)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            tennhacsi,
            request.form.get('ngaysinh'),
            request.form.get('gioitinh'),
            request.form.get('quequan'),
            request.form.get('tieusu'),
            avatar_path
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm nhạc sĩ thành công!', 'success')
        
        return redirect(url_for('nhacsi_list'))
        
    except Exception as e:
        logger.error(f"Error adding nhacsi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_nhacsi'))

@app.route('/nhacsi/edit/<int:idnhacsi>', methods=['GET', 'POST'])
@csrf.exempt
def edit_nhacsi(idnhacsi):
    """Chỉnh sửa nhạc sĩ"""
    if request.method == 'GET':
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'danger')
            return redirect(url_for('nhacsi_list'))
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM nhacsi WHERE idnhacsi = %s", (idnhacsi,))
        nhacsi = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not nhacsi:
            flash('Không tìm thấy nhạc sĩ', 'danger')
            return redirect(url_for('nhacsi_list'))
        
        return render_template('nhacsi/nhacsi_edit.html', nhacsi=nhacsi)
    
    # POST request
    try:
        tennhacsi = request.form.get('tennhacsi', '').strip()
        if not tennhacsi:
            flash('Tên nhạc sĩ không được để trống', 'danger')
            return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))
        
        query = """
            UPDATE nhacsi 
            SET tennhacsi = %s, ngaysinh = %s, gioitinh = %s, 
                quequan = %s, tieusu = %s
            WHERE idnhacsi = %s
        """
        params = (
            tennhacsi,
            request.form.get('ngaysinh'),
            request.form.get('gioitinh'),
            request.form.get('quequan'),
            request.form.get('tieusu'),
            idnhacsi
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Cập nhật nhạc sĩ thành công!', 'success')
        
        return redirect(url_for('nhacsi_detail', id=idnhacsi))
        
    except Exception as e:
        logger.error(f"Error editing nhacsi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_nhacsi', idnhacsi=idnhacsi))

# =============================
# ROUTES - CA SĨ
# =============================

@app.route('/casi')
def casi_list():
    """Danh sách ca sĩ"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    filter_by = request.args.get('filter', 'all')
    
    # Query cơ bản
    query = """
        SELECT c.*, COUNT(b.idbanthuam) as soluong_banthuam
        FROM casi c
        LEFT JOIN banthuam b ON c.idcasi = b.idcasi
    """
    
    # Thêm điều kiện lọc
    if filter_by == 'has_records':
        query += " WHERE b.idbanthuam IS NOT NULL"
    
    query += " GROUP BY c.idcasi ORDER BY c.tencasi"
    
    # Đếm tổng số
    count_result, _ = execute_query("SELECT COUNT(*) as total FROM casi", fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    # Lấy dữ liệu phân trang
    offset = (page - 1) * per_page
    paginated_query = query + f" LIMIT {per_page} OFFSET {offset}"
    result, error = execute_query(paginated_query)
    
    if error:
        flash(f'Lỗi: {error}', 'danger')
        return render_template('casi/casi_list.html', casi_list=[], page=page, total_pages=1, filter_by=filter_by)
    
    return render_template('casi/casi_list.html',
                         casi_list=result or [],
                         page=page,
                         total_pages=total_pages,
                         filter_by=filter_by,
                         per_page=per_page)

@app.route('/casi/<int:id>')
def casi_detail(id):
    """Chi tiết ca sĩ"""
    conn = get_db_connection()
    if not conn:
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT idcasi, tencasi, Ngaysinh as ngaysinh, 
                   Sunghiep as sunghiep, anhdaidien,
                   DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them
            FROM casi WHERE idcasi = %s
        """, (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return render_template('404.html'), 404
        
        cursor.execute("""
            SELECT ba.*, bn.tenbannhac, ns.tennhacsi,
                   DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
            FROM banthuam ba
            JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE ba.idcasi = %s
            ORDER BY ba.created_at DESC
        """, (id,))
        banthuam = cursor.fetchall()
        
        return render_template('casi/casi_detail.html',
                             casi=casi,
                             banthuam=banthuam)
    except Exception as e:
        logger.error(f"Error in casi_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/casi/add', methods=['GET', 'POST'])
@csrf.exempt
def add_casi():
    """Thêm ca sĩ mới"""
    if request.method == 'GET':
        return render_template('casi/casi_add.html')
    
    try:
        tencasi = request.form.get('tencasi', '').strip()
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('add_casi'))
        
        anhdaidien = None
        if 'anhdaidien' in request.files:
            file = request.files['anhdaidien']
            if file and file.filename:
                if not allowed_image(file.filename):
                    flash('Định dạng ảnh không hợp lệ', 'danger')
                    return redirect(url_for('add_casi'))
                
                filename = secure_filename(f"cs_{int(time.time())}_{file.filename}")
                save_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], filename)
                file.save(save_path)
                anhdaidien = filename
        
        query = """
            INSERT INTO casi (tencasi, Ngaysinh, Sunghiep, anhdaidien)
            VALUES (%s, %s, %s, %s)
        """
        params = (
            tencasi,
            request.form.get('ngaysinh'),
            request.form.get('sunghiep'),
            anhdaidien
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm ca sĩ thành công!', 'success')
        
        return redirect(url_for('casi_list'))
        
    except Exception as e:
        logger.error(f"Error adding casi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_casi'))

@app.route('/casi/edit/<int:idcasi>', methods=['GET', 'POST'])
@csrf.exempt
def edit_casi(idcasi):
    """Chỉnh sửa ca sĩ"""
    if request.method == 'GET':
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'danger')
            return redirect(url_for('casi_list'))
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT idcasi, tencasi, Ngaysinh as ngaysinh, 
                   Sunghiep as sunghiep, anhdaidien
            FROM casi WHERE idcasi = %s
        """, (idcasi,))
        casi = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not casi:
            flash('Không tìm thấy ca sĩ', 'danger')
            return redirect(url_for('casi_list'))
        
        return render_template('casi/casi_edit.html', casi=casi)
    
    # POST request
    try:
        tencasi = request.form.get('tencasi', '').strip()
        if not tencasi:
            flash('Tên ca sĩ không được để trống', 'danger')
            return redirect(url_for('edit_casi', idcasi=idcasi))
        
        query = """
            UPDATE casi 
            SET tencasi = %s, Ngaysinh = %s, Sunghiep = %s
            WHERE idcasi = %s
        """
        params = (
            tencasi,
            request.form.get('ngaysinh'),
            request.form.get('sunghiep'),
            idcasi
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Cập nhật ca sĩ thành công!', 'success')
        
        return redirect(url_for('casi_detail', id=idcasi))
        
    except Exception as e:
        logger.error(f"Error editing casi: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_casi', idcasi=idcasi))

@app.route('/api/casi/<int:id>', methods=['DELETE'])
@csrf.exempt
def delete_casi(id):
    """Xóa ca sĩ"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Lỗi kết nối database"}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Kiểm tra ca sĩ tồn tại
        cursor.execute("SELECT * FROM casi WHERE idcasi = %s", (id,))
        casi = cursor.fetchone()
        
        if not casi:
            return jsonify({"success": False, "message": "Ca sĩ không tồn tại"}), 404
        
        # Kiểm tra bản thu âm
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idcasi = %s", (id,))
        count = cursor.fetchone()['count']
        
        if count > 0:
            return jsonify({"success": False, "message": "Không thể xóa ca sĩ đã có bản thu âm"}), 400
        
        # Xóa ảnh nếu có
        if casi['anhdaidien']:
            file_path = os.path.join(app.config['SINGER_IMAGE_FOLDER'], casi['anhdaidien'])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Xóa ca sĩ
        cursor.execute("DELETE FROM casi WHERE idcasi = %s", (id,))
        conn.commit()
        
        return jsonify({"success": True, "message": "Xóa ca sĩ thành công"})
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting casi: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# =============================
# ROUTES - BẢN NHẠC
# =============================

@app.route('/bannhac')
def bannhac_list():
    """Danh sách bản nhạc"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    nhacsi_id = request.args.get('nhacsi', None)
    sort_by = request.args.get('sort', 'newest')
    
    # Query cơ bản
    query = """
        SELECT b.*, n.tennhacsi, COUNT(ba.idbanthuam) as soluong_banthuam,
               DATE_FORMAT(b.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        LEFT JOIN banthuam ba ON b.idbannhac = ba.idbannhac
    """
    
    conditions = []
    params = []
    
    if nhacsi_id:
        conditions.append("b.idnhacsi = %s")
        params.append(nhacsi_id)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " GROUP BY b.idbannhac"
    
    # Sắp xếp
    if sort_by == 'newest':
        query += " ORDER BY b.created_at DESC"
    elif sort_by == 'oldest':
        query += " ORDER BY b.created_at ASC"
    elif sort_by == 'name_asc':
        query += " ORDER BY b.tenbannhac ASC"
    elif sort_by == 'name_desc':
        query += " ORDER BY b.tenbannhac DESC"
    elif sort_by == 'popular':
        query += " ORDER BY soluong_banthuam DESC"
    
    # Đếm tổng số
    count_query = "SELECT COUNT(*) as total FROM bannhac"
    if conditions:
        count_query += " WHERE " + " AND ".join(conditions)
    
    count_result, _ = execute_query(count_query, params if conditions else None, fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    # Lấy dữ liệu phân trang
    offset = (page - 1) * per_page
    paginated_query = query + f" LIMIT {per_page} OFFSET {offset}"
    result, error = execute_query(paginated_query, params if conditions else None)
    
    # Lấy danh sách nhạc sĩ cho filter
    composers, _ = execute_query("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
    
    if error:
        flash(f'Lỗi: {error}', 'danger')
        return render_template('bannhac/bannhac_list.html', 
                             bannhac_list=[], nhacsi_list=composers or [],
                             page=page, total_pages=1, nhacsi_id=nhacsi_id, sort_by=sort_by)
    
    return render_template('bannhac/bannhac_list.html',
                         bannhac_list=result or [],
                         nhacsi_list=composers or [],
                         page=page,
                         total_pages=total_pages,
                         per_page=per_page,
                         nhacsi_id=nhacsi_id,
                         sort_by=sort_by)

@app.route('/bannhac/<int:id>')
def bannhac_detail(id):
    """Chi tiết bản nhạc"""
    conn = get_db_connection()
    if not conn:
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT b.*, n.tennhacsi,
                   DATE_FORMAT(b.created_at, '%d/%m/%Y') as ngay_them
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            WHERE b.idbannhac = %s
        """, (id,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            return render_template('404.html'), 404
        
        cursor.execute("""
            SELECT ba.*, c.tencasi,
                   DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
            FROM banthuam ba
            JOIN casi c ON ba.idcasi = c.idcasi
            WHERE ba.idbannhac = %s
            ORDER BY ba.created_at DESC
        """, (id,))
        banthuam = cursor.fetchall()
        
        return render_template('bannhac/bannhac_detail.html',
                             bannhac=bannhac,
                             banthuam=banthuam)
    except Exception as e:
        logger.error(f"Error in bannhac_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/bannhac/add', methods=['GET', 'POST'])
@csrf.exempt
def add_bannhac():
    """Thêm bản nhạc mới"""
    if request.method == 'GET':
        # Lấy danh sách nhạc sĩ cho dropdown
        nhacsi_list, _ = execute_query("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        return render_template('bannhac/bannhac_add.html', nhacsi_list=nhacsi_list or [])
    
    try:
        tenbannhac = request.form.get('tenbannhac', '').strip()
        if not tenbannhac:
            flash('Tên bài hát không được để trống', 'danger')
            return redirect(url_for('add_bannhac'))
        
        idnhacsi = request.form.get('idnhacsi')
        if not idnhacsi:
            flash('Vui lòng chọn nhạc sĩ', 'danger')
            return redirect(url_for('add_bannhac'))
        
        query = """
            INSERT INTO bannhac (tenbannhac, theloai, idnhacsi)
            VALUES (%s, %s, %s)
        """
        params = (
            tenbannhac,
            request.form.get('theloai', ''),
            idnhacsi
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm bài hát thành công!', 'success')
        
        return redirect(url_for('bannhac_list'))
        
    except Exception as e:
        logger.error(f"Error adding bannhac: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_bannhac'))

@app.route('/bannhac/edit/<int:idbannhac>', methods=['GET', 'POST'])
@csrf.exempt
def edit_bannhac(idbannhac):
    """Chỉnh sửa bản nhạc"""
    if request.method == 'GET':
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'danger')
            return redirect(url_for('bannhac_list'))
        
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT b.*, n.tennhacsi
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            WHERE b.idbannhac = %s
        """, (idbannhac,))
        bannhac = cursor.fetchone()
        
        # Lấy danh sách nhạc sĩ cho dropdown
        cursor.execute("SELECT idnhacsi, tennhacsi FROM nhacsi ORDER BY tennhacsi")
        nhacsi_list = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not bannhac:
            flash('Không tìm thấy bài hát', 'danger')
            return redirect(url_for('bannhac_list'))
        
        return render_template('bannhac/bannhac_edit.html', 
                             bannhac=bannhac,
                             nhacsi_list=nhacsi_list)
    
    # POST request
    try:
        tenbannhac = request.form.get('tenbannhac', '').strip()
        if not tenbannhac:
            flash('Tên bài hát không được để trống', 'danger')
            return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
        
        idnhacsi = request.form.get('idnhacsi')
        if not idnhacsi:
            flash('Vui lòng chọn nhạc sĩ', 'danger')
            return redirect(url_for('edit_bannhac', idbannhac=idbannhac))
        
        query = """
            UPDATE bannhac 
            SET tenbannhac = %s, theloai = %s, idnhacsi = %s
            WHERE idbannhac = %s
        """
        params = (
            tenbannhac,
            request.form.get('theloai', ''),
            idnhacsi,
            idbannhac
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Cập nhật bài hát thành công!', 'success')
        
        return redirect(url_for('bannhac_detail', id=idbannhac))
        
    except Exception as e:
        logger.error(f"Error editing bannhac: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_bannhac', idbannhac=idbannhac))

@app.route('/api/bannhac/<int:id>', methods=['DELETE'])
@csrf.exempt
def delete_bannhac_api(id):
    """Xóa bản nhạc"""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Lỗi kết nối database"}), 500
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Kiểm tra bản nhạc tồn tại
        cursor.execute("SELECT * FROM bannhac WHERE idbannhac = %s", (id,))
        bannhac = cursor.fetchone()
        
        if not bannhac:
            return jsonify({"success": False, "message": "Bài hát không tồn tại"}), 404
        
        # Kiểm tra bản thu âm
        cursor.execute("SELECT COUNT(*) as count FROM banthuam WHERE idbannhac = %s", (id,))
        count = cursor.fetchone()['count']
        
        if count > 0:
            return jsonify({"success": False, "message": "Không thể xóa bài hát đã có bản thu âm"}), 400
        
        # Xóa bài hát
        cursor.execute("DELETE FROM bannhac WHERE idbannhac = %s", (id,))
        conn.commit()
        
        return jsonify({"success": True, "message": "Xóa bài hát thành công"})
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting bannhac: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# =============================
# ROUTES - BẢN THU ÂM
# =============================

@app.route('/banthuam')
def banthuam_list():
    """Danh sách bản thu âm"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search_query = request.args.get('q', '').strip()
    artist_id = request.args.get('artist', '')
    sort_option = request.args.get('sort', 'newest')
    
    # Query cơ bản
    query = """
        SELECT ba.*, bn.tenbannhac, c.tencasi, ns.tennhacsi,
               DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
        FROM banthuam ba
        JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
        JOIN casi c ON ba.idcasi = c.idcasi
        JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
        WHERE 1=1
    """
    
    params = []
    
    if search_query:
        query += " AND (bn.tenbannhac LIKE %s OR c.tencasi LIKE %s OR ns.tennhacsi LIKE %s)"
        search_pattern = f"%{search_query}%"
        params.extend([search_pattern, search_pattern, search_pattern])
    
    if artist_id:
        query += " AND ba.idcasi = %s"
        params.append(artist_id)
    
    # Sắp xếp
    if sort_option == 'newest':
        query += " ORDER BY ba.created_at DESC"
    elif sort_option == 'oldest':
        query += " ORDER BY ba.created_at ASC"
    elif sort_option == 'name_asc':
        query += " ORDER BY bn.tenbannhac ASC"
    elif sort_option == 'name_desc':
        query += " ORDER BY bn.tenbannhac DESC"
    
    # Đếm tổng số
    count_query = "SELECT COUNT(*) as total FROM (" + query + ") as subquery"
    count_result, _ = execute_query(count_query, params if params else None, fetch_one=True)
    total = count_result['total'] if count_result else 0
    total_pages = (total + per_page - 1) // per_page
    
    # Lấy dữ liệu phân trang
    offset = (page - 1) * per_page
    paginated_query = query + " LIMIT %s OFFSET %s"
    paginated_params = params + [per_page, offset] if params else [per_page, offset]
    
    result, error = execute_query(paginated_query, paginated_params)
    
    # Lấy danh sách ca sĩ cho filter
    artists, _ = execute_query("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
    
    if error:
        flash(f'Lỗi: {error}', 'danger')
        return render_template('banthuam/banthuam_list.html', 
                             banthuam_list=[], artists=artists or [],
                             page=page, total_pages=1, search_query=search_query)
    
    return render_template('banthuam/banthuam_list.html',
                         banthuam_list=result or [],
                         artists=artists or [],
                         page=page,
                         per_page=per_page,
                         total_pages=total_pages,
                         search_query=search_query)

@app.route('/banthuam/detail/<int:recording_id>')
def recording_detail(recording_id):
    """Chi tiết bản thu âm"""
    conn = get_db_connection()
    if not conn:
        return render_template('404.html'), 404
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("""
            SELECT ba.*, bn.tenbannhac, c.tencasi, ns.tennhacsi,
                   DATE_FORMAT(ba.ngaythuam, '%d/%m/%Y') as ngaythu,
                   DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
            FROM banthuam ba
            JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
            JOIN casi c ON ba.idcasi = c.idcasi
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE ba.idbanthuam = %s
        """, (recording_id,))
        recording = cursor.fetchone()
        
        if not recording:
            return render_template('404.html'), 404
        
        # Lấy bản thu liên quan
        cursor.execute("""
            SELECT ba.idbanthuam, c.tencasi, 
                   DATE_FORMAT(ba.ngaythuam, '%d/%m/%Y') as ngaythu,
                   ba.thoiluong
            FROM banthuam ba
            JOIN casi c ON ba.idcasi = c.idcasi
            WHERE ba.idbannhac = %s AND ba.idbanthuam != %s
            ORDER BY ba.created_at DESC
            LIMIT 5
        """, (recording['idbannhac'], recording_id))
        related = cursor.fetchall()
        
        return render_template('banthuam/banthuam_detail.html',
                             recording=recording,
                             related_recordings=related)
    except Exception as e:
        logger.error(f"Error in recording_detail: {e}")
        return render_template('500.html'), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/banthuam/add', methods=['GET', 'POST'])
@csrf.exempt
def add_banthuam():
    """Thêm bản thu âm mới"""
    if request.method == 'GET':
        # Lấy danh sách bài hát
        songs, _ = execute_query("""
            SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            ORDER BY b.tenbannhac
        """)
        
        # Lấy danh sách ca sĩ
        artists, _ = execute_query("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
        
        return render_template('banthuam/banthuam_add.html', 
                             songs=songs or [],
                             artists=artists or [])
    
    try:
        idbannhac = request.form.get('idbannhac')
        idcasi = request.form.get('idcasi')
        
        if not idbannhac or not idcasi:
            flash('Vui lòng chọn bài hát và ca sĩ', 'danger')
            return redirect(url_for('add_banthuam'))
        
        # Xử lý file upload
        file_path = None
        if 'audio_file' in request.files:
            file = request.files['audio_file']
            if file and file.filename:
                if not allowed_file(file.filename):
                    flash('Định dạng file không hợp lệ', 'danger')
                    return redirect(url_for('add_banthuam'))
                
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = secure_filename(f"recording_{int(time.time())}.{ext}")
                save_path = os.path.join('static/recordings', filename)
                file.save(save_path)
                file_path = filename
        
        if not file_path:
            flash('Vui lòng chọn file âm thanh', 'danger')
            return redirect(url_for('add_banthuam'))
        
        query = """
            INSERT INTO banthuam (idbannhac, idcasi, ngaythuam, thoiluong, lyrics, ghichu, file_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            idbannhac,
            idcasi,
            request.form.get('ngaythuam'),
            request.form.get('thoiluong'),
            request.form.get('lyrics', ''),
            request.form.get('ghichu', ''),
            file_path
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Thêm bản thu âm thành công!', 'success')
        
        return redirect(url_for('banthuam_list'))
        
    except Exception as e:
        logger.error(f"Error adding banthuam: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('add_banthuam'))

@app.route('/banthuam/edit/<int:idbanthuam>', methods=['GET', 'POST'])
@csrf.exempt
def edit_banthuam(idbanthuam):
    """Chỉnh sửa bản thu âm"""
    if request.method == 'GET':
        conn = get_db_connection()
        if not conn:
            flash('Lỗi kết nối database', 'danger')
            return redirect(url_for('banthuam_list'))
        
        cursor = conn.cursor(dictionary=True)
        
        # Lấy thông tin bản thu âm
        cursor.execute("""
            SELECT ba.*, bn.tenbannhac, c.tencasi, ns.tennhacsi
            FROM banthuam ba
            JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
            JOIN casi c ON ba.idcasi = c.idcasi
            JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
            WHERE ba.idbanthuam = %s
        """, (idbanthuam,))
        banthuam = cursor.fetchone()
        
        if not banthuam:
            cursor.close()
            conn.close()
            flash('Không tìm thấy bản thu âm', 'danger')
            return redirect(url_for('banthuam_list'))
        
        # Lấy danh sách bài hát và ca sĩ cho dropdown
        cursor.execute("""
            SELECT b.idbannhac, b.tenbannhac, n.tennhacsi 
            FROM bannhac b
            JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
            ORDER BY b.tenbannhac
        """)
        songs = cursor.fetchall()
        
        cursor.execute("SELECT idcasi, tencasi FROM casi ORDER BY tencasi")
        artists = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return render_template('banthuam/banthuam_edit.html',
                             banthuam=banthuam,
                             songs=songs,
                             artists=artists)
    
    # POST request
    try:
        idbannhac = request.form.get('idbannhac')
        idcasi = request.form.get('idcasi')
        
        if not idbannhac or not idcasi:
            flash('Vui lòng chọn bài hát và ca sĩ', 'danger')
            return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))
        
        query = """
            UPDATE banthuam 
            SET idbannhac = %s, idcasi = %s, ngaythuam = %s, 
                thoiluong = %s, lyrics = %s, ghichu = %s
            WHERE idbanthuam = %s
        """
        params = (
            idbannhac,
            idcasi,
            request.form.get('ngaythuam'),
            request.form.get('thoiluong'),
            request.form.get('lyrics', ''),
            request.form.get('ghichu', ''),
            idbanthuam
        )
        
        _, error = execute_query(query, params)
        if error:
            flash(f'Lỗi: {error}', 'danger')
        else:
            flash('Cập nhật bản thu âm thành công!', 'success')
        
        return redirect(url_for('recording_detail', recording_id=idbanthuam))
        
    except Exception as e:
        logger.error(f"Error editing banthuam: {e}")
        flash(f'Lỗi: {str(e)}', 'danger')
        return redirect(url_for('edit_banthuam', idbanthuam=idbanthuam))

@app.route('/banthuam/delete/<int:recording_id>', methods=['POST'])
@csrf.exempt
def delete_recording(recording_id):
    """Xóa bản thu âm"""
    conn = get_db_connection()
    if not conn:
        flash('Lỗi kết nối database', 'danger')
        return redirect(url_for('banthuam_list'))
    
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Lấy thông tin file để xóa
        cursor.execute("SELECT file_path FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        recording = cursor.fetchone()
        
        if recording and recording['file_path']:
            file_path = os.path.join('static/recordings', recording['file_path'])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Xóa khỏi database
        cursor.execute("DELETE FROM banthuam WHERE idbanthuam = %s", (recording_id,))
        conn.commit()
        
        flash('Xóa bản thu âm thành công!', 'success')
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error deleting recording: {e}")
        flash(f'Lỗi khi xóa: {str(e)}', 'danger')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('banthuam_list'))

# =============================
# API ROUTES
# =============================

@app.route('/api/stats')
def get_stats():
    """Thống kê database"""
    queries = {
        'nhacsi': "SELECT COUNT(*) as count FROM nhacsi",
        'casi': "SELECT COUNT(*) as count FROM casi",
        'bannhac': "SELECT COUNT(*) as count FROM bannhac",
        'banthuam': "SELECT COUNT(*) as count FROM banthuam"
    }
    
    stats = {}
    for key, query in queries.items():
        result, error = execute_query(query, fetch_one=True)
        if error:
            return jsonify({'error': error}), 500
        stats[key] = result['count'] if result else 0
    
    return jsonify(stats)

@app.route('/api/nhacsi')
def api_nhacsi():
    """API lấy danh sách nhạc sĩ"""
    result, error = execute_query("SELECT * FROM nhacsi ORDER BY tennhacsi")
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/nhacsi/latest')
def api_nhacsi_latest():
    """API lấy nhạc sĩ mới nhất"""
    result, error = execute_query("""
        SELECT idnhacsi, tennhacsi, tieusu,
               DATE_FORMAT(created_at, '%d/%m/%Y') as ngay_them
        FROM nhacsi
        ORDER BY created_at DESC
        LIMIT 5
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/casi')
def api_casi():
    """API lấy danh sách ca sĩ"""
    result, error = execute_query("SELECT * FROM casi ORDER BY tencasi")
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/casi/latest')
def api_casi_latest():
    """API lấy ca sĩ mới nhất"""
    result, error = execute_query("""
        SELECT idcasi, tencasi, Ngaysinh as ngaysinh, Sunghiep as sunghiep,
               DATE_FORMAT(created_at, '%%d/%%m/%%Y') as ngay_them
        FROM casi
        ORDER BY created_at DESC
        LIMIT 5
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/bannhac')
def api_bannhac():
    """API lấy danh sách bản nhạc"""
    result, error = execute_query("""
        SELECT b.*, n.tennhacsi
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        ORDER BY b.created_at DESC
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/bannhac/noibat')
def api_bannhac_noibat():
    """API lấy bản nhạc nổi bật"""
    result, error = execute_query("""
        SELECT b.idbannhac, b.tenbannhac, n.tennhacsi,
               COUNT(ba.idbanthuam) as soluong_banthuam,
               DATE_FORMAT(b.created_at, '%d/%m/%Y') as ngay_them
        FROM bannhac b
        JOIN nhacsi n ON b.idnhacsi = n.idnhacsi
        LEFT JOIN banthuam ba ON b.idbannhac = ba.idbannhac
        GROUP BY b.idbannhac
        ORDER BY soluong_banthuam DESC
        LIMIT 4
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/banthuam/noibat')
def api_banthuam_noibat():
    """API lấy bản thu âm nổi bật"""
    result, error = execute_query("""
        SELECT ba.idbanthuam, ba.ngaythuam, bn.tenbannhac, c.tencasi,
               DATE_FORMAT(ba.created_at, '%d/%m/%Y') as ngay_them
        FROM banthuam ba
        JOIN bannhac bn ON ba.idbannhac = bn.idbannhac
        JOIN casi c ON ba.idcasi = c.idcasi
        ORDER BY ba.created_at DESC
        LIMIT 6
    """)
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

@app.route('/api/banthuam', methods=['GET'])
def get_recordings():
    """API lấy danh sách bản thu âm"""
    song_id = request.args.get('bannhac')
    
    if song_id:
        query = """
            SELECT bt.idbanthuam, bt.ngaythuam, cs.tencasi
            FROM banthuam bt
            JOIN casi cs ON bt.idcasi = cs.idcasi
            WHERE bt.idbannhac = %s
            ORDER BY bt.created_at DESC
        """
        result, error = execute_query(query, (song_id,))
    else:
        result, error = execute_query("SELECT * FROM banthuam ORDER BY created_at DESC LIMIT 50")
    
    if error:
        return jsonify({'error': error}), 500
    return jsonify(result or [])

# =============================
# ROUTES - AI FEATURES
# =============================

@app.route('/thuc-hanh-ai', methods=['GET', 'POST'])
@csrf.exempt
def thuc_hanh_ai():
    """Trang thực hành AI"""
    if request.method == 'GET':
        return render_template('thuc_hanh_ai.html')
    
    try:
        data = request.get_json() if request.is_json else request.form.to_dict()
        if not data:
            return jsonify({'status': 'error', 'message': 'Không có dữ liệu'}), 400
        
        action = data.get('action', 'evaluate')
        sql_query = data.get('sql_query', '').strip()
        
        if not sql_query:
            return jsonify({'status': 'error', 'message': 'Vui lòng nhập SQL'}), 400
        
        if action == 'evaluate':
            result = sql_assistant.evaluate_sql(sql_query, data.get('exercise_id', '1'))
            return jsonify(result)
        elif action == 'execute':
            result = sql_assistant.execute_sql_safe(sql_query)
            return jsonify(result)
        
        return jsonify({'status': 'error', 'message': 'Action không hợp lệ'}), 400
        
    except Exception as e:
        logger.error(f"Error in thuc_hanh_ai: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ai-chat', methods=['POST'])
@csrf.exempt
def ai_chat_api():
    """API chat với AI"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Không có dữ liệu'}), 400
        
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'success': False, 'error': 'Vui lòng nhập câu hỏi'}), 400
        
        response = sql_assistant.chat_response(message, data.get('context', ''))
        return jsonify({'success': True, 'response': response})
        
    except Exception as e:
        logger.error(f"Error in ai_chat_api: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/generate-exercise', methods=['POST'])
@csrf.exempt
def generate_exercise_api():
    """API tạo bài tập mới"""
    try:
        data = request.get_json() or {}
        topic = data.get('topic', '')
        exercise = sql_assistant.generate_exercise(topic)
        return jsonify(exercise)
    except Exception as e:
        logger.error(f"Error generating exercise: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/validate-sql', methods=['POST'])
@csrf.exempt
def validate_sql_api():
    """API kiểm tra cú pháp SQL"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({"valid": False, "error": "Câu lệnh SQL trống"})
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"valid": False, "error": "Không thể kết nối database"})
        
        cursor = conn.cursor()
        try:
            cursor.execute(f"EXPLAIN {sql}")
            return jsonify({"valid": True, "message": "Cú pháp SQL hợp lệ"})
        except Error as err:
            return jsonify({"valid": False, "error": f"Lỗi cú pháp: {err.msg}"})
        finally:
            cursor.close()
            conn.close()
            
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)})

@app.route('/api/execute-sql', methods=['POST'])
@csrf.exempt
def execute_sql_api():
    """API thực thi SQL an toàn"""
    try:
        data = request.get_json()
        sql = data.get('sql', '').strip()
        
        if not sql:
            return jsonify({"success": False, "error": "Vui lòng nhập câu lệnh SQL"})
        
        # Chỉ cho phép câu lệnh SELECT
        if not sql.strip().upper().startswith('SELECT'):
            return jsonify({"success": False, "error": "Chỉ được phép thực thi câu lệnh SELECT"})
        
        result, error = execute_query(sql)
        if error:
            return jsonify({"success": False, "error": error})
        
        return jsonify({"success": True, "data": result, "count": len(result) if result else 0})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# =============================
# ERROR HANDLERS
# =============================

@app.errorhandler(404)
def not_found(error):
    """Xử lý lỗi 404"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Xử lý lỗi 500"""
    logger.error(f"Internal error: {error}")
    return render_template('500.html'), 500

# =============================
# CHẠY ỨNG DỤNG
# =============================

if __name__ == '__main__':
    # Kiểm tra kết nối database
    logger.info("Kiểm tra kết nối database...")
    conn = get_db_connection()
    if conn and conn.is_connected():
        logger.info("✅ Kết nối database thành công!")
        conn.close()
    else:
        logger.warning("⚠️ Không thể kết nối database. Kiểm lại cấu hình!")
    
    # Lấy port từ environment (Railway tự động set PORT)
    port = int(os.environ.get('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"🚀 Server starting on port {port}")
    logger.info(f"Debug mode: {debug}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)