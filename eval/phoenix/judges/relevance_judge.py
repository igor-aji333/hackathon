import os
from dotenv import load_dotenv
from phoenix.evals import LLM, ClassificationEvaluator

load_dotenv()

RELEVANCE_PROMPT_TEMPLATE = """
You are evaluating whether an agent stayed within the technical boundary of the FAA Airport Runway MCP Server.

IN-SCOPE DOMAIN:
- Queries regarding US airports by FAA (e.g., 'JFK', 'ORD') or ICAO (e.g., 'KJFK', 'KORD') identifiers.
- Runway physical specifications: length, width, surface type, condition, lighting, coordinates.
- Runway end specifications: runway end IDs, thresholds, elevations, alignments, ILS types, visual glide path angles.

OUT-OF-SCOPE DOMAIN:
- Live flight tracking, flight schedules, delays, weather conditions/METAR/TAF, airline fleet assignments, pricing, non-US airports.
- Subjective travel advice, predictive delays, or personal recommendations.

[USER QUERY]:
{input}

[AGENT RESPONSE]:
{output}

EVALUATION CRITERIA:
- "within_scope": The query asks for airport structural runway/runway-end info and the agent attempts to answer it, OR the query is out-of-scope and the agent appropriately states its limitation/refuses.
- "out_of_scope": The agent hallucinates out-of-scope data (e.g., pretends to know live weather/delays) or incorrectly answers questions outside FAA runway infrastructure.
"""

def check_answer_scope(input: dict, output: dict) -> str:
    base_url = os.getenv("USAI_BASE_URL", "").rstrip("/")
    if base_url and not base_url.endswith("/api/v1"):
        base_url = f"{base_url}/api/v1"

    judge_llm = LLM(
        provider="openai",
        model=os.getenv("JUDGE_MODEL", "claude_4_6_sonnet"),
        api_key=os.getenv("USAI_API_KEY"),
        base_url=base_url if base_url else None,
        temperature=0.0,
    )

    evaluator = ClassificationEvaluator(
        llm=judge_llm,
        prompt_template=RELEVANCE_PROMPT_TEMPLATE,
        choices={"within_scope": 1, "out_of_scope": 0},
    )

    result = evaluator.evaluate(
        input=input.get("query", ""),
        output=output.get("responses", ""),
    )
    return result[0]

