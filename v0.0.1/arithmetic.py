from typing import List, Tuple, Dict
from collections import Counter
import pickle

# 符号化精度（ビット長）
PRECISION = 32
MAX_RANGE = 1 << PRECISION
MASK = MAX_RANGE - 1
HALF = 1 << (PRECISION - 1)
QUARTER = 1 << (PRECISION - 2)

# ビットストリーム書き込み
class BitWriter:
    def __init__(self):
        self.buffer = 0
        self.nbits = 0
        self.bytes = bytearray()
    def write(self, bit):
        self.buffer = (self.buffer << 1) | bit
        self.nbits += 1
        if self.nbits == 8:
            self.bytes.append(self.buffer)
            self.buffer = 0
            self.nbits = 0
    def flush(self):
        if self.nbits > 0:
            self.bytes.append(self.buffer << (8 - self.nbits))
            self.buffer = 0
            self.nbits = 0
    def get_bytes(self):
        return bytes(self.bytes)

# ビットストリーム読み込み
class BitReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.nbits = 0
        self.buffer = 0
    def read(self):
        if self.nbits == 0:
            if self.pos < len(self.data):
                self.buffer = self.data[self.pos]
                self.pos += 1
                self.nbits = 8
            else:
                return 0  # パディング
        self.nbits -= 1
        return (self.buffer >> self.nbits) & 1

# エンコード
def arithmetic_encode(data: List[int]) -> Tuple[bytes, Dict]:
    freq = Counter(data)
    total = sum(freq.values())
    symbols = sorted(freq)
    # 累積分布
    cum = {s: 0 for s in symbols}
    c = 0
    for s in symbols:
        cum[s] = c
        c += freq[s]
    low, high = 0, MASK
    pending = 0
    writer = BitWriter()
    for d in data:
        r = high - low + 1
        high = low + (r * (cum[d] + freq[d]) // total) - 1
        low = low + (r * cum[d] // total)
        while True:
            if high < HALF:
                writer.write(0)
                for _ in range(pending):
                    writer.write(1)
                pending = 0
            elif low >= HALF:
                writer.write(1)
                for _ in range(pending):
                    writer.write(0)
                pending = 0
                low -= HALF
                high -= HALF
            elif low >= QUARTER and high < 3 * QUARTER:
                pending += 1
                low -= QUARTER
                high -= QUARTER
            else:
                break
            low = (low << 1) & MASK
            high = ((high << 1) & MASK) | 1
    pending += 1
    if low < QUARTER:
        writer.write(0)
        for _ in range(pending):
            writer.write(1)
    else:
        writer.write(1)
        for _ in range(pending):
            writer.write(0)
    writer.flush()
    out = writer.get_bytes()
    model = {'freq': dict(freq), 'total': total, 'precision': PRECISION, 'len': len(data)}
    return out, model

# デコード
def arithmetic_decode(data: bytes, model: Dict) -> List[int]:
    freq = model['freq']
    total = model['total']
    precision = model['precision']
    n = model['len']
    symbols = sorted(freq)
    # 累積分布
    cum = {s: 0 for s in symbols}
    c = 0
    for s in symbols:
        cum[s] = c
        c += freq[s]
    low, high = 0, MASK
    reader = BitReader(data)
    value = 0
    for _ in range(PRECISION):
        value = (value << 1) | reader.read()
    out = []
    for _ in range(n):
        r = high - low + 1
        x = ((value - low + 1) * total - 1) // r
        for s in symbols:
            if cum[s] + freq[s] > x >= cum[s]:
                out.append(s)
                high = low + (r * (cum[s] + freq[s]) // total) - 1
                low = low + (r * cum[s] // total)
                while True:
                    if high < HALF:
                        pass
                    elif low >= HALF:
                        value -= HALF
                        low -= HALF
                        high -= HALF
                    elif low >= QUARTER and high < 3 * QUARTER:
                        value -= QUARTER
                        low -= QUARTER
                        high -= QUARTER
                    else:
                        break
                    low = (low << 1) & MASK
                    high = ((high << 1) & MASK) | 1
                    value = ((value << 1) & MASK) | reader.read()
                break
    return out

class ArithmeticCompressor:
    """算術符号化圧縮クラス"""
    
    def compress(self, data: bytes) -> bytes:
        """
        算術符号化圧縮
        
        Args:
            data: 圧縮するデータ
        
        Returns:
            bytes: 圧縮されたデータ
        """
        if len(data) == 0:
            return b''
        
        # バイトデータを整数リストに変換
        data_list = list(data)
        
        # 算術符号化圧縮
        compressed_data, model = arithmetic_encode(data_list)
        
        # モデル情報をシリアライズ
        model_bytes = pickle.dumps(model, protocol=4)
        
        # 結果を結合（モデルサイズ + モデルデータ + 圧縮データ）
        result = len(model_bytes).to_bytes(4, 'big') + model_bytes + compressed_data
        
        return result
    
    def decompress(self, data: bytes) -> bytes:
        """
        算術符号化解凍
        
        Args:
            data: 圧縮されたデータ
        
        Returns:
            bytes: 解凍されたデータ
        """
        if len(data) == 0:
            return b''
        
        # モデルサイズを読み取り
        model_size = int.from_bytes(data[:4], 'big')
        
        # モデルデータを読み取り
        model_bytes = data[4:4+model_size]
        compressed_data = data[4+model_size:]
        
        # モデル情報をデシリアライズ
        model = pickle.loads(model_bytes)
        
        # 算術符号化解凍
        decompressed_list = arithmetic_decode(compressed_data, model)
        
        # 整数リストをバイトデータに変換
        return bytes(decompressed_list)

# テスト用
if __name__ == "__main__":
    # テストデータ
    test_data = b"This is a test string for arithmetic coding compression. " * 100
    
    print("=== 算術符号化圧縮テスト ===")
    print(f"元データサイズ: {len(test_data):,} bytes")
    
    # 圧縮
    compressor = ArithmeticCompressor()
    compressed = compressor.compress(test_data)
    print(f"圧縮後サイズ: {len(compressed):,} bytes")
    print(f"圧縮率: {(1 - len(compressed) / len(test_data)) * 100:.1f}%")
    
    # 解凍
    decompressed = compressor.decompress(compressed)
    print(f"解凍後サイズ: {len(decompressed):,} bytes")
    print(f"復元成功: {test_data == decompressed}") 