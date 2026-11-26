import os
import sys
import json
import time
import shutil
import ctypes
import threading
import subprocess
from collections import deque


def run_ui_process():
    import tkinter as tk
    from tkinter import BOTH, Canvas, Frame, Label, Menu, font

    class UIState:
        def __init__(self):
            self.is_recording = False
            self.is_paused = False
            self.timer_enabled = True
            self.should_exit = False

    ui_state = UIState()

    def stdin_reader():
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                if line == "EXIT":
                    ui_state.should_exit = True
                    break
                try:
                    data = json.loads(line)
                    ui_state.is_recording = data.get("is_recording", False)
                    ui_state.is_paused = data.get("is_paused", False)
                    ui_state.timer_enabled = data.get("timer_enabled", True)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            ui_state.should_exit = True

    class IndicatorApp(tk.Frame):
        def __init__(self, master=None):
            super().__init__(master)
            self.master = master
            self.pack()

            self.start_time = 0.0
            self.accumulated_time = 0.0
            self.timer_running = False
            self.last_time_str = "00:00:00"
            self.is_visible = False
            self.last_paused = None
            self.last_timer_enabled = None
            self.win_opacity = 0.8
            self.master.configure(bg="#0f0f0f")
            self.master.overrideredirect(True)
            self.master.attributes("-topmost", True)
            self.master.attributes("-transparentcolor", "#0f0f0f")
            self.config(bg="#0f0f0f")

            self.master.withdraw()

            if sys.platform == "win32":
                try:
                    self.master.update_idletasks()
                    WDA_EXCLUDEFROMCAPTURE = 0x00000011
                    user32 = ctypes.windll.user32
                    hwnd = user32.GetParent(self.master.winfo_id())
                    if hwnd:
                        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
                except Exception:
                    pass

            self.update_position()

            self.container = Frame(
                self,
                bg="#252525",
                bd=0,
                highlightthickness=1,
                highlightbackground="#404040",
            )
            self.container.pack(padx=5, pady=5, fill=BOTH, expand=True)
            font_style = font.Font(size=int(11 * self.scale), weight="bold")
            self.icon_size = max(12, int(font_style.metrics("ascent") * 0.75))

            self.canvas = Canvas(
                self.container,
                height=self.icon_size,
                width=self.icon_size,
                bg="#252525",
                highlightthickness=0,
            )
            self.canvas.grid(row=0, column=0, padx=(10, 6), pady=6)
            self.canvas.bind("<Button-1>", self.toggle_pause)

            self.stopwatch_label = Label(
                self.container,
                text="00:00:00",
                font=font_style,
                bg="#252525",
                fg="#ffffff",
            )
            self.stopwatch_label.grid(
                row=0, column=1, padx=(0, 12), pady=6, sticky="ew"
            )

            self.popup_menu = Menu(self, tearoff=False)
            self.popup_menu.add_command(
                label="Pause Recording", command=self.toggle_pause
            )
            self.popup_menu.add_command(
                label="Stop Recording", command=self.stop_recording
            )
            self.popup_menu.add_separator()
            self.popup_menu.add_command(
                label="Reset Window Location", command=self.update_position
            )

            self.master.bind("<Button-3>", self.show_menu)
            self.master.bind("<Button-1>", self.on_click)
            self.master.bind("<B1-Motion>", self.on_drag)
            self.master.bind("<ButtonRelease-1>", self.on_release)

            self.last_x = 0
            self.last_y = 0

            self.update_loop()

        def draw_indicator(self, is_paused):
            self.canvas.delete("all")
            s = self.icon_size
            p = max(1, int(s * 0.1))

            if is_paused:
                inner = s - 2 * p
                bar_w = max(2, int(inner * 0.32))
                x1 = p + int(inner * 0.12)
                x2 = s - p - int(inner * 0.12) - bar_w
                self.canvas.create_rectangle(
                    x1, p, x1 + bar_w, s - p, fill="#f8a63d", outline=""
                )
                self.canvas.create_rectangle(
                    x2, p, x2 + bar_w, s - p, fill="#f8a63d", outline=""
                )
            else:
                self.canvas.create_oval(p, p, s - p, s - p, fill="red", outline="")

        def update_position(self):
            screen_w = self.master.winfo_screenwidth()
            w = max(300, min(500, int(screen_w * 0.20)))
            h = max(150, int(w * 0.20))
            x = (screen_w - w) // 2
            y = 20
            self.scale = max(1.0, screen_w / 1920)
            self.master.geometry(f"{w}x{h}+{x}+{y}")
            self.master.update_idletasks()

        def on_click(self, event):
            self.last_x = event.x
            self.last_y = event.y

        def on_drag(self, event):
            x = event.x - self.last_x + self.master.winfo_x()
            y = event.y - self.last_y + self.master.winfo_y()
            self.master.geometry(f"+{x}+{y}")

        def on_release(self, event):
            screen_w = self.master.winfo_screenwidth()
            screen_h = self.master.winfo_screenheight()
            win_w = self.master.winfo_width()
            win_h = self.master.winfo_height()

            new_x = max(0, min(self.master.winfo_x(), screen_w - win_w))
            new_y = max(0, min(self.master.winfo_y(), screen_h - win_h))
            self.master.geometry(f"+{new_x}+{new_y}")

        def show_menu(self, event):
            self.popup_menu.tk_popup(event.x_root, event.y_root)

        def toggle_pause(self, event=None):
            print("TOGGLE_PAUSE", flush=True)

        def stop_recording(self):
            print("STOP_RECORDING", flush=True)

        def update_loop(self):
            if ui_state.should_exit:
                self.master.destroy()
                return

            if ui_state.is_recording:
                if not self.is_visible:
                    self.master.deiconify()
                    self.master.attributes("-alpha", self.win_opacity)
                    self.master.attributes("-topmost", True)
                    self.is_visible = True
                    self.last_paused = None
                if ui_state.is_paused != self.last_paused:
                    self.draw_indicator(ui_state.is_paused)
                    menu_label = (
                        "Unpause Recording" if ui_state.is_paused else "Pause Recording"
                    )
                    self.popup_menu.entryconfig(0, label=menu_label)
                    self.last_paused = ui_state.is_paused

                    if ui_state.is_paused:
                        if self.timer_running:
                            self.accumulated_time += time.time() - self.start_time
                            self.timer_running = False
                    else:
                        if not self.timer_running:
                            self.start_time = time.time()
                            self.timer_running = True

                if self.timer_running and ui_state.timer_enabled:
                    elapsed = int(time.time() - self.start_time + self.accumulated_time)
                    hours = elapsed // 3600
                    minutes = (elapsed % 3600) // 60
                    seconds = elapsed % 60
                    time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    if time_str != self.last_time_str:
                        self.stopwatch_label.config(text=time_str)
                        self.last_time_str = time_str
            else:
                if self.is_visible:
                    self.master.withdraw()
                    self.is_visible = False
                self.last_paused = None
                self.timer_running = False
                self.accumulated_time = 0.0
                if self.last_time_str != "00:00:00":
                    self.stopwatch_label.config(text="00:00:00")
                    self.last_time_str = "00:00:00"
            if ui_state.timer_enabled != self.last_timer_enabled:
                if ui_state.timer_enabled:
                    self.stopwatch_label.grid()
                else:
                    self.stopwatch_label.grid_remove()
                self.last_timer_enabled = ui_state.timer_enabled

            self.after(100, self.update_loop)

    reader_thread = threading.Thread(target=stdin_reader, daemon=True)
    reader_thread.start()

    root = tk.Tk()
    root.title("OBS Recording Indicator")
    app = IndicatorApp(master=root)
    app.mainloop()


if __name__ == "__main__" and "--ui" in sys.argv:
    run_ui_process()
    sys.exit(0)

import obspython as obs


class OBSState:
    def __init__(self):
        self.is_recording = False
        self.is_paused = False
        self.timer_enabled = True
        self.sound_enabled = False
        self.start_sound_path = ""
        self.stop_sound_path = ""


state = OBSState()
ui_proc = None
cmd_queue = deque()


def play_sound(file_path):
    if not state.sound_enabled or not file_path or not os.path.isfile(file_path):
        return

    try:
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["afplay", file_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            player = shutil.which("paplay") or shutil.which("aplay")
            if player:
                subprocess.Popen(
                    [player, file_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    except Exception as e:
        print(f"[Recording Indicator] Failed to play sound: {e}")


def find_python_executable():
    candidates = []
    for base in (sys.base_prefix, sys.prefix):
        if base:
            if sys.platform == "win32":
                candidates.append(os.path.join(base, "pythonw.exe"))
                candidates.append(os.path.join(base, "python.exe"))
            else:
                candidates.append(os.path.join(base, "bin", "python3"))
                candidates.append(os.path.join(base, "bin", "python"))

    for path in candidates:
        if os.path.isfile(path):
            return path

    if sys.platform == "win32":
        return shutil.which("pythonw") or shutil.which("python")
    return shutil.which("python3") or shutil.which("python")


def send_state_to_ui():
    global ui_proc
    if ui_proc is None or ui_proc.poll() is not None:
        return
    try:
        payload = json.dumps(
            {
                "is_recording": state.is_recording,
                "is_paused": state.is_paused,
                "timer_enabled": state.timer_enabled,
            }
        )
        ui_proc.stdin.write(payload + "\n")
        ui_proc.stdin.flush()
    except Exception:
        pass


def ui_stdout_reader(proc):
    try:
        for line in proc.stdout:
            cmd = line.strip()
            if cmd:
                cmd_queue.append(cmd)
    except Exception:
        pass


def process_ui_commands():
    while cmd_queue:
        cmd = cmd_queue.popleft()
        if cmd == "TOGGLE_PAUSE":
            obs.obs_frontend_recording_pause(not state.is_paused)
        elif cmd == "STOP_RECORDING":
            obs.obs_frontend_recording_stop()


def start_ui_process():
    global ui_proc
    stop_ui_process()

    python_exe = find_python_executable()
    if not python_exe:
        print("[Recording Indicator] Python executable not found.")
        return

    script_path = os.path.abspath(__file__)
    kwargs = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "encoding": "utf-8",
        "bufsize": 1,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        ui_proc = subprocess.Popen([python_exe, script_path, "--ui"], **kwargs)
        threading.Thread(target=ui_stdout_reader, args=(ui_proc,), daemon=True).start()
        send_state_to_ui()
    except Exception as e:
        print(f"[Recording Indicator] Failed to launch UI process: {e}")
        ui_proc = None


def stop_ui_process():
    global ui_proc
    if ui_proc is None:
        return

    proc = ui_proc
    ui_proc = None
    try:
        if proc.poll() is None:
            try:
                proc.stdin.write("EXIT\n")
                proc.stdin.flush()
                proc.stdin.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                proc.terminate()
    except Exception:
        pass


def frontend_event_handler(event):
    if event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTING:
        state.is_recording = True
        state.is_paused = False
        send_state_to_ui()
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_STARTED:
        state.is_recording = True
        state.is_paused = False
        send_state_to_ui()
        play_sound(state.start_sound_path)
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_STOPPED:
        state.is_recording = False
        state.is_paused = False
        send_state_to_ui()
        play_sound(state.stop_sound_path)
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_PAUSED:
        state.is_paused = True
        send_state_to_ui()
    elif event == obs.OBS_FRONTEND_EVENT_RECORDING_UNPAUSED:
        state.is_paused = False
        send_state_to_ui()
    elif event == obs.OBS_FRONTEND_EVENT_EXIT:
        stop_ui_process()


def script_load(settings):
    state.is_recording = obs.obs_frontend_recording_active()
    state.is_paused = obs.obs_frontend_recording_paused()
    state.timer_enabled = obs.obs_data_get_bool(settings, "timer_bool")
    state.sound_enabled = obs.obs_data_get_bool(settings, "sound_bool")
    state.start_sound_path = obs.obs_data_get_string(settings, "start_sound_path")
    state.stop_sound_path = obs.obs_data_get_string(settings, "stop_sound_path")

    obs.obs_frontend_add_event_callback(frontend_event_handler)
    obs.timer_add(process_ui_commands, 100)
    start_ui_process()


def script_unload():
    obs.timer_remove(process_ui_commands)
    obs.obs_frontend_remove_event_callback(frontend_event_handler)
    stop_ui_process()


def script_update(settings):
    state.timer_enabled = obs.obs_data_get_bool(settings, "timer_bool")
    state.sound_enabled = obs.obs_data_get_bool(settings, "sound_bool")
    state.start_sound_path = obs.obs_data_get_string(settings, "start_sound_path")
    state.stop_sound_path = obs.obs_data_get_string(settings, "stop_sound_path")
    send_state_to_ui()


def script_defaults(settings):
    obs.obs_data_set_default_bool(settings, "timer_bool", True)
    obs.obs_data_set_default_bool(settings, "sound_bool", False)
    obs.obs_data_set_default_string(settings, "start_sound_path", "")
    obs.obs_data_set_default_string(settings, "stop_sound_path", "")


def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_bool(props, "timer_bool", "Enable Timer")
    obs.obs_properties_add_bool(props, "sound_bool", "Enable Sound Notifications")

    if sys.platform == "win32":
        audio_filter = "WAV Files (*.wav);;All Files (*.*)"
    else:
        audio_filter = "Audio Files (*.wav *.mp3 *.ogg);;All Files (*.*)"

    obs.obs_properties_add_path(
        props,
        "start_sound_path",
        "Start Recording Sound",
        obs.OBS_PATH_FILE,
        audio_filter,
        None,
    )
    obs.obs_properties_add_path(
        props,
        "stop_sound_path",
        "Stop Recording Sound",
        obs.OBS_PATH_FILE,
        audio_filter,
        None,
    )
    return props


def script_description():
    return """
    <h2><font>Recording Indicator</font></h2>
    <p>Recording Indicator For Your OBS Studio</p>
    <hr>

    <p style="font-size: 14px; margin-top: 10px;">
        <img src="data:image/svg+xml;base64,PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0iVVRGLTgiIHN0YW5kYWxvbmU9Im5vIj8+CjxzdmcKICAgeG1sbnM6ZGM9Imh0dHA6Ly9wdXJsLm9yZy9kYy9lbGVtZW50cy8xLjEvIgogICB4bWxuczpjYz0iaHR0cDovL2NyZWF0aXZlY29tbW9ucy5vcmcvbnMjIgogICB4bWxuczpyZGY9Imh0dHA6Ly93d3cudzMub3JnLzE5OTkvMDIvMjItcmRmLXN5bnRheC1ucyMiCiAgIHhtbG5zOnN2Zz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciCiAgIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIKICAgeG1sbnM6c29kaXBvZGk9Imh0dHA6Ly9zb2RpcG9kaS5zb3VyY2Vmb3JnZS5uZXQvRFREL3NvZGlwb2RpLTAuZHRkIgogICB4bWxuczppbmtzY2FwZT0iaHR0cDovL3d3dy5pbmtzY2FwZS5vcmcvbmFtZXNwYWNlcy9pbmtzY2FwZSIKICAgd2lkdGg9IjEwMjQiCiAgIGhlaWdodD0iMTAyNCIKICAgdmlld0JveD0iMCAwIDEwMjQgMTAyNCIKICAgZmlsbD0ibm9uZSIKICAgdmVyc2lvbj0iMS4xIgogICBpZD0ic3ZnODM1IgogICBzb2RpcG9kaTpkb2NuYW1lPSJPY3RpY29ucy1tYXJrLWdpdGh1Yi5zdmciCiAgIGlua3NjYXBlOnZlcnNpb249IjEuMC4yIChlODZjODcwOCwgMjAyMS0wMS0xNSkiPgogIDxtZXRhZGF0YQogICAgIGlkPSJtZXRhZGF0YTg0MSI+CiAgICA8cmRmOlJERj4KICAgICAgPGNjOldvcmsKICAgICAgICAgcmRmOmFib3V0PSIiPgogICAgICAgIDxkYzpmb3JtYXQ+aW1hZ2Uvc3ZnK3htbDwvZGM6Zm9ybWF0PgogICAgICAgIDxkYzp0eXBlCiAgICAgICAgICAgcmRmOnJlc291cmNlPSJodHRwOi8vcHVybC5vcmcvZGMvZGNtaXR5cGUvU3RpbGxJbWFnZSIgLz4KICAgICAgPC9jYzpXb3JrPgogICAgPC9yZGY6UkRGPgogIDwvbWV0YWRhdGE+CiAgPGRlZnMKICAgICBpZD0iZGVmczgzOSIgLz4KICA8c29kaXBvZGk6bmFtZWR2aWV3CiAgICAgcGFnZWNvbG9yPSIjZmZmZmZmIgogICAgIGJvcmRlcmNvbG9yPSIjNjY2NjY2IgogICAgIGJvcmRlcm9wYWNpdHk9IjEiCiAgICAgb2JqZWN0dG9sZXJhbmNlPSIxMCIKICAgICBncmlkdG9sZXJhbmNlPSIxMCIKICAgICBndWlkZXRvbGVyYW5jZT0iMTAiCiAgICAgaW5rc2NhcGU6cGFnZW9wYWNpdHk9IjAiCiAgICAgaW5rc2NhcGU6cGFnZXNoYWRvdz0iMiIKICAgICBpbmtzY2FwZTp3aW5kb3ctd2lkdGg9IjE0NDAiCiAgICAgaW5rc2NhcGU6d2luZG93LWhlaWdodD0iNzk4IgogICAgIGlkPSJuYW1lZHZpZXc4MzciCiAgICAgc2hvd2dyaWQ9ImZhbHNlIgogICAgIGlua3NjYXBlOnpvb209IjAuNjA0NDkyMTkiCiAgICAgaW5rc2NhcGU6Y3g9IjUxMiIKICAgICBpbmtzY2FwZTpjeT0iNTEyIgogICAgIGlua3NjYXBlOndpbmRvdy14PSIwIgogICAgIGlua3NjYXBlOndpbmRvdy15PSIyNSIKICAgICBpbmtzY2FwZTp3aW5kb3ctbWF4aW1pemVkPSIwIgogICAgIGlua3NjYXBlOmN1cnJlbnQtbGF5ZXI9InN2ZzgzNSIgLz4KICA8cGF0aAogICAgIGZpbGwtcnVsZT0iZXZlbm9kZCIKICAgICBjbGlwLXJ1bGU9ImV2ZW5vZGQiCiAgICAgZD0iTTggMEMzLjU4IDAgMCAzLjU4IDAgOEMwIDExLjU0IDIuMjkgMTQuNTMgNS40NyAxNS41OUM1Ljg3IDE1LjY2IDYuMDIgMTUuNDIgNi4wMiAxNS4yMUM2LjAyIDE1LjAyIDYuMDEgMTQuMzkgNi4wMSAxMy43MkM0IDE0LjA5IDMuNDggMTMuMjMgMy4zMiAxMi43OEMzLjIzIDEyLjU1IDIuODQgMTEuODQgMi41IDExLjY1QzIuMjIgMTEuNSAxLjgyIDExLjEzIDIuNDkgMTEuMTJDMy4xMiAxMS4xMSAzLjU3IDExLjcgMy43MiAxMS45NEM0LjQ0IDEzLjE1IDUuNTkgMTIuODEgNi4wNSAxMi42QzYuMTIgMTIuMDggNi4zMyAxMS43MyA2LjU2IDExLjUzQzQuNzggMTEuMzMgMi45MiAxMC42NCAyLjkyIDcuNThDMi45MiA2LjcxIDMuMjMgNS45OSAzLjc0IDUuNDNDMy42NiA1LjIzIDMuMzggNC40MSAzLjgyIDMuMzFDMy44MiAzLjMxIDQuNDkgMy4xIDYuMDIgNC4xM0M2LjY2IDMuOTUgNy4zNCAzLjg2IDguMDIgMy44NkM4LjcgMy44NiA5LjM4IDMuOTUgMTAuMDIgNC4xM0MxMS41NSAzLjA5IDEyLjIyIDMuMzEgMTIuMjIgMy4zMUMxMi42NiA0LjQxIDEyLjM4IDUuMjMgMTIuMyA1LjQzQzEyLjgxIDUuOTkgMTMuMTIgNi43IDEzLjEyIDcuNThDMTMuMTIgMTAuNjUgMTEuMjUgMTEuMzMgOS40NyAxMS41M0M5Ljc2IDExLjc4IDEwLjAxIDEyLjI2IDEwLjAxIDEzLjAxQzEwLjAxIDE0LjA4IDEwIDE0Ljk0IDEwIDE1LjIxQzEwIDE1LjQyIDEwLjE1IDE1LjY3IDEwLjU1IDE1LjU5QzEzLjcxIDE0LjUzIDE2IDExLjUzIDE2IDhDMTYgMy41OCAxMi40MiAwIDggMFoiCiAgICAgdHJhbnNmb3JtPSJzY2FsZSg2NCkiCiAgICAgZmlsbD0iIzFCMUYyMyIKICAgICBpZD0icGF0aDgzMyIKICAgICBzdHlsZT0iZmlsbDojZmZmZmZmO2ZpbGwtb3BhY2l0eToxIiAvPgo8L3N2Zz4K" width="16" height="16" style="vertical-align: middle;"/>
       <a href="https://github.com/channel101/obs_recording_indicator" style="color: #1E90FF; text-decoration: none; font-weight: bold; margin-left: 5px;">GitHub Repository</a>
    </p>
    """
