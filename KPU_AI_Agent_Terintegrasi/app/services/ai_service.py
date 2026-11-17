"""Request-local LangChain v1 agent (LangGraph under the hood)."""
from dataclasses import dataclass
import re

from app.core.config import get_settings
from app.schemas.chat import Source


ABSTAIN = (
    "Saya belum dapat memastikan jawabannya berdasarkan dokumen resmi yang tersedia "
    "dalam basis pengetahuan. Silakan periksa JDIH atau website resmi KPU Kabupaten Subang "
    "atau hubungi petugas untuk memperoleh informasi terverifikasi."
)


@dataclass
class AgentResult:
    answer: str
    sources: list[Source]
    grounded: bool


def answer_question(message: str, history: list[tuple[str, str]]) -> AgentResult:
    from langchain.agents import create_agent
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_openai import ChatOpenAI
    from app.agent.prompts import SYSTEM_PROMPT
    from app.agent.tools import Evidence, build_tools

    s = get_settings()
    if not s.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY belum dikonfigurasi.")
    evidence = Evidence()
    
    agent = create_agent(
        model=ChatOpenAI(
            model=s.openai_model,
            api_key=s.openai_api_key,
            use_responses_api=True,
            reasoning={"effort": "low"},
            timeout=35,
            max_retries=1,
        ),
        tools=build_tools(evidence),
        system_prompt=SYSTEM_PROMPT,
    )

    messages = []
    for role, content in history[-s.max_context_messages:]:
        messages.append(HumanMessage(content=content) if role == "user" else AIMessage(content=content))
    messages.append(HumanMessage(content=message))
    result = agent.invoke({"messages": messages}, config={"recursion_limit": 12})
    last = result["messages"][-1]
    answer = last.content if isinstance(last.content, str) else "".join(
        p.get("text", "") for p in last.content if isinstance(p, dict)
    )
    answer = answer.strip() or ABSTAIN
    # No sourced evidence -> never present a factual answer as verified.
    # Greeting and drafting/channel directions can be answered without RAG.
    if evidence.retrieved and not evidence.sources:
        return AgentResult(answer=ABSTAIN, sources=[], grounded=False)
    if evidence.sources:
        # Only cited, tool-verified URLs are returned. Missing/invalid citations
        # are not silently treated as evidence of correctness.
        citations = set(int(x) for x in re.findall(r"\[(\d+)\]", answer))
        if not citations or any(i < 1 or i > len(evidence.sources) for i in citations):
            return AgentResult(answer=ABSTAIN, sources=[], grounded=False)
        return AgentResult(answer=answer, sources=[
            src for index, src in enumerate(evidence.sources, 1) if index in citations
        ], grounded=True)
    if evidence.used_draft_tool or evidence.used_channels_tool or _is_nonfactual(message):
        return AgentResult(answer=answer, sources=[], grounded=False)
    return AgentResult(answer=ABSTAIN, sources=[], grounded=False)


def _is_nonfactual(message: str) -> bool:
    return message.strip().lower().strip(".!? ") in {
        "halo", "hai", "hello", "hi", "terima kasih", "makasih", "selamat pagi", "selamat siang", "selamat sore",
    }
