from flask import (Blueprint, abort, json, jsonify, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from myaakash import SessionService
from myaakash.exceptions import LoginError

from . import db
from .models import MyAakashSession

auth = Blueprint("auth", __name__)


@auth.route("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.profile"))
    return render_template("login.html")


def create_session(aakash: SessionService):

    login_time = aakash.tokens["login_timestamp"]

    sess = MyAakashSession(
        psid=aakash.profile["psid"],
        name=aakash.profile["name"],
        login=login_time,
        tokens=aakash.tokens,
    )
    db.session.add(sess)
    db.session.commit()

    return sess


@auth.post("/login")
def login_post():
    data = request.get_json()
    psid, pswd = data["psid"], data["pswd"]

    aakash = SessionService()
    try:
        aakash.login(psid, pswd)
    except LoginError:
        abort(401)

    sess = MyAakashSession.query.filter_by(psid=psid).first()

    if sess:
        sess.name = aakash.profile["name"]
        sess.login = aakash.tokens["login_timestamp"]
        sess.tokens = aakash.tokens
        db.session.commit()
    else:
        sess = create_session(aakash)

    login_user(sess, remember=True)

    return jsonify({"name": sess.name})


@login_required
@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
