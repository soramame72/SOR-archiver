import struct
import os
import lzma
import pickle
from typing import Dict, List, Tuple
from s_lzma import LZMACompressor
from bwt import bwt_decode, bwt_decode_block
from rle import rle_decode
from mtf import mtf_decode
from huffman import HuffmanCompressor
from arithmetic import ArithmeticCompressor
from pattern_subst import pattern_decode
from ppm import ppm_encode, ppm_decode
import re

# .sorファイルのマジックバイトとバージョン
MAGIC = b'SOR2'
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

# 後方互換性のための定数
MAGIC_V1 = b'SOR1'
TYPE_TEXT = 1
TYPE_UNCOMP_IMG = 2
TYPE_COMP_IMG = 3
TYPE_BINARY = 4
METHOD_BWT_RLE_LZMA = 5
METHOD_STORE_V1 = 6
METHOD_DUP_REF_V1 = 7
METHOD_PATTERN_LZMA_V1 = 8

def sanitize_filename(name):
    # パス区切りで分割し、各ファイル名部分だけサニタイズ
    parts = name.split('/')
    safe_parts = []
    for part in parts:
        # Windows禁止文字: : * ? " < > | および制御文字（/と\\は除外）
        part = re.sub(r'[:*?"<>|\\\x00-\x1F]', '_', part)
        part = part.strip(' .')
        safe_parts.append(part)
    return os.path.join(*safe_parts)

class SORDecompressor:
    """SORアーカイバ解凍クラス"""
    
    def __init__(self):
        self.decompressed_files = {}  # 重複参照用
    
    def decompress_file(self, f, method_code: int, original_size: int) -> bytes:
        """
        単一ファイルを解凍
        
        Args:
            f: ファイルオブジェクト
            method_code: 圧縮方式コード
            original_size: 元ファイルサイズ
        
        Returns:
            bytes: 解凍されたデータ
        """
        if method_code == METHOD_STORE:
            # 無圧縮
            compressed_size = struct.unpack('<I', f.read(4))[0]
            return f.read(compressed_size)
            
        elif method_code == METHOD_HUFFMAN:
            # Huffman符号化
            compressed_size = struct.unpack('<I', f.read(4))[0]
            compressed_data = f.read(compressed_size)
            huffman = HuffmanCompressor()
            return huffman.decompress(compressed_data)
            
        elif method_code == METHOD_BWT_RLE_MTF_HUFFMAN:
            # BWT + RLE + MTF + Huffman
            return self._bwt_rle_mtf_huffman_decompress(f)
            
        elif method_code == METHOD_BWT_RLE_MTF_ARITHMETIC:
            # BWT + RLE + MTF + 算術符号化
            return self._bwt_rle_mtf_arithmetic_decompress(f)
            
        elif method_code == METHOD_LZMA:
            # LZMA
            compressed_size = struct.unpack('<I', f.read(4))[0]
            compressed_data = f.read(compressed_size)
            return LZMACompressor.decompress(compressed_data)
            
        elif method_code == METHOD_BWT_LZMA:
            # BWT + LZMAハイブリッド
            compressed_size = struct.unpack('<I', f.read(4))[0]
            compressed_data = f.read(compressed_size)
            return LZMACompressor.bwt_lzma_decompress(compressed_data)
            
        elif method_code == METHOD_PATTERN_LZMA:
            # パターン置換 + LZMA
            table_len = struct.unpack('<I', f.read(4))[0]
            table_bytes = f.read(table_len)
            subst_table = pickle.loads(table_bytes)
            lzma_size = struct.unpack('<I', f.read(4))[0]
            lzma_data = f.read(lzma_size)
            pat_data = LZMACompressor.decompress(lzma_data)
            return pattern_decode(pat_data, subst_table)[:original_size]
            
        elif method_code == METHOD_DUP_REF:
            # 重複参照
            ref_index = struct.unpack('<I', f.read(4))[0]
            if ref_index in self.decompressed_files:
                return self.decompressed_files[ref_index]
            else:
                raise ValueError(f"参照ファイルが見つかりません: {ref_index}")
            
        elif method_code == METHOD_BWT_RLE_MTF_PPM:
            compressed_size = struct.unpack('<I', f.read(4))[0]
            compressed_data = f.read(compressed_size)
            return self._bwt_rle_mtf_ppm_decompress_from_bytes(compressed_data, original_size)
                
        else:
            raise ValueError(f"未知の圧縮方式: {method_code}")
    
    def _bwt_rle_mtf_huffman_decompress(self, f):
        compressed_size = struct.unpack('<I', f.read(4))[0]
        compressed_data = f.read(compressed_size)
        huffman = HuffmanCompressor()
        mtf_data = huffman.decompress(compressed_data)
        rle_data = mtf_decode(mtf_data)
        bwt_block_data = rle_decode(rle_data)
        original = bwt_decode_block(bwt_block_data)
        return original
    
    def _bwt_rle_mtf_arithmetic_decompress(self, f) -> bytes:
        """BWT + RLE + MTF + 算術符号化解凍"""
        # 圧縮データを読み取り
        compressed_size = struct.unpack('<I', f.read(4))[0]
        compressed_data = f.read(compressed_size)
        
        # 算術符号化解凍
        arithmetic = ArithmeticCompressor()
        mtf_data = arithmetic.decompress(compressed_data)
        
        # MTF逆変換
        rle_data = mtf_decode(mtf_data)
        
        # RLE解凍
        bwt_block_data = rle_decode(bytes(rle_data))
        
        # BWTブロック逆変換
        original = bwt_decode_block(bwt_block_data)
        
        return original
    
    def _bwt_rle_mtf_ppm_decompress_from_bytes(self, data: bytes, original_size: int) -> bytes:
        import pickle
        print('解凍開始 - 圧縮データ長:', len(data))
        meta_len = int.from_bytes(data[:4], 'big')
        meta_bytes = data[4:4+meta_len]
        meta = pickle.loads(meta_bytes)
        block_infos = meta['block_infos']
        num_blocks = meta['num_blocks']
        compressed_data = data[4+meta_len:]
        pos = 0
        restored_blocks = []
        for i, block_meta in enumerate(block_infos):
            data_len = block_meta['data_len']
            model_info = block_meta['model_info']
            ppm_model = block_meta['ppm_model']
            mtf_len = block_meta['mtf_len']
            enc_bytes = compressed_data[pos:pos+data_len]
            pos += data_len
            print(f'--- ブロック{i+1}/{num_blocks} ---')
            from ppm import ppm_decode_to_list
            mtf_data_list = ppm_decode_to_list(enc_bytes, model_info, ppm_model)
            print('PPMデコード後MTFデータ長:', len(mtf_data_list), type(mtf_data_list))
            print('PPMデコード後MTFデータ内容（最初の20要素）:', mtf_data_list[:20])
            print('PPMデコード後MTFデータ値域:', min(mtf_data_list) if mtf_data_list else None, max(mtf_data_list) if mtf_data_list else None)
            from mtf import mtf_decode_to_list
            rle_data = mtf_decode_to_list(mtf_data_list)
            print('MTFデコード後RLEデータ長:', len(rle_data), type(rle_data))
            print('MTFデコード後RLEデータ内容（最初の20要素）:', rle_data[:20])
            from rle import rle_decode
            bwt_block_data = rle_decode(bytes(rle_data))
            print('RLEデコード後BWTデータ長:', len(bwt_block_data), type(bwt_block_data))
            print('RLEデコード後BWTデータ内容（最初の20バイト）:', list(bwt_block_data[:20]))
            restored_blocks.append(bwt_block_data)
        # BWTブロック形式に再構成
        if num_blocks == 1:
            # 1ブロック形式: 4バイトインデックス＋本体
            block = restored_blocks[0]
            bwt_block = block  # そのまま
        else:
            bwt_block = num_blocks.to_bytes(4, 'big')
            for block in restored_blocks:
                bwt_block += len(block).to_bytes(4, 'big') + block
        print('BWTデコード直前データ（最初の20バイト）:', list(bwt_block[:20]))
        from bwt import bwt_decode_block
        original = bwt_decode_block(bwt_block)
        print('BWTデコード後元データ長:', len(original), '期待値:', original_size)
        print('BWTデコード後元データ内容（最初の20バイト）:', list(original[:20]))
        return original[:original_size]
    
    def decompress_from_sor(self, sor_path: str, output_dir: str, progress_callback=None) -> Dict:
        stats = {
            'total_files': 0,
            'total_original_size': 0,
            'total_decompressed_size': 0,
            'file_stats': []
        }
        with open(sor_path, 'rb') as f:
            magic = f.read(4)
            if magic == MAGIC:
                version = struct.unpack('<I', f.read(4))[0]
                file_count = struct.unpack('<I', f.read(4))[0]
                is_v2 = True
            elif magic == MAGIC_V1:
                file_count = struct.unpack('<I', f.read(4))[0]
                is_v2 = False
            else:
                raise ValueError('Not a valid SOR file')
            print('SORファイル内のファイル数:', file_count)
            stats['total_files'] = file_count
            for i in range(file_count):
                filename = None
                try:
                    name_len = struct.unpack('<H', f.read(2))[0]
                    filename_bytes = f.read(name_len)
                    try:
                        filename = sanitize_filename(filename_bytes.decode('utf-8'))
                    except Exception as e:
                        print(f"ファイル名デコードエラー: {filename_bytes} - {e}")
                        stats['file_stats'].append({'filename': str(filename_bytes), 'error': str(e)})
                        continue
                    print('解凍するファイル:', filename)
                    if is_v2:
                        file_type = struct.unpack('<B', f.read(1))[0]
                        method_code = struct.unpack('<B', f.read(1))[0]
                        original_size = struct.unpack('<I', f.read(4))[0]
                    else:
                        file_type = struct.unpack('<B', f.read(1))[0]
                        original_size = struct.unpack('<I', f.read(4))[0]
                        method_code = struct.unpack('<B', f.read(1))[0]
                    data = self.decompress_file(f, method_code, original_size)
                    self.decompressed_files[i] = data
                    out_path = os.path.join(output_dir, filename)
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    print('書き出しデータ長:', len(data), 'ファイル名:', filename)
                    print('書き出しデータ内容（最初の20バイト）:', list(data[:20]), 'ファイル名:', filename)
                    if not data:
                        print('警告: 書き出しデータが空です:', filename)
                    with open(out_path, 'wb') as fout:
                        fout.write(data)
                    print('書き出しファイル絶対パス:', os.path.abspath(out_path))
                    decompressed_size = len(data)
                    stats['total_original_size'] += original_size
                    stats['total_decompressed_size'] += decompressed_size
                    file_stat = {
                        'filename': filename,
                        'file_type': file_type,
                        'method': method_code,
                        'original_size': original_size,
                        'decompressed_size': decompressed_size,
                        'restored': original_size == decompressed_size
                    }
                    stats['file_stats'].append(file_stat)
                except Exception as e:
                    print(f"エラー: {filename} - {e}")
                    stats['file_stats'].append({
                        'filename': filename,
                        'file_type': None,
                        'method': None,
                        'original_size': None,
                        'decompressed_size': 0,
                        'restored': False,
                        'error': str(e)
                    })
                    continue
                if progress_callback:
                    progress_callback(i+1, file_count)
        return stats

# 後方互換性のための関数
def decompress_from_sor(sor_path, output_dir, progress_callback=None):
    """従来のdecompress_from_sor関数（後方互換性）"""
    decompressor = SORDecompressor()
    return decompressor.decompress_from_sor(sor_path, output_dir, progress_callback)

# テスト用
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: python decompressor.py input.sor output_dir')
        sys.exit(1)
    
    decompressor = SORDecompressor()
    stats = decompressor.decompress_from_sor(sys.argv[1], sys.argv[2])
    
    print("=== 解凍完了 ===")
    print(f"総ファイル数: {stats['total_files']}")
    print(f"総元サイズ: {stats['total_original_size']:,} bytes")
    print(f"総解凍後サイズ: {stats['total_decompressed_size']:,} bytes")
    
    print("\n=== ファイル別統計 ===")
    for file_stat in stats['file_stats']:
        print(f"{file_stat['filename']}:")
        print(f"  タイプ: {file_stat['file_type']}")
        print(f"  方式: {file_stat['method']}")
        print(f"  元サイズ: {file_stat['original_size']:,} bytes")
        print(f"  解凍後: {file_stat['decompressed_size']:,} bytes")
        print(f"  復元成功: {file_stat['restored']}")
        print()
 