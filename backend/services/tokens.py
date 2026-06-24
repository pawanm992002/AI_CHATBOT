from functools import lru_cache

import tiktoken

TOKEN_ENCODING_NAME = "cl100k_base"

@lru_cache(maxsize=1)
def _encoding():
    return tiktoken.get_encoding(TOKEN_ENCODING_NAME)

def count_tokens(text: str) -> int:
    if not text:
        return 0

    return len(_encoding().encode(text))
