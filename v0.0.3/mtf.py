from typing import List

def mtf_encode(data: bytes) -> List[int]:
    """
    Move-to-Front Transform encode.
    Returns a list of integer indices.
    """
    symbol_table = list(range(256))
    result = []
    for byte in data:
        idx = symbol_table.index(byte)
        result.append(idx)
        # Move to front
        symbol_table.pop(idx)
        symbol_table.insert(0, byte)
    return result

def mtf_decode(data: List[int]) -> bytes:
    """
    Move-to-Front Transform decode.
    Returns the original bytes.
    """
    symbol_table = list(range(256))
    result = bytearray()
    for idx in data:
        byte = symbol_table[idx]
        result.append(byte)
        # Move to front
        symbol_table.pop(idx)
        symbol_table.insert(0, byte)
    return bytes(result)

def mtf_decode_to_list(data: List[int]) -> List[int]:
    """
    Move-to-Front Transform decode to list.
    Returns the original list of integers.
    """
    symbol_table = list(range(256))
    result = []
    for idx in data:
        byte = symbol_table[idx]
        result.append(byte)
        # Move to front
        symbol_table.pop(idx)
        symbol_table.insert(0, byte)
    return result 