from threading import Thread
from urllib.parse import unquote

import requests
from flask import (
    Blueprint,
    abort,
    copy_current_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required
from myaakash import SessionService, TestPlatform
from sqlalchemy.orm import scoped_session, sessionmaker

from . import db
from .models import *
from .sync import Sync

main = Blueprint("main", __name__)
T = []


@main.route("/")
@login_required
def index():
    return render_template("dashboard.html", name=current_user.name)


@main.get("/question-bank")
@login_required
def bank():

    r = Chapters.query.all()
    chapters = {}
    for i in r:
        if not isinstance(chapters.get(i.subject), set):
            chapters[i.subject] = set()

        chapters[i.subject].add(i.name)

    for i, k in chapters.items():
        chapters[i] = sorted(k, key=lambda x: x)
    return render_template(
        "question-bank.html", name=current_user.name, chapters=chapters
    )


@main.get("/question/<int:qid>")
# @login_required
def question(qid: int):
    ques = Questions.query.filter_by(id=qid).first_or_404()

    choice_type = True if ques.type == "SCMCQ" else False
    question = ques.content
    choices = tuple(ques.choices.values())

    if not current_user.is_authenticated:
        name = "Anonymous"
    else:
        name = current_user.name

    return render_template(
        "question.html",
        name=name,
        is_correct=False,
        question_id=qid,
        question=question,
        choice_type=choice_type,
        choice=choices,
        answer=ques.answer,
        solution=ques.solution,
    )


def generate_filters(config: dict):
    tests = config["tests"]

    AVAILABLE_TESTS = {
        "fts": "Final Test Series",
        "ats": "Archive Test Series",
        "aiats": "AIATS",
        "ut": "Unit Test",
        "tt": "Term Test",
        "pt": "Practice Test",
    }

    AVAILABLE_PATTERNS = {"adv": "Advanced", "mains": "Mains"}

    filters = {
        "type": [],
        "pattern": config["patterns"],
        "user_state": ["completed"],
        "status": ["passed", "live"],
        "mode": ["Online"],
    }
    for test in tests:
        if AVAILABLE_TESTS.get(test):
            filters["type"].append(AVAILABLE_TESTS[test])

    for pattern in config["patterns"]:
        if AVAILABLE_PATTERNS.get(pattern):
            filters["pattern"].append(AVAILABLE_PATTERNS[pattern])

    return filters


def test_pattern(test: dict):
    test_short_code = test["short_code"] or test["test_short_sequence"]
    test_pattern = "Mains"

    if test_short_code[-2] == "P":
        test_pattern = "Advanced"

    return test_pattern


def test_filter(test: dict, filter: dict) -> bool:
    if test["status"] not in filter["status"]:
        return False
    elif test["type"] not in filter["type"]:
        return False
    elif test_pattern(test) not in filter["pattern"]:
        return False
    elif test["user_state"] not in filter["user_state"]:
        return False
    elif test["mode"] not in filter["mode"]:
        return False

    return True


@main.get("/tests")
def get_tests():
    user = current_user
    if not current_user.is_authenticated:
        user = MyAakashSession.query.filter_by(psid="00002588208").first()
    aakash = SessionService()
    aakash.token_login(user.tokens)

    t = aakash.get_tests("live")
    t.extend(aakash.get_tests("passed"))

    config = {"tests": ["fts", "ats"], "patterns": ["adv"]}
    filters = generate_filters(config)

    tests = list(filter(lambda test: test_filter(test, filters), t))
    name = []
    for test in tests:
        n = f"{test['type']} - {test['short_code'][-3]} - Paper {test['short_code'][-1]} - Phase {test['short_code'][8]} (JEE Advanced)"
        name.append(
            (n, "/test/" + test["id"] + "/" + test["short_code"] + "/" + test["number"])
        )

    return render_template("tests.html", tests=name)
    return str(name)


@main.get("/test/<string:test_id>/<string:test_code>/<string:number>")
def get_test(test_id, test_code, number):
    user = MyAakashSession.query.filter_by(psid="00002588208").first()
    test_id, test_code, number = unquote(test_id), unquote(test_code), unquote(number)
    aakash = SessionService()
    aakash.token_login(user.tokens)

    url = aakash.get_url(
        test_id,
        number,
        test_code,
        "result",
    )["result_url"]

    test_platform = TestPlatform(url)
    question_json_link = test_platform.attempt(False)["questions_url"]
    questions = requests.get(question_json_link).json()["questions"]
    try:
        answers = test_platform.get_analysis_answers()
    except TypeError:
        answers = None

    serialize_questions = []
    for question_id, question in sorted(list(questions.items())):
        chapter = question["subjects"][0]["name"]
        question_id = int(question_id)

        if question["question_type"] in ["SCMCQ", "MCMCQ", "SAN", "MATCHLIST"]:
            content = question["language_data"]["en"]["text"]
            desc = question["language_data"]["en"]["short_text"]
            choices = dict(
                map(
                    lambda x: (x["choice_id"], x["text"]),
                    question["language_data"]["en"]["choices"],
                )
            )
            marking_scheme = (
                f"{int(question['marks'])}/{int(question['negative_marks'] or '0')}"
            )

            parent_id = question.get("parent_question_id")
            chapter_id = question["chapters"][0]["id"]
            children_id = []
            if parent_id != None:
                continue
            choice_type = True if question["question_type"] != "SAN" else False
            q = (
                question["sequence"],
                True,
                question_id,
                content,
                choice_type,
                tuple(choices.values()),
                "",
                "",
                question["question_type"],
                chapter,
            )
            serialize_questions.append(q)

        elif question["question_type"] in ["Scenario", "QSTEM"]:
            content = question["language_data"]["en"]["text"]
            desc = question["language_data"]["en"]["short_text"]
            chapter_id = question["chapters"][0]["id"]
            children_id = question["child_questions"]
            parent_q = (
                questions[str(children_id[0])]["sequence"],
                True,
                question_id,
                content,
                False,
                {},
                "[]",
                "",
                "QSTEM",
                chapter,
            )
            serialize_questions.append(parent_q)
            for qu in children_id:
                q_id = qu
                qu = questions[str(qu)]

                choice_type = True if qu["question_type"] != "SAN" else False
                co = qu["language_data"]["en"]["text"]
                choices = dict(
                    map(
                        lambda x: (x["choice_id"], x["text"]),
                        qu["language_data"]["en"]["choices"],
                    )
                )

                correct = True

                q = (
                    qu["sequence"],
                    correct,
                    int(q_id),
                    co,
                    choice_type,
                    tuple(choices.values()),
                    "",
                    "",
                    qu["question_type"],
                    chapter,
                )
                serialize_questions.append(q)

    return render_template(
        "chapter.html",
        name="Anonymous" if not current_user.is_authenticated else current_user.name,
        questions=sorted(serialize_questions, key=lambda x: x[0]),
        subject="",
        chapter="",
    )


@main.get("/s/<string:subject>/c/<string:chapter>")
def get_chapter(subject: str, chapter: str):
    subject, chapter = unquote(subject), unquote(chapter)
    chapters = db.session.query(Chapters.id).filter_by(name=chapter, subject=subject)

    questions = []
    for i in chapters:
        questions.extend(Questions.query.filter_by(chapter_id=i[0]).all())

    if not questions:
        abort(404)

    serialize_questions = []
    for i, ques in enumerate(questions, start=1):
        if ques.parent_id != None:
            continue

        attempt = (
            db.session.query(Attempts.correct)
            .filter_by(question_id=ques.id, account_psid=current_user.psid)
            .first()
        )
        if not attempt:
            continue

        if ques.type == "QSTEM":
            a = db.session.query(Questions).filter_by(parent_id=ques.id)
            parent_q = (
                i,
                True,
                ques.id,
                ques.content,
                False,
                {},
                "[]",
                "",
                ques.type,
                chapter,
            )
            serialize_questions.append(parent_q)
            for qu in a.all():

                choice_type = True if qu.type != "SAN" else False
                question = qu.content
                choices = tuple(qu.choices.values())

                correct = True

                q = (
                    i,
                    correct,
                    qu.id,
                    question,
                    choice_type,
                    choices,
                    qu.answer,
                    qu.solution,
                    qu.type,
                    chapter,
                )
                serialize_questions.append(q)

            continue

        if not attempt:
            continue
        correct = attempt[0]
        if correct == None:
            correct = True
        choice_type = True if ques.type != "SAN" else False
        question = ques.content
        choices = tuple(ques.choices.values())

        q = (
            i,
            correct,
            ques.id,
            question,
            choice_type,
            choices,
            ques.answer,
            ques.solution,
            ques.type,
            chapter,
        )
        serialize_questions.append(q)

    return render_template(
        "chapter.html",
        name=current_user.name,
        questions=serialize_questions,
        subject=subject,
        chapter=chapter,
    )


@main.route("/profile")
@login_required
def profile():
    return redirect(url_for("main.index"))


@main.get("/sync")
@login_required
def get_sync_progress():
    progress = current_user.sync_progress
    if not progress:
        progress = 0

    return str(progress)


def clean_threads():
    global T

    new_t = []
    for i in T:
        i: Thread
        if i.is_alive():
            new_t.append(i)

    T = new_t
    if len(T) == 0:
        return True
    return False


@main.get("/status")
@login_required
def get_status():

    if clean_threads():
        current_user.is_in_sync = False
        db.session.commit()

    progress = current_user.sync_progress
    if not progress:
        progress = 0

    is_in_sync = current_user.is_in_sync
    config = current_user.config
    if not config:
        config = {"tests": [], "patterns": []}

    return jsonify({"config": config, "sync": is_in_sync, "progress": progress})


@main.post("/sync-settings")
@login_required
def set_sync_settings():
    if current_user.is_in_sync:
        return jsonify({"message": "ERROR: Already in sync!"})

    config = request.json["config"]
    aakash = SessionService()
    aakash.token_login(current_user.tokens)
    session_factory = db.session.session_factory

    @copy_current_request_context
    def start_sync(
        config: dict, aakash: SessionService, user_id: int, sess_fac: sessionmaker
    ):
        session = scoped_session(sess_fac)
        user = session.get(MyAakashSession, user_id)
        user.config = config
        user.is_in_sync = True
        user.sync_progress = 0

        session.commit()

        try:
            Sync(session, user_id, aakash).sync(config)
            # sync(config, aakash, session, user_id)
        except Exception as e:
            user.is_in_sync = False
            user.sync_progress = 100
            session.commit()
            raise e

    t = Thread(
        target=start_sync, args=(config, aakash, current_user.id, session_factory)
    )
    T.append(t)
    t.start()

    return jsonify({"message": "OK"})
