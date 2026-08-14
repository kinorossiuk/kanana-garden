import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from kanana_garden.baseline import (
    run_server_baseline,
    write_server_baseline_report,
)
from kanana_garden.client import ChatResult
from kanana_garden.recipe import iter_builtin_recipes
from kanana_garden.report_validation import (
    load_assets,
    validate_report_path,
    validate_server_baseline,
)
from kanana_garden.stability import compare_server_baselines


MODEL = "kakaocorp/kanana-2-1.3b-instruct"
CHECKED_AT = datetime(2026, 7, 31, 1, 2, 3, tzinfo=timezone.utc)
SESSION_1 = "11111111-1111-4111-8111-111111111111"
SESSION_2 = "22222222-2222-4222-8222-222222222222"


class FakeClient:
    def __init__(self, session_id: str = SESSION_1) -> None:
        self.chat_count = 0
        self.session_id = session_id

    def runtime_info(self, model: str) -> dict:
        return {
            "exposed_models": [MODEL],
            "runtime": {
                "session_id": self.session_id,
                "revision": "c10f59f16af7e3e3a9b2801f528a98c1e4ff6171",
                "dtype": "float32",
                "host_profile": "ryzen-5-5600g",
            },
        }

    def chat(self, **kwargs: object) -> ChatResult:
        self.chat_count += 1
        messages = kwargs["messages"]
        assert isinstance(messages, list)
        prompt = messages[-1]["content"]
        if "차량에서 들은 사용자 명령" in prompt:
            actions = {
                "볼륨 올려줘": "volume_up",
                "소리 좀 줄여": "volume_down",
                "볼륨 30퍼센트": "volume_set",
                "강남역": "navigation_start",
                "길 안내 그만": "navigation_stop",
                "음악 재생": "media_play",
                "다음 곡": "media_next",
                "내비게이션 앱": "app_open",
                "창문": "unsupported",
            }
            action = next(
                value for phrase, value in actions.items() if phrase in prompt
            )
            slots: dict[str, object] = {}
            if action == "volume_set":
                slots = {"level_percent": 30}
            elif action == "navigation_start":
                slots = {"destination": "강남역"}
            elif action == "app_open":
                slots = {"app": "navigation"}
            elif action == "unsupported":
                slots = {"reason": "허용되지 않은 차량 기능"}
            content = json.dumps(
                {
                    "action": action,
                    "slots": slots,
                    "confidence": "high",
                    "requires_confirmation": action in {
                        "navigation_start",
                        "unsupported",
                    },
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        elif "액션 아이템 표" in prompt:
            content = "액션 아이템"
        elif "## 쉬운 문장" in prompt:
            content = "14일"
        else:
            content = "7일 MVP"
        return ChatResult(
            content=content,
            model=MODEL,
            usage={"completion_tokens": 10},
        )


class HalfSecondClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.5
        return self.value


class BaselineTests(unittest.TestCase):
    def run_baseline(self, session_id: str = SESSION_1) -> tuple[dict, FakeClient]:
        client = FakeClient(session_id)
        report = run_server_baseline(
            client=client,
            endpoint="http://server.local:8000/v1",
            model=MODEL,
            recipes=iter_builtin_recipes(),
            repetitions=3,
            clock=HalfSecondClock(),
            checked_at=CHECKED_AT,
        )
        return report, client

    def test_three_repetitions_build_a_complete_valid_baseline(self) -> None:
        report, client = self.run_baseline()
        self.assertTrue(report["complete"])
        self.assertTrue(report["passed"])
        expected_samples = sum(
            len(recipe.examples) for recipe in iter_builtin_recipes()
        ) * 3
        self.assertEqual(client.chat_count, expected_samples)
        self.assertEqual(report["summary"]["sample_count"], expected_samples)
        self.assertEqual(report["summary"]["median_latency_seconds"], 0.5)
        self.assertEqual(report["summary"]["median_tokens_per_second"], 20.0)
        recipes, suites = load_assets()
        self.assertEqual(validate_server_baseline(report, recipes), [])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            write_server_baseline_report(report, path)
            self.assertEqual(validate_report_path(path, recipes, suites), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), report)

    def test_tampered_content_summary_and_rate_are_rejected(self) -> None:
        report, _ = self.run_baseline()
        first = report["recipes"][0]["samples"][0]
        first["content"] = "관련 없는 응답"
        first["tokens_per_second"] = 999
        report["summary"]["pass_rate"] = 1
        recipes, _ = load_assets()
        errors = validate_server_baseline(report, recipes)
        self.assertTrue(any(".passed" in error for error in errors))
        self.assertTrue(any("tokens_per_second" in error for error in errors))
        self.assertTrue(any("summary.pass_rate" in error for error in errors))
        self.assertTrue(any(error.startswith("passed") for error in errors))

    def test_distinct_server_sessions_prove_restart_stability(self) -> None:
        first, _ = self.run_baseline(SESSION_1)
        second, _ = self.run_baseline(SESSION_2)
        recipes, _ = load_assets()
        comparison = compare_server_baselines(
            first,
            second,
            recipes,
            compared_at=CHECKED_AT,
        )
        self.assertTrue(comparison["passed"])
        self.assertEqual(
            comparison["performance_delta"]["median_latency_percent"],
            0.0,
        )
        self.assertEqual(comparison["compared_at"], "2026-07-31T01:02:03Z")

    def test_same_server_session_does_not_prove_restart(self) -> None:
        first, _ = self.run_baseline()
        recipes, _ = load_assets()
        comparison = compare_server_baselines(
            first,
            copy.deepcopy(first),
            recipes,
            compared_at=CHECKED_AT,
        )
        self.assertFalse(comparison["passed"])
        distinct = next(
            check
            for check in comparison["checks"]
            if check["name"] == "distinct_server_sessions"
        )
        self.assertFalse(distinct["passed"])

    def test_different_revision_does_not_prove_stability(self) -> None:
        first, _ = self.run_baseline(SESSION_1)
        second, _ = self.run_baseline(SESSION_2)
        second["runtime"]["revision"] = "different-revision"
        recipes, _ = load_assets()
        comparison = compare_server_baselines(first, second, recipes)
        self.assertFalse(comparison["passed"])

    def test_compare_rejects_tampered_baseline(self) -> None:
        first, _ = self.run_baseline(SESSION_1)
        second, _ = self.run_baseline(SESSION_2)
        second["summary"]["sample_count"] = 999
        recipes, _ = load_assets()
        with self.assertRaisesRegex(Exception, "유효하지 않습니다"):
            compare_server_baselines(first, second, recipes)


if __name__ == "__main__":
    unittest.main()
