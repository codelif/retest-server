from datetime import datetime

import requests
from myaakash import SessionService, TestPlatform

from .models import *


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
        "status": ["passed"],
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
    elif datetime.now() < datetime.fromisoformat(test["result_date_time"][:-6]):
        return False

    return True


def sync(config: dict, aakash: SessionService, session, user_id):
    current_user = session.query(MyAakashSession).filter_by(id=user_id).first()
    filters = generate_filters(config)

    tests = list(
        filter(lambda test: test_filter(test, filters), aakash.get_tests("passed"))
    )

    for i, test in enumerate(tests, start=1):
        session.begin(nested=True)
        test_id = test["id"]
        test_number = test["number"]
        test_short_code = test["short_code"] or test["test_short_sequence"]
        tpattern = test_pattern(test)
        if not session.query(Tests).filter_by(id=test_id).first():
            session.add(
                Tests(
                    id=test_id,
                    type=test["type"],
                    short_code=test_short_code,
                )
            )

        print(
            f"Hoarding Test '{test_short_code}' [{i}/{len(tests)}]     ",
            end="\r",
            flush=True,
        )

        url = aakash.get_url(
            test_id,
            test_number,
            test_short_code,
            "result",
        )["result_url"]

        test_platform = TestPlatform(url)
        question_json_link = test_platform.attempt(False)["questions_url"]
        questions = requests.get(question_json_link).json()["questions"]
        answers = test_platform.get_analysis_answers()

        for question_id, question in questions.items():
            question_id = int(question_id)
            if (
                not session.query(Chapters)
                .filter_by(id=question["chapters"][0]["id"])
                .first()
            ):
                session.add(
                    Chapters(
                        id=question["chapters"][0]["id"],
                        name=question["chapters"][0]["name"],
                        subject=question["subjects"][0]["name"],
                    )
                )
            if question["question_type"] in ["SCMCQ", "MCMCQ", "SAN"]:
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

                answer_struct = list(
                    filter(
                        lambda x: x["question_id"] == question_id,
                        answers,
                    )
                )
                if not answer_struct:
                    session.reset()
                    continue
                answer_struct = answer_struct[0]

                answer = answer_struct["answer"]
                solution = answer_struct["language_data"]["en"]["solution"]

                parent_id = question.get("parent_question_id")
                chapter_id = question["chapters"][0]["id"]
                children_id = []

                if not session.query(Questions).filter_by(id=question_id).first():
                    session.add(
                        Questions(
                            id=question_id,
                            content=content,
                            desc=desc,
                            type=question["question_type"],
                            pattern=tpattern,
                            choices=choices,
                            marking_scheme=marking_scheme,
                            answer=answer,
                            solution=solution,
                            chapter_id=chapter_id,
                            children_id=children_id,
                            parent_id=parent_id,
                        )
                    )

                if (
                    not session.query(Attempts)
                    .filter_by(
                        test_id=test_id,
                        question_id=question_id,
                        account_psid=aakash.profile["psid"],
                    )
                    .first()
                ):
                    session.add(
                        Attempts(
                            question_id=question_id,
                            answer=answer,
                            correct=answer_struct.get("is_correct"),
                            test_id=test_id,
                            account_psid=aakash.profile["psid"],
                        )
                    )
            elif question["question_type"] in ["Scenario", "QSTEM"]:
                content = question["language_data"]["en"]["text"]
                desc = question["language_data"]["en"]["short_text"]
                chapter_id = question["chapters"][0]["id"]
                children_id = question["child_questions"]

                if not session.query(Questions).filter_by(id=question_id).first():
                    session.add(
                        Questions(
                            id=question_id,
                            content=content,
                            desc=desc,
                            type="QSTEM",
                            pattern=tpattern,
                            chapter_id=chapter_id,
                            children_id=children_id,
                        )
                    )

        current_user.sync_progress = int(i / len(tests) * 100)
        session.commit()

    print()
