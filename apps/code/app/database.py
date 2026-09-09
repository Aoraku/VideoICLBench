import os
import secrets
from sqlmodel import SQLModel, create_engine, Session
from app.models import User, Language
import bcrypt
import datetime
from sqlmodel import select
import uuid

engine = create_engine(os.environ.get("DATABASE_URL", "sqlite:///oj.db"), echo=False)


def reset_db():
    SQLModel.metadata.drop_all(engine)
def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)

def create_initial_admin():
    with get_session() as session:
        admin = session.exec(select(User).where(User.username == "admin")).first()
        if admin:
            return
        admin = User(
            user_id=uuid.uuid4().hex,
            username="admin",
            password=bcrypt.hashpw(os.environ["VIC_OJ_ADMIN_PASSWORD"].encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            role="admin",
            join_time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
        )
        session.add(admin)
        session.commit()
        
def create_initial_language():
    with get_session() as session:
        language = session.exec(select(Language).where(Language.name == "python")).first()
        if language:
            return
        language = Language(
            name="python",
            file_ext=".py",
            source_template="{code}",
            run_cmd="python3 {src}",
            time_limit=1.0,
            memory_limit=128
        )
        session.add(language)
        session.commit()