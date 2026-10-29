import os
from dotenv import load_dotenv
from phoenix.evals import LLM, ClassificationEvaluator

load_dotenv()

CORRECTNESS_PROMPT_TEMPLATE = """
You are an expert aviation evaluator assessing an AI agent's response against ground truth.
The agent queries an FAA Airport Runway MCP server to answer questions about airport runway lengths,
widths, surfaces, coordinates, runway ends, glide path angles, and elevations.

[QUESTION]:
{input}

[REFERENCE (GROUND TRUTH)]:
{reference}

[AGENT RESPONSE]:
{output}

EVALUATION CRITERIA:
1. Is the factual answer in the agent response consistent with the ground truth reference?
2. Allow reasonable formatting differences: rounding of decimal units (e.g., elevation 12.5 vs 13 ft),
   omission of trailing zeros, unit designations (feet, ft, '), or natural conversational prose.
3. If multiple runways are asked and all key ground-truth details match, mark correct.
4. Mark incorrect if the value contradicts ground truth, hallucinates data, or fails to find an existing record.

Label choices:
- "correct": The core factual values accurately match ground truth.
- "incorrect": The core values disagree, contradict, or the agent failed to answer.
"""

def match_expected_response(input: dict, output: dict, expected: dict) -> str:
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
        prompt_template=CORRECTNESS_PROMPT_TEMPLATE,
        choices={"correct": 1, "incorrect": 0},
    )

    result = evaluator.evaluate(
        input=input.get("query", ""),
        output=output.get("responses", ""),
        reference=expected.get("responses", ""),
    )
    return result[0]
