from .correctness_judge import contains_answer, exact_match
from .relevance_judge import check_answer_scope

EVALUATORS = [exact_match, contains_answer, check_answer_scope]

__all__ = ["EVALUATORS", "exact_match", "contains_answer", "check_answer_scope"]
