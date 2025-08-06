from typing import List, Tuple, Dict, Any
import heapq
from collections import Counter

class Node:
    def __init__(self, symbol=None, freq=0, left=None, right=None):
        self.symbol = symbol
        self.freq = freq
        self.left = left
        self.right = right
    def __lt__(self, other):
        return self.freq < other.freq

def build_huffman_tree(data: List[int]) -> Node:
    freq = Counter(data)
    heap = [Node(symbol=s, freq=f) for s, f in freq.items()]
    heapq.heapify(heap)
    while len(heap) > 1:
        n1 = heapq.heappop(heap)
        n2 = heapq.heappop(heap)
        merged = Node(freq=n1.freq + n2.freq, left=n1, right=n2)
        heapq.heappush(heap, merged)
    return heap[0] if heap else None

def build_code_table(node: Node, prefix: str = '', table: Dict[int, str] = None) -> Dict[int, str]:
    if table is None:
        table = {}
    if node.symbol is not None:
        table[node.symbol] = prefix or '0'
    else:
        build_code_table(node.left, prefix + '0', table)
        build_code_table(node.right, prefix + '1', table)
    return table

def serialize_tree(node: Node) -> Any:
    if node.symbol is not None:
        return ('L', node.symbol)
    return ('I', serialize_tree(node.left), serialize_tree(node.right))

def deserialize_tree(obj: Any) -> Node:
    if obj[0] == 'L':
        return Node(symbol=obj[1])
    return Node(left=deserialize_tree(obj[1]), right=deserialize_tree(obj[2]))

def serialize_tree_bin(node) -> bytes:
    out = bytearray()
    def _ser(n):
        if n.symbol is not None:
            out.append(1)
            sym = n.symbol if isinstance(n.symbol, int) else int(n.symbol)
            if 0 <= sym <= 254:
                out.append(sym)
            else:
                out.append(255)
                out.extend(sym.to_bytes(2, 'little'))
        else:
            out.append(0)
            _ser(n.left)
            _ser(n.right)
    _ser(node)
    return bytes(out)

def deserialize_tree_bin(data: bytes) -> 'Node':
    idx = [0]
    def _des():
        if data[idx[0]] == 1:
            idx[0] += 1
            if data[idx[0]] < 255:
                sym = data[idx[0]]
                idx[0] += 1
            else:
                idx[0] += 1
                sym = int.from_bytes(data[idx[0]:idx[0]+2], 'little')
                idx[0] += 2
            return Node(symbol=sym)
        else:
            idx[0] += 1
            left = _des()
            right = _des()
            return Node(left=left, right=right)
    return _des()

def huffman_encode(data: List[int]) -> Tuple[bytes, Dict, Node]:
    tree = build_huffman_tree(data)
    code_table = build_code_table(tree)
    # エンコード
    bitstr = ''.join(code_table[sym] for sym in data)
    # 8ビットごとにまとめてバイト列に
    padding = (8 - len(bitstr) % 8) % 8
    bitstr += '0' * padding
    b = bytearray()
    for i in range(0, len(bitstr), 8):
        b.append(int(bitstr[i:i+8], 2))
    # 木とパディング情報をdictで返す
    tree_dict = {'tree': serialize_tree(tree), 'padding': padding}
    return bytes(b), tree_dict, tree

def huffman_decode(data: bytes, tree: Dict) -> List[int]:
    root = deserialize_tree(tree['tree'])
    padding = tree['padding']
    # バイト列をビット列に
    bitstr = ''.join(f'{byte:08b}' for byte in data)
    if padding:
        bitstr = bitstr[:-padding]
    # 復号
    result = []
    node = root
    for bit in bitstr:
        node = node.left if bit == '0' else node.right
        if node.symbol is not None:
            result.append(node.symbol)
            node = root
    return result

class HuffmanCompressor:
    """Huffman圧縮クラス"""
    
    def compress(self, data: bytes) -> bytes:
        """
        Huffman圧縮
        
        Args:
            data: 圧縮するデータ
        
        Returns:
            bytes: 圧縮されたデータ
        """
        if len(data) == 0:
            return b''
        
        # バイトデータを整数リストに変換
        data_list = list(data)
        
        # Huffman圧縮
        compressed_data, tree_dict, _ = huffman_encode(data_list)
        
        # 木情報をシリアライズ
        import pickle
        tree_bytes = pickle.dumps(tree_dict, protocol=4)
        
        # 結果を結合（木サイズ + 木データ + 圧縮データ）
        result = len(tree_bytes).to_bytes(4, 'big') + tree_bytes + compressed_data
        
        return result
    
    def decompress(self, data: bytes) -> bytes:
        """
        Huffman解凍
        
        Args:
            data: 圧縮されたデータ
        
        Returns:
            bytes: 解凍されたデータ
        """
        if len(data) == 0:
            return b''
        
        # 木サイズを読み取り
        tree_size = int.from_bytes(data[:4], 'big')
        
        # 木データを読み取り
        tree_bytes = data[4:4+tree_size]
        compressed_data = data[4+tree_size:]
        
        # 木情報をデシリアライズ
        import pickle
        tree_dict = pickle.loads(tree_bytes)
        
        # Huffman解凍
        decompressed_list = huffman_decode(compressed_data, tree_dict)
        
        # 整数リストをバイトデータに変換
        return bytes(decompressed_list)

# テスト用
if __name__ == "__main__":
    # テストデータ
    test_data = b"This is a test string for Huffman compression. " * 100
    
    print("=== Huffman圧縮テスト ===")
    print(f"元データサイズ: {len(test_data):,} bytes")
    
    # 圧縮
    compressor = HuffmanCompressor()
    compressed = compressor.compress(test_data)
    print(f"圧縮後サイズ: {len(compressed):,} bytes")
    print(f"圧縮率: {(1 - len(compressed) / len(test_data)) * 100:.1f}%")
    
    # 解凍
    decompressed = compressor.decompress(compressed)
    print(f"解凍後サイズ: {len(decompressed):,} bytes")
    print(f"復元成功: {test_data == decompressed}") 