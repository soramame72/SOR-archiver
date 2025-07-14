from typing import List, Tuple, Dict
from collections import Counter
from arithmetic import arithmetic_encode, arithmetic_decode

def ppm_encode(data, order: int = 0):
    # data: bytesまたはList[int]
    # シンプルなorder-0 PPM（頻度モデルのみ、ESCAPEやコンテキストなし）
    if isinstance(data, bytes):
        symbols = list(data)
    else:
        symbols = list(data)
    enc_bytes, model_info = arithmetic_encode(symbols)
    return enc_bytes, model_info, {'order': order}

def ppm_decode(enc_bytes: bytes, model_info: Dict, model: Dict) -> bytes:
    # order-0: 頻度モデルのみ
    symbols = arithmetic_decode(enc_bytes, model_info)
    return bytes(symbols)

def ppm_decode_to_list(enc_bytes: bytes, model_info: Dict, model: Dict) -> list:
    # order-0: 頻度モデルのみ
    symbols = arithmetic_decode(enc_bytes, model_info)
    return list(symbols)

if __name__ == "__main__":
    # テスト: bytes/list[int]両方でencode→decode完全一致
    test_data = bytes([1,2,3,4,5,6,7,8,9,10,255,0,128,64,32,16,8,4,2,1])
    print('PPMテスト: 元データ:', list(test_data))
    enc, model_info, model = ppm_encode(list(test_data), order=0)
    dec = ppm_decode_to_list(enc, model_info, model)
    print('PPMテスト: 復号データ:', dec)
    print('完全一致:', list(test_data) == dec)
    enc2, model_info2, model2 = ppm_encode(test_data, order=0)
    dec2 = ppm_decode_to_list(enc2, model_info2, model2)
    print('PPMテスト(bytes): 復号データ:', dec2)
    print('完全一致(bytes):', list(test_data) == dec2) 