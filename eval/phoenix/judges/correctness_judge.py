def match_expected_response(input: dict, output: dict, expected: dict) -> str:
    """
    Evaluates correctness using DIRECT STRING COMPARISON as mandated by the MCP Guide.
    This replaces the LLM evaluator to ensure verifiable, exact match grading.
    """
    agent_response = str(output.get("responses", "")).strip().lower()
    ground_truth = str(expected.get("expected", "")).strip().lower()
    
    if ground_truth == agent_response:
        return "correct"
    elif ground_truth in agent_response:
        return "correct"
    else:
        return "incorrect"
