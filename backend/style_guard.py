import re
from typing import List, Tuple

_WORD_RE = re.compile(r"\b\w[\w'\u2019\u2011-]*\b")

def word_count(s: str) -> int:
    return len(_WORD_RE.findall(s))

def violations(s: str) -> List[str]:
    s = s.strip()
    v = []
    if len(re.findall(r"[.!?]", s)) > 1: v.append("multiple_sentences")
    if word_count(s) > 18: v.append("too_many_words")
    if re.search(r"(?:[^,]*,){2,}[^,]*", s): v.append("list_like")
    if re.search(r"\band\b.*\band\b", s.lower()): v.append("list_like")
    if re.search(r"(#\w|…|[\U0001F300-\U0001FAFF])", s): v.append("hashtags_emojis_ellipsis")
    if re.search(r"[.!?]{2,}\s*$", s): v.append("trailing_punct")
    return v

def clean_summary(s: str) -> str:
    s = s.strip()
    s = s.replace('\\"', '"').replace("\\'", "'")
    s = re.sub(r"\\+", "", s)
    s = re.sub(r"(?<!\w)['`]s\b", "", s)
    s = re.sub(r"\s{2,}", " ", s).strip()

    if word_count(s) > 18:
        words = _WORD_RE.findall(s)
        s = " ".join(words[:18])

    s = re.sub(r"[,\-;:]+$", "", s).strip()          
    s = re.sub(r"\s+([,.;!?])", r"\1", s) 

    if re.match(r'^[\'"“”].*[\'"“”]$', s):
        s = s.strip('\'"“” ').strip()

    if not re.search(r"[.!?][\'\"”’)]*\s*$", s):
        s += "."
    s = re.sub(r"([.!?])([.!?])+([\'\"”’)]*\s*)$", r"\1\3", s)

    return s

def enforce_style(s: str) -> Tuple[str, List[str]]:
    cleaned = clean_summary(s)
    return cleaned, violations(cleaned)