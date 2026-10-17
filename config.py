"""수집할 영상에서 빼고 싶은 것들. 여기만 고치면 됨."""
import re

# 한글이 조금이라도 들어가면 제외 (한국 영상 + 한국 연예인 영상 한 번에 컷)
HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]")

# 영어 욕설 / 한국 연예 쪽 영어 키워드 (단어 단위로만 걸림)
BAD_WORDS = [
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard", "dick", "pussy", "cunt",
    "kpop", "k-pop", "idol", "bts", "blackpink", "newjeans", "korean", "korea",
    "celebrity", "gossip",
]
BAD_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BAD_WORDS) + r")\b", re.I)


def is_blocked(title, channel="", description=""):
    text = f"{title or ''} {channel or ''} {description or ''}"
    if HANGUL.search(text):
        return True
    if BAD_RE.search(text):
        return True
    return False
