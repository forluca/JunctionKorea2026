"""그래프 배선.

targetType으로 명시적 분기 (요청이 schedule/trip을 구분해서 들어옴):

- schedule (바우처·티켓 1건):
    START → ingest → classify → ┬→ parse   ─┬→ orchestrate → act → END
                                └→ extract ─┘   (fan-out 병렬, fan-in 대기)

- trip (전체 여행 계획 문서) — 아직 미구현, 자리만 잡아둠:
    START → ingest → trip_flow(placeholder) → END
    (확정 시: extract_itinerary → orchestrate_itinerary → act 로 교체 — nodes.py에 미배선 상태로 준비됨)
"""

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import DocState


def route_by_target(state: DocState) -> str:
    if state.get("target_type") == "trip":
        return "trip_flow"
    return "classify"


def build_graph():
    g = StateGraph(DocState)
    g.add_node("ingest", nodes.ingest)
    # schedule 분기
    g.add_node("classify", nodes.classify)
    g.add_node("parse", nodes.parse)
    g.add_node("extract", nodes.extract)
    g.add_node("orchestrate", nodes.orchestrate)
    g.add_node("act", nodes.act)
    # trip 분기 (placeholder)
    g.add_node("trip_flow", nodes.trip_flow_placeholder)

    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", route_by_target, ["classify", "trip_flow"])
    # schedule 분기: classify 후 parse/extract 병렬 → orchestrate에서 합류
    g.add_edge("classify", "parse")
    g.add_edge("classify", "extract")
    g.add_edge("parse", "orchestrate")
    g.add_edge("extract", "orchestrate")
    g.add_edge("orchestrate", "act")
    g.add_edge("act", END)
    # trip 분기: placeholder로 종료
    g.add_edge("trip_flow", END)
    return g.compile()


GRAPH = build_graph()
