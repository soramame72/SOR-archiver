# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
from compressor import compress_to_sor
from decompressor import decompress_from_sor
import webbrowser
import random
import string
import datetime
import tkinter.font as tkFont
import sys
sys.stderr = open('error.log', 'w')

class SORApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('SOR Archiver')
        self.geometry('700x500')
        self.resizable(False, False)
        self.configure(bg='#ededed')
        self.create_widgets()

    def create_widgets(self):
        # メニューバー
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label='File', menu=self.file_menu)
        self.file_menu.add_command(label='退出', command=self.quit)
        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label='Help', menu=self.help_menu)
        self.help_menu.add_command(label='使い方', command=self.show_usage)
        self.help_menu.add_command(label='情報', command=self.show_info)

        # 2カラムレイアウト
        self.main_frame = tk.Frame(self, bg='#ededed')
        self.main_frame.pack(fill='both', expand=True)

        # 左ペイン（ライブラリ）
        self.left_frame = tk.Frame(self.main_frame, width=200, bg='#e5e5e5')
        self.left_frame.pack(side='left', fill='y')
        self.left_frame.pack_propagate(False)
        # 一番最初のシンプルなロゴ（SOR Archiver、太字・大きめ・中央揃え・装飾なし）
        logo_label = tk.Label(self.left_frame, text='SOR Archiver', font=('Segoe UI', 20, 'bold'), fg='#2563eb', bg='#e5e5e5')
        logo_label.pack(anchor='nw', padx=16, pady=(18, 18))
        tk.Label(self.left_frame, text='メニュー', font=('Segoe UI', 12), bg='#e5e5e5').pack(anchor='nw', padx=16)
        self.mode_var = tk.StringVar(value='compress')
        tk.Radiobutton(self.left_frame, text='圧縮', variable=self.mode_var, value='compress', bg='#e5e5e5', font=('Segoe UI', 11), command=self.switch_mode).pack(anchor='nw', padx=24, pady=(8,0))
        tk.Radiobutton(self.left_frame, text='解凍', variable=self.mode_var, value='decompress', bg='#e5e5e5', font=('Segoe UI', 11), command=self.switch_mode).pack(anchor='nw', padx=24)

        # 右ペイン
        self.right_frame = tk.Frame(self.main_frame, bg='#ededed')
        self.right_frame.pack(side='left', fill='both', expand=True)
        self.center_frame = tk.Frame(self.right_frame, bg='#ededed')
        self.center_frame.place(relx=0.5, rely=0.4, anchor='center')
        self.compress_widgets = []
        self.decompress_widgets = []
        self.create_compress_ui()
        self.create_decompress_ui()
        self.show_mode('compress')

    def create_compress_ui(self):
        # 圧縮UI
        label = tk.Label(self.center_frame, text='圧縮するフォルダを選択', font=('Segoe UI', 13), bg='#ededed')
        label.pack(pady=(0,10))
        self.compress_widgets.append(label)
        # フォルダパス入力欄＋参照ボタン
        path_frame = tk.Frame(self.center_frame, bg='#ededed')
        tk.Label(path_frame, text='フォルダパス:', font=('Segoe UI', 11), bg='#ededed').pack(side='left', padx=(0,3))
        self.compress_folder = tk.StringVar(value='')
        entry = tk.Entry(path_frame, textvariable=self.compress_folder, font=('Segoe UI', 11), width=28)
        entry.pack(side='left', padx=(0,5))
        btn_sel = tk.Button(path_frame, text='参照', font=('Segoe UI', 10), command=self.add_folder)
        btn_sel.pack(side='left')
        path_frame.pack(pady=5)
        self.compress_widgets.extend([path_frame])
        # 出力先パス
        out_frame = tk.Frame(self.center_frame, bg='#ededed')
        tk.Label(out_frame, text='出力先パス:', font=('Segoe UI', 11), bg='#ededed').pack(side='left', padx=(0,3))
        self.compress_out = tk.StringVar(value='')
        out_entry = tk.Entry(out_frame, textvariable=self.compress_out, font=('Segoe UI', 11), width=28)
        out_entry.pack(side='left', padx=(0,5))
        btn_out = tk.Button(out_frame, text='参照', font=('Segoe UI', 10), command=self.select_compress_out)
        btn_out.pack(side='left')
        out_frame.pack(pady=5)
        self.compress_widgets.extend([out_frame])
        # 圧縮開始
        btn_start = tk.Button(self.center_frame, text='圧縮開始', font=('Segoe UI', 12), command=self.start_compress)
        btn_start.pack(pady=(10, 0))
        self.compress_widgets.append(btn_start)
        # ボタンとバーの間にスペース
        self.compress_bar_spacer = tk.Frame(self.center_frame, height=18, bg='#ededed')
        self.compress_bar_spacer.pack()
        self.compress_widgets.append(self.compress_bar_spacer)
        # 進捗バー
        self.progress1 = tk.Canvas(self.center_frame, width=350, height=28, bg='#f7fff7', highlightthickness=1, highlightbackground='black')
        self.progress1.pack(pady=(0, 18))
        self.progress1_bar = self.progress1.create_rectangle(0, 0, 0, 28, fill='#3a8fff', outline='')
        self.progress1_text = self.progress1.create_text(175, 14, text='', fill='#222', font=('Segoe UI', 12, 'bold'))
        self.compress_widgets.append(self.progress1)
        # ステータス
        self.compress_status = tk.Label(self.center_frame, text='準備完了', font=('Segoe UI', 12), bg='#ededed')
        self.compress_status.pack(pady=(10, 15))
        self.compress_widgets.append(self.compress_status)
        # キャンセルボタン（圧縮中のみ表示）
        self.compress_cancel_btn = tk.Button(self.center_frame, text='キャンセル', font=('Segoe UI', 11), command=self.cancel_compress)
        self.compress_widgets.append(self.compress_cancel_btn)
        self.compress_cancel_btn.pack_forget()

    def create_decompress_ui(self):
        # 解凍UI
        label = tk.Label(self.center_frame, text='解凍するアーカイブを選択', font=('Segoe UI', 13), bg='#ededed')
        self.decompress_widgets.append(label)
        # アーカイブパス
        in_frame = tk.Frame(self.center_frame, bg='#ededed')
        tk.Label(in_frame, text='アーカイブパス:', font=('Segoe UI', 11), bg='#ededed').pack(side='left', padx=(0,3))
        self.decomp_file = tk.StringVar(value='')
        in_entry = tk.Entry(in_frame, textvariable=self.decomp_file, font=('Segoe UI', 11), width=28)
        in_entry.pack(side='left', padx=(0,5))
        btn_sel = tk.Button(in_frame, text='参照', font=('Segoe UI', 10), command=self.select_sor)
        btn_sel.pack(side='left')
        in_frame.pack(pady=5)
        self.decompress_widgets.append(in_frame)
        # 出力先パス
        out_frame = tk.Frame(self.center_frame, bg='#ededed')
        tk.Label(out_frame, text='出力先パス:', font=('Segoe UI', 11), bg='#ededed').pack(side='left', padx=(0,3))
        self.decomp_out = tk.StringVar(value='')
        out_entry = tk.Entry(out_frame, textvariable=self.decomp_out, font=('Segoe UI', 11), width=28)
        out_entry.pack(side='left', padx=(0,5))
        btn_out = tk.Button(out_frame, text='参照', font=('Segoe UI', 10), command=self.select_decomp_out)
        btn_out.pack(side='left')
        out_frame.pack(pady=5)
        self.decompress_widgets.append(out_frame)
        # フォルダ名エントリー欄は削除
        # 解凍開始
        btn_start = tk.Button(self.center_frame, text='解凍開始', font=('Segoe UI', 12), command=self.start_decompress)
        self.decompress_widgets.append(btn_start)
        btn_start.pack(pady=(10, 0))
        # ボタンとバーの間にスペース
        self.decompress_bar_spacer = tk.Frame(self.center_frame, height=18, bg='#ededed')
        self.decompress_bar_spacer.pack()
        self.decompress_widgets.append(self.decompress_bar_spacer)
        # 進捗バー
        self.progress2 = tk.Canvas(self.center_frame, width=350, height=28, bg='#f7fff7', highlightthickness=1, highlightbackground='black')
        self.progress2.pack(pady=(0, 18))
        self.progress2_bar = self.progress2.create_rectangle(0, 0, 0, 28, fill='#3a8fff', outline='')
        self.progress2_text = self.progress2.create_text(175, 14, text='', fill='#222', font=('Segoe UI', 12, 'bold'))
        self.decompress_widgets.append(self.progress2)
        # ステータス
        self.decompress_status = tk.Label(self.center_frame, text='準備完了', font=('Segoe UI', 12), bg='#ededed')
        self.decompress_status.pack(pady=(10, 15))
        self.decompress_widgets.append(self.decompress_status)
        # キャンセルボタン（解凍中のみ表示）
        self.decompress_cancel_btn = tk.Button(self.center_frame, text='キャンセル', font=('Segoe UI', 11), command=self.cancel_decompress)
        self.decompress_widgets.append(self.decompress_cancel_btn)
        self.decompress_cancel_btn.pack_forget()

    def show_mode(self, mode):
        for w in self.compress_widgets:
            w.pack_forget()
        for w in self.decompress_widgets:
            w.pack_forget()
        if mode == 'compress':
            for w in self.compress_widgets:
                # 圧縮中以外はキャンセルボタン非表示
                if w == self.compress_cancel_btn:
                    continue
                w.pack()
        else:
            for w in self.decompress_widgets:
                # 解凍中以外はキャンセルボタン非表示
                if w == self.decompress_cancel_btn:
                    continue
                w.pack()

    def show_compress_cancel(self, show=True):
        if show:
            self.compress_cancel_btn.pack(pady=(15, 5))
        else:
            self.compress_cancel_btn.pack_forget()

    def show_decompress_cancel(self, show=True):
        if show:
            self.decompress_cancel_btn.pack(pady=(15, 5))
        else:
            self.decompress_cancel_btn.pack_forget()

    def switch_mode(self):
        self.show_mode(self.mode_var.get())

    def add_folder(self):
        folder = filedialog.askdirectory(title='圧縮するフォルダを選択')
        if folder:
            self.compress_folder.set(folder)
            self.compress_root = folder  # ルートディレクトリを記憶

    def select_compress_out(self):
        out_path = filedialog.asksaveasfilename(defaultextension='.sor', filetypes=[('SOR Archive', '*.sor')])
        if out_path:
            self.compress_out.set(out_path)

    def reset_progress1(self):
        self.progress1.coords(self.progress1_bar, 0, 0, 0, 28)
        self.progress1.itemconfig(self.progress1_text, text='')
    def reset_progress2(self):
        self.progress2.coords(self.progress2_bar, 0, 0, 0, 28)
        self.progress2.itemconfig(self.progress2_text, text='')

    def cancel_compress(self):
        self._compress_cancelled = True
        self.compress_status.config(text='キャンセル中...')

    def cancel_decompress(self):
        self._decompress_cancelled = True
        self.decompress_status.config(text='キャンセル中...')

    def start_compress(self):
        folder = self.compress_folder.get()
        out_path = self.compress_out.get()
        if not folder:
            messagebox.showerror('エラー', '圧縮するフォルダを選択してください')
            return
        if not out_path:
            messagebox.showerror('エラー', '出力先を指定してください')
            return
        self.compress_status.config(text='圧縮中...')
        self.reset_progress1()
        self._compress_cancelled = False
        self.show_compress_cancel(True)
        file_list = []
        for root, _, files in os.walk(folder):
            for f in files:
                abs_path = os.path.join(root, f)
                rel_path = os.path.relpath(abs_path, folder).replace("\\", "/")
                file_list.append(rel_path)
        print('圧縮対象ファイルリスト:', file_list)
        threading.Thread(target=self.do_compress, args=(folder, out_path, file_list), daemon=True).start()

    def do_compress(self, folder, out_path, file_list):
        try:
            from compressor import compress_to_sor
            def progress_callback(current, total):
                if self._compress_cancelled:
                    raise Exception('キャンセルされました')
                percent = int(current / total * 100)
                bar_len = int(350 * current / total)
                self.progress1.coords(self.progress1_bar, 0, 0, bar_len, 28)
                self.progress1.itemconfig(self.progress1_text, text=f'{percent}%')
                self.compress_status.config(text=f'圧縮中...（{current}/{total}）')
            compress_to_sor(file_list, out_path, root_dir=folder, progress_callback=progress_callback)
            self.progress1.coords(self.progress1_bar, 0, 0, 350, 28)
            self.progress1.itemconfig(self.progress1_text, text='完了!')
            self.compress_status.config(text='圧縮完了')
        except Exception as e:
            self.progress1.coords(self.progress1_bar, 0, 0, 350, 28)
            self.progress1.itemconfig(self.progress1_text, text='エラー')
            self.compress_status.config(text='エラー: ' + str(e))
        finally:
            self.show_compress_cancel(False)

    def select_sor(self):
        path = filedialog.askopenfilename(filetypes=[('SOR Archive', '*.sor')])
        if path:
            self.decomp_file.set(path)

    def select_decomp_out(self):
        path = filedialog.askdirectory()
        if path:
            self.decomp_out.set(path)

    def start_decompress(self):
        sor_path = self.decomp_file.get()
        out_dir = self.decomp_out.get()
        if not sor_path:
            messagebox.showerror('エラー', 'アーカイブを選択してください')
            return
        if not out_dir:
            messagebox.showerror('エラー', '出力先を指定してください')
            return
        now = datetime.datetime.now()
        dir_name = 'sor_{:04d}-{:02d}-{:02d}-{:02d}-{:02d}-{:02d}'.format(
            now.year, now.month, now.day, now.hour, now.minute, now.second)
        extract_dir = os.path.join(out_dir, dir_name)
        os.makedirs(extract_dir, exist_ok=True)
        self.decompress_status.config(text='解凍中...')
        self.reset_progress2()
        self._decompress_cancelled = False
        self.show_decompress_cancel(True)
        threading.Thread(target=self.do_decompress, args=(sor_path, extract_dir), daemon=True).start()

    def do_decompress(self, sor_path, out_dir):
        try:
            def progress_callback(current, total):
                if self._decompress_cancelled:
                    raise Exception('キャンセルされました')
                percent = int(current / total * 100)
                bar_len = int(350 * current / total)
                self.progress2.coords(self.progress2_bar, 0, 0, bar_len, 28)
                self.progress2.itemconfig(self.progress2_text, text=f'{percent}%')
                self.decompress_status.config(text=f'解凍中...（{current}/{total}）')
            decompress_from_sor(sor_path, out_dir, progress_callback=progress_callback)
            self.progress2.coords(self.progress2_bar, 0, 0, 350, 28)
            self.progress2.itemconfig(self.progress2_text, text='完了!')
            self.decompress_status.config(text='解凍完了')
        except Exception as e:
            self.progress2.coords(self.progress2_bar, 0, 0, 350, 28)
            self.progress2.itemconfig(self.progress2_text, text='エラー')
            self.decompress_status.config(text='エラー: ' + str(e))
        finally:
            self.show_decompress_cancel(False)

    def show_usage(self):
        usage_text = """【圧縮】\n1. 左の「圧縮」を選択\n2. 「参照」で圧縮したいフォルダを選択\n3. 「参照」で出力先を指定\n4. 「圧縮開始」をクリック\n\n【解凍】\n1. 左の「解凍」を選択\n2. 「参照」で.sorファイルを選択\n3. 「参照」で出力先フォルダを指定\n4. 「解凍開始」をクリック"""
        win = tk.Toplevel(self)
        win.title('使い方')
        win.geometry('500x380')
        win.resizable(False, False)
        tk.Label(win, text='使い方', font=('Segoe UI', 15, 'bold')).pack(pady=(15,10))
        text = tk.Text(win, font=('Segoe UI', 12), wrap='word', height=12, width=54, bg='#f7f7f7')
        text.insert('1.0', usage_text)
        text.config(state='disabled')
        text.pack(padx=15, pady=5, fill='both', expand=True)
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text='閉じる', command=win.destroy, font=('Segoe UI', 12), width=16).pack()

    def show_info(self):
        info_text = """製作者: soramame72\nWebサイト: https://soramame72.22web.org/software/sor/index.html\nVersion: 0.0.2\n\n【リリースノート】\nv0.0.2 2025/01/13\n変更点:\n• LZMA圧縮をRAW形式に変更し、Web版との完全互換性を実現\n• 圧縮率を維持しながら、ブラウザでの解凍が可能に\n• 日本語ファイル名の正しい処理を改善\n• ファイル構造解析の精度向上\n• 解凍時に出力フォルダ名を指定できるように\n\nv0.0.1 2025/07/8\n• 初回リリース\n• 基本的な圧縮・解凍機能\n• GUIインターフェース\n• 複数の圧縮アルゴリズム対応"""
        win = tk.Toplevel(self)
        win.title('情報')
        win.geometry('500x380')
        win.resizable(False, False)
        tk.Label(win, text='情報', font=('Segoe UI', 15, 'bold')).pack(pady=(15,10))
        text = tk.Text(win, font=('Segoe UI', 12), wrap='word', height=12, width=54, bg='#f7f7f7')
        text.insert('1.0', info_text)
        # URL部分にタグを付与
        url = 'https://soramame72.22web.org/software/sor/index.html'
        start_idx = '1.0'
        while True:
            idx = text.search(url, start_idx, stopindex='end')
            if not idx:
                break
            end_idx = f"{idx}+{len(url)}c"
            text.tag_add('url', idx, end_idx)
            start_idx = end_idx
        text.tag_config('url', foreground='blue', underline=1)
        def open_url(event=None):
            import webbrowser
            webbrowser.open(url)
        text.tag_bind('url', '<Button-1>', open_url)
        text.config(state='disabled')
        text.pack(padx=15, pady=5, fill='both', expand=True)
        btn_frame = tk.Frame(win)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text='閉じる', command=win.destroy, font=('Segoe UI', 12), width=16).pack()

if __name__ == '__main__':
    app = SORApp()
    app.mainloop() 