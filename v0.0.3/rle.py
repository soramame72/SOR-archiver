from typing import Tuple

def rle_encode(data: bytes) -> bytes:
    """
    RLE圧縮（バイト単位）。
    255連続まで対応。
    フォーマット: (バイト値, 繰り返し回数)
    """
    if not data:
        return b''
    out = bytearray()
    prev = data[0]
    count = 1
    for b in data[1:]:
        if b == prev and count < 255:
            count += 1
        else:
            out.append(prev)
            out.append(count)
            prev = b
            count = 1
    out.append(prev)
    out.append(count)
    return bytes(out)

def rle_decode(data: bytes) -> bytes:
    """
    RLE復号（バイト単位）。
    フォーマット: (バイト値, 繰り返し回数)
    """
    out = bytearray()
    if len(data) % 2 != 0:
        raise ValueError('RLEデータ長が不正です')
    for i in range(0, len(data), 2):
        b = data[i]
        count = data[i+1]
        out.extend([b] * count)
    return bytes(out) 