from datetime import date, time, timedelta

import bcrypt

from app.database import SessionLocal, init_db
from app.models import Flashcard, FlashcardDeck, RoutineBlock, StudyTask, User, UserProfile


def seed_demo_user() -> None:
    init_db()
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == "demo@aprovaos.local").first():
            return
        user = User(
            name="Estudante Demo",
            email="demo@aprovaos.local",
            hashed_password=bcrypt.hashpw("demo12345".encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            age=17,
        )
        db.add(user)
        db.flush()
        db.add(
            UserProfile(
                user_id=user.id,
                school_year="3º ano do ensino médio",
                routine_type="escola regular + cursinho",
                target_course="Medicina",
                target_universities="UFBA, ENEM",
                target_exams="ENEM, UFBA",
                main_difficulty="excesso de material",
                weekly_priority="Equilíbrio",
                overload_risk="moderado",
                study_profile_summary="Estudante com rotina cheia, precisa priorizar escola e vestibular sem acumular revisões.",
            )
        )
        db.add_all(
            [
                RoutineBlock(user_id=user.id, title="Escola", block_type="escola", weekday=0, start_time=time(7), end_time=time(12, 30)),
                RoutineBlock(user_id=user.id, title="Cursinho", block_type="cursinho", weekday=1, start_time=time(14), end_time=time(18)),
                StudyTask(user_id=user.id, title="Lista de funções", subject="matemática", source_type="escola", priority="alta", deadline=date.today() + timedelta(days=1), estimated_minutes=60),
                StudyTask(user_id=user.id, title="Revisar ecologia", subject="biologia", source_type="vestibular", priority="média", deadline=date.today() + timedelta(days=3), estimated_minutes=45),
            ]
        )
        deck = FlashcardDeck(user_id=user.id, title="Revisão inicial", subject="geral", source_type="pessoal")
        db.add(deck)
        db.flush()
        db.add(Flashcard(user_id=user.id, deck_id=deck.id, subject="biologia", topic="ecologia", front="O que é sucessão ecológica?", back="É o processo gradual de mudança nas comunidades de um ecossistema ao longo do tempo."))
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_user()
