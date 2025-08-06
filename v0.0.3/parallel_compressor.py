import struct
import os
import lzma
import hashlib
import pickle
from typing import List, Dict, Tuple
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import multiprocessing as mp
from functools import partial
import time
from file_detector import FileTypeDetector
from s_lzma import LZMACompressor
from bwt import bwt_encode, bwt_decode, bwt_encode_block, bwt_decode_block
from rle import rle_encode, rle_decode
from mtf import mtf_encode, mtf_decode
from huffman import HuffmanCompressor
from arithmetic import ArithmeticCompressor
from pattern_subst import pattern_encode, pattern_decode
from ppm import ppm_encode, ppm_decode

# .sorファイルのマジックバイトとバージョン
MAGIC = b'SOR2'  # バージョン2に更新
VERSION = 2

# 圧縮方式の定数
METHOD_STORE = 0           # 無圧縮
METHOD_HUFFMAN = 1         # Huffman符号化のみ
METHOD_BWT_RLE_MTF_HUFFMAN = 2  # BWT + RLE + MTF + Huffman
METHOD_BWT_RLE_MTF_ARITHMETIC = 3  # BWT + RLE + MTF + 算術符号化
METHOD_LZMA = 4            # LZMAのみ
METHOD_BWT_LZMA = 5        # BWT + LZMAハイブリッド
METHOD_PATTERN_LZMA = 6    # パターン置換 + LZMA
METHOD_DUP_REF = 7         # 重複参照
METHOD_BWT_RLE_MTF_PPM = 8  # 新方式: BWT→RLE→MTF→PPM→算術符号化

# ファイルタイプの定数
FILE_TYPE_COMPRESSED = 0   # 既圧縮ファイル
FILE_TYPE_TEXT = 1         # テキストファイル
FILE_TYPE_BINARY = 2       # 未圧縮バイナリ
FILE_TYPE_UNKNOWN = 3      # 不明

# BWTブロックサイズ
BWT_BLOCK_SIZE = 1024 * 1024  # 1MB

class ParallelSORCompressor:
    """並列処理対応SORアーカイバ圧縮クラス"""
    
    def __init__(self, max_workers=None):
        self.file_detector = FileTypeDetector()
        self.hash_map = {}  # 重複排除用
        self.max_workers = max_workers or min(mp.cpu_count(), 8)  # CPU数に応じて調整
        
    def compress_single_file(self, file_info: Tuple[str, str, str]) -> Tuple[str, bytes, int, int, int]:
        """
        単一ファイルを圧縮（並列処理用）
        
        Args:
            file_info: (file_path, root_dir, relative_path) のタプル
        
        Returns:
            Tuple[str, bytes, int, int, int]: (ファイルパス, 圧縮データ, 圧縮方式, ファイルタイプ, 元サイズ)
        """
        file_path, root_dir, relative_path = file_info
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")
        
        filename = os.path.basename(file_path)
        ext = os.path.splitext(filename)[1].lower()
        text_exts = {'.txt', '.csv', '.tsv', '.json', '.xml', '.html', '.htm', '.md', '.py', '.c', '.cpp', '.java', '.js', '.css', '.ini', '.conf', '.log'}
        image_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff'}
        compressed_exts = {'.zip', '.rar', '.7z', '.gz', '.bz2', '.xz', '.lzma', '.mp3', '.mp4', '.avi', '.mov', '.flac', '.ogg', '.pdf'}
        
        # ファイルデータ読み込み
        with open(file_path, 'rb') as f:
            data = f.read()
        file_size = len(data)
        
        # ファイルタイプ判定
        if ext in text_exts:
            file_type = FILE_TYPE_TEXT
        elif ext in image_exts:
            file_type = FILE_TYPE_BINARY
        elif ext in compressed_exts:
            file_type = FILE_TYPE_COMPRESSED
        else:
            # その他は内容で判定
            null_count = data.count(b'\x00')
            printable_count = sum(1 for b in data[:1024] if 32 <= b <= 126 or b in [9, 10, 13])
            if null_count < len(data[:1024]) * 0.1 and printable_count > len(data[:1024]) * 0.7:
                file_type = FILE_TYPE_TEXT
            else:
                file_type = FILE_TYPE_BINARY
        
        candidates = []
        method_code_map = {
            "STORE": METHOD_STORE,
            "LZMA(preset=3)": METHOD_LZMA,
            "LZMA(preset=6)": METHOD_LZMA,
            "LZMA(preset=9)": METHOD_LZMA,
            "BWT_RLE_MTF_PPM(order=0)": METHOD_BWT_RLE_MTF_PPM,
            "BWT_RLE_MTF_PPM(order=1)": METHOD_BWT_RLE_MTF_PPM,
            "BWT_RLE_MTF_PPM(order=2)": METHOD_BWT_RLE_MTF_PPM,
            "BWT_RLE_MTF_PPM(order=3)": METHOD_BWT_RLE_MTF_PPM,
            "BWT_RLE_MTF_HUFFMAN": METHOD_BWT_RLE_MTF_HUFFMAN,
            "BWT_RLE_MTF_ARITHMETIC": METHOD_BWT_RLE_MTF_ARITHMETIC,
            "BWT_LZMA": METHOD_BWT_LZMA,
            "PATTERN_LZMA": METHOD_PATTERN_LZMA,
            "HUFFMAN": METHOD_HUFFMAN,
            "ARITHMETIC": METHOD_BWT_RLE_MTF_ARITHMETIC,
        }
        
        # 圧縮方式選択ロジック
        if file_type == FILE_TYPE_TEXT:
            candidates.append(("STORE", data))
            for preset in [3, 6, 9]:
                try:
                    lzma_data = LZMACompressor.compress(data, preset=preset)
                    candidates.append((f"LZMA(preset={preset})", lzma_data))
                except Exception as e:
                    pass
            for order in range(4):
                try:
                    ppm_data = self._bwt_rle_mtf_ppm_compress(data, order=order)
                    candidates.append((f"BWT_RLE_MTF_PPM(order={order})", ppm_data))
                except Exception as e:
                    pass
            try:
                huff_data = self._bwt_rle_mtf_huffman_compress(data)
                candidates.append(("BWT_RLE_MTF_HUFFMAN", huff_data))
            except Exception as e:
                pass
            try:
                arith_data = self._bwt_rle_mtf_arithmetic_compress(data)
                candidates.append(("BWT_RLE_MTF_ARITHMETIC", arith_data))
            except Exception as e:
                pass
            try:
                bwt_lzma_data = LZMACompressor.bwt_lzma_compress(data)
                candidates.append(("BWT_LZMA", bwt_lzma_data))
            except Exception as e:
                pass
            try:
                pat_data, subst_table = pattern_encode(data)
                pat_lzma = LZMACompressor.compress(pat_data, preset=9)
                import pickle
                table_bytes = pickle.dumps(subst_table)
                table_len = len(table_bytes).to_bytes(4, 'little')
                lzma_len = len(pat_lzma).to_bytes(4, 'little')
                pat_lzma_full = table_len + table_bytes + lzma_len + pat_lzma
                candidates.append(("PATTERN_LZMA", pat_lzma_full))
            except Exception as e:
                pass
            try:
                huffman = HuffmanCompressor()
                huff_only = huffman.compress(data)
                candidates.append(("HUFFMAN", huff_only))
            except Exception as e:
                pass
        else:
            # 画像・バイナリ・既圧縮ファイルはLZMA/STOREのみ
            candidates.append(("STORE", data))
            for preset in [3, 6, 9]:
                try:
                    lzma_data = LZMACompressor.compress(data, preset=preset)
                    candidates.append((f"LZMA(preset={preset})", lzma_data))
                except Exception as e:
                    pass
        
        method, compressed_data = min(candidates, key=lambda x: len(x[1]))
        if len(compressed_data) >= len(data):
            method = "STORE"
            compressed_data = data
        
        method_code = method_code_map.get(method, METHOD_STORE)
        
        # 重複排除チェック
        file_hash = hashlib.sha256(data).digest()
        if file_hash in self.hash_map:
            return relative_path, b'', METHOD_DUP_REF, file_type, file_size
        
        # 重複排除用にハッシュを保存
        self.hash_map[file_hash] = len(self.hash_map)
        
        return relative_path, compressed_data, method_code, file_type, file_size
    
    def _bwt_rle_mtf_huffman_compress(self, data: bytes) -> bytes:
        """BWT + RLE + MTF + Huffman圧縮"""
        if len(data) == 0:
            return b''
        
        # データサイズが小さい場合は通常のHuffman
        if len(data) < 8*1024:
            huffman = HuffmanCompressor()
            return huffman.compress(data)
        
        # BWTブロック処理（メモリ効率化版）
        bwt_block_data = bwt_encode_block(data, block_size=8*1024)  # 8KBブロック
        
        # RLE圧縮
        rle_data = rle_encode(bwt_block_data)
        
        # MTF変換
        mtf_data = mtf_encode(rle_data)
        
        # Huffman符号化
        huffman = HuffmanCompressor()
        return huffman.compress(mtf_data)
    
    def _bwt_rle_mtf_arithmetic_compress(self, data: bytes) -> bytes:
        """BWT + RLE + MTF + 算術符号化"""
        if len(data) == 0:
            return b''
        
        # BWTブロック処理
        bwt_block_data = bwt_encode_block(data, block_size=8*1024)
        
        # RLE圧縮
        rle_data = rle_encode(bwt_block_data)
        
        # MTF変換
        mtf_data = mtf_encode(rle_data)
        
        # 算術符号化
        arithmetic = ArithmeticCompressor()
        return arithmetic.compress(mtf_data)
    
    def _bwt_rle_mtf_ppm_compress(self, data: bytes, order: int = 0) -> bytes:
        """BWT + RLE + MTF + PPM圧縮"""
        if len(data) == 0:
            return b''
        
        # BWTブロック処理
        bwt_block_data = bwt_encode_block(data, block_size=8*1024)
        
        # RLE圧縮
        rle_data = rle_encode(bwt_block_data)
        
        # MTF変換
        mtf_data = mtf_encode(rle_data)
        
        # PPM予測
        ppm_bytes, model_info, model = ppm_encode(mtf_data, order=order)
        
        # 算術符号化で最終圧縮
        arithmetic = ArithmeticCompressor()
        return arithmetic.compress(ppm_bytes)
    
    def compress_to_sor_parallel(self, file_paths: List[str], output_path: str, root_dir: str = None, progress_callback=None) -> Dict:
        """
        並列処理で複数ファイルをSORアーカイブに圧縮
        
        Args:
            file_paths: 圧縮するファイルパスのリスト
            output_path: 出力SORファイルパス
            root_dir: ルートディレクトリの絶対パス
            progress_callback: 進捗コールバック関数
        
        Returns:
            Dict: 圧縮統計情報
        """
        start_time = time.time()
        
        stats = {
            'total_files': len(file_paths),
            'total_original_size': 0,
            'total_compressed_size': 0,
            'file_stats': [],
            'processing_time': 0,
            'parallel_workers': self.max_workers
        }
        
        # ファイル情報を準備
        file_infos = []
        for file_path in file_paths:
            abs_path = os.path.join(root_dir, file_path) if root_dir else file_path
            file_infos.append((abs_path, root_dir, file_path))
        
        # 並列処理でファイルを圧縮
        compressed_files = []
        completed = 0
        
        print(f"並列処理開始: {self.max_workers}個のワーカーを使用")
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # 各ファイルの圧縮を並列実行
            future_to_file = {executor.submit(self.compress_single_file, file_info): file_info for file_info in file_infos}
            
            # 完了したファイルを処理
            for future in as_completed(future_to_file):
                try:
                    relative_path, compressed_data, method_code, file_type, original_size = future.result()
                    compressed_files.append((relative_path, compressed_data, method_code, file_type, original_size))
                    
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(file_paths))
                    
                    print(f"圧縮完了: {relative_path} ({completed}/{len(file_paths)})")
                    
                except Exception as e:
                    print(f"圧縮エラー: {e}")
        
        # 結果をソート（元の順序を保持）
        compressed_files.sort(key=lambda x: file_paths.index(x[0]))
        
        # SORファイルに書き込み
        with open(output_path, 'wb') as f:
            # ヘッダー書き込み
            f.write(MAGIC)
            f.write(struct.pack('<I', VERSION))
            f.write(struct.pack('<I', len(compressed_files)))
            
            # 各ファイルを書き込み
            for relative_path, compressed_data, method_code, file_type, original_size in compressed_files:
                # ファイル名
                filename = relative_path.encode('utf-8')
                f.write(struct.pack('<H', len(filename)))
                f.write(filename)
                
                # 圧縮データ
                f.write(struct.pack('<I', method_code))
                f.write(struct.pack('<I', file_type))
                f.write(struct.pack('<Q', original_size))
                f.write(struct.pack('<I', len(compressed_data)))
                f.write(compressed_data)
                
                # 統計情報を更新
                stats['total_original_size'] += original_size
                stats['total_compressed_size'] += len(compressed_data)
                stats['file_stats'].append({
                    'path': relative_path,
                    'original_size': original_size,
                    'compressed_size': len(compressed_data),
                    'method': method_code,
                    'compression_ratio': len(compressed_data) / original_size if original_size > 0 else 1.0
                })
        
        stats['processing_time'] = time.time() - start_time
        stats['compression_ratio'] = stats['total_compressed_size'] / stats['total_original_size'] if stats['total_original_size'] > 0 else 1.0
        
        print(f"並列圧縮完了: {stats['processing_time']:.2f}秒")
        print(f"圧縮率: {stats['compression_ratio']:.2%}")
        print(f"使用ワーカー数: {self.max_workers}")
        
        return stats

def compress_to_sor_parallel(file_paths, output_path, root_dir=None, progress_callback=None, max_workers=None):
    """
    並列処理でSORアーカイブに圧縮する関数
    
    Args:
        file_paths: 圧縮するファイルパスのリスト
        output_path: 出力SORファイルパス
        root_dir: ルートディレクトリの絶対パス
        progress_callback: 進捗コールバック関数
        max_workers: 並列ワーカー数（Noneの場合は自動設定）
    
    Returns:
        Dict: 圧縮統計情報
    """
    compressor = ParallelSORCompressor(max_workers=max_workers)
    return compressor.compress_to_sor_parallel(file_paths, output_path, root_dir, progress_callback)

# 並列処理の性能テスト用関数
def benchmark_parallel_compression(test_files, output_dir, max_workers_list=[1, 2, 4, 8]):
    """
    並列処理の性能をベンチマーク
    
    Args:
        test_files: テストファイルのリスト
        output_dir: 出力ディレクトリ
        max_workers_list: テストするワーカー数のリスト
    """
    results = {}
    
    for max_workers in max_workers_list:
        print(f"\n=== {max_workers}ワーカーでのテスト ===")
        
        output_path = os.path.join(output_dir, f"test_parallel_{max_workers}.sor")
        
        start_time = time.time()
        stats = compress_to_sor_parallel(test_files, output_path, progress_callback=None, max_workers=max_workers)
        end_time = time.time()
        
        results[max_workers] = {
            'processing_time': stats['processing_time'],
            'compression_ratio': stats['compression_ratio'],
            'total_original_size': stats['total_original_size'],
            'total_compressed_size': stats['total_compressed_size']
        }
        
        print(f"処理時間: {stats['processing_time']:.2f}秒")
        print(f"圧縮率: {stats['compression_ratio']:.2%}")
        print(f"元サイズ: {stats['total_original_size']:,}バイト")
        print(f"圧縮後サイズ: {stats['total_compressed_size']:,}バイト")
    
    # 結果の比較
    print("\n=== 性能比較 ===")
    baseline_time = results[1]['processing_time']
    for workers, result in results.items():
        speedup = baseline_time / result['processing_time']
        print(f"{workers}ワーカー: {result['processing_time']:.2f}秒 (速度向上: {speedup:.2f}x)")

if __name__ == "__main__":
    # 使用例
    test_files = [
        "test_files/sample.txt",
        "test_files/sample.py",
        "test_files/sample.c",
        "test_files/sample.bin"
    ]
    
    # 並列圧縮の実行
    stats = compress_to_sor_parallel(test_files, "test_parallel.sor", max_workers=4)
    print(f"並列圧縮結果: {stats}") 