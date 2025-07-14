import struct
import os

def check_sor_file(filename):
    with open(filename, 'rb') as f:
        magic = f.read(4)
        version = struct.unpack('<I', f.read(4))[0]
        count = struct.unpack('<I', f.read(4))[0]
        print(f'Magic: {magic}, Version: {version}, Count: {count}')
        
        for i in range(count):
            name_len = struct.unpack('<H', f.read(2))[0]
            try:
                name = f.read(name_len).decode('utf-8')
            except UnicodeDecodeError:
                name = f"file_{i+1}"
                f.read(name_len)  # スキップ
            file_type = f.read(1)[0]
            method = f.read(1)[0]
            size = struct.unpack('<I', f.read(4))[0]
            print(f'File {i+1}: {name}, Type: {file_type}, Method: {method}, Size: {size}')

if __name__ == '__main__':
    downloads_path = os.path.expanduser("~/Downloads")
    latest_sor = os.path.join(downloads_path, "54w.sor")
    check_sor_file(latest_sor) 