"""Analytical assistant: traceable deterministic answers, abstention, figure verification and the
model loop (with a scripted stand-in for the Anthropic client; no network)."""

import json
from pathlib import Path
from types import SimpleNamespace

import anthropic
import pytest

from nina import analyst
from test_reports import client  # noqa: F401  (shared fixture: artifact + context layers)

CONTEXT = {"country": "Peru", "ubigeo": "25", "year": 2025, "month": 9}
EVAL = json.loads((Path(__file__).parents[1] / "docs/reference/analyst_eval.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "NINA_ANALYST_ENGINE", "NINA_ANALYST_MODEL"):
        monkeypatch.delenv(name, raising=False)


def ask(test_client, question, language="en", context=CONTEXT):
    response = test_client.post("/api/analyst", json={"question": question, "language": language, "context": context})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("question", "language", "intent", "expected"),
    [
        ("What does this period show?", "en", "overview", "rank 1 of 14"),
        ("Is the trend real or a sensor artefact?", "en", "trend", "harmonized series shows a significant increase"),
        ("How many INDECI emergencies were registered?", "en", "events", "INDECI registered 2"),
        ("How much forest was lost?", "en", "forest", "layer ends in 2024"),
        ("¿Hubo sequía este mes?", "es", "climate", "sequía: sí"),
        ("Is the coverage sufficient?", "en", "quality", "region-days have valid archive support"),
        ("How reliable is the harmonization here?", "en", "validation", "Validation status"),
        ("¿Qué departamentos destacan este mes?", "es", "compare", "Ucayali"),
        ("How does NINA harmonize MODIS and VIIRS?", "en", "method", "ratio-of-totals"),
        ("How did the fire season rank?", "en", "season", "fire season (July–October) 2025"),
    ],
)
def test_deterministic_answers_are_traceable(client, question, language, intent, expected):
    test_client, _ = client
    result = ask(test_client, question, language)
    assert result["engine"] == "deterministic" and result["intent"] == intent
    assert expected in result["answer"]
    assert result["verification"]["passed"], result["verification"]["unverified"]
    assert result["tools"] and all(t["ok"] for t in result["tools"])
    assert result["verification"]["checked"] > 0 or intent == "validation"  # the fixture has no strata details
    assert result["facts"] and result["dataset_id"] == "b" * 24


@pytest.mark.parametrize("item", [i for i in EVAL["items"] if i["abstain"]], ids=lambda i: i["id"])
def test_out_of_scope_questions_abstain_without_data(client, item):
    test_client, _ = client
    result = ask(test_client, item["question"], item["language"])
    assert result["abstained"] and result["intent"] == "scope"
    assert result["tools"] == [] and result["facts"] == []


def test_evaluation_set_is_classified_as_declared():
    for item in EVAL["items"]:
        assert analyst.classify(item["question"])[0] == item["intent"], item["id"]


def test_place_and_period_come_from_the_question_or_the_screen(client):
    context = analyst.AnalystContext(**CONTEXT)
    assert analyst.place_in("How much forest was lost in Ucayali?") == "25"
    assert analyst.place_in("¿Y en la provincia de Coronel Portillo?") == "2501"
    assert analyst.place_in("What does this period show?") is None
    assert analyst.period_in("¿Qué pasó en setiembre de 2024?", context) == (2024, 9)
    assert analyst.period_in("And in May 2020?", context) == (2020, 5)
    assert analyst.period_in("Which departments may stand out?", context) == (2025, 9)  # 'may' is not a month here


def test_verifier_accepts_traced_figures_and_flags_invented_ones():
    request = analyst.AnalystQuestion(question="How was 2024?", context={"year": 2024, "month": 9})
    session = analyst.Session(request)
    session.calls.append({"name": "territory_profile", "input": {}, "ok": True, "output": {
        "value": 20909.5, "anomaly_percent": 48.53, "rank": 3, "rank_of": 23, "passed_fraction": 0.6585,
        "rule": "significant = at least 5 active cell-days", "coverage": ["2003-01-01", "2026-06-30"]}})
    checked, unverified = session.verify(
        "In 2024 there were 20,909.5 units (about 21,000), +48.5 % against the median, rank 3 of 23; 65.9 % of "
        "strata pass; NOAA-20 fills H3 cells; at least 5 cell-days; INDECI records end on 2026-06-30.")
    assert unverified == [] and checked >= 9
    _, unverified = session.verify("2024 had 21,500 units, rank 4 of 23, and records end on 2026-07-31.")
    assert {"21,500", "4", "2026-07-31"} <= set(unverified)


def test_calculate_only_uses_figures_already_returned():
    session = analyst.Session(analyst.AnalystQuestion(question="Ratio?", context={"year": 2024, "month": 9}))
    session.calls.append({"name": "territory_profile", "input": {}, "ok": True, "output": {"value": 20909.5}})
    assert "error" in session.run("calculate", {"expression": "(20909.5 - 14081) / 14081 * 100"})
    session.calls[0]["output"]["median"] = 14081.0
    assert session.run("calculate", {"expression": "(20909.5 - 14081) / 14081 * 100"})["result"] == pytest.approx(48.4945, abs=1e-3)
    assert "error" in session.run("calculate", {"expression": "__import__('os').getcwd()"})


def test_status_reports_the_engine(client, monkeypatch):
    test_client, _ = client
    assert test_client.get("/api/analyst").json() == {"engine": "deterministic", "model": None}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert test_client.get("/api/analyst").json() == {"engine": "claude", "model": "claude-opus-5-5"}


def scripted_client(monkeypatch, responses):
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            return responses.pop(0)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(beta=SimpleNamespace(messages=Messages())))
    return calls


def tool_use(name, arguments):
    block = SimpleNamespace(type="tool_use", id=f"toolu_{name}", name=name, input=arguments)
    return SimpleNamespace(stop_reason="tool_use", model="claude-opus-5-5", content=[block])


def text(answer):
    return SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5",
                           content=[SimpleNamespace(type="text", text=answer)])


def test_model_answer_is_rewritten_until_its_figures_are_traced(client, monkeypatch):
    test_client, _ = client
    calls = scripted_client(monkeypatch, [
        tool_use("territory_profile", {"place": None, "year": None, "month": None}),
        text("September 2025 had 151 active cell-days."),
        text("September 2025 had 150 VIIRS-equivalent active cell-days, the highest of 14 compared years."),
    ])
    result = ask(test_client, "Is this September unusual?")
    assert result["engine"] == "claude" and result["model"] == "claude-opus-5-5"
    assert result["verification"]["passed"] and [t["name"] for t in result["tools"]] == ["territory_profile"]
    rewrite = [m["content"] for m in calls[2]["messages"] if m["role"] == "user" and isinstance(m["content"], str)]
    assert len(calls) == 3 and "151" in rewrite[-1] and "Automatic check" in rewrite[-1]
    first = calls[0]
    assert first["model"] == "claude-opus-5-5" and first["fallbacks"] == "default"
    assert all(tool["strict"] for tool in first["tools"]) and "tool_choice" not in first
    assert first["messages"][0]["content"].startswith("Answer language: English")


def test_unverifiable_model_answer_falls_back_to_the_deterministic_engine(client, monkeypatch):
    test_client, _ = client
    scripted_client(monkeypatch, [
        tool_use("territory_profile", {"place": "Ucayali", "year": 2025, "month": 9}),
        text("There were 999 fires."),
        text("There were 998 fires."),
    ])
    result = ask(test_client, "What does this period show?", "es")
    assert result["engine"] == "deterministic" and result["verification"]["passed"]
    assert "determinista" in result["notice"] and "Ucayali" in result["answer"]


def test_model_errors_fall_back_to_the_deterministic_engine(client, monkeypatch):
    test_client, _ = client

    class Broken:
        def create(self, **_):
            raise anthropic.APIConnectionError(request=None)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: SimpleNamespace(beta=SimpleNamespace(messages=Broken())))
    result = ask(test_client, "Is the coverage sufficient?")
    assert result["engine"] == "deterministic" and "could not be reached" in result["notice"]
