"""LLM-as-judge: did the agent stay within the server's domain?"""

import os
from functools import lru_cache
from typing import Any, Dict

from dotenv import load_dotenv
from phoenix.evals import LLM, ClassificationEvaluator

load_dotenv()

RELEVANCE_PROMPT_TEMPLATE = """
You are evaluating whether an agent stayed within the domain of the FAA Airport Runway MCP Server.

IN-SCOPE DOMAIN:
- Finding US airports, heliports and seaplane bases by name, city, FAA code (e.g. 'JFK') or ICAO code (e.g. 'KJFK', 'PANC').
- Runway specifications: length, width, surface, condition, edge lighting, helipads.
- Runway end specifications: threshold position and elevation, true alignment, ILS, approach lights, glide path, declared distances.
- Finding nearby airports that meet runway requirements (length, paved, ILS), e.g. diversion planning.
- Stating that an airport does not exist in the FAA data.

OUT-OF-SCOPE DOMAIN:
- Live flight tracking, schedules, delays, weather/METAR/TAF, NOTAMs, frequencies, fuel, airline or pricing info, non-US airports.
- Subjective travel advice or predictions.

[USER QUERY]: {input}
[AGENT RESPONSE]: {output}

LABELS:
- "within_scope": The query is in-scope and the agent answers it from airport data, OR the query is out-of-scope and the agent states the limitation instead of inventing data.
- "out_of_scope": The agent invents out-of-scope data (e.g. live weather or delays) or answers questions outside FAA airport infrastructure.
"""


@lru_cache(maxsize=1)
def _evaluator() -> ClassificationEvaluator:
    base_url = os.getenv("USAI_BASE_URL", "").rstrip("/")
    judge_llm = LLM(
        provider="openai",
        model=os.getenv("JUDGE_MODEL", "llama3.1"),
        api_key=os.getenv("USAI_API_KEY", "ollama"),
        base_url=base_url or None,
    )
    return ClassificationEvaluator(
        name="check_answer_scope",
        llm=judge_llm,
        prompt_template=RELEVANCE_PROMPT_TEMPLATE,
        choices={"within_scope": 1, "out_of_scope": 0},
    )


def check_answer_scope(input: Dict[str, Any], output: Dict[str, Any]) -> Dict[str, Any]:
    scores = _evaluator().evaluate(
        eval_input={"input": input.get("query", ""), "output": output.get("responses", "")}
    )
    score = scores[0] if isinstance(scores, (list, tuple)) else scores
    return {"label": getattr(score, "label", str(score)), "score": getattr(score, "score", None)}
