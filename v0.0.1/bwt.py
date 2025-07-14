from typing import Tuple
import heapq

def bwt_encode(data):
    n = len(data)
    if n == 0:
        return b'', 0
    if n < 1000:
        indices = list(range(n))
        def get_rotation(i):
            return data[i:] + data[:i]
        indices.sort(key=lambda i: get_rotation(i))
        last_column = bytes([data[(i - 1) % n] for i in indices])
        original_index = indices.index(0)
        return last_column, original_index
    return bwt_encode_simple(data)

def bwt_encode_simple(data):
    n = len(data)
    if n == 0:
        return b'', 0
    indices = list(range(n))
    def get_rotation(i):
        return data[i:] + data[:i]
    indices.sort(key=lambda i: get_rotation(i))
    last_column = bytes([data[(i - 1) % n] for i in indices])
    original_index = indices.index(0)
    return last_column, original_index

def bwt_encode_block(data, block_size=8*1024):
    if len(data) == 0:
        return b''
    if len(data) <= block_size:
        bwt_data, bwt_index = bwt_encode(data)
        return int(bwt_index).to_bytes(4, 'big') + bwt_data
    compressed_blocks = []
    total_size = len(data)
    for i in range(0, total_size, block_size):
        block = data[i:i + block_size]
        bwt_data, bwt_index = bwt_encode(block)
        block_info = int(bwt_index).to_bytes(4, 'big') + bwt_data
        compressed_blocks.append(block_info)
    result = len(compressed_blocks).to_bytes(4, 'big')
    for block in compressed_blocks:
        result += len(block).to_bytes(4, 'big') + block
    return result

def bwt_decode(data, index):
    n = len(data)
    if n == 0:
        return b''
    # 1. 各文字の出現回数
    count = [0] * 256
    for byte in data:
        count[byte] += 1
    # 2. 累積和
    tot = 0
    cum_count = [0] * 256
    for i in range(256):
        cum_count[i] = tot
        tot += count[i]
    # 3. LF-mapping
    occ = [0] * 256
    lf = [0] * n
    for i in range(n):
        b = data[i]
        lf[i] = cum_count[b] + occ[b]
        occ[b] += 1
    # 4. 復元
    res = bytearray(n)
    p = index
    for i in range(n-1, -1, -1):
        res[i] = data[p]
        p = lf[p]
    return bytes(res)

def bwt_decode_block(data):
    if len(data) == 0:
        return b''
    if len(data) < 4:
        raise ValueError("Invalid BWT block data")
    # 小さいデータ形式（1ブロック）の場合
    if len(data) > 4:
        # 先頭4バイトをbwt_indexとして扱い、残りをbwt_dataとする
        bwt_index = int.from_bytes(data[:4], 'big')
        bwt_data = data[4:]
        if bwt_index < len(bwt_data):
            return bwt_decode(bwt_data, bwt_index)
    # 複数ブロック形式
    num_blocks = int.from_bytes(data[:4], 'big')
    pos = 4
    decompressed_blocks = []
    for _ in range(num_blocks):
        if pos + 4 > len(data):
            raise ValueError("Invalid BWT block data")
        block_size = int.from_bytes(data[pos:pos+4], 'big')
        pos += 4
        if pos + block_size > len(data):
            raise ValueError("Invalid BWT block data")
        block_data = data[pos:pos+block_size]
        pos += block_size
        bwt_index = int.from_bytes(block_data[:4], 'big')
        bwt_data = block_data[4:]
        original_block = bwt_decode(bwt_data, bwt_index)
        decompressed_blocks.append(original_block)
    return b''.join(decompressed_blocks)

if __name__ == "__main__":
    test_data = b"banana"
    print("元データ: {}".format(test_data))
    bwt_data, bwt_index = bwt_encode(test_data)
    print("BWT後: {} インデックス: {}".format(bwt_data, bwt_index))
    decoded = bwt_decode(bwt_data, bwt_index)
    print("復元後: {}".format(decoded))
    print("復元成功: {}".format(test_data == decoded))
    large_data = b"This is a test for block processing. " * 100
    print("\n大きなデータ（{} bytes）でブロック処理テスト:".format(len(large_data)))
    try:
        block_compressed = bwt_encode_block(large_data, block_size=1024)
        block_decompressed = bwt_decode_block(block_compressed)
        print("ブロック処理成功: {}".format(large_data == block_decompressed))
        print("圧縮後サイズ: {} bytes".format(len(block_compressed)))
    except Exception as e:
        print("ブロック処理エラー: {}".format(e)) 