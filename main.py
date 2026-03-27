from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import sqlite3
import os

app = FastAPI(title="Teachers Reviews API", version="1.0.0")

# CORS - разрешаем запросы с любых источников
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== РАБОТА С БАЗОЙ ДАННЫХ ====================

DB_PATH = "teachers.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            photo_url TEXT,
            experience INTEGER,
            education TEXT,
            FOREIGN KEY (subject_id) REFERENCES subjects(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            clarity_rating INTEGER NOT NULL,
            fairness_rating INTEGER NOT NULL,
            attitude_rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

init_db()

# ==================== ЭНДПОИНТЫ ====================

@app.get("/health")
def health():
    return {"status": "healthy", "database": "sqlite"}

# ГЛАВНАЯ СТРАНИЦА - перенаправляем на index.html
@app.get("/")
def root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>index.html не найден</h1>", status_code=404)

# ==================== ПРЕДМЕТЫ ====================

@app.get("/subjects")
def get_subjects():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM subjects ORDER BY id")
    subjects = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return subjects

@app.post("/subjects")
def create_subject(name: str):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
        conn.commit()
        subject_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Предмет уже существует")
    conn.close()
    return {"id": subject_id, "name": name}

# ==================== УЧИТЕЛЯ ====================

@app.get("/teachers")
def get_teachers():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.name as subject_name 
        FROM teachers t 
        LEFT JOIN subjects s ON t.subject_id = s.id
        ORDER BY t.id
    ''')
    teachers = [dict(row) for row in cursor.fetchall()]
    
    for teacher in teachers:
        cursor.execute("SELECT * FROM reviews WHERE teacher_id = ? ORDER BY id DESC", (teacher["id"],))
        teacher["reviews"] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return teachers

@app.get("/teachers/{teacher_id}")
def get_teacher(teacher_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.name as subject_name 
        FROM teachers t 
        LEFT JOIN subjects s ON t.subject_id = s.id 
        WHERE t.id = ?
    ''', (teacher_id,))
    teacher = cursor.fetchone()
    
    if not teacher:
        conn.close()
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    result = dict(teacher)
    cursor.execute("SELECT * FROM reviews WHERE teacher_id = ? ORDER BY id DESC", (teacher_id,))
    result["reviews"] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return result

@app.post("/teachers")
def create_teacher(
    name: str,
    subject_id: int,
    photo_url: str = None,
    experience: int = None,
    education: str = None
):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM subjects WHERE id = ?", (subject_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Предмет не найден")
    
    cursor.execute('''
        INSERT INTO teachers (name, subject_id, photo_url, experience, education)
        VALUES (?, ?, ?, ?, ?)
    ''', (name, subject_id, photo_url, experience, education))
    conn.commit()
    teacher_id = cursor.lastrowid
    conn.close()
    
    return {"id": teacher_id, "name": name, "subject_id": subject_id}

@app.put("/teachers/{teacher_id}")
def update_teacher(
    teacher_id: int,
    name: str,
    subject_id: int,
    photo_url: str = None,
    experience: int = None,
    education: str = None
):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM teachers WHERE id = ?", (teacher_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    cursor.execute("SELECT id FROM subjects WHERE id = ?", (subject_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Предмет не найден")
    
    cursor.execute('''
        UPDATE teachers 
        SET name = ?, subject_id = ?, photo_url = ?, experience = ?, education = ?
        WHERE id = ?
    ''', (name, subject_id, photo_url, experience, education, teacher_id))
    conn.commit()
    conn.close()
    
    return {"id": teacher_id, "name": name, "subject_id": subject_id}

@app.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM teachers WHERE id = ?", (teacher_id,))
    teacher = cursor.fetchone()
    if not teacher:
        conn.close()
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    cursor.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
    conn.commit()
    conn.close()
    
    return {"message": f"Учитель '{teacher['name']}' удален"}

# ==================== ОТЗЫВЫ ====================

@app.get("/teachers/{teacher_id}/reviews")
def get_teacher_reviews(teacher_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM teachers WHERE id = ?", (teacher_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    cursor.execute('''
        SELECT * FROM reviews WHERE teacher_id = ? ORDER BY id DESC
    ''', (teacher_id,))
    reviews = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return reviews

@app.post("/reviews")
def create_review(
    teacher_id: int,
    author_name: str,
    clarity_rating: int,
    fairness_rating: int,
    attitude_rating: int,
    comment: str
):
    if not all(1 <= r <= 5 for r in [clarity_rating, fairness_rating, attitude_rating]):
        raise HTTPException(status_code=400, detail="Оценки должны быть от 1 до 5")
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM teachers WHERE id = ?", (teacher_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Учитель не найден")
    
    cursor.execute('''
        INSERT INTO reviews (teacher_id, author_name, clarity_rating, fairness_rating, attitude_rating, comment)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (teacher_id, author_name, clarity_rating, fairness_rating, attitude_rating, comment))
    conn.commit()
    review_id = cursor.lastrowid
    conn.close()
    
    return {"id": review_id, "teacher_id": teacher_id}

@app.delete("/reviews/{review_id}")
def delete_review(review_id: int):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT author_name FROM reviews WHERE id = ?", (review_id,))
    review = cursor.fetchone()
    if not review:
        conn.close()
        raise HTTPException(status_code=404, detail="Отзыв не найден")
    
    cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    conn.commit()
    conn.close()
    
    return {"message": f"Отзыв от {review['author_name']} удален"}

# ==================== ПОИСК ====================

@app.get("/search/teachers")
def search_teachers(q: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, s.name as subject_name 
        FROM teachers t 
        LEFT JOIN subjects s ON t.subject_id = s.id 
        WHERE t.name LIKE ?
        ORDER BY t.id
    ''', (f"%{q}%",))
    teachers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return teachers

# ==================== СТАТИЧЕСКИЕ ФАЙЛЫ ====================

# Раздаём все файлы из текущей папки, кроме тех, у которых есть свои эндпоинты
# Это позволяет index.html открываться без перенаправления
app.mount("/static", StaticFiles(directory=".", html=True), name="static")

# ==================== ЗАПУСК ====================

if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("PORT", 8000))
    
    print("\n" + "="*50)
    print("🚀 ЗАПУСК СЕРВЕРА")
    print("="*50)
    print(f"📁 База данных: {DB_PATH}")
    print(f"📝 Документация: http://localhost:{port}/docs")
    print(f"🔍 Health check: http://localhost:{port}/health")
    print(f"🌐 Главная страница: http://localhost:{port}/")
    print("="*50 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=port)
