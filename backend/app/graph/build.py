"""그래프 배선.

START → ingest → classify → ┬→ parse   ─┬→ orchestrate → act → END
                            └→ extract ─┘   (fan-out 병렬, fan-in 대기)
"""

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import DocState


def build_graph():
    g = StateGraph(DocState)
    g.add_node("ingest", nodes.ingest)
    g.add_node("classify", nodes.classify)
    g.add_node("parse", nodes.parse)
    g.add_node("extract", nodes.extract)
    g.add_node("orchestrate", nodes.orchestrate)
    g.add_node("act", nodes.act)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_edge("classify", "parse")
    g.add_edge("classify", "extract")
    g.add_edge("parse", "orchestrate")
    g.add_edge("extract", "orchestrate")
    g.add_edge("orchestrate", "act")
    g.add_edge("act", END)
    return g.compile()


GRAPH = build_graph()
