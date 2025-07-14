from typing import Tuple, Dict, List
from collections import Counter

# 置換に使う記号（未使用バイト値）
SUBST_CODES = list(range(0xF0, 0x100))  # 0xF0～0xFF

# パターン検出・置換エンコード
def pattern_encode(data: bytes, minlen=2, maxlen=8, topn=8) -> Tuple[bytes, Dict[int, bytes]]:
    # パターン頻度カウント
    patterns = Counter()
    for l in range(minlen, maxlen+1):
        for i in range(len(data)-l+1):
            patterns[data[i:i+l]] += 1
    # 最頻パターンを選択
    subst_table = {}
    used = set()
    for pat, _ in patterns.most_common(topn):
        if pat in used or len(pat) < minlen:
            continue
        code = SUBST_CODES[len(subst_table)]
        subst_table[code] = pat
        used.add(pat)
        if len(subst_table) >= len(SUBST_CODES):
            break
    # 置換
    out = bytearray()
    i = 0
    while i < len(data):
        matched = False
        for code, pat in subst_table.items():
            l = len(pat)
            if data[i:i+l] == pat:
                out.append(code)
                i += l
                matched = True
                break
        if not matched:
            out.append(data[i])
            i += 1
    return bytes(out), subst_table

# パターン検出・置換デコード
def pattern_decode(data: bytes, subst_table: Dict[int, bytes]) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b in subst_table:
            out.extend(subst_table[b])
            i += 1
        else:
            out.append(b)
            i += 1
    return bytes(out) 