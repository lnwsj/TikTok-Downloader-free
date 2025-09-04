# tiktok_downloader_gui.py
"""
TikTok Downloader (GUI, Python + yt-dlp)

คุณสมบัติ
- โหลดจาก "ช่อง/โปรไฟล์" (เช่น https://www.tiktok.com/@yourname) ทั้งชุด
- หรือวาง "ลิงก์วิดีโอหลายลิงก์" ทีละบรรทัด
- เลือกโฟลเดอร์ปลายทาง, จำกัดจำนวนคลิปสูงสุด, เลือกคุณภาพ (Best / 1080p / 720p / MP4 only)
- รองรับ cookies.txt (ไว้โหลดคลิปส่วนตัว/จำกัดอายุ) และไฟล์บันทึกกันโหลดซ้ำ (download archive)
- แสดง log และสถานะความคืบหน้า

ติดตั้งครั้งแรก:
    pip install yt-dlp
(ถ้าต้องรวมไฟล์วิดีโอ+เสียงหรือแปลงเป็น MP4 คุณภาพสูง แนะนำติดตั้ง ffmpeg เพิ่ม)

ข้อควรทราบ:
- โปรดใช้กับคอนเทนต์ของคุณเอง หรือได้รับอนุญาตให้ดาวน์โหลด และปฏิบัติตามเงื่อนไขการใช้งานของ TikTok
"""
import os
import threading
import queue
from pathlib import Path
from typing import List, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.scrolledtext as scrolledtext

# ตรวจสอบ yt-dlp
try:
    import yt_dlp as ytdlp
except Exception as e:
    raise SystemExit("กรุณาติดตั้ง yt-dlp ก่อน: pip install yt-dlp")

APP_TITLE = "TikTok Downloader — yt-dlp GUI"

class TikTokDLGUI:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("980x700")
        root.minsize(920, 640)

        # UI state
        self.profile_url = tk.StringVar(value="")
        self.out_dir = tk.StringVar(value="")
        self.max_videos = tk.IntVar(value=0)  # 0 = ไม่จำกัด
        self.quality = tk.StringVar(value="Best (auto)")
        self.use_archive = tk.BooleanVar(value=True)
        self.archive_path = tk.StringVar(value="")
        self.cookies_path = tk.StringVar(value="")
        self.stop_flag = False
        self.worker: Optional[threading.Thread] = None
        self.q = queue.Queue()

        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        pad = {'padx': 10, 'pady': 6}
        frm = ttk.Frame(self.root); frm.pack(fill='both', expand=True)

        # Row: output folder
        r_out = ttk.Frame(frm); r_out.pack(fill='x', **pad)
        ttk.Label(r_out, text="โฟลเดอร์ปลายทาง:").pack(side='left')
        ttk.Entry(r_out, textvariable=self.out_dir).pack(side='left', fill='x', expand=True, padx=6)
        ttk.Button(r_out, text="Browse…", command=self.pick_out).pack(side='left')

        # Row: profile
        r_prof = ttk.Frame(frm); r_prof.pack(fill='x', **pad)
        ttk.Label(r_prof, text="โปรไฟล์/ช่อง (URL):").pack(side='left')
        ttk.Entry(r_prof, textvariable=self.profile_url).pack(side='left', fill='x', expand=True, padx=6)

        # Row: URLs box
        r_url = ttk.Labelframe(frm, text="หรือ วางลิงก์วิดีโอ (ทีละบรรทัด)")
        r_url.pack(fill='both', expand=False, **pad)
        self.urls_box = scrolledtext.ScrolledText(r_url, height=6)
        self.urls_box.pack(fill='both', expand=True, padx=8, pady=6)

        # Options
        opt = ttk.Labelframe(frm, text="ตัวเลือก")
        opt.pack(fill='x', **pad)

        o1 = ttk.Frame(opt); o1.pack(fill='x', padx=10, pady=4)
        ttk.Label(o1, text="คุณภาพ:").pack(side='left')
        ttk.Combobox(o1, textvariable=self.quality, width=18, state='readonly',
                     values=["Best (auto)","Max 1080p","Max 720p","MP4 only"]).pack(side='left', padx=6)
        ttk.Label(o1, text="จำกัดจำนวน (0 = ไม่จำกัด):").pack(side='left', padx=12)
        ttk.Spinbox(o1, from_=0, to=10000, textvariable=self.max_videos, width=7).pack(side='left')

        o2 = ttk.Frame(opt); o2.pack(fill='x', padx=10, pady=4)
        ttk.Checkbutton(o2, text="ใช้ Download Archive (กันโหลดซ้ำ)", variable=self.use_archive,
                        command=self._toggle_archive).pack(side='left')
        ttk.Entry(o2, textvariable=self.archive_path, width=40).pack(side='left', padx=6)
        ttk.Button(o2, text="เลือกไฟล์…", command=self.pick_archive).pack(side='left', padx=4)

        o3 = ttk.Frame(opt); o3.pack(fill='x', padx=10, pady=4)
        ttk.Label(o3, text="cookies.txt (ถ้าคลิปส่วนตัว/จำกัดสิทธิ์):").pack(side='left')
        ttk.Entry(o3, textvariable=self.cookies_path, width=40).pack(side='left', padx=6)
        ttk.Button(o3, text="เลือกไฟล์…", command=self.pick_cookies).pack(side='left', padx=4)

        # Progress
        prog = ttk.Labelframe(frm, text="ความคืบหน้า")
        prog.pack(fill='x', **pad)
        self.pb = ttk.Progressbar(prog, mode='indeterminate')
        self.pb.pack(fill='x', padx=10, pady=6)
        self.status = ttk.Label(prog, text="พร้อมทำงาน")
        self.status.pack(side='left', padx=10, pady=4)
        ttk.Button(prog, text="เริ่มดาวน์โหลด", command=self.start).pack(side='right', padx=8)
        ttk.Button(prog, text="ยกเลิก", command=self.stop).pack(side='right', padx=8)

        # Log
        logf = ttk.Labelframe(frm, text="Log")
        logf.pack(fill='both', expand=True, **pad)
        self.log = scrolledtext.ScrolledText(logf, height=12, state='disabled')
        self.log.pack(fill='both', expand=True, padx=8, pady=6)

        # default archive path
        self._toggle_archive(init=True)

    def _toggle_archive(self, init: bool=False):
        if not self.archive_path.get():
            out = self.out_dir.get() or "."
            self.archive_path.set(str(Path(out) / "downloaded_archive.txt"))

    def pick_out(self):
        d = filedialog.askdirectory(title="เลือกโฟลเดอร์ปลายทาง")
        if d:
            self.out_dir.set(d)
            self._toggle_archive()

    def pick_archive(self):
        p = filedialog.asksaveasfilename(title="เลือก/ตั้งชื่อไฟล์ Archive",
                                         defaultextension=".txt",
                                         filetypes=[("Text", "*.txt")],
                                         initialfile="downloaded_archive.txt")
        if p:
            self.archive_path.set(p)

    def pick_cookies(self):
        p = filedialog.askopenfilename(title="เลือก cookies.txt",
                                       filetypes=[("Cookies txt","*.txt"),("All","*.*")])
        if p:
            self.cookies_path.set(p)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        out_dir = Path(self.out_dir.get() or ".")
        out_dir.mkdir(parents=True, exist_ok=True)
        profile = self.profile_url.get().strip()
        url_lines = [u.strip() for u in self.urls_box.get("1.0","end").strip().splitlines() if u.strip()]

        if not profile and not url_lines:
            messagebox.showinfo("ยังไม่มี URL", "กรุณาใส่โปรไฟล์ TikTok หรือวางลิงก์วิดีโอ")
            return

        self.stop_flag = False
        self.pb.start(12)
        self.status.config(text="กำลังเริ่มดาวน์โหลด…")
        self._log("Start")

        self.worker = threading.Thread(target=self._run_download, args=(profile, url_lines, out_dir), daemon=True)
        self.worker.start()

    def stop(self):
        self.stop_flag = True
        self._log("ขอหยุดหลังจบไฟล์ปัจจุบัน…")
        self.status.config(text="กำลังยกเลิกเมื่อจบไฟล์นี้…")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log.configure(state='normal')
                    self.log.insert('end', payload + "\n")
                    self.log.see('end')
                    self.log.configure(state='disabled')
                elif kind == "status":
                    self.status.config(text=payload)
                elif kind == "stop":
                    self.pb.stop()
        except queue.Empty:
            pass
        self.root.after(120, self._poll_queue)

    def _log(self, msg: str):
        self.q.put(("log", msg))

    def _status(self, msg: str):
        self.q.put(("status", msg))

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            speed = d.get('_speed_str', '')
            eta = d.get('eta')
            eta_str = f" ETA {eta}s" if eta is not None else ""
            self._status(f"กำลังดาวน์โหลด… {speed}{eta_str}")
        elif d['status'] == 'finished':
            self._status("กำลัง post-process/บันทึกไฟล์…")
        if self.stop_flag:
            raise ytdlp.utils.DownloadError("ผู้ใช้ยกเลิก (stop at end of current item)")

    def _format_selector(self) -> str:
        q = self.quality.get()
        if q == "Max 1080p":
            return "bv*[height<=1080]+ba/b[height<=1080]"
        if q == "Max 720p":
            return "bv*[height<=720]+ba/b[height<=720]"
        if q == "MP4 only":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        return "bestvideo*+bestaudio/best"  # Best (auto)

    def _build_ydl_opts(self, out_dir: Path) -> dict:
        outtmpl = str(out_dir / "%(uploader)s/%(upload_date)s_%(title).80B_%(id)s.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "format": self._format_selector(),
            "noplaylist": False,
            "ignoreerrors": True,
            "progress_hooks": [self._progress_hook],
            "retries": 5,
            "concurrent_fragment_downloads": 5,
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ],
        }
        if self.cookies_path.get().strip():
            ydl_opts["cookiefile"] = self.cookies_path.get().strip()
        if self.use_archive.get():
            ydl_opts["download_archive"] = self.archive_path.get().strip()
        mv = int(self.max_videos.get() or 0)
        if mv > 0:
            ydl_opts["playlistend"] = mv
        return ydl_opts

    def _run_download(self, profile: str, url_lines: List[str], out_dir: Path):
        try:
            ydl_opts = self._build_ydl_opts(out_dir)

            targets: List[str] = []
            if profile:
                targets.append(profile)
            if url_lines:
                targets.extend(url_lines)

            self._log(f"Output: {out_dir}")
            self._log(f"Format: {ydl_opts['format']}")
            if ydl_opts.get("cookiefile"):
                self._log(f"ใช้ cookies: {ydl_opts['cookiefile']}")
            if ydl_opts.get("download_archive"):
                self._log(f"ใช้ archive: {ydl_opts['download_archive']}")

            with ytdlp.YoutubeDL(ydl_opts) as ydl:
                for idx, url in enumerate(targets, start=1):
                    if self.stop_flag:
                        break
                    self._log(f"[{idx}/{len(targets)}] {url}")
                    try:
                        ydl.download([url])
                    except Exception as e:
                        self._log(f"✗ ERROR: {e}")

            self._status("เสร็จสิ้น")
        finally:
            self.q.put(("stop", ""))

def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root); style.theme_use("clam")
    except Exception:
        pass
    app = TikTokDLGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
