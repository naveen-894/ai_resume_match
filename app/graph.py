from app.nodes import ChatState, MatchState, answer_node, get_reasoning_chain, get_skill_matching_missing_chain, off_topic_node, parse_job_description_text, parse_resume_text, topic_guard_node
from langgraph.graph import StateGraph, START, END

def resume_parser_graph(checkpointer):
    """
    Builds and compiles a state graph for the resume parsing and job matching process.
    """

    graph = StateGraph(MatchState)

    # Define nodes (each represents a processing step)
    graph.add_node('parse_resume', parse_resume_text)
    graph.add_node('parse_jd', parse_job_description_text)
    graph.add_node('skill_chain', get_skill_matching_missing_chain)
    graph.add_node('reasoning_chain', get_reasoning_chain)

    # Define edges (execution flow between nodes)
    # parse_resume and parse_jd are independent, so they fan out from START in parallel.
    # skill_chain reads both resume_summary and jd_summary, so it joins on both.
    graph.add_edge(START, 'parse_resume')
    graph.add_edge(START, 'parse_jd')
    graph.add_edge(['parse_resume', 'parse_jd'], 'skill_chain')
    graph.add_edge('skill_chain', 'reasoning_chain')
    graph.add_edge('reasoning_chain', END)

    # Compile the graph with a checkpoint handler
    return graph.compile(checkpointer)

def chat_graph(checkpointer):
    graph = StateGraph(ChatState)
    # LangGraph will restore resume_summary & jd_summary from checkpoint using the same thread_id.
    graph.add_node("topic_guard", topic_guard_node)
    graph.add_node("answer", answer_node)
    graph.add_node("off_topic", off_topic_node)
    # Only questions about this resume/job match reach the answering model
    graph.add_edge(START, "topic_guard")
    graph.add_conditional_edges(
        "topic_guard",
        lambda state: "answer" if state.on_topic else "off_topic",
        ["answer", "off_topic"],
    )
    graph.add_edge("answer", END)
    graph.add_edge("off_topic", END)
    return graph.compile(checkpointer)