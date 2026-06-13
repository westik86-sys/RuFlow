#!/usr/bin/env python3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runner import normalize_text


class NormalizeTextTests(unittest.TestCase):
    def assert_normalizes_cases(self, cases: list[tuple[str, str]]) -> None:
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(normalize_text(source), expected)

    def test_adds_missing_space_before_dash(self) -> None:
        self.assertEqual(normalize_text("Пример— это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_space_after_dash(self) -> None:
        self.assertEqual(normalize_text("Пример —это бла бла бла"), "Пример — это бла бла бла")

    def test_adds_missing_spaces_around_dash(self) -> None:
        self.assertEqual(normalize_text("Пример—это бла бла бла"), "Пример — это бла бла бла")

    def test_keeps_leading_dialogue_dash_at_start(self) -> None:
        self.assertEqual(normalize_text("— Пример"), "— Пример")

    def test_normalizes_llm_word_variant(self) -> None:
        self.assertEqual(normalize_text("это ллм модель"), "это LLM модель")

    def test_normalizes_llm_spelled_as_letters(self) -> None:
        self.assertEqual(normalize_text("это л л м модель"), "это LLM модель")

    def test_normalizes_llm_phonetic_variants(self) -> None:
        self.assertEqual(normalize_text("это эл эл эм модель"), "это LLM модель")
        self.assertEqual(normalize_text("это эль эль эм модель"), "это LLM модель")

    def test_normalizes_llm_hyphenated_variants(self) -> None:
        self.assertEqual(normalize_text("это эл-эл-эм модель"), "это LLM модель")
        self.assertEqual(normalize_text("это эл—эл—эм модель"), "это LLM модель")

    def test_does_not_replace_partial_llm_sounds(self) -> None:
        self.assertEqual(normalize_text("это эм модель"), "это эм модель")

    def test_normalizes_common_technical_terms(self) -> None:
        self.assert_normalizes_cases(
            [
                ("открой апи и джейсон", "открой API и JSON"),
                ("проверь ямл и икс эм эл", "проверь YAML и XML"),
                ("запрос по эйч ти ти пи эс", "запрос по HTTPS"),
                ("старый хттп эндпоинт", "старый HTTP эндпоинт"),
                ("скопируй урл", "скопируй URL"),
                ("обнови эс ди кей и си эл ай", "обнови SDK и CLI"),
                ("проверь джей дабл ю ти и о аус", "проверь JWT и OAuth"),
                ("это рест и граф кью эл", "это REST и GraphQL"),
            ]
        )

    def test_normalizes_ai_products_and_tooling(self) -> None:
        self.assert_normalizes_cases(
            [
                ("чат жпт работает через оупен ай", "ChatGPT работает через OpenAI"),
                ("гпт и клод", "GPT и Claude"),
                ("антропик и джемини", "Anthropic и Gemini"),
                ("открой копайлот и курсор", "открой Copilot и Cursor"),
                ("виспер лежит на хаггинг фейс", "Whisper лежит на Hugging Face"),
                ("цепочка на ланг чейн и раг", "цепочка на LangChain и RAG"),
            ]
        )

    def test_normalizes_development_terms(self) -> None:
        self.assert_normalizes_cases(
            [
                ("гитхаб экшены упали", "GitHub Actions упали"),
                ("синхронизируй гитхаб и гит лаб", "синхронизируй GitHub и GitLab"),
                ("закоммить в гит", "закоммить в Git"),
                ("подними докер и кубер", "подними Docker и Kubernetes"),
                ("деплой в кей эйтс через терраформ", "деплой в K8s через Terraform"),
                ("почини си ай си ди", "почини CI/CD"),
                ("энжинкс редис постгрес", "Nginx Redis PostgreSQL"),
                ("май эс кью эл монго дб кафка", "MySQL MongoDB Kafka"),
                ("рэббит эм кью", "RabbitMQ"),
            ]
        )

    def test_normalizes_languages_and_frameworks(self) -> None:
        self.assert_normalizes_cases(
            [
                ("пайтон джаваскрипт тайпскрипт", "Python JavaScript TypeScript"),
                ("нод жс реакт некст жс вью", "Node.js React Next.js Vue"),
                ("свифт ю ай и икс код", "SwiftUI и Xcode"),
                ("котлин джава раст дотнет", "Kotlin Java Rust .NET"),
            ]
        )

    def test_normalizes_russian_fintech_terms(self) -> None:
        self.assert_normalizes_cases(
            [
                ("сбербанк и сбер", "Сбербанк и Сбер"),
                ("т банк и тинькофф", "T-Банк и Тинькофф"),
                ("альфа банк втб газпром банк", "Альфа-Банк ВТБ Газпромбанк"),
                ("райфайзенбанк и ю мани", "Райффайзенбанк и ЮMoney"),
                ("ю касса киви клауд пейментс", "ЮKassa QIWI CloudPayments"),
                ("робо касса и банк точка", "Robokassa и Банк Точка"),
                ("модуль банк совком банк и с б п", "Модульбанк Совкомбанк и СБП"),
                ("яндекс пэй яндекс банк озон банк", "Яндекс Pay Яндекс Банк Ozon Банк"),
                ("вб банк", "WB Банк"),
            ]
        )

    def test_does_not_replace_fintech_words_that_are_too_generic(self) -> None:
        self.assertEqual(normalize_text("точка входа и мир вокруг"), "точка входа и мир вокруг")


if __name__ == "__main__":
    unittest.main()
