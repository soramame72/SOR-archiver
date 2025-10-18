import os
import struct
from typing import Tuple, Dict, List

class FileTypeDetector:
    """ファイルタイプを自動判別し、最適な圧縮方式を決定するクラス"""
    
    # 既圧縮ファイルの拡張子（圧縮効果が期待できない）
    COMPRESSED_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp',  # 画像
        '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',     # 動画・音声
        '.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz',        # アーカイブ
        '.pdf', '.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp',  # ドキュメント
        '.exe', '.dll', '.so', '.dylib', '.app',                    # 実行ファイル（既に圧縮済みの場合）
    }
    
    # テキストファイルの拡張子
    TEXT_EXTENSIONS = {
        '.txt', '.md', '.py', '.js', '.html', '.css', '.xml', '.json',
        '.csv', '.log', '.ini', '.cfg', '.conf', '.sh', '.bat', '.ps1',
        '.cpp', '.c', '.h', '.java', '.php', '.rb', '.go', '.rs',
        '.sql', '.yaml', '.yml', '.toml', '.lock', '.gitignore'
    }
    
    # 未圧縮バイナリファイルの拡張子
    BINARY_EXTENSIONS = {
        '.exe', '.dll', '.so', '.dylib', '.app', '.bin', '.dat',
        '.obj', '.o', '.a', '.lib', '.pdb', '.map', '.elf'
    }
    
    # ファイルヘッダーマジックナンバー
    MAGIC_HEADERS = {
        # 画像
        b'\xff\xd8\xff': 'JPEG',
        b'\x89PNG\r\n\x1a\n': 'PNG',
        b'GIF87a': 'GIF',
        b'GIF89a': 'GIF',
        b'BM': 'BMP',
        b'II*\x00': 'TIFF',
        b'MM\x00*': 'TIFF',
        
        # 動画・音声
        b'ID3': 'MP3',
        b'\x00\x00\x00\x20ftyp': 'MP4',
        b'RIFF': 'AVI',
        b'\x1a\x45\xdf\xa3': 'MKV',
        
        # アーカイブ
        b'PK\x03\x04': 'ZIP',
        b'Rar!\x1a\x07': 'RAR',
        b'7z\xbc\xaf\x27\x1c': '7ZIP',
        b'\x1f\x8b\x08': 'GZIP',
        b'BZ': 'BZIP2',
        b'\xfd7zXZ\x00': 'XZ',
        
        # ドキュメント
        b'%PDF': 'PDF',
        b'PK\x03\x04': 'DOCX/XLSX/PPTX',  # OfficeファイルもZIPベース
        
        # 実行ファイル
        b'MZ': 'EXE',  # Windows PE
        b'\x7fELF': 'ELF',  # Linux
        b'\xfe\xed\xfa': 'MACHO',  # macOS
    }
    
    @staticmethod
    def detect_file_type(file_path: str) -> Tuple[str, str]:
        """
        ファイルタイプを判別し、最適な圧縮方式を決定
        
        Returns:
            Tuple[str, str]: (ファイルタイプ, 推奨圧縮方式)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ファイルが見つかりません: {file_path}")
        
        # 拡張子ベースの判別
        _, ext = os.path.splitext(file_path.lower())
        
        # 既圧縮ファイルの判別
        if ext in FileTypeDetector.COMPRESSED_EXTENSIONS:
            return "COMPRESSED", "STORE"
        
        # テキストファイルの判別
        if ext in FileTypeDetector.TEXT_EXTENSIONS:
            return "TEXT", "BWT_RLE_MTF_HUFFMAN"
        
        # 未圧縮バイナリの判別
        if ext in FileTypeDetector.BINARY_EXTENSIONS:
            return "BINARY", "LZMA"
        
        # ファイルヘッダーによる判別
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)  # 最初の16バイトを読み取り
                
                for magic, file_type in FileTypeDetector.MAGIC_HEADERS.items():
                    if header.startswith(magic):
                        if file_type in ['JPEG', 'PNG', 'GIF', 'BMP', 'TIFF', 'MP3', 'MP4', 'AVI', 'MKV', 'ZIP', 'RAR', '7ZIP', 'GZIP', 'BZIP2', 'XZ', 'PDF']:
                            return "COMPRESSED", "STORE"
                        elif file_type in ['EXE', 'ELF', 'MACHO']:
                            return "BINARY", "LZMA"
        
        except Exception:
            pass
        
        # 内容ベースの判別（テキストかバイナリか）
        try:
            with open(file_path, 'rb') as f:
                sample = f.read(1024)  # 最初の1KBをサンプル
                
                # テキストファイルの判定（NULLバイトが少なく、印字可能文字が多い）
                null_count = sample.count(b'\x00')
                printable_count = sum(1 for b in sample if 32 <= b <= 126 or b in [9, 10, 13])  # スペース、改行、タブ含む
                
                if null_count < len(sample) * 0.1 and printable_count > len(sample) * 0.7:
                    return "TEXT", "BWT_RLE_MTF_HUFFMAN"
                else:
                    return "BINARY", "LZMA"
                    
        except Exception:
            pass
        
        # デフォルト
        return "UNKNOWN", "LZMA"
    
    @staticmethod
    def get_compression_method(file_type: str, file_size: int) -> str:
        """
        ファイルタイプとサイズに基づいて最適な圧縮方式を決定
        """
        # 一時的に全ファイルでBWT_RLE_MTF_PPMを強制適用
        return "BWT_RLE_MTF_PPM"
    
    @staticmethod
    def analyze_files(file_paths: List[str]) -> Dict[str, Dict]:
        """
        複数ファイルを分析し、圧縮方式を決定
        
        Args:
            file_paths: ファイルパスのリスト
        
        Returns:
            Dict: ファイルごとの分析結果
        """
        results = {}
        
        for file_path in file_paths:
            try:
                file_type, recommended_method = FileTypeDetector.detect_file_type(file_path)
                file_size = os.path.getsize(file_path)
                final_method = FileTypeDetector.get_compression_method(file_type, file_size)
                
                results[file_path] = {
                    'file_type': file_type,
                    'recommended_method': recommended_method,
                    'final_method': final_method,
                    'file_size': file_size,
                    'extension': os.path.splitext(file_path)[1].lower()
                }
                
            except Exception as e:
                results[file_path] = {
                    'error': str(e),
                    'final_method': 'STORE'  # エラー時は無圧縮
                }
        
        return results

# テスト用
if __name__ == "__main__":
    # テストファイルの例
    test_files = [
        "test.txt",
        "test.exe", 
        "test.jpg",
        "test.py",
        "test.zip"
    ]
    
    detector = FileTypeDetector()
    
    for file_path in test_files:
        if os.path.exists(file_path):
            file_type, method = detector.detect_file_type(file_path)
            size = os.path.getsize(file_path)
            final_method = detector.get_compression_method(file_type, size)
            
            print(f"{file_path}:")
            print(f"  タイプ: {file_type}")
            print(f"  推奨方式: {method}")
            print(f"  最終方式: {final_method}")
            print(f"  サイズ: {size:,} bytes")
            print() 