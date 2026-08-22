"""그래프 배선.

문서 유형 분기는 **Upstage Studio Agent 내부**에서 일어난다 (바우처 vs 여행 계획서):

    START → ingest → ┬→ studio_agent ─┬→ act → END
                     └→ decode_codes ─┘  (fan-out 병렬, fan-in 대기)

- studio_agent: classify → parse → 유형별 Extract → Instruct(정규화·판단)를 잡 하나로 수행.
  바우처면 일정 1건 + 액션 계획, 여행 계획서(itinerary)면 일정 배열(액션 없이 저장만).
- decode_codes: 원본에서 QR/바코드 디코딩 + 크롭 저장 (로컬, LLM 불가 영역)
- act: 계획된 액션 실행 — 저장(중복 409/충돌 표시 정책), 캘린더 등록 등

targetType은 처리 분기가 아니라 여행 생성 방식만 결정한다
(trip → 새 여행 생성 / schedule → tripId의 기존 여행에 추가).
"""

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import DocState


def build_graph():
    g = StateGraph(DocState)
    g.add_node("ingest", nodes.ingest)
    g.add_node("studio_agent", nodes.studio_agent)
    g.add_node("decode_codes", nodes.decode_codes)
    g.add_node("act", nodes.act)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "studio_agent")
    g.add_edge("ingest", "decode_codes")
    g.add_edge("studio_agent", "act")
    g.add_edge("decode_codes", "act")
    g.add_edge("act", END)
    return g.compile()


GRAPH = build_graph()
