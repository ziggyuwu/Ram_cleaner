"""
RAM Cleaner & Task Manager
--------------------------
Requirements:
    pip install psutil

Run:
    python ram_cleaner.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import psutil
import threading
import time

# ── colour palette ──────────────────────────────────────────────────────────
BG        = "#0d1117"
SURFACE   = "#161b22"
BORDER    = "#30363d"
ACCENT    = "#58a6ff"
DANGER    = "#f85149"
WARNING   = "#e3b341"
SUCCESS   = "#3fb950"
TEXT      = "#e6edf3"
SUBTEXT   = "#8b949e"
HIGHLIGHT = "#1f2937"

FONT_TITLE = ("Consolas", 18, "bold")
FONT_HEAD  = ("Consolas", 10, "bold")
FONT_BODY  = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)


def bytes_to_mb(b: int) -> float:
    return round(b / (1024 ** 2), 1)


# ── Windows system / kernel processes to hide ────────────────────────────────
# These are core OS tasks that cannot (and should not) be killed.
WINDOWS_SYSTEM_PROCS: set[str] = {
    # NT kernel & hardware abstraction
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "winlogon.exe", "lsass.exe", "lsaiso.exe", "services.exe",
    "svchost.exe", "ntoskrnl.exe", "hal.dll",

    # Session / desktop management
    "dwm.exe", "fontdrvhost.exe", "conhost.exe", "dashost.exe",
    "sihost.exe", "ctfmon.exe", "dllhost.exe", "rundll32.exe",
    "taskhost.exe", "taskhostw.exe", "userinit.exe",

    # Windows Update & store
    "wuauclt.exe", "musnotification.exe", "musnotificationux.exe",
    "wudfhost.exe", "updateassistant.exe", "windowsupdatebox.exe",
    "wsappx.exe", "waasmedicagent.exe", "sedsvc.exe",

    # Security / Defender
    "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
    "securityhealthsystray.exe", "smartscreen.exe", "mpcmdrun.exe",
    "antimalware service executable",

    # Windows shell & explorer helpers
    "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
    "searchhost.exe", "searchindexer.exe", "searchfilterhost.exe",
    "searchprotocolhost.exe", "runtimebroker.exe", "applicationframehost.exe",
    "textinputhost.exe", "lockapp.exe", "logonui.exe",

    # Networking & connectivity
    "spoolsv.exe", "netprofm.dll", "wlanext.exe", "wificonfigsvc.exe",
    "iphlpsvc.dll", "dnscache", "nlanmsvc.dll",

    # Device / driver services
    "audiodg.exe", "wdfsvc.exe", "wmiprvse.exe", "wmiapsrv.exe",
    "msdtc.exe", "vds.exe", "diskhost.exe", "storagespace.exe",

    # COM / RPC infrastructure
    "rpcss.dll", "rpcsub.exe", "dcomlaunch", "comhost.exe",

    # Telemetry / diagnostics (annoying but OS-level)
    "compattelrunner.exe", "diaghost.exe", "diagsvcerr.exe",
    "disksnapshot.exe", "pcasvc.dll", "pcastat.exe", "rdpclip.exe",

    # Credential / biometric
    "credentialuibroker.exe", "bioisd.exe", "wbiosrvc.dll",

    # Misc core services
    "memory compression", "registry", "secure system",
    "system interrupts", "idle",
}


def is_windows_system_proc(name: str) -> bool:
    """Return True if the process name matches a known Windows system task."""
    return name.lower() in WINDOWS_SYSTEM_PROCS


def get_processes(hide_system: bool = True):
    procs = []
    for p in psutil.process_iter(["pid", "name", "memory_info", "status", "cpu_percent"]):
        try:
            info = p.info
            name = info["name"] or "—"
            if hide_system and is_windows_system_proc(name):
                continue
            mem_mb = bytes_to_mb(info["memory_info"].rss) if info["memory_info"] else 0
            procs.append({
                "pid":    info["pid"],
                "name":   name,
                "mem_mb": mem_mb,
                "status": info["status"] or "?",
                "cpu":    round(info["cpu_percent"] or 0, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(procs, key=lambda x: x["mem_mb"], reverse=True)


class RamCleaner(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RAM Cleaner")
        self.configure(bg=BG)
        self.geometry("860x620")
        self.minsize(720, 480)
        self._build_ui()
        self._refresh()
        self._auto_refresh()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── header ──
        hdr = tk.Frame(self, bg=BG, pady=12)
        hdr.pack(fill="x", padx=24)

        tk.Label(hdr, text="⬡ RAM CLEANER", font=FONT_TITLE,
                 bg=BG, fg=ACCENT).pack(side="left")

        self.ram_label = tk.Label(hdr, text="", font=FONT_SMALL,
                                  bg=BG, fg=SUBTEXT)
        self.ram_label.pack(side="right", padx=(0, 4))

        # ── toolbar ──
        bar = tk.Frame(self, bg=SURFACE, pady=8, padx=16,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill="x", padx=24, pady=(0, 8))

        # search
        tk.Label(bar, text="SEARCH", font=FONT_SMALL,
                 bg=SURFACE, fg=SUBTEXT).pack(side="left")
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        tk.Entry(bar, textvariable=self._search_var, width=22,
                 bg=HIGHLIGHT, fg=TEXT, insertbackground=TEXT,
                 relief="flat", font=FONT_BODY,
                 highlightbackground=BORDER, highlightthickness=1
                 ).pack(side="left", padx=(6, 20), ipady=3)

        # sort
        tk.Label(bar, text="SORT BY", font=FONT_SMALL,
                 bg=SURFACE, fg=SUBTEXT).pack(side="left")
        self._sort_var = tk.StringVar(value="Memory ↓")
        sort_options = ["Memory ↓", "Memory ↑", "Name A-Z", "PID", "CPU ↓"]
        sort_menu = ttk.Combobox(bar, textvariable=self._sort_var,
                                 values=sort_options, state="readonly",
                                 width=12, font=FONT_BODY)
        sort_menu.pack(side="left", padx=(6, 20))
        sort_menu.bind("<<ComboboxSelected>>", lambda _: self._apply_filter())

        # select all / none
        tk.Button(bar, text="Select All", font=FONT_SMALL,
                  bg=HIGHLIGHT, fg=TEXT, relief="flat", cursor="hand2",
                  padx=8, pady=3,
                  command=self._select_all).pack(side="left", padx=2)
        tk.Button(bar, text="Clear", font=FONT_SMALL,
                  bg=HIGHLIGHT, fg=TEXT, relief="flat", cursor="hand2",
                  padx=8, pady=3,
                  command=self._clear_selection).pack(side="left", padx=2)

        tk.Button(bar, text="↻ Refresh", font=FONT_SMALL,
                  bg=HIGHLIGHT, fg=ACCENT, relief="flat", cursor="hand2",
                  padx=8, pady=3,
                  command=self._refresh).pack(side="right", padx=2)

        # hide / show system processes toggle
        self._sys_btn_var = tk.StringVar(value="⊘ Hide System")
        tk.Button(bar, textvariable=self._sys_btn_var, font=FONT_SMALL,
                  bg=HIGHLIGHT, fg=WARNING, relief="flat", cursor="hand2",
                  padx=8, pady=3,
                  command=self._toggle_system).pack(side="right", padx=2)

        # ── table ──
        cols = ("sel", "pid", "name", "mem", "cpu", "status")
        self._tree = ttk.Treeview(self, columns=cols,
                                  show="headings", selectmode="none")
        self._style_table()

        self._tree.heading("sel",    text="✓",        anchor="center")
        self._tree.heading("pid",    text="PID",       anchor="center")
        self._tree.heading("name",   text="PROCESS",   anchor="w")
        self._tree.heading("mem",    text="RAM (MB)",  anchor="e")
        self._tree.heading("cpu",    text="CPU %",     anchor="e")
        self._tree.heading("status", text="STATUS",    anchor="center")

        self._tree.column("sel",    width=34,  stretch=False, anchor="center")
        self._tree.column("pid",    width=68,  stretch=False, anchor="center")
        self._tree.column("name",   width=300, stretch=True,  anchor="w")
        self._tree.column("mem",    width=100, stretch=False, anchor="e")
        self._tree.column("cpu",    width=80,  stretch=False, anchor="e")
        self._tree.column("status", width=90,  stretch=False, anchor="center")

        self._tree.bind("<Button-1>", self._on_row_click)

        scroll = tk.Scrollbar(self, orient="vertical",
                              command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)

        self._tree.pack(fill="both", expand=True,
                        padx=24, pady=(0, 0), side="left")
        scroll.pack(fill="y", padx=(0, 24), pady=(0, 0), side="left")

        # ── footer / kill bar ──
        foot = tk.Frame(self, bg=BG, pady=12)
        foot.pack(fill="x", padx=24)

        self._sel_label = tk.Label(foot, text="0 processes selected",
                                   font=FONT_SMALL, bg=BG, fg=SUBTEXT)
        self._sel_label.pack(side="left")

        self._kill_btn = tk.Button(
            foot, text="⚠  KILL SELECTED",
            font=FONT_HEAD, bg=DANGER, fg="white",
            relief="flat", cursor="hand2",
            padx=18, pady=6,
            activebackground="#c03030",
            command=self._kill_selected
        )
        self._kill_btn.pack(side="right")

        self._selected_pids: set[int] = set()
        self._all_procs: list[dict] = []
        self._hide_system = True   # default: system procs hidden

    def _style_table(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
                        background=SURFACE,
                        foreground=TEXT,
                        rowheight=26,
                        fieldbackground=SURFACE,
                        bordercolor=BORDER,
                        borderwidth=0,
                        font=FONT_BODY)
        style.configure("Treeview.Heading",
                        background=HIGHLIGHT,
                        foreground=SUBTEXT,
                        font=FONT_HEAD,
                        relief="flat",
                        borderwidth=0)
        style.map("Treeview",
                  background=[("selected", HIGHLIGHT)],
                  foreground=[("selected", TEXT)])
        style.map("Treeview.Heading",
                  background=[("active", BORDER)])

    # ── data ────────────────────────────────────────────────────────────────

    def _refresh(self):
        self._all_procs = get_processes(hide_system=self._hide_system)
        self._apply_filter()
        self._update_ram_label()

    def _toggle_system(self):
        self._hide_system = not self._hide_system
        if self._hide_system:
            self._sys_btn_var.set("⊘ Hide System")
        else:
            self._sys_btn_var.set("◉ Show System")
        self._refresh()

    def _update_ram_label(self):
        vm = psutil.virtual_memory()
        used = bytes_to_mb(vm.used)
        total = bytes_to_mb(vm.total)
        pct = vm.percent
        colour = SUCCESS if pct < 60 else WARNING if pct < 85 else DANGER
        self.ram_label.config(
            text=f"RAM  {used:,.0f} / {total:,.0f} MB  ({pct}%)",
            fg=colour
        )

    def _apply_filter(self):
        query = self._search_var.get().lower()
        sort  = self._sort_var.get()

        procs = [p for p in self._all_procs
                 if query in p["name"].lower() or query in str(p["pid"])]

        key_map = {
            "Memory ↓": lambda x: -x["mem_mb"],
            "Memory ↑": lambda x: x["mem_mb"],
            "Name A-Z": lambda x: x["name"].lower(),
            "PID":      lambda x: x["pid"],
            "CPU ↓":   lambda x: -x["cpu"],
        }
        procs.sort(key=key_map.get(sort, lambda x: -x["mem_mb"]))

        self._tree.delete(*self._tree.get_children())
        for p in procs:
            check = "☑" if p["pid"] in self._selected_pids else "☐"
            mem_colour = (DANGER  if p["mem_mb"] > 500 else
                          WARNING if p["mem_mb"] > 100 else "")
            iid = self._tree.insert("", "end",
                values=(check, p["pid"], p["name"],
                        f'{p["mem_mb"]:,.1f}', f'{p["cpu"]:.1f}',
                        p["status"]),
                tags=(str(p["pid"]),))
            if mem_colour:
                self._tree.tag_configure(str(p["pid"]), foreground=mem_colour)

        self._update_sel_label()

    def _auto_refresh(self):
        def _loop():
            while True:
                time.sleep(5)
                self.after(0, self._refresh)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ── interaction ──────────────────────────────────────────────────────────

    def _on_row_click(self, event):
        row = self._tree.identify_row(event.y)
        if not row:
            return
        vals = self._tree.item(row, "values")
        if not vals:
            return
        pid = int(vals[1])
        if pid in self._selected_pids:
            self._selected_pids.discard(pid)
        else:
            self._selected_pids.add(pid)
        self._apply_filter()

    def _select_all(self):
        self._selected_pids = {p["pid"] for p in self._all_procs
                                if self._search_var.get().lower() in
                                p["name"].lower()}
        self._apply_filter()

    def _clear_selection(self):
        self._selected_pids.clear()
        self._apply_filter()

    def _update_sel_label(self):
        n = len(self._selected_pids)
        self._sel_label.config(
            text=f"{n} process{'es' if n != 1 else ''} selected",
            fg=ACCENT if n else SUBTEXT
        )

    def _kill_selected(self):
        if not self._selected_pids:
            messagebox.showinfo("Nothing selected",
                                "Click rows to select processes first.")
            return

        names = []
        for p in self._all_procs:
            if p["pid"] in self._selected_pids:
                names.append(f"  • {p['name']}  (PID {p['pid']},  "
                             f"{p['mem_mb']:.1f} MB)")
        names_str = "\n".join(names[:20])
        if len(names) > 20:
            names_str += f"\n  … and {len(names)-20} more"

        ok = messagebox.askyesno(
            "Confirm Kill",
            f"Terminate {len(self._selected_pids)} process(es)?\n\n"
            f"{names_str}\n\n"
            "Unsaved work in those apps will be lost.",
            icon="warning"
        )
        if not ok:
            return

        killed, failed = [], []
        for pid in list(self._selected_pids):
            try:
                psutil.Process(pid).kill()
                killed.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                failed.append(f"PID {pid}: {e}")

        self._selected_pids -= set(killed)
        msg = f"✓ Killed {len(killed)} process(es)."
        if failed:
            msg += f"\n\n⚠ Could not kill {len(failed)}:\n" + "\n".join(failed)
        messagebox.showinfo("Done", msg)
        self._refresh()


if __name__ == "__main__":
    app = RamCleaner()
    app.mainloop()
