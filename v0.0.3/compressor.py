import struct
import os
import lzma
import hashlib
import pickle
from typing import List, Dict, Tuple
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

class SORCompressor:
    """SORアーカイバ圧縮クラス - 7zip級の高圧縮率を実現"""
    
    def __init__(self):
        self.file_detector = FileTypeDetector()
        self.hash_map = {}  # 重複排除用
    
    def compress_file(self, file_path: str) -> Tuple[bytes, int, int, int]:
        """
        単一ファイルを圧縮
        
        Args:
            file_path: 圧縮するファイルパス
        
        Returns:
            Tuple[bytes, int, int, int]: (圧縮データ, 圧縮方式, ファイルタイプ, 元サイズ)
        """
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
        print(f"ファイル名: {filename}, 拡張子: {ext}, file_type: {file_type} (0=COMPRESSED,1=TEXT,2=BINARY,3=UNKNOWN)")
        
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
            print(f"ファイル種別: TEXT → 全方式を試します")
            candidates.append(("STORE", data))
            for preset in [3, 6, 9]:
                try:
                    lzma_data = LZMACompressor.compress(data, preset=preset)
                    candidates.append((f"LZMA(preset={preset})", lzma_data))
                except Exception as e:
                    print(f"LZMA(preset={preset}) failed: {e}")
            for order in range(4):
                try:
                    ppm_data = self._bwt_rle_mtf_ppm_compress(data, order=order)
                    candidates.append((f"BWT_RLE_MTF_PPM(order={order})", ppm_data))
                except Exception as e:
                    print(f"BWT_RLE_MTF_PPM(order={order}) failed: {e}")
            try:
                huff_data = self._bwt_rle_mtf_huffman_compress(data)
                candidates.append(("BWT_RLE_MTF_HUFFMAN", huff_data))
            except Exception as e:
                print(f"BWT_RLE_MTF_HUFFMAN failed: {e}")
            try:
                arith_data = self._bwt_rle_mtf_arithmetic_compress(data)
                candidates.append(("BWT_RLE_MTF_ARITHMETIC", arith_data))
            except Exception as e:
                print(f"BWT_RLE_MTF_ARITHMETIC failed: {e}")
            try:
                bwt_lzma_data = LZMACompressor.bwt_lzma_compress(data)
                candidates.append(("BWT_LZMA", bwt_lzma_data))
            except Exception as e:
                print(f"BWT_LZMA failed: {e}")
            try:
                pat_data, subst_table = pattern_encode(data)
                pat_lzma = LZMACompressor.compress(pat_data, preset=9)
                # PATTERN_LZMA形式: テーブル長(4) + テーブル(pickle) + LZMA長(4) + LZMAデータ
                import pickle
                table_bytes = pickle.dumps(subst_table)
                table_len = len(table_bytes).to_bytes(4, 'little')
                lzma_len = len(pat_lzma).to_bytes(4, 'little')
                pat_lzma_full = table_len + table_bytes + lzma_len + pat_lzma
                candidates.append(("PATTERN_LZMA", pat_lzma_full))
            except Exception as e:
                print(f"PATTERN_LZMA failed: {e}")
            try:
                huffman = HuffmanCompressor()
                huff_only = huffman.compress(data)
                candidates.append(("HUFFMAN", huff_only))
            except Exception as e:
                print(f"HUFFMAN failed: {e}")
        else:
            # 画像・バイナリ・既圧縮ファイルはLZMA/STOREのみ
            print(f"ファイル種別: BINARY/COMPRESSED/OTHER → LZMA/STOREのみを試します")
            candidates.append(("STORE", data))
            for preset in [3, 6, 9]:
                try:
                    lzma_data = LZMACompressor.compress(data, preset=preset)
                    candidates.append((f"LZMA(preset={preset})", lzma_data))
                except Exception as e:
                    print(f"LZMA(preset={preset}) failed: {e}")
        for name, comp in candidates:
            print(f"{name}: {len(comp)} bytes")
        method, compressed_data = min(candidates, key=lambda x: len(x[1]))
        print(f"Selected: {method}, size={len(compressed_data)} bytes (original={len(data)})")
        if len(compressed_data) >= len(data):
            method = "STORE"
            compressed_data = data
            print(f"Final: STORE selected (圧縮後サイズ >= 元サイズ)")
        method_code = method_code_map.get(method, METHOD_STORE)
        
        # 重複排除チェック
        file_hash = hashlib.sha256(data).digest()
        if file_hash in self.hash_map:
            return b'', METHOD_DUP_REF, file_type, file_size
        
        # 重複排除用にハッシュを保存
        self.hash_map[file_hash] = len(self.hash_map)
        
        return compressed_data, method_code, file_type, file_size
    
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
        
        # Huffman圧縮
        huffman = HuffmanCompressor()
        huffman_data = huffman.compress(mtf_data)
        
        return huffman_data
    
    def _bwt_rle_mtf_arithmetic_compress(self, data: bytes) -> bytes:
        """BWT + RLE + MTF + 算術符号化圧縮"""
        if len(data) == 0:
            return b''
        
        # データサイズが小さい場合は通常の算術符号化
        if len(data) < BWT_BLOCK_SIZE:
            arithmetic = ArithmeticCompressor()
            return arithmetic.compress(data)
        
        # BWTブロック処理（メモリ効率化版）
        bwt_block_data = bwt_encode_block(data, block_size=8*1024)  # 8KBブロック
        
        # RLE圧縮
        rle_data = rle_encode(bwt_block_data)
        
        # MTF変換
        mtf_data = mtf_encode(rle_data)
        
        # 算術符号化
        arithmetic = ArithmeticCompressor()
        arithmetic_data = arithmetic.compress(mtf_data)
        
        return arithmetic_data
    
    def _bwt_rle_mtf_ppm_compress(self, data: bytes, order: int = 0) -> bytes:
        from bwt import bwt_encode_block
        from rle import rle_encode
        from mtf import mtf_encode
        from ppm import ppm_encode
        import pickle
        print('圧縮開始 - 元データ長:', len(data))
        block_size = 8*1024  # bwt.pyのデフォルトと合わせる
        bwt_block = bwt_encode_block(data, block_size=block_size)
        print(f'全BWTブロックデータ長: {len(bwt_block)}')
        block_infos = []
        compressed_datas = []
        # 小さいデータ形式か判定
        if len(data) <= block_size:
            print('小さいデータ形式（1ブロック）として処理')
            # bwt_block: 4バイトインデックス＋本体
            # 8バイト長さヘッダは付与せず、そのままRLE/MTF/PPMに渡す
            rle_data = rle_encode(bwt_block)
            print('RLE後データ長:', len(rle_data), type(rle_data))
            print('RLE後データ内容（最初の20バイト）:', list(rle_data[:20]))
            # MTF
            mtf_data = mtf_encode(bytes(rle_data))
            print('MTF後データ長:', len(mtf_data), type(mtf_data))
            print('MTF後データ内容（最初の20要素）:', list(mtf_data[:20]))
            print('MTF後データ値域:', min(mtf_data) if mtf_data else None, max(mtf_data) if mtf_data else None)
            # PPM
            ppm_bytes, model_info, ppm_model = ppm_encode(mtf_data, order=order)
            print('PPM圧縮後データ長:', len(ppm_bytes), type(ppm_bytes))
            print('PPM圧縮後データ内容（最初の20バイト）:', list(ppm_bytes[:20]))
            block_infos.append({
                'data_len': len(ppm_bytes),
                'model_info': model_info,
                'ppm_model': ppm_model,
                'mtf_len': len(mtf_data),
            })
            compressed_datas.append(ppm_bytes)
            num_blocks = 1
        else:
            # 複数ブロック形式
            num_blocks = int.from_bytes(bwt_block[:4], 'big')
            print(f'BWTブロック数: {num_blocks}')
            pos = 4
            for block_idx in range(num_blocks):
                if pos + 4 > len(bwt_block):
                    print(f'警告: ブロック{block_idx+1}のblock_size読み取り位置が範囲外: pos={pos}')
                    break
                block_size_bytes = int.from_bytes(bwt_block[pos:pos+4], 'big')
                pos += 4
                print(f'ブロック{block_idx+1}: 開始位置={pos}, サイズ={block_size_bytes}')
                if pos + block_size_bytes > len(bwt_block):
                    print(f'警告: ブロック{block_idx+1}のデータが範囲外: pos={pos}, block_size={block_size_bytes}, 全長={len(bwt_block)}')
                    break
                block_data = bwt_block[pos:pos+block_size_bytes]
                pos += block_size_bytes
                bwt_index = int.from_bytes(block_data[:4], 'big')
                print(f'ブロック{block_idx+1}のBWTインデックス: {bwt_index}')
                print('BWTブロックデータ長:', len(block_data), type(block_data))
                print('BWTブロックデータ内容（最初の20バイト）:', list(block_data[:20]))
                # RLE
                rle_data = rle_encode(block_data)
                print('RLE後データ長:', len(rle_data), type(rle_data))
                print('RLE後データ内容（最初の20バイト）:', list(rle_data[:20]))
                # MTF
                mtf_data = mtf_encode(bytes(rle_data))
                print('MTF後データ長:', len(mtf_data), type(mtf_data))
                print('MTF後データ内容（最初の20要素）:', list(mtf_data[:20]))
                print('MTF後データ値域:', min(mtf_data) if mtf_data else None, max(mtf_data) if mtf_data else None)
                # PPM
                ppm_bytes, model_info, ppm_model = ppm_encode(mtf_data, order=order)
                print('PPM圧縮後データ長:', len(ppm_bytes), type(ppm_bytes))
                print('PPM圧縮後データ内容（最初の20バイト）:', list(ppm_bytes[:20]))
                block_infos.append({
                    'data_len': len(ppm_bytes),
                    'model_info': model_info,
                    'ppm_model': ppm_model,
                    'mtf_len': len(mtf_data),
                })
                compressed_datas.append(ppm_bytes)
        # メタデータ作成
        meta = {
            'num_blocks': num_blocks,
            'block_infos': block_infos,
        }
        meta_bytes = pickle.dumps(meta)
        meta_len = len(meta_bytes).to_bytes(4, 'big')
        return meta_len + meta_bytes + b''.join(compressed_datas)

    def _bwt_rle_mtf_ppm_compress_to_bytes(self, data: bytes) -> bytes:
        from bwt import bwt_encode_block
        from rle import rle_encode
        from mtf import mtf_encode
        import pickle
        print('圧縮開始 - 元データ長:', len(data))
        bwt_data = bwt_encode_block(data)
        # 1ブロックの場合も必ずヘッダーを付与
        if len(data) <= 8*1024:
            block = bwt_data
            bwt_data = (1).to_bytes(4, 'big') + len(block).to_bytes(4, 'big') + block
        print('BWT後データ長:', len(bwt_data))
        print('BWT後データ内容（最初の20バイト）:', list(bwt_data[:20]))
        rle_data = rle_encode(bwt_data)
        print('RLE後データ長:', len(rle_data), type(rle_data))
        print('RLEデータ内容（最初の20バイト）:', list(rle_data[:20]))
        mtf_data = mtf_encode(bytes(rle_data))
        print('MTF後データ長:', len(mtf_data), type(mtf_data))
        print('MTFデータ内容（最初の20要素）:', mtf_data[:20])
        # PPM完全スキップ
        mtf_bytes = bytes(mtf_data)
        meta = {'skipped_ppm': True, 'data': mtf_bytes}
        meta_bytes = pickle.dumps(meta)
        meta_len = len(meta_bytes).to_bytes(4, 'big')
        return meta_len + meta_bytes + mtf_bytes

    def compress_to_sor(self, file_paths: List[str], output_path: str, root_dir: str = None, progress_callback=None) -> Dict:
        """
        複数ファイルをSORアーカイブに圧縮
        
        Args:
            file_paths: 圧縮するファイルパスのリスト
            output_path: 出力SORファイルパス
            root_dir: ルートディレクトリの絶対パス
        
        Returns:
            Dict: 圧縮統計情報
        """
        stats = {
            'total_files': len(file_paths),
            'total_original_size': 0,
            'total_compressed_size': 0,
            'file_stats': []
        }
        
        with open(output_path, 'wb') as f:
            # ヘッダー書き込み
            f.write(MAGIC)
            f.write(struct.pack('<I', VERSION))
            f.write(struct.pack('<I', len(file_paths)))
            
            # 各ファイルを圧縮
            for i, file_path in enumerate(file_paths):
                if progress_callback:
                    progress_callback(i+1, len(file_paths))
                try:
                    # 相対パスをSORに格納
                    filename = file_path.encode('utf-8')
                    print('SORに書き込むファイル:', file_path)
                    f.write(struct.pack('<H', len(filename)))
                    f.write(filename)
                    
                    # ファイルタイプ
                    abs_path = os.path.join(root_dir, file_path) if root_dir else file_path
                    file_type_str, _ = self.file_detector.detect_file_type(abs_path)
                    if file_type_str == "TEXT":
                        file_type = FILE_TYPE_TEXT
                    elif file_type_str == "BINARY":
                        file_type = FILE_TYPE_BINARY
                    elif file_type_str == "COMPRESSED":
                        file_type = FILE_TYPE_COMPRESSED
                    else:
                        file_type = FILE_TYPE_UNKNOWN

                    # 圧縮方式選択ロジックをcompress_fileと同じに
                    candidates = []
                    with open(abs_path, 'rb') as file_f:
                        data = file_f.read()
                    print('元ファイル内容（最初の20バイト）:', list(data[:20]), 'ファイル名:', file_path)
                    print('ファイルサイズ:', len(data))
                    original_size = len(data)
                    if file_type == FILE_TYPE_TEXT:
                        print(f"ファイル種別: TEXT → 全方式を試します")
                        candidates.append(("STORE", data))
                        for preset in [3, 6, 9]:
                            try:
                                lzma_data = LZMACompressor.compress(data, preset=preset)
                                candidates.append((f"LZMA(preset={preset})", lzma_data))
                            except Exception as e:
                                print(f"LZMA(preset={preset}) failed: {e}")
                        for order in range(4):
                            try:
                                ppm_data = self._bwt_rle_mtf_ppm_compress(data, order=order)
                                candidates.append((f"BWT_RLE_MTF_PPM(order={order})", ppm_data))
                            except Exception as e:
                                print(f"BWT_RLE_MTF_PPM(order={order}) failed: {e}")
                        try:
                            huff_data = self._bwt_rle_mtf_huffman_compress(data)
                            candidates.append(("BWT_RLE_MTF_HUFFMAN", huff_data))
                        except Exception as e:
                            print(f"BWT_RLE_MTF_HUFFMAN failed: {e}")
                        try:
                            arith_data = self._bwt_rle_mtf_arithmetic_compress(data)
                            candidates.append(("BWT_RLE_MTF_ARITHMETIC", arith_data))
                        except Exception as e:
                            print(f"BWT_RLE_MTF_ARITHMETIC failed: {e}")
                        try:
                            bwt_lzma_data = LZMACompressor.bwt_lzma_compress(data)
                            candidates.append(("BWT_LZMA", bwt_lzma_data))
                        except Exception as e:
                            print(f"BWT_LZMA failed: {e}")
                        try:
                            pat_data, subst_table = pattern_encode(data)
                            pat_lzma = LZMACompressor.compress(pat_data, preset=9)
                            # PATTERN_LZMA形式: テーブル長(4) + テーブル(pickle) + LZMA長(4) + LZMAデータ
                            import pickle
                            table_bytes = pickle.dumps(subst_table)
                            table_len = len(table_bytes).to_bytes(4, 'little')
                            lzma_len = len(pat_lzma).to_bytes(4, 'little')
                            pat_lzma_full = table_len + table_bytes + lzma_len + pat_lzma
                            candidates.append(("PATTERN_LZMA", pat_lzma_full))
                        except Exception as e:
                            print(f"PATTERN_LZMA failed: {e}")
                        try:
                            huffman = HuffmanCompressor()
                            huff_only = huffman.compress(data)
                            candidates.append(("HUFFMAN", huff_only))
                        except Exception as e:
                            print(f"HUFFMAN failed: {e}")
                    else:
                        print(f"ファイル種別: BINARY/COMPRESSED/OTHER → LZMA/STOREのみを試します")
                        candidates.append(("STORE", data))
                        for preset in [3, 6, 9]:
                            try:
                                lzma_data = LZMACompressor.compress(data, preset=preset)
                                candidates.append((f"LZMA(preset={preset})", lzma_data))
                            except Exception as e:
                                print(f"LZMA(preset={preset}) failed: {e}")
                    for name, comp in candidates:
                        print(f"{name}: {len(comp)} bytes")
                    method, compressed_data = min(candidates, key=lambda x: len(x[1]))
                    print(f"Selected: {method}, size={len(compressed_data)} bytes (original={len(data)})")
                    if len(compressed_data) >= len(data):
                        method = "STORE"
                        compressed_data = data
                        print(f"Final: STORE selected (圧縮後サイズ >= 元サイズ)")
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
                    method_code = method_code_map.get(method, METHOD_STORE)
                    
                    # 重複排除チェック
                    file_hash = hashlib.sha256(data).digest()
                    if file_hash in self.hash_map:
                        compressed_data = b''
                        method_code = METHOD_DUP_REF
                    else:
                        # 重複排除用にハッシュを保存
                        self.hash_map[file_hash] = len(self.hash_map)
                        # 圧縮方式はcandidatesから選んだものをそのまま使う
                        # method, compressed_data, method_codeはすでにセット済み
                    
                    # ファイル情報書き込み
                    f.write(struct.pack('<B', int(file_type)))  # ファイルタイプ
                    f.write(struct.pack('<B', int(method_code)))  # 圧縮方式
                    f.write(struct.pack('<I', int(original_size)))  # 元サイズ
                    
                    if method_code == METHOD_DUP_REF:
                        # 重複参照の場合
                        ref_index = self.hash_map[hashlib.sha256(open(abs_path, 'rb').read()).digest()]
                        f.write(struct.pack('<I', ref_index))
                    else:
                        # 圧縮データサイズを必ず書き込む
                        f.write(struct.pack('<I', int(len(compressed_data))))
                        # LZMA圧縮の場合は先頭20バイトをprint
                        if method_code == METHOD_LZMA:
                            print('SOR書き込み直前のLZMAデータ先頭20バイト:', list(compressed_data[:20]))
                        f.write(compressed_data)
                    
                    # 統計情報更新
                    compressed_size = int(len(compressed_data)) if method_code != METHOD_DUP_REF else 0
                    stats['total_original_size'] += int(original_size)
                    stats['total_compressed_size'] += compressed_size
                    
                    file_stat = {
                        'filename': file_path,
                        'file_type': int(file_type),
                        'method': int(method_code),
                        'original_size': int(original_size),
                        'compressed_size': compressed_size,
                        'compression_ratio': (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
                    }
                    stats['file_stats'].append(file_stat)
                    
                except Exception as e:
                    print(f"エラー: {file_path} - {e}")
                    continue
        
        # 全体の圧縮率計算
        if stats['total_original_size'] > 0:
            stats['overall_compression_ratio'] = (1 - stats['total_compressed_size'] / stats['total_original_size']) * 100
        else:
            stats['overall_compression_ratio'] = 0
        
        return stats

# 後方互換性のための関数
def compress_to_sor(file_paths, output_path, root_dir=None, progress_callback=None):
    """従来のcompress_to_sor関数（後方互換性）
    file_paths: ルートディレクトリからの相対パスリスト
    root_dir: ルートディレクトリの絶対パス
    """
    compressor = SORCompressor()
    return compressor.compress_to_sor(file_paths, output_path, root_dir=root_dir, progress_callback=progress_callback)

# テスト用
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print('Usage: python compressor.py output.sor input1 [input2 ...]')
        sys.exit(1)
    
    compressor = SORCompressor()
    stats = compressor.compress_to_sor(sys.argv[2:], sys.argv[1])
    
    print("=== 圧縮完了 ===")
    print(f"総ファイル数: {stats['total_files']}")
    print(f"総元サイズ: {stats['total_original_size']:,} bytes")
    print(f"総圧縮後サイズ: {stats['total_compressed_size']:,} bytes")
    print(f"全体圧縮率: {stats['overall_compression_ratio']:.1f}%")
    
    print("\n=== ファイル別統計 ===")
    for file_stat in stats['file_stats']:
        print(f"{file_stat['filename']}:")
        print(f"  タイプ: {file_stat['file_type']}")
        print(f"  方式: {file_stat['method']}")
        print(f"  元サイズ: {file_stat['original_size']:,} bytes")
        print(f"  圧縮後: {file_stat['compressed_size']:,} bytes")
        print(f"  圧縮率: {file_stat['compression_ratio']:.1f}%")
        print()
 