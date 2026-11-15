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
    for name in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "ANTHROPIC_AUTH_TOKEN", "NINA_ANALYST_ENGINE",
                 "NINA_ANALYST_MODEL"):
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
    monkeypatch.setenv("CLAUDE_API_KEY", "test-key")  # alias accepted
    assert test_client.get("/api/analyst").json() == {"engine": "claude", "model": "claude-haiku-5-5"}


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
    return SimpleNamespace(stop_reason="tool_use", model="claude-sonnet-5-5", content=[block])


def text(answer):
    return SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5",
                           content=[SimpleNamespace(type="text", text=answer)])


def test_model_answer_is_rewritten_until_its_figures_are_traced(client, monkeypatch):
    test_client, _ = client
    calls = scripted_client(monkeypatch, [
        tool_use("territory_profile", {"place": None, "year": None, "month": None}),
        text("September 2025 had 151 active cell-days."),
        text("September 2025 had 150 VIIRS-equivalent active cell-days, the highest of 14 compared years."),
    ])
    result = ask(test_client, "Is this September unusual?")
    assert result["engine"] == "claude" and result["model"] == "claude-sonnet-5-5"
    assert result["verification"]["passed"] and [t["name"] for t in result["tools"]] == ["territory_profile"]
    rewrite = [m["content"] for m in calls[2]["messages"] if m["role"] == "user" and isinstance(m["content"], str)]
    assert len(calls) == 3 and "151" in rewrite[-1] and "Automatic check" in rewrite[-1]
    first = calls[0]
    assert first["model"] == "claude-haiku-5-5" and "fallbacks" not in first  # Haiku has no server-side fallback
    client_tools = [tool for tool in first["tools"] if "input_schema" in tool]
    assert all(tool["strict"] for tool in client_tools) and "tool_choice" not in first
    [web] = [tool for tool in first["tools"] if tool.get("name") == "web_search"]
    assert web["allowed_domains"] and web["max_uses"] <= 3 and "blocked_domains" not in web
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


def test_model_visuals_and_actions_come_from_nina_data(client, monkeypatch):
    test_client, _ = client
    scripted_client(monkeypatch, [
        tool_use("show_visual", {"kind": "same_month_by_year", "place": None, "year": None, "month": None}),
        tool_use("propose_action", {"action": "open_report", "place": None, "year": None, "month": None,
                                    "label": None}),
        text("The chart below compares September of every year; the button opens the full report."),
    ])
    result = ask(test_client, "Show me September in every year and open the report.")
    assert result["engine"] == "claude" and result["verification"]["passed"]
    [chart] = result["visuals"]
    assert chart["type"] == "chart" and chart["chart"] == "bar" and chart["highlight"] == "2025"
    assert chart["categories"] and all(c.isdigit() for c in chart["categories"])
    assert len(chart["series"][0]["values"]) == len(chart["categories"])
    [action] = result["actions"]
    assert action["kind"] == "open_report" and action["report_id"] == result["report_id"]
    assert action["country"] == "Peru" and action["year"] == 2025 and action["month"] == 9
    assert len(result["follow_ups"]) == 3


def test_deterministic_answers_attach_a_chart_and_detect_requested_actions(client):
    test_client, _ = client
    result = ask(test_client, "Is the trend real or a sensor artefact?")
    assert [v["kind"] for v in result["visuals"]] == ["annual_totals"]
    names = [s["name"] for s in result["visuals"][0]["series"]]
    assert len(names) == 2 and "show_visual" not in [t["name"] for t in result["tools"]]
    result = ask(test_client, "Abre el calendario de este período", "es")
    assert [a["kind"] for a in result["actions"]] == ["open_calendar"]
    assert result["actions"][0]["label"].startswith("Abrir el calendario")
    scope = ask(test_client, "Will there be fires here next week?")
    assert scope["abstained"] and not scope["visuals"] and not scope["actions"]


def test_visual_limits_and_unknown_kinds_are_reported_to_the_model(client):
    test_client, _ = client
    request = analyst.AnalystQuestion(question="x", context=analyst.AnalystContext(**CONTEXT))
    session = analyst.Session(request)
    assert "error" in session.run("show_visual", {"kind": "pie", "place": None, "year": None, "month": None})
    for _ in range(analyst.MAX_VISUALS):
        assert "error" not in session.run("show_visual", {"kind": "monthly_series", "place": None, "year": None,
                                                          "month": None})
    assert "error" in session.run("show_visual", {"kind": "monthly_series", "place": None, "year": None, "month": None})
    assert len(session.visuals) == analyst.MAX_VISUALS


def test_strict_tool_schemas_stay_within_the_union_parameter_limit():
    # The API rejects strict tool sets with more than 16 nullable (anyOf / type-array) parameters in total.
    unions = sum(1 for tool in analyst.TOOL_SCHEMAS for p in tool["input_schema"]["properties"].values()
                 if "anyOf" in p or isinstance(p.get("type"), list))
    assert unions <= 16
    assert analyst.unset(0) is None and analyst.unset("") is None and analyst.unset("Cusco") == "Cusco"


def test_web_citations_become_sources_and_back_their_figures(client, monkeypatch):
    test_client, _ = client
    citation = SimpleNamespace(type="web_search_result_location", url="https://www.gob.pe/x", title="DS 097-2024-PCM",
                               cited_text="Declárese el Estado de Emergencia en 23 distritos por 60 días")
    content = [
        SimpleNamespace(type="text", text="Searching official sources."),
        SimpleNamespace(type="server_tool_use", name="web_search", input={"query": "estado de emergencia incendios"}),
        SimpleNamespace(type="web_search_tool_result"),
        SimpleNamespace(type="text", text="The decree declared an emergency in 23 districts for 60 days.",
                        citations=[citation]),
    ]
    scripted_client(monkeypatch, [SimpleNamespace(stop_reason="end_turn", model="claude-sonnet-5-5", content=content)])
    result = ask(test_client, "Was an emergency declared? Check official sources.")
    assert result["engine"] == "claude" and result["verification"]["passed"]
    assert result["answer"] == "The decree declared an emergency in 23 districts for 60 days."
    assert result["sources"] == [{"title": "DS 097-2024-PCM", "url": "https://www.gob.pe/x",
                                  "cited_text": citation.cited_text}]
    assert "web_search" in [t["name"] for t in result["tools"]]


def test_web_search_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("NINA_ANALYST_WEB", "false")
    assert analyst.web_tool() == []


def test_answer_written_before_a_chart_request_is_kept(client, monkeypatch):
    test_client, _ = client
    first = SimpleNamespace(stop_reason="tool_use", model="claude-sonnet-5-5", content=[
        SimpleNamespace(type="text", text="September 2025 had 150 VIIRS-equivalent active cell-days, the highest of 14."),
        SimpleNamespace(type="tool_use", id="toolu_v", name="show_visual",
                        input={"kind": "same_month_by_year", "place": "current", "year": 0, "month": 0}),
    ])
    scripted_client(monkeypatch, [
        tool_use("territory_profile", {"place": None, "year": None, "month": None}),
        first,
        text("The chart below compares every September."),
    ])
    result = ask(test_client, "Is this September unusual?")
    assert result["engine"] == "claude" and result["verification"]["passed"]
    assert result["answer"].startswith("September 2025 had 150") and result["answer"].endswith("every September.")
    assert [v["kind"] for v in result["visuals"]] == ["same_month_by_year"]


def test_haiku_requests_carry_no_server_side_fallback():
    assert analyst.fallback_options("claude-haiku-5-5") == {}
    assert analyst.fallback_options("claude-sonnet-5-5")["fallbacks"] == "default"
    cost = analyst.question_cost({"input_tokens": 1_000_000, "output_tokens": 0}, "claude-haiku-5-5")
    assert abs(cost - 0.10) < 1e-9


def test_stream_reports_progress_then_the_same_answer(client):
    test_client, _ = client
    body = {"question": "Is the trend real or a sensor artefact?", "language": "en", "context": CONTEXT}
    with test_client.stream("POST", "/api/analyst/stream", json=body) as response:
        assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    kinds = [event["type"] for event in events]
    assert kinds[-1] == "answer" and "tool" in kinds
    started = [e["name"] for e in events if e["type"] == "tool" and e["state"] == "start"]
    assert "territory_profile" in started
    answer = events[-1]["answer"]
    assert answer["engine"] == "deterministic" and answer["verification"]["passed"] and answer["visuals"]
