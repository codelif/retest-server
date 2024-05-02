from datetime import datetime
from typing import List

import requests
from myaakash import SessionService, TestPlatform
from sqlalchemy.orm import Session
from sqlalchemy.sql import select

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
        "pattern": [],
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


def get_test_pattern(test_short_code):
    test_pattern = "Mains"

    if test_short_code[-2] == "P":
        test_pattern = "Advanced"

    return test_pattern


def test_filter(test: dict, filters: dict) -> bool:
    categories = ["status", "type", "mode", "user_state"]
    for cat in categories:
        if test[cat] not in filters[cat]:
            return False

    if get_test_pattern(test["short_code"]) not in filters["pattern"]:
        return False
    if datetime.now() < datetime.fromisoformat(test["result_date_time"][:-6]):
        return False

    return True


class Sync:
    def __init__(self, session: Session, user_id: int, aakash: SessionService) -> None:
        self.session = session
        self.aakash = aakash
        self.user = self.session.query(MyAakashSession).filter_by(id=user_id).first()
        self.prefetch_db()

    def get_tests(self, config: dict):
        filters = generate_filters(config)
        func_filter = lambda test: test_filter(test, filters)
        tests = self.aakash.get_tests("passed")
        return list(filter(func_filter, tests))

    def prefetch_db(self):
        stmt = select(Tests.id)
        tests = self.session.execute(stmt).all()
        stmt = select(Chapters.id)
        chapters = self.session.execute(stmt).all()
        stmt = select(Questions.id)
        questions = self.session.execute(stmt).all()

        self.tests: List[int] = [i[0] for i in tests]
        self.chapters: List[int] = [i[0] for i in chapters]
        self.questions: List[int] = [i[0] for i in questions]

    def fetch_remote_test(self, test_id, test_number, test_short_code):
        print(test_id, test_number, test_short_code)
        url = self.aakash.get_url(
            test_id,
            test_number,
            test_short_code,
            "result",
        )["result_url"]

        test_platform = TestPlatform(url)
        question_json_link = test_platform.attempt(False)["questions_url"]
        questions = requests.get(question_json_link).json()["questions"]
        answers = test_platform.get_analysis_answers()

        return questions, answers

    def add_test(self, test_id: int, test_type: str, test_short_code: str):
        test = Tests(id=test_id, type=test_type, short_code=test_short_code)
        self.session.add(test)
        self.tests.append(test_id)

    def add_chapter(self, chapter: dict, subject: str):
        chap = Chapters(id=chapter["id"], name=chapter["name"], subject=subject)
        self.session.add(chap)
        self.chapters.append(int(chapter["id"]))

    def add_question(
        self,
        qid: int,
        qcontent: str,
        qdesc: str,
        qtype: str,
        qpattern: str,
        qchoices: dict,
        qmarking: str,
        qanswer: list,
        qsolution: str,
        qchap: dict,
        qparentid: int,
    ):

        question = Questions(
            id=qid,
            content=qcontent,
            desc=qdesc,
            type=qtype,
            pattern=qpattern,
            choices=qchoices,
            marking_scheme=qmarking,
            answer=qanswer,
            solution=qsolution,
            chapter_id=qchap["id"],
            children_id=[],
            parent_id=qparentid,
        )

        self.session.add(question)
        self.questions.append(qid)

    def add_stem_question(
        self,
        qid: int,
        qcontent: str,
        qdesc: str,
        qpattern: str,
        qchap: dict,
        qchildren: list,
    ):

        question = Questions(
            id=qid,
            content=qcontent,
            desc=qdesc,
            type="QSTEM",
            pattern=qpattern,
            chapter_id=qchap["id"],
            children_id=qchildren,
        )
        self.session.add(question)
        self.questions.append(qid)

    def add_attempt(self, qid: int, uanswer: list, uis_correct: bool, test_id: int):

        attempt = Attempts(
            question_id=qid,
            answer=uanswer,
            correct=uis_correct,
            test_id=test_id,
            account_psid=self.aakash.profile["psid"],
        )
        self.session.add(attempt)

    def is_test_attempted(self, test_id: int) -> bool:

        stmt = select(Attempts.id).where(
            Attempts.test_id == test_id,
            Attempts.account_psid == self.aakash.profile["psid"],
        )
        attempt = self.session.execute(stmt).first()

        if attempt:
            return True

        return False

    def sync(self, config: dict):

        tests = self.get_tests(config)
        for i, test in enumerate(tests, start=1):
            self.session.begin_nested()
            test_id = int(test["id"])
            test_number = test["number"]
            test_type = test["type"]
            test_short_code = test["short_code"] or test["test_short_sequence"]
            test_pattern = get_test_pattern(test_short_code)

            if self.is_test_attempted(test_id):
                continue

            if test_id not in self.tests:
                self.add_test(test_id, test_type, test_short_code)

            questions, answers = self.fetch_remote_test(
                test_id, test_number, test_short_code
            )

            self.sync_test(questions, answers, test_pattern, test_id)

            self.user.sync_progress = int(i / len(tests) * 100)
            self.session.commit()

    def __choices_mapper(self, choice: dict):
        return (choice["choice_id"], choice["text"])

    def __answers_mapper(self, answer):
        return (int(answer["question_id"]), answer)

    def sync_test(
        self, questions: dict, answers: list, test_pattern: str, test_id: int
    ):
        for question_id, question in questions.items():
            question_id = int(question_id)
            question_type = question["question_type"]
            question_subject = question["subjects"][0]
            question_chapter = question["chapters"][0]
            question_content = question["language_data"]["en"]["text"]
            question_desc = question["language_data"]["en"]["short_text"]

            question_choices = question["language_data"]["en"]["choices"]
            choices_map = map(self.__choices_mapper, question_choices)
            question_choices = dict(choices_map)

            answers_mapped = map(self.__answers_mapper, answers)
            answers_map = dict(answers_mapped)
            self.sync_question(
                question_id,
                question_type,
                question_subject,
                question_chapter,
                question_content,
                question_desc,
                question_choices,
                question,
                answers_map,
                test_id,
                test_pattern,
            )

    def __marking_scheme(self, question: dict):
        return f"{int(question['marks'])}/{int(question['negative_marks'] or '0')}"

    def sync_question(
        self,
        qid: int,
        qtype: str,
        qsub: dict,
        qchapter: dict,
        qcontent: str,
        qdesc: str,
        qchoices: dict,
        question: dict,
        answers: dict,
        test_id: int,
        test_pattern: str,
    ):
        stem_question_types = ["QSTEM", "Scenario"]
        if qid in self.questions:
            return

        if int(qchapter["id"]) not in self.chapters:
            self.add_chapter(qchapter, qsub["name"])

        if qtype in stem_question_types:
            if qid in self.questions:
                return
            children_id = question["child_questions"]
            self.add_stem_question(
                qid, qcontent, qdesc, test_pattern, qchapter, children_id
            )
        else:
            qmarking = self.__marking_scheme(question)
            answer_struct = answers[qid]
            answer = answer_struct["answer"]
            solution = answer_struct["language_data"]["en"]["solution"]
            parent_id: int = question.get("parent_question_id")

            if qid in self.questions:
                uanswer = answer_struct["selected_answer"] or []
                uis_correct = answer_struct.get("is_correct")

                self.add_attempt(qid, uanswer, uis_correct, test_id)
                return

            self.add_question(
                qid,
                qcontent,
                qdesc,
                qtype,
                test_pattern,
                qchoices,
                qmarking,
                answer,
                solution,
                qchapter,
                parent_id,
            )

            uanswer = answer_struct["selected_answer"] or []
            uis_correct = answer_struct.get("is_correct")

            self.add_attempt(qid, uanswer, uis_correct, test_id)
