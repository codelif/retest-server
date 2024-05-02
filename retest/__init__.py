from dotenv import load_dotenv
import os
from flask import Flask
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase


STATIC_FOLDER = "assets"
STATIC_URL = "/assets"


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)


def create_app():
    load_dotenv(".env.local")
    load_dotenv(".env")
    app = Flask(__name__, STATIC_URL, STATIC_FOLDER)

    app.config["SECRET_KEY"] = (
        "210d47c8b857c8081b538bfdc6d4308217eb6890fb8cb9fdac7d30c0f0cd88db"
    )
    # app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///db.sqlite"
    # app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("POSTGRES_URL").replace(
    #     "postgres://", "postgresql://"
    # )
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("AWS_POSTGRES_URL")

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    from .models import MyAakashSession

    @login_manager.user_loader
    def load_user(user_psid):
        return MyAakashSession.query.filter_by(psid=user_psid).first()

    # blueprint for auth routes in our app
    from .auth import auth as auth_blueprint

    app.register_blueprint(auth_blueprint)

    # blueprint for non-auth parts of app
    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)

    with app.app_context():
        db.create_all()

    return app
