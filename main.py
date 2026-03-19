from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.exc import SQLAlchemyError
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "MySQLBest1!"
DB_NAME = "teachers_db"

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        echo=False
    )

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        logger.info("✅ Успешное подключение к MySQL")
        logger.info(f"   Сервер: {DB_HOST}:{DB_PORT}")
        logger.info(f"   База: {DB_NAME}")
        logger.info(f"   Пользователь: {DB_USER}")

except Exception as e:
    logger.error(f"❌ Ошибка подключения к MySQL: {e}")
    logger.error("Проверьте параметры подключения и убедитесь, что MySQL запущен")
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ==================== МОДЕЛИ БАЗЫ ДАННЫХ ====================

class SubjectModel(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    # Связь с учителями
    teachers = relationship("TeacherModel", back_populates="subject")


class TeacherModel(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False)
    photo_url = Column(Text, nullable=True)
    # Новые поля
    experience = Column(Integer, nullable=True)
    education = Column(Text, nullable=True)

    # Связи
    subject = relationship("SubjectModel", back_populates="teachers")
    reviews = relationship("ReviewModel", back_populates="teacher", cascade="all, delete-orphan")

class ReviewModel(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    author_name = Column(String(100), nullable=False)
    clarity_rating = Column(Integer, nullable=False)
    fairness_rating = Column(Integer, nullable=False)
    attitude_rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=False)

    teacher = relationship("TeacherModel", back_populates="reviews")

Base.metadata.create_all(bind=engine)
logger.info("✅ Таблицы проверены/созданы")

# ==================== PYDANTIC МОДЕЛИ ====================

from pydantic import ConfigDict


class SubjectBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)


class SubjectCreate(SubjectBase):
    pass


class SubjectResponse(SubjectBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TeacherBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    subject_id: int
    photo_url: Optional[str] = None
    experience: Optional[int] = Field(None, ge=0, le=70, description="Стаж в годах")
    education: Optional[str] = Field(None, max_length=200, description="Образование")


class TeacherCreate(TeacherBase):
    pass


class TeacherResponse(TeacherBase):
    id: int
    subject_name: Optional[str] = None
    reviews: List[ReviewResponse] = []
    model_config = ConfigDict(from_attributes=True)


class ReviewBase(BaseModel):
    teacher_id: int
    author_name: str = Field(..., min_length=2, max_length=100)
    clarity_rating: int = Field(..., ge=1, le=5)
    fairness_rating: int = Field(..., ge=1, le=5)
    attitude_rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=1, max_length=500)

    @field_validator('clarity_rating', 'fairness_rating', 'attitude_rating')
    def validate_rating(cls, v):
        if v not in [1, 2, 3, 4, 5]:
            raise ValueError('Оценка должна быть от 1 до 5')
        return v


class ReviewCreate(ReviewBase):
    pass


class ReviewResponse(ReviewBase):
    id: int
    teacher_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class TeacherWithReviews(TeacherResponse):
    total_reviews: int = 0
    average_ratings: Dict[str, float] = {
        "clarity": 0,
        "fairness": 0,
        "attitude": 0,
        "overall": 0
    }
    recent_reviews: List[ReviewResponse] = []


# ==================== ИНИЦИАЛИЗАЦИЯ FASTAPI ====================

app = FastAPI(
    title="API отзывов об учителях",
    description=f"Подключено к MySQL на {DB_HOST}",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== ЗАВИСИМОСТЬ ====================

def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Ошибка БД: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ==================== ЭНДПОИНТЫ ====================

@app.get("/")
def root():
    return {
        "message": "Teachers Reviews API",
        "database": {
            "host": DB_HOST,
            "database": DB_NAME,
            "status": "connected"
        },
        "docs": "/docs"
    }


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """Проверка здоровья сервиса"""
    try:
        db.execute(text("SELECT 1")).first()
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database connection failed: {e}")


# ==================== ПРЕДМЕТЫ ====================

@app.post("/subjects", response_model=SubjectResponse, status_code=201)
def create_subject(subject: SubjectCreate, db: Session = Depends(get_db)):
    """Создать новый предмет"""
    existing = db.query(SubjectModel).filter(SubjectModel.name == subject.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Предмет с таким названием уже существует")

    db_subject = SubjectModel(name=subject.name)
    db.add(db_subject)
    db.commit()
    db.refresh(db_subject)
    return db_subject


@app.get("/subjects", response_model=List[SubjectResponse])
def get_all_subjects(db: Session = Depends(get_db)):
    """Получить все предметы"""
    return db.query(SubjectModel).all()


@app.get("/subjects/{subject_id}", response_model=SubjectResponse)
def get_subject(subject_id: int, db: Session = Depends(get_db)):
    """Получить предмет по ID"""
    subject = db.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    return subject


# ==================== УЧИТЕЛЯ ====================

@app.post("/teachers", response_model=TeacherResponse, status_code=201)
def create_teacher(teacher: TeacherCreate, db: Session = Depends(get_db)):
    """Создать нового учителя"""
    # Проверяем что предмет существует
    subject = db.query(SubjectModel).filter(SubjectModel.id == teacher.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # Создаем учителя с новыми полями
    db_teacher = TeacherModel(
        name=teacher.name,
        subject_id=teacher.subject_id,
        photo_url=teacher.photo_url,
        experience=teacher.experience,
        education=teacher.education
    )
    db.add(db_teacher)
    db.commit()
    db.refresh(db_teacher)

    # Добавляем название предмета в ответ
    response = TeacherResponse.model_validate(db_teacher)
    response.subject_name = subject.name
    return response


@app.get("/teachers", response_model=List[TeacherResponse])
def get_all_teachers(db: Session = Depends(get_db)):
    """Получить всех учителей"""
    teachers = db.query(TeacherModel).all()
    result = []
    for teacher in teachers:
        teacher_dict = TeacherResponse.model_validate(teacher)
        if teacher.subject:
            teacher_dict.subject_name = teacher.subject.name
        result.append(teacher_dict)
    return result


@app.get("/teachers/{teacher_id}", response_model=TeacherResponse)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Получить учителя по ID"""
    teacher = db.query(TeacherModel).filter(TeacherModel.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    response = TeacherResponse.model_validate(teacher)
    if teacher.subject:
        response.subject_name = teacher.subject.name
    return response


@app.put("/teachers/{teacher_id}", response_model=TeacherResponse)
def update_teacher(teacher_id: int, teacher: TeacherCreate, db: Session = Depends(get_db)):
    """Обновить данные учителя"""
    db_teacher = db.query(TeacherModel).filter(TeacherModel.id == teacher_id).first()
    if not db_teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    # Проверяем предмет
    subject = db.query(SubjectModel).filter(SubjectModel.id == teacher.subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    # Обновляем данные
    db_teacher.name = teacher.name
    db_teacher.subject_id = teacher.subject_id
    db_teacher.photo_url = teacher.photo_url
    db_teacher.experience = teacher.experience
    db_teacher.education = teacher.education

    db.commit()
    db.refresh(db_teacher)

    response = TeacherResponse.model_validate(db_teacher)
    response.subject_name = subject.name
    return response


@app.delete("/teachers/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """Удалить учителя"""
    teacher = db.query(TeacherModel).filter(TeacherModel.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    reviews_count = len(teacher.reviews)
    db.delete(teacher)
    db.commit()

    return {
        "message": f"Учитель '{teacher.name}' удален",
        "deleted_reviews": reviews_count
    }


@app.get("/teachers/subject/{subject_id}", response_model=List[TeacherResponse])
def get_teachers_by_subject(subject_id: int, db: Session = Depends(get_db)):
    """Получить всех учителей по предмету"""
    subject = db.query(SubjectModel).filter(SubjectModel.id == subject_id).first()
    if not subject:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    teachers = db.query(TeacherModel).filter(TeacherModel.subject_id == subject_id).all()
    result = []
    for teacher in teachers:
        teacher_dict = TeacherResponse.model_validate(teacher)
        teacher_dict.subject_name = subject.name
        result.append(teacher_dict)
    return result


# ==================== ОТЗЫВЫ ====================

@app.post("/reviews", response_model=ReviewResponse, status_code=201)
def create_review(review: ReviewCreate, db: Session = Depends(get_db)):
    """Создать новый отзыв"""
    teacher = db.query(TeacherModel).filter(TeacherModel.id == review.teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    db_review = ReviewModel(
        teacher_id=review.teacher_id,
        author_name=review.author_name,
        clarity_rating=review.clarity_rating,
        fairness_rating=review.fairness_rating,
        attitude_rating=review.attitude_rating,
        comment=review.comment
    )
    db.add(db_review)
    db.commit()
    db.refresh(db_review)

    response = ReviewResponse.model_validate(db_review)
    response.teacher_name = teacher.name
    return response


@app.get("/teachers/{teacher_id}/reviews", response_model=List[ReviewResponse])
def get_teacher_reviews(teacher_id: int, db: Session = Depends(get_db)):
    """Получить все отзывы учителя"""
    teacher = db.query(TeacherModel).filter(TeacherModel.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    reviews = teacher.reviews
    result = []
    for review in reviews:
        review_dict = ReviewResponse.model_validate(review)
        review_dict.teacher_name = teacher.name
        result.append(review_dict)
    return result


@app.get("/reviews/{review_id}", response_model=ReviewResponse)
def get_review_by_id(review_id: int, db: Session = Depends(get_db)):
    """Получить отзыв по ID"""
    review = db.query(ReviewModel).filter(ReviewModel.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    response = ReviewResponse.model_validate(review)
    if review.teacher:
        response.teacher_name = review.teacher.name
    return response


@app.delete("/reviews/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db)):
    """Удалить отзыв"""
    review = db.query(ReviewModel).filter(ReviewModel.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Отзыв не найден")

    author_name = review.author_name
    db.delete(review)
    db.commit()

    return {"message": f"Отзыв от {author_name} удален"}


@app.get("/reviews", response_model=List[ReviewResponse])
def get_all_reviews(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Получить все отзывы"""
    reviews = db.query(ReviewModel).order_by(ReviewModel.id.desc()).offset(skip).limit(limit).all()
    result = []
    for review in reviews:
        review_dict = ReviewResponse.model_validate(review)
        if review.teacher:
            review_dict.teacher_name = review.teacher.name
        result.append(review_dict)
    return result


# ==================== СТАТИСТИКА ====================

@app.get("/teachers/{teacher_id}/stats")
def get_teacher_stats(teacher_id: int, db: Session = Depends(get_db)):
    """Получить статистику учителя"""
    teacher = db.query(TeacherModel).filter(TeacherModel.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Учитель не найден")

    reviews = teacher.reviews

    if not reviews:
        return {
            "teacher_id": teacher_id,
            "teacher_name": teacher.name,
            "subject": teacher.subject.name if teacher.subject else None,
            "photo_url": teacher.photo_url,
            "experience": teacher.experience,
            "education": teacher.education,
            "total_reviews": 0,
            "average_ratings": {
                "clarity": 0,
                "fairness": 0,
                "attitude": 0,
                "overall": 0
            }
        }

    total = len(reviews)
    clarity_sum = sum(r.clarity_rating for r in reviews)
    fairness_sum = sum(r.fairness_rating for r in reviews)
    attitude_sum = sum(r.attitude_rating for r in reviews)

    clarity_avg = round(clarity_sum / total, 2)
    fairness_avg = round(fairness_sum / total, 2)
    attitude_avg = round(attitude_sum / total, 2)
    overall_avg = round((clarity_avg + fairness_avg + attitude_avg) / 3, 2)

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.name,
        "subject": teacher.subject.name if teacher.subject else None,
        "photo_url": teacher.photo_url,
        "experience": teacher.experience,
        "education": teacher.education,
        "total_reviews": total,
        "average_ratings": {
            "clarity": clarity_avg,
            "fairness": fairness_avg,
            "attitude": attitude_avg,
            "overall": overall_avg
        }
    }


# ==================== ПОИСК ====================

@app.get("/search/teachers")
def search_teachers(q: str, db: Session = Depends(get_db)):
    """Поиск учителей по имени"""
    teachers = db.query(TeacherModel).filter(TeacherModel.name.contains(q)).all()
    result = []
    for teacher in teachers:
        result.append({
            "id": teacher.id,
            "name": teacher.name,
            "subject": teacher.subject.name if teacher.subject else None,
            "photo_url": teacher.photo_url,
            "experience": teacher.experience,
            "education": teacher.education
        })
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)