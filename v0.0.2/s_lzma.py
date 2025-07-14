import lzma
import bwt
import rle
from typing import Tuple, Optional

class LZMACompressor:
    """LZMA圧縮クラス - 7zip級の高圧縮率を実現"""
    
    @staticmethod
    def compress(data: bytes, preset: int = 9, filters: Optional[list] = None) -> bytes:
        """
        LZMA圧縮（LZMA-JS互換形式で出力）
        Args:
            data: 圧縮するデータ
            preset: 圧縮レベル (0-9, 9が最高圧縮率)
            filters: カスタムフィルター設定
        Returns:
            bytes: 圧縮されたデータ
        """
        # LZMA-JS互換のフィルタ設定
        if filters is None:
            filters = [{
                'id': lzma.FILTER_LZMA1,
                'preset': preset
            }]
        
        # LZMA RAW形式で圧縮（ヘッダーなし）
        compressed_data = lzma.compress(data, format=lzma.FORMAT_RAW, filters=filters)
        
        # LZMA-JS互換のヘッダーを手動で構築
        # プロパティバイト: lc + lp * 9 + pb * 45
        prop_byte = 3 + 0 * 9 + 2 * 45  # lc=3, lp=0, pb=2
        
        # 辞書サイズ: 8MiB (0x800000)
        dict_size = 1 << 23  # 8MiB
        dict_size_bytes = dict_size.to_bytes(4, 'little')
        
        # データサイズ（リトルエンディアン）
        data_size_bytes = len(data).to_bytes(8, 'little')
        
        # LZMA-JS互換形式: プロパティバイト + 辞書サイズ + データサイズ + 圧縮データ
        result = bytes([prop_byte]) + dict_size_bytes + data_size_bytes + compressed_data
        
        return result

    @staticmethod
    def decompress(data: bytes, filters: Optional[list] = None) -> bytes:
        """
        LZMA解凍（LZMA-JS互換形式）
        Args:
            data: 圧縮されたデータ
            filters: カスタムフィルター設定（通常はNoneでOK）
        Returns:
            bytes: 解凍されたデータ
        """
        if len(data) < 13:  # プロパティバイト(1) + 辞書サイズ(4) + データサイズ(8)
            raise ValueError("Invalid LZMA data: too short")
        
        # ヘッダーを解析
        prop_byte = data[0]
        dict_size = int.from_bytes(data[1:5], 'little')
        original_size = int.from_bytes(data[5:13], 'little')
        compressed_data = data[13:]
        
        # フィルターを構築
        if filters is None:
            lc = prop_byte % 9
            lp = (prop_byte // 9) % 5
            pb = (prop_byte // 45) % 5
            
            filters = [{
                'id': lzma.FILTER_LZMA1,
                'dict_size': dict_size,
                'lc': lc,
                'lp': lp,
                'pb': pb
            }]
        
        return lzma.decompress(compressed_data, format=lzma.FORMAT_RAW, filters=filters)
    
    @staticmethod
    def bwt_lzma_compress(data: bytes, bwt_block_size: int = 1024*1024, lzma_preset: int = 9) -> bytes:
        """
        BWT + LZMA ハイブリッド圧縮（テキスト・バイナリに最適）
        
        Args:
            data: 圧縮するデータ
            bwt_block_size: BWTブロックサイズ（バイト）
            lzma_preset: LZMA圧縮レベル
        
        Returns:
            bytes: 圧縮されたデータ
        """
        if len(data) == 0:
            return b''
        
        # データサイズが小さい場合は通常のLZMA
        if len(data) < bwt_block_size:
            return LZMACompressor.compress(data, preset=lzma_preset)
        
        # BWTブロック処理
        compressed_blocks = []
        total_size = len(data)
        
        for i in range(0, total_size, bwt_block_size):
            block = data[i:i + bwt_block_size]
            
            # BWT変換
            bwt_data, bwt_index = bwt.bwt_encode(block)
            
            # RLE圧縮
            rle_data = rle.rle_encode(bwt_data)
            
            # LZMA圧縮
            lzma_data = LZMACompressor.compress(rle_data, preset=lzma_preset)
            
            # ブロック情報を保存（BWTインデックス + 圧縮データ）
            block_info = bwt_index.to_bytes(4, 'big') + lzma_data
            compressed_blocks.append(block_info)
        
        # 全ブロックを結合
        result = len(compressed_blocks).to_bytes(4, 'big')  # ブロック数
        for block in compressed_blocks:
            result += len(block).to_bytes(4, 'big') + block  # ブロックサイズ + ブロックデータ
        
        return result
    
    @staticmethod
    def bwt_lzma_decompress(data: bytes) -> bytes:
        """
        BWT + LZMA ハイブリッド解凍
        
        Args:
            data: 圧縮されたデータ
        
        Returns:
            bytes: 解凍されたデータ
        """
        if len(data) == 0:
            return b''
        
        # ブロック数を読み取り
        if len(data) < 4:
            raise ValueError("Invalid compressed data")
        
        num_blocks = int.from_bytes(data[:4], 'big')
        pos = 4
        
        decompressed_blocks = []
        
        for _ in range(num_blocks):
            # ブロックサイズを読み取り
            if pos + 4 > len(data):
                raise ValueError("Invalid compressed data")
            
            block_size = int.from_bytes(data[pos:pos+4], 'big')
            pos += 4
            
            # ブロックデータを読み取り
            if pos + block_size > len(data):
                raise ValueError("Invalid compressed data")
            
            block_data = data[pos:pos+block_size]
            pos += block_size
            
            # BWTインデックスを読み取り
            bwt_index = int.from_bytes(block_data[:4], 'big')
            lzma_data = block_data[4:]
            
            # LZMA解凍
            rle_data = LZMACompressor.decompress(lzma_data)
            
            # RLE解凍
            bwt_data = rle.rle_decode(rle_data)
            
            # BWT逆変換
            original_block = bwt.bwt_decode(bwt_data, bwt_index)
            
            decompressed_blocks.append(original_block)
        
        # 全ブロックを結合
        return b''.join(decompressed_blocks)
    
    @staticmethod
    def get_compression_info(data: bytes, method: str = "LZMA") -> dict:
        """
        圧縮情報を取得
        
        Args:
            data: 元データ
            method: 圧縮方式
        
        Returns:
            dict: 圧縮情報
        """
        original_size = len(data)
        
        if method == "LZMA":
            compressed_data = LZMACompressor.compress(data, preset=9)
        elif method == "BWT_LZMA":
            compressed_data = LZMACompressor.bwt_lzma_compress(data)
        else:
            raise ValueError(f"Unknown compression method: {method}")
        
        compressed_size = len(compressed_data)
        compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
        
        return {
            'original_size': original_size,
            'compressed_size': compressed_size,
            'compression_ratio': compression_ratio,
            'method': method
        }

# 後方互換性のための関数
def lzma_compress(data: bytes) -> bytes:
    """従来のLZMA圧縮関数（後方互換性）"""
    return LZMACompressor.compress(data, preset=9)

def lzma_decompress(data: bytes) -> bytes:
    """従来のLZMA解凍関数（後方互換性）"""
    return LZMACompressor.decompress(data)

# テスト用
if __name__ == "__main__":
    # テストデータ
    test_text = b"This is a test text for compression. " * 1000
    test_binary = b'\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09' * 1000
    
    print("=== LZMA圧縮テスト ===")
    
    # 通常のLZMA
    lzma_compressed = LZMACompressor.compress(test_text, preset=9)
    lzma_decompressed = LZMACompressor.decompress(lzma_compressed)
    
    print(f"テキスト - 元サイズ: {len(test_text):,} bytes")
    print(f"テキスト - LZMA圧縮後: {len(lzma_compressed):,} bytes")
    print(f"テキスト - 圧縮率: {(1 - len(lzma_compressed) / len(test_text)) * 100:.1f}%")
    print(f"テキスト - 復元成功: {test_text == lzma_decompressed}")
    
    # BWT+LZMAハイブリッド
    bwt_lzma_compressed = LZMACompressor.bwt_lzma_compress(test_text)
    bwt_lzma_decompressed = LZMACompressor.bwt_lzma_decompress(bwt_lzma_compressed)
    
    print(f"テキスト - BWT+LZMA圧縮後: {len(bwt_lzma_compressed):,} bytes")
    print(f"テキスト - BWT+LZMA圧縮率: {(1 - len(bwt_lzma_compressed) / len(test_text)) * 100:.1f}%")
    print(f"テキスト - BWT+LZMA復元成功: {test_text == bwt_lzma_decompressed}")
    
    print()
    
    # バイナリデータのテスト
    lzma_binary_compressed = LZMACompressor.compress(test_binary, preset=9)
    bwt_lzma_binary_compressed = LZMACompressor.bwt_lzma_compress(test_binary)
    
    print(f"バイナリ - 元サイズ: {len(test_binary):,} bytes")
    print(f"バイナリ - LZMA圧縮後: {len(lzma_binary_compressed):,} bytes")
    print(f"バイナリ - LZMA圧縮率: {(1 - len(lzma_binary_compressed) / len(test_binary)) * 100:.1f}%")
    print(f"バイナリ - BWT+LZMA圧縮後: {len(bwt_lzma_binary_compressed):,} bytes")
    print(f"バイナリ - BWT+LZMA圧縮率: {(1 - len(bwt_lzma_binary_compressed) / len(test_binary)) * 100:.1f}%") 