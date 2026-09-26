#!/usr/bin/env python3
"""
mapgen_app.py -- Meridian Map Generator: pick a style, a size, a folder and a
map name, then Generate.  The map it made is drawn in the window.

The room's box spans -X/2..X/2 left to right and -Y/2..Y/2 down to up; the map
fits inside it without having to fill it.  There are no size ranges in the
window: a size is only refused when the generator, the .roo format or the server
genuinely cannot handle it, and the message says which and why.

Generation runs on a worker thread with a large stack (deep BSP trees on huge
maps); the window polls a queue for the result, so tkinter is only touched from
the main thread.

Run:    python roomedit/roogen/mapgen_app.py
Build:  powershell -File roomedit/roogen/build_mapgen.ps1
"""
import json
import os
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import preview  # noqa: E402
import styles  # noqa: E402
from roofile import Room  # noqa: E402

DEFAULT_SIZE = 3136
STACK_MB = 200             # CPython on Windows refuses thread stacks over 256 MB
PREVIEW = 340
BAD_NAME_CHARS = '\\/:*?"<>|'

INK = "#1f2430"
MUTED = "#6b7280"
EDGE = "#d4d7de"
PANEL = "#f7f8fa"

SETTINGS = os.path.join(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()),
                        "MeridianMapGenerator", "settings.json")


def load_settings():
    try:
        with open(SETTINGS) as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        with open(SETTINGS, "w") as fh:
            json.dump(data, fh)
    except Exception:
        pass                                   # remembering is a convenience, not a requirement


class App:
    def __init__(self, root):
        self.root = root
        self.results = queue.Queue()
        self.image = None
        self.busy = False
        self.preview_path = os.path.join(tempfile.gettempdir(), "meridian_mapgen_preview.png")
        saved = load_settings()
        root.title("Meridian Map Generator")
        root.resizable(False, False)
        root.configure(background=PANEL)

        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=INK)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 15), foreground=INK)
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=MUTED)
        style.configure("Field.TLabel", font=("Segoe UI", 9), foreground=MUTED)
        style.configure("Status.TLabel", font=("Segoe UI", 9), foreground=INK)
        style.configure("Go.TButton", font=("Segoe UI Semibold", 10), padding=(0, 7))

        outer = ttk.Frame(root, padding=(18, 14, 18, 16))
        outer.grid(sticky="nsew")
        outer.grid_columnconfigure(0, minsize=PREVIEW)

        ttk.Label(outer, text="Meridian Map Generator", style="Title.TLabel").grid(
            row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(outer, text="Generates a Meridian 59 room (.roo) to open in the room editor.",
                  style="Sub.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 12))

        # -- style
        ttk.Label(outer, text="STYLE", style="Field.TLabel").grid(row=2, column=0, sticky="w")
        self.style_var = tk.StringVar(value=saved.get("style") if saved.get("style") in styles.names()
                                      else styles.names()[0])
        ttk.Combobox(outer, textvariable=self.style_var, values=styles.names(), state="readonly",
                     font=("Segoe UI", 10)).grid(row=3, column=0, columnspan=4, sticky="we", pady=(2, 10))

        # -- size
        ttk.Label(outer, text="SIZE", style="Field.TLabel").grid(row=4, column=0, sticky="w")
        size_row = ttk.Frame(outer)
        size_row.grid(row=5, column=0, columnspan=4, sticky="we", pady=(2, 2))
        self.x = tk.StringVar(value=str(saved.get("x", DEFAULT_SIZE)))
        self.y = tk.StringVar(value=str(saved.get("y", DEFAULT_SIZE)))
        ttk.Spinbox(size_row, textvariable=self.x, from_=1, to=styles.MAX_SPAN, increment=64,
                    width=9, font=("Segoe UI", 10)).pack(side="left")
        ttk.Label(size_row, text="×", font=("Segoe UI", 11)).pack(side="left", padx=8)
        ttk.Spinbox(size_row, textvariable=self.y, from_=1, to=styles.MAX_SPAN, increment=64,
                    width=9, font=("Segoe UI", 10)).pack(side="left")
        ttk.Label(size_row, text="editor units", style="Sub.TLabel").pack(side="left", padx=(10, 0))
        ttk.Label(outer, text="The room spans -X/2 to X/2 and -Y/2 to Y/2, centred on 0,0.",
                  style="Sub.TLabel").grid(row=6, column=0, columnspan=4, sticky="w", pady=(0, 10))

        # -- folder
        ttk.Label(outer, text="SAVE IN", style="Field.TLabel").grid(row=7, column=0, sticky="w")
        folder_row = ttk.Frame(outer)
        folder_row.grid(row=8, column=0, columnspan=4, sticky="we", pady=(2, 10))
        self.folder = tk.StringVar(value=saved.get("folder") or os.path.join(
            os.path.expanduser("~"), "Desktop"))
        self.folder_entry = ttk.Entry(folder_row, textvariable=self.folder, font=("Segoe UI", 9))
        self.folder_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(folder_row, text="Browse…", width=10, command=self.choose_folder).pack(side="left", padx=(6, 0))

        # -- map name
        ttk.Label(outer, text="MAP NAME", style="Field.TLabel").grid(row=9, column=0, sticky="w")
        name_row = ttk.Frame(outer)
        name_row.grid(row=10, column=0, columnspan=4, sticky="we", pady=(2, 2))
        self.name = tk.StringVar(value="")
        self.name_entry = ttk.Entry(name_row, textvariable=self.name, font=("Segoe UI", 10))
        self.name_entry.pack(side="left", fill="x", expand=True)
        ttk.Label(name_row, text=".roo", style="Sub.TLabel").pack(side="left", padx=(6, 0))
        self.name_hint = ttk.Label(outer, text="Enter a name to generate.", style="Sub.TLabel")
        self.name_hint.grid(row=11, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.name.trace_add("write", lambda *_: self.refresh_button())

        # -- go
        self.button = ttk.Button(outer, text="Generate…", style="Go.TButton", command=self.generate,
                                 takefocus=False)      # otherwise it opens wearing a focus ring
        self.button.grid(row=12, column=0, columnspan=4, sticky="we")
        self.bar = ttk.Progressbar(outer, mode="indeterminate", length=100)
        self.bar.grid(row=13, column=0, columnspan=4, sticky="we", pady=(8, 0))
        self.bar.grid_remove()

        # -- preview
        self.canvas = tk.Canvas(outer, width=PREVIEW, height=int(PREVIEW * 0.82), highlightthickness=1,
                                highlightbackground=EDGE, background="#ffffff")
        self.canvas.grid(row=14, column=0, columnspan=4, pady=(14, 8))
        self.canvas.create_text(PREVIEW / 2, PREVIEW * 0.41, width=PREVIEW - 40,
                                text="The map you generate appears here", fill=MUTED,
                                font=("Segoe UI", 9), justify="center")

        self.status = ttk.Label(outer, text="Pick a style and a size, name the map, then Generate.",
                                style="Status.TLabel", wraplength=PREVIEW, justify="left", anchor="nw")
        self.status.grid(row=15, column=0, columnspan=4, sticky="we")
        outer.grid_rowconfigure(15, minsize=58)

        self.refresh_button()
        self.name_entry.focus_set()

    # -- helpers ----------------------------------------------------------
    def clean_name(self):
        n = self.name.get().strip().strip(".")
        if n.lower().endswith(".roo"):
            n = n[:-4]
        return n

    def refresh_button(self):
        n = self.clean_name()
        bad = [c for c in BAD_NAME_CHARS if c in n]
        if self.busy:
            return
        if not n:
            self.button.state(["disabled"])
            self.name_hint.config(text="Enter a name to generate.")
        elif bad:
            self.button.state(["disabled"])
            self.name_hint.config(text="A file name cannot contain %s" % " ".join(bad))
        else:
            self.button.state(["!disabled"])
            self.name_hint.config(text="Saves as %s.roo" % n)

    def choose_folder(self):
        start = self.folder.get() if os.path.isdir(self.folder.get()) else os.path.expanduser("~")
        chosen = filedialog.askdirectory(title="Save maps in", initialdir=start)
        if chosen:
            self.folder.set(os.path.normpath(chosen))

    # -- generating -------------------------------------------------------
    def generate(self):
        style = self.style_var.get()
        name = self.clean_name()
        if not name:
            return
        folder = self.folder.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror("Meridian Map Generator",
                                 "That folder does not exist:\n%s\n\nPick one with Browse." % folder)
            return
        try:
            width, height = int(self.x.get().strip()), int(self.y.get().strip())
        except ValueError:
            messagebox.showerror("Meridian Map Generator",
                                 "X and Y must be whole numbers (you entered X '%s', Y '%s')."
                                 % (self.x.get(), self.y.get()))
            return
        if width < 1 or height < 1:
            messagebox.showerror("Meridian Map Generator",
                                 "X and Y are the room's full width and height, so they must be positive "
                                 "(you entered %d x %d). For a room spanning -250..250, enter 500." % (width, height))
            return
        path = os.path.join(folder, name + ".roo")
        if os.path.exists(path) and not messagebox.askyesno(
                "Meridian Map Generator", "%s already exists in that folder.\n\nReplace it?" % (name + ".roo")):
            return
        save_settings({"style": style, "x": width, "y": height, "folder": folder})
        self.busy = True
        self.button.state(["disabled"])
        self.bar.grid()
        self.bar.start(12)
        self.status.config(text="Generating %s, %d × %d…" % (style, width, height))
        threading.stack_size(STACK_MB * 1024 * 1024)
        try:
            threading.Thread(target=self.work, args=(style, width, height, path), daemon=True).start()
        finally:
            threading.stack_size(0)
        self.root.after(150, self.poll)

    def work(self, style, width, height, path):
        started = time.time()
        sys.setrecursionlimit(max(sys.getrecursionlimit(), 200000))
        try:
            room, summary, seed = styles.generate(style, width, height)
            room.save(path)
            again = Room.load(path)
            with open(path, "rb") as fh:
                if again.to_bytes() != fh.read():
                    raise RuntimeError("the saved file did not read back identically")
            shot = None
            try:
                if preview.render(room, self.preview_path, size=PREVIEW):
                    shot = self.preview_path
            except Exception:
                shot = None                      # a missing preview must not lose the map
            self.results.put(("ok", "Saved %s\n%s\nspans %d..%d by %d..%d · seed %d · %.0f seconds"
                              % (os.path.basename(path), summary, -(width // 2), width - width // 2,
                                 -(height // 2), height - height // 2, seed, time.time() - started), shot))
        except MemoryError:
            self.results.put(("error", "Not enough memory to generate %s at %d × %d." % (style, width, height), None))
        except Exception as e:  # shown to the user, not swallowed
            self.results.put(("error", str(e) if isinstance(e, ValueError) else "%s: %s" % (type(e).__name__, e), None))

    def poll(self):
        try:
            kind, text, shot = self.results.get_nowait()
        except queue.Empty:
            self.root.after(150, self.poll)
            return
        self.bar.stop()
        self.bar.grid_remove()
        self.busy = False
        self.refresh_button()
        self.status.config(text=text if kind == "ok" else "Failed. " + text)
        if kind == "error":
            messagebox.showerror("Meridian Map Generator", text)
            return
        if shot:
            self.image = tk.PhotoImage(file=shot)
            self.canvas.delete("all")
            self.canvas.create_image(PREVIEW / 2, PREVIEW * 0.41, image=self.image)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
