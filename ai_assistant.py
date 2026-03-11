# ai_assistant.py
import google.generativeai as genai
import os
import re
import mysql.connector
from config import DB_CONFIG
from difflib import SequenceMatcher
import json
import random
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv()

class SQLAssistant:
    def __init__(self, api_key=None):
        """Khởi tạo trợ lý SQL với Gemini AI (dùng package google.genai mới)"""
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        
        print("=" * 50)
        print("🔧 KHỞI TẠO TRỢ LÝ AI")
        print("=" * 50)
        
        # Khởi tạo client với package mới
        if self.api_key:
            print(f"✅ Đã tìm thấy API key: {self.api_key[:10]}...{self.api_key[-5:]}")
            try:
                self.client = genai.Client(api_key=self.api_key)
                
                # Danh sách các model khả dụng (bao gồm Gemini 2.0)
                available_models = [
                    # Gemini 2.0 models (mới nhất)
                    'gemini-2.0-flash-exp',
                    'gemini-2.0-pro-exp',
                    'gemini-2.0-flash',
                    
                    # Gemini 1.5 models
                    'gemini-1.5-flash',
                    'gemini-1.5-pro',
                    'gemini-1.5-flash-8b',
                    
                    # Gemini 1.0 models
                    'gemini-pro',
                    'gemini-1.0-pro'
                ]
                
                self.use_ai = False
                self.model_name = None
                
                print("🔄 Đang tìm kiếm model khả dụng...")
                
                # Thử từng model để tìm model hoạt động
                for model in available_models:
                    try:
                        print(f"  📡 Đang thử kết nối với model: {model}")
                        test_response = self.client.models.generate_content(
                            model=model,
                            contents="Hello, are you working?"
                        )
                        
                        if test_response and hasattr(test_response, 'text'):
                            self.model_name = model
                            self.use_ai = True
                            print(f"  ✅ Kết nối thành công với model: {model}")
                            print(f"  📝 Test response: {test_response.text[:50]}...")
                            break
                        else:
                            print(f"  ⚠️ Model {model} không trả về kết quả")
                    except Exception as e:
                        error_msg = str(e)
                        if "not found" in error_msg.lower():
                            print(f"  ❌ Model {model} không tồn tại")
                        elif "quota" in error_msg.lower():
                            print(f"  ⚠️ Model {model} vượt quota")
                        else:
                            print(f"  ⚠️ Model {model} lỗi: {error_msg[:50]}...")
                        continue
                
                if not self.use_ai:
                    print("❌ Không tìm thấy model nào khả dụng!")
                    
                    # Thử list models để xem có những model nào
                    try:
                        print("\n📋 Đang lấy danh sách model từ API:")
                        models = self.client.models.list()
                        for model in models:
                            print(f"  - {model.name}")
                    except Exception as e:
                        print(f"  ⚠️ Không thể list models: {e}")
                    
            except Exception as e:
                print(f"⚠️ Lỗi khởi tạo AI: {e}")
                self.use_ai = False
        else:
            print("⚠️ Chưa cấu hình API key cho Gemini AI")
            self.use_ai = False
        
        print(f"📊 Trạng thái AI: {'Online' if self.use_ai else 'Offline'}")
        if self.use_ai:
            print(f"📌 Model đang dùng: {self.model_name}")
        print("=" * 50)
        
        # Schema database mẫu
        self.db_schema = """
        Database: mymusic
        Tables:
        1. nhacsi (Nhạc sĩ)
           - idnhacsi (INT, PRIMARY KEY)
           - tennhacsi (VARCHAR) - Tên nhạc sĩ
           - ngaysinh (DATE)
           - tieusu (TEXT)
           - avatar (VARCHAR)
        
        2. casi (Ca sĩ)
           - idcasi (INT, PRIMARY KEY)
           - tencasi (VARCHAR) - Tên ca sĩ
           - Ngaysinh (DATE)
           - Sunghiep (TEXT)
           - anhdaidien (VARCHAR)
        
        3. bannhac (Bản nhạc)
           - idbannhac (INT, PRIMARY KEY)
           - tenbannhac (VARCHAR)
           - theloai (VARCHAR)
           - idnhacsi (INT, FOREIGN KEY)
        
        4. banthuam (Bản thu âm)
           - idbanthuam (INT, PRIMARY KEY)
           - idbannhac (INT, FOREIGN KEY)
           - idcasi (INT, FOREIGN KEY)
           - ngaythuam (DATE)
           - thoiluong (VARCHAR)
           - lyrics (TEXT)
           - file_path (VARCHAR)
        """
        
        # Câu lệnh SQL mẫu cho các bài tập
        self.sample_exercises = {
            '1': {
                'title': 'Liệt kê tất cả nhạc sĩ',
                'description': 'Viết câu lệnh SQL để lấy danh sách tất cả nhạc sĩ trong database',
                'solution': 'SELECT * FROM nhacsi',
                'hint': 'Sử dụng SELECT * FROM [tên_bảng]'
            },
            '2': {
                'title': 'Tìm ca sĩ theo tên',
                'description': 'Tìm ca sĩ có tên chứa "Trịnh"',
                'solution': "SELECT * FROM casi WHERE tencasi LIKE '%Trịnh%'",
                'hint': 'Sử dụng LIKE với ký tự đại diện %'
            },
            '3': {
                'title': 'Đếm số lượng bản nhạc theo thể loại',
                'description': 'Đếm số lượng bản nhạc của mỗi thể loại',
                'solution': 'SELECT theloai, COUNT(*) as soluong FROM bannhac GROUP BY theloai',
                'hint': 'Dùng GROUP BY và COUNT(*)'
            },
            '4': {
                'title': 'Tìm bài hát của nhạc sĩ Văn Cao',
                'description': 'Liệt kê các bài hát do nhạc sĩ Văn Cao sáng tác',
                'solution': """
                    SELECT bn.* 
                    FROM bannhac bn
                    JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi
                    WHERE ns.tennhacsi = 'Văn Cao'
                """,
                'hint': 'Cần JOIN hai bảng bannhac và nhacsi'
            },
            '5': {
                'title': 'Ca sĩ có nhiều bản thu nhất',
                'description': 'Tìm ca sĩ có nhiều bản thu âm nhất',
                'solution': """
                    SELECT c.tencasi, COUNT(bt.idbanthuam) as soluong
                    FROM casi c
                    LEFT JOIN banthuam bt ON c.idcasi = bt.idcasi
                    GROUP BY c.idcasi
                    ORDER BY soluong DESC
                    LIMIT 1
                """,
                'hint': 'Dùng GROUP BY, COUNT và ORDER BY'
            }
        }
        
        # Câu trả lời mẫu cho các câu hỏi thường gặp
        self.faq_responses = {
            'chào': '👋 Xin chào! Tôi là trợ lý SQL của bạn. Bạn cần giúp gì về bài tập hôm nay?',
            'help': '💡 Tôi có thể giúp bạn viết câu lệnh SQL, giải thích cú pháp, hoặc gợi ý cách giải bài tập.',
            'select': '📝 Câu lệnh SELECT dùng để truy vấn dữ liệu. Ví dụ: SELECT * FROM nhacsi',
            'join': '🔗 JOIN dùng để kết hợp dữ liệu từ nhiều bảng. Ví dụ: SELECT * FROM bannhac JOIN nhacsi ON bannhac.idnhacsi = nhacsi.idnhacsi',
            'group by': '📊 GROUP BY dùng để nhóm các hàng có cùng giá trị. Ví dụ: SELECT theloai, COUNT(*) FROM bannhac GROUP BY theloai',
            'insert': '➕ INSERT dùng để thêm dữ liệu mới. Ví dụ: INSERT INTO nhacsi (tennhacsi) VALUES ("Trịnh Công Sơn")',
            'update': '✏️ UPDATE dùng để cập nhật dữ liệu. Ví dụ: UPDATE casi SET sunghiep = "Ca sĩ nổi tiếng" WHERE idcasi = 1',
            'delete': '🗑️ DELETE dùng để xóa dữ liệu. Ví dụ: DELETE FROM banthuam WHERE idbanthuam = 1',
            'table': '📋 Các bảng trong database: nhacsi (nhạc sĩ), casi (ca sĩ), bannhac (bản nhạc), banthuam (bản thu âm)'
        }
    
    def generate_content(self, prompt, timeout=30):
        """Gửi prompt đến Gemini AI sử dụng package mới"""
        if not self.use_ai or not self.model_name:
            return None
            
        try:
            print(f"🔄 Đang gọi AI với model {self.model_name}...")  # Debug
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            
            if response and hasattr(response, 'text'):
                print(f"✅ Nhận được response từ AI ({len(response.text)} ký tự)")
                return response.text
            else:
                print("⚠️ Response từ AI không có text")
                return None
                
        except Exception as e:
            print(f"⚠️ Lỗi khi gọi AI: {e}")
            return None
    
    def generate_exercise(self, topic=None):
        """Tạo bài tập SQL mới bằng AI"""
        if self.use_ai and self.model_name:
            prompt = f"""
            Tạo một bài tập SQL cho database quản lý âm nhạc với schema sau:
            {self.db_schema}
            
            Yêu cầu:
            - Chủ đề: {topic or 'ngẫu nhiên'}
            - Bài tập phải phù hợp cho người mới học SQL
            - Trả về dạng JSON với các trường:
              - title: tiêu đề bài tập (ngắn gọn, 5-10 từ)
              - description: mô tả chi tiết (1-2 câu)
              - solution: câu lệnh SQL mẫu
              - hint: gợi ý (1 câu ngắn gọn)
            
            Ví dụ format:
            {{
                "title": "Tìm tất cả bài hát của nhạc sĩ Trịnh Công Sơn",
                "description": "Viết câu lệnh SQL để lấy danh sách các bài hát do nhạc sĩ Trịnh Công Sơn sáng tác",
                "solution": "SELECT * FROM bannhac WHERE idnhacsi = (SELECT idnhacsi FROM nhacsi WHERE tennhacsi = 'Trịnh Công Sơn')",
                "hint": "Dùng subquery hoặc JOIN để tìm id nhạc sĩ trước"
            }}
            
            Chỉ trả về JSON, không kèm giải thích.
            """
            
            response = self.generate_content(prompt)
            
            if response:
                try:
                    # Tìm JSON trong response
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        exercise = json.loads(json_match.group())
                        # Kiểm tra và đảm bảo có đủ các trường
                        if all(k in exercise for k in ['title', 'description', 'solution', 'hint']):
                            return exercise
                except Exception as e:
                    print(f"Lỗi parse JSON từ AI: {e}")
        
        # Fallback về bài tập mẫu nếu AI không hoạt động
        sample_list = [
            {
                'title': 'Liệt kê tất cả ca sĩ',
                'description': 'Viết câu lệnh SQL để lấy danh sách tất cả ca sĩ trong database',
                'solution': 'SELECT * FROM casi',
                'hint': 'Sử dụng SELECT * FROM [tên_bảng]'
            },
            {
                'title': 'Tìm bản nhạc theo tên',
                'description': 'Tìm các bản nhạc có tên chứa từ "tình"',
                'solution': "SELECT * FROM bannhac WHERE tenbannhac LIKE '%tình%'",
                'hint': 'Dùng LIKE với ký tự đại diện %'
            },
            {
                'title': 'Đếm số lượng bản thu âm theo ca sĩ',
                'description': 'Đếm số lượng bản thu âm của mỗi ca sĩ',
                'solution': 'SELECT c.tencasi, COUNT(bt.idbanthuam) as soluong FROM casi c LEFT JOIN banthuam bt ON c.idcasi = bt.idcasi GROUP BY c.idcasi',
                'hint': 'Dùng LEFT JOIN và GROUP BY'
            }
        ]
        return random.choice(sample_list)
    
    def evaluate_sql(self, user_sql, exercise_id=None):
        """Chấm điểm câu lệnh SQL của người dùng"""
        # Lấy SQL mẫu nếu có exercise_id
        correct_sql = None
        if exercise_id and exercise_id in self.sample_exercises:
            correct_sql = self.sample_exercises[exercise_id]['solution'].strip()
        
        # Chuẩn hóa câu SQL để so sánh
        def normalize_sql(sql):
            if not sql:
                return ""
            # Xóa khoảng trắng thừa, chuyển về chữ thường
            sql = ' '.join(sql.lower().split())
            # Xóa comment
            sql = re.sub(r'--.*', '', sql)
            sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
            # Xóa dấu ngoặc kép thừa
            sql = sql.replace('"', "'")
            return sql.strip()
        
        user_sql_norm = normalize_sql(user_sql)
        
        # Nếu có SQL mẫu để so sánh
        if correct_sql:
            correct_norm = normalize_sql(correct_sql)
            
            # So sánh chính xác
            if user_sql_norm == correct_norm:
                return {
                    'score': 100,
                    'status': 'perfect',
                    'message': '✅ Chính xác! Câu lệnh SQL của bạn hoàn hảo.',
                    'feedback': 'Bạn đã viết đúng cú pháp và logic.'
                }
            
            # Tính độ tương đồng
            similarity = SequenceMatcher(None, user_sql_norm, correct_norm).ratio()
            
            if similarity > 0.8:
                return {
                    'score': int(similarity * 100),
                    'status': 'good',
                    'message': '👍 Gần đúng! Câu lệnh của bạn khá tốt.',
                    'feedback': 'Có một số điểm chưa chính xác, hãy xem gợi ý bên dưới.'
                }
            else:
                return {
                    'score': int(similarity * 100),
                    'status': 'incorrect',
                    'message': '❌ Chưa chính xác. Hãy thử lại!',
                    'feedback': 'Câu lệnh SQL của bạn còn sai nhiều. Tham khảo gợi ý hoặc xem câu mẫu.'
                }
        
        # Nếu không có SQL mẫu, dùng AI để đánh giá (nếu có)
        if self.use_ai:
            prompt = f"""
            Đánh giá câu lệnh SQL sau cho database quản lý âm nhạc:
            
            Câu SQL: {user_sql}
            
            Schema:
            {self.db_schema}
            
            Hãy đánh giá:
            1. Cú pháp có đúng không? (Syntax)
            2. Logic có hợp lý không? (Logic)
            3. Có thể tối ưu không? (Optimization)
            
            Trả về JSON với format:
            {{
                "score": (0-100),
                "status": "perfect/good/incorrect",
                "message": "Ngắn gọn (1 câu)",
                "feedback": "Nhận xét chi tiết (2-3 câu)"
            }}
            
            Chỉ trả về JSON, không kèm giải thích.
            """
            
            response = self.generate_content(prompt)
            if response:
                try:
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                except Exception as e:
                    print(f"Lỗi parse JSON từ AI: {e}")
        
        return {
            'score': 50,
            'status': 'unknown',
            'message': '🤔 Cần kiểm tra thêm',
            'feedback': 'Không thể đánh giá tự động. Hãy thử chạy câu lệnh để xem kết quả.'
        }
    
    def chat_response(self, message, context=""):
        """Tạo phản hồi chat cho người dùng"""
        message_lower = message.lower()
        
        # Kiểm tra câu hỏi mẫu
        for key, response in self.faq_responses.items():
            if key in message_lower:
                return response
        
        # Nếu có AI, dùng AI để trả lời
        if self.use_ai:
            prompt = f"""
            Bạn là trợ lý AI chuyên về SQL cho database quản lý âm nhạc.
            
            Schema database:
            {self.db_schema}
            
            Ngữ cảnh hiện tại: {context}
            
            Câu hỏi: {message}
            
            Hãy trả lời một cách thân thiện, dễ hiểu và cung cấp ví dụ SQL cụ thể nếu có.
            Nếu là câu hỏi về SQL, hãy giải thích và đưa ví dụ cụ thể.
            Nếu là câu chào hỏi, hãy chào lại và hỏi xem cần giúp gì.
            
            Trả lời bằng tiếng Việt.
            """
            
            response = self.generate_content(prompt)
            if response:
                return response
        
        # Trả lời mặc định
        return """👋 Xin chào! Tôi là trợ lý SQL. 

Tôi có thể giúp bạn:
- 📝 Viết câu lệnh SELECT
- 🔗 Cách JOIN các bảng
- 📊 Sử dụng GROUP BY và hàm tổng hợp
- 💡 Gợi ý giải bài tập SQL

Ví dụ: "Làm thế nào để tìm tất cả bài hát của nhạc sĩ Văn Cao?"
→ SELECT bn.* FROM bannhac bn 
   JOIN nhacsi ns ON bn.idnhacsi = ns.idnhacsi 
   WHERE ns.tennhacsi = 'Văn Cao'

Bạn muốn hỏi gì thêm không? 🤗"""
    
    def execute_sql_safe(self, sql):
        """Thực thi SQL an toàn (chỉ SELECT)"""
        if not sql:
            return {
                'success': False,
                'error': 'Vui lòng nhập câu lệnh SQL'
            }
        
        sql_lower = sql.lower().strip()
        
        # Chỉ cho phép câu lệnh SELECT
        if not sql_lower.startswith('select'):
            return {
                'success': False,
                'error': '⚠️ Chỉ được phép thực thi câu lệnh SELECT để đảm bảo an toàn!'
            }
        
        # Kiểm tra các từ khóa nguy hiểm
        dangerous_keywords = ['drop', 'delete', 'update', 'insert', 'alter', 'create', 'truncate', 'replace']
        for keyword in dangerous_keywords:
            if keyword in sql_lower:
                return {
                    'success': False,
                    'error': f'⚠️ Câu lệnh chứa từ khóa "{keyword}" không được phép!'
                }
        
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute(sql)
            results = cursor.fetchall()
            
            # Giới hạn số lượng kết quả trả về
            if len(results) > 100:
                results = results[:100]
                
            cursor.close()
            conn.close()
            
            return {
                'success': True,
                'data': results,
                'count': len(results)
            }
            
        except mysql.connector.Error as err:
            return {
                'success': False,
                'error': f'❌ Lỗi SQL: {err.msg}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'❌ Lỗi: {str(e)}'
            }
    
    def get_hint(self, exercise_id):
        """Lấy gợi ý cho bài tập"""
        if exercise_id in self.sample_exercises:
            return self.sample_exercises[exercise_id]['hint']
        return "Hãy xem lại cú pháp SQL và cấu trúc database."

# Tạo instance toàn cục
print("🚀 Đang khởi tạo SQL Assistant...")
sql_assistant = SQLAssistant()