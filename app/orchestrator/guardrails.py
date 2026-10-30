"""Deterministic pre-LLM policy checks (defense in depth).

The tool layer already makes other users' data unreachable; this check
makes the *refusal* deterministic too, instead of relying on the model."""
import re

# Bare "history" is excluded on purpose ("Python's history" is a topic, not an account)
_ACCOUNT = r"(loans?|borrow\w*|reservations?|holds?|account|fines?|penalt\w+|due dates?|checkouts?|(reading|borrowing|circulation) history)"
# Possessives that refer to things, not people ("this book's due date", "the library's loan policy")
_NOT_A_PERSON = r"(my|your|our|the|this|that|library|book|item|title|resource|paper|journal|ebook)"

_OTHER_USER_PATTERNS = [
    # "Meera's loans", "my friend's borrowing history" (but not "my loans" or "this book's due date")
    re.compile(rf"\b(?!{_NOT_A_PERSON}'s)[a-z]+'s\s+(\w+\s+)?{_ACCOUNT}\b", re.I),
    # "loans of user u-1002", "u-1002 borrowed", "student id 1002"
    re.compile(r"\bu-\d{3,}\b", re.I),
    re.compile(rf"\b(another|other|different)\s+(user|student|person|member|patron|people)('s)?\b.*\b{_ACCOUNT}\b", re.I),
    re.compile(rf"\b{_ACCOUNT}\b.*\b(of|for|by)\s+(another|other|a different)\s+(user|student|person|member|patron)\b", re.I),
    re.compile(rf"\b(someone else|everyone|all users|all students)('s)?\b.*\b{_ACCOUNT}\b", re.I),
    re.compile(r"\bwhat (has|did|is)\s+(?!i\b|you\b|we\b)[a-z]+\s+(borrow\w*|reserv\w*|check\w* out)", re.I),
]

PRIVACY_REFUSAL = ("I can't share another person's borrowing, reservation or account information. "
                   "I can only show your own account details.")


def is_other_user_account_request(message: str) -> bool:
    return any(p.search(message) for p in _OTHER_USER_PATTERNS)
