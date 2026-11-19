"""One Windows control window: open starts, minimize hides, close stops."""
import ctypes
import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox

from PIL import Image, ImageDraw, ImageTk
import pystray
import win32event

from . import service
from .settings import ROOT, STATE_DIR

BG = '#101513'
PANEL = '#253228'
ACCENT = '#cff09b'
TEXT = '#f3f4ec'
MUTED = '#a1aca4'
LOG = logging.getLogger('laptop_remote.panel')
APP_ID = 'LaptopRemote.ControlPanel'


def icon_image(kind, size=48):
    image = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if kind == 'pair':
        for x, y in [(12, 12), (55, 12), (12, 55)]:
            draw.rectangle((x, y, x + 27, y + 27), outline=ACCENT, width=5)
            draw.rectangle((x + 10, y + 10, x + 17, y + 17), fill=ACCENT)
        for x, y in [(55, 55), (72, 55), (55, 72), (72, 72), (81, 81)]:
            draw.rectangle((x, y, x + 7, y + 7), fill=ACCENT)
    elif kind == 'unpair':
        draw.rounded_rectangle((23, 40, 73, 82), radius=9, outline=ACCENT, width=5)
        draw.arc((33, 12, 63, 64), 180, 360, fill=ACCENT, width=5)
        draw.line((39, 53, 57, 71), fill=ACCENT, width=5)
        draw.line((57, 53, 39, 71), fill=ACCENT, width=5)
    elif kind == 'app':
        draw.rounded_rectangle((0, 0, 95, 95), radius=22, fill=BG)
        draw.rounded_rectangle((18, 19, 78, 63), radius=5, outline=ACCENT, width=5)
        draw.line((12, 77, 84, 77), fill=ACCENT, width=5)
        draw.polygon([(41, 30), (60, 42), (41, 54)], fill=ACCENT)
    else:
        raise ValueError('Unknown panel icon: ' + kind)
    return image.resize((size, size), Image.Resampling.LANCZOS)


class ControlPanel:
    def __init__(self, root, show_event):
        self.root = root
        self.show_event = show_event
        self.messages = queue.Queue()
        self.busy = False
        self.closing = False
        self.closed = False
        self.tray_ready = False
        self.server = None
        self.root.title('Laptop Remote')
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.geometry(f'350x230+{max(0, (root.winfo_screenwidth() - 350) // 2)}+{max(0, (root.winfo_screenheight() - 230) // 2)}')
        self.images = {name: ImageTk.PhotoImage(icon_image(name)) for name in ('pair', 'unpair', 'app')}
        self.root.iconbitmap(default=str(ROOT / 'assets' / 'remote.ico'))
        tk.Label(root, text='Laptop Remote', bg=BG, fg=TEXT, font=('Segoe UI', 14, 'bold')).pack(pady=(15, 3))
        self.status = tk.Label(root, text='Starting…', bg=BG, fg=MUTED, font=('Segoe UI', 10))
        self.status.pack()
        actions = tk.Frame(root, bg=BG)
        actions.pack(pady=(14, 12))
        self.buttons = []
        for column, (action, text, image) in enumerate([('pair', 'Pair', 'pair'), ('unpair', 'Unpair all devices', 'unpair')]):
            button = tk.Button(actions, text=text, image=self.images[image], compound='top', command=lambda a=action: self.perform(a),
                               bg=PANEL, fg=TEXT, activebackground='#35482c', activeforeground=ACCENT,
                               disabledforeground='#6d786e', font=('Segoe UI', 10), relief='flat', bd=0,
                               highlightthickness=0, width=138, height=92, cursor='hand2', state='disabled')
            button.grid(row=0, column=column, padx=7)
            self.buttons.append(button)
        tk.Label(root, text='Minimize to keep running. Close to stop.', bg=BG, fg=MUTED, font=('Segoe UI', 9)).pack()
        root.protocol('WM_DELETE_WINDOW', self.quit)
        root.bind('<Unmap>', self.on_minimize)
        self.tray = pystray.Icon('LaptopRemote', icon_image('app', 64), 'Laptop Remote', menu=pystray.Menu(
            pystray.MenuItem('Open', lambda: self.messages.put(('show', None)), default=True),
            pystray.MenuItem('Pair', lambda: self.messages.put(('action', 'pair')), enabled=lambda item: not self.busy and not self.closing),
            pystray.MenuItem('Unpair all devices', lambda: self.messages.put(('action', 'unpair')), enabled=lambda item: not self.busy and not self.closing),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Quit', lambda: self.messages.put(('quit', None))),
        ))
        self.tray_thread = threading.Thread(target=self.run_tray, daemon=True)
        self.tray_thread.start()
        self.root.after(50, self.drain)

    def run_tray(self):
        def ready(icon):
            try:
                icon.visible = True
                self.messages.put(('tray_ready', None))
            except Exception as exc:
                LOG.exception('Tray setup failed')
                self.messages.put(('error', str(exc)))
        try:
            self.tray.run(setup=ready)
        except Exception as exc:
            LOG.exception('Tray failed')
            self.messages.put(('error', str(exc)))
        finally:
            self.messages.put(('tray_closed', None))

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def on_minimize(self, event):
        if event.widget is self.root and self.root.state() == 'iconic':
            if self.tray_ready and self.tray_thread.is_alive():
                self.root.withdraw()
                LOG.info('Panel minimized to tray')
            else:
                self.show()
                messagebox.showerror('Laptop Remote', 'The tray icon could not be shown. Laptop Remote will stay visible.', parent=self.root)

    def set_busy(self, busy):
        self.busy = busy
        for button in self.buttons:
            button.configure(state='disabled' if busy or self.closing else 'normal')
        if self.tray_ready:
            self.tray.update_menu()

    def perform(self, action):
        if self.busy or self.closed or (self.closing and action != 'quit'):
            return
        actions = {'start': service.start_server, 'pair': service.pair_phone, 'unpair': service.unpair_all, 'quit': service.stop_server}
        if action not in actions:
            raise ValueError('Unknown panel action: ' + action)
        self.set_busy(True)
        self.status.configure(text={'start': 'Starting…', 'pair': 'Pairing…', 'unpair': 'Unpairing…', 'quit': 'Stopping…'}[action], fg=MUTED)
        def work():
            try:
                result = actions[action]()
                self.messages.put(('done', (action, result)))
            except Exception as exc:
                LOG.exception('Panel action failed: %s', action)
                self.messages.put(('error', str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def quit(self):
        if self.closed:
            return
        self.closing = True
        self.set_busy(self.busy)
        if not self.busy:
            self.perform('quit')

    def drain(self):
        if win32event.WaitForSingleObject(self.show_event, 0) == win32event.WAIT_OBJECT_0:
            self.show()
        while not self.messages.empty():
            event, value = self.messages.get_nowait()
            if event == 'show':
                self.show()
            elif event == 'action':
                self.perform(value)
            elif event == 'quit':
                self.quit()
            elif event == 'tray_ready':
                self.tray_ready = True
                if not self.busy:
                    self.perform('quit' if self.closing else 'start')
            elif event == 'tray_closed':
                if not self.closed:
                    LOG.warning('Tray closed; stopping remote')
                    self.quit()
            elif event == 'error':
                self.closing = False
                self.set_busy(False)
                self.status.configure(text='Error', fg='#f1b29a')
                self.show()
                messagebox.showerror('Laptop Remote', value, parent=self.root)
            elif event == 'done':
                action, process = value
                self.set_busy(False)
                if action == 'quit':
                    self.closed = True
                    self.tray.stop()
                    LOG.info('Panel and remote stopped')
                    self.root.destroy()
                    return
                self.server = process
                self.status.configure(text='Devices unpaired' if action == 'unpair' else 'Running', fg=ACCENT)
                self.tray.title = 'Laptop Remote — Running'
                LOG.info('Panel action completed: %s', action)
                if self.closing:
                    self.perform('quit')
        if self.server is not None and not self.busy and not self.closing and not self.server.is_running():
            self.server = None
            self.status.configure(text='Server stopped', fg='#f1b29a')
            self.show()
            messagebox.showerror('Laptop Remote', 'The remote stopped unexpectedly. Close and reopen Laptop Remote.', parent=self.root)
        if not self.closed:
            self.root.after(100, self.drain)


def main():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=STATE_DIR / 'panel.log', level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    show_event = win32event.CreateEvent(None, False, False, service.INSTANCE_NAME + '-show')
    mutex = win32event.CreateMutex(None, False, service.INSTANCE_NAME + '-panel')
    owned = False
    try:
        result = win32event.WaitForSingleObject(mutex, 0)
        if result == win32event.WAIT_TIMEOUT:
            win32event.SetEvent(show_event)
            LOG.info('Opened existing control panel')
            return
        if result not in (win32event.WAIT_OBJECT_0, win32event.WAIT_ABANDONED):
            raise RuntimeError('Could not acquire the control panel instance lock.')
        owned = True
        set_app_id = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        set_app_id.argtypes = [ctypes.c_wchar_p]
        set_app_id.restype = ctypes.c_long
        result = set_app_id(APP_ID)
        if result < 0:
            raise OSError(f'Could not set the taskbar identity (HRESULT {result:#x}).')
        root = tk.Tk()
        panel = ControlPanel(root, show_event)
        root.mainloop()
        panel.tray_thread.join(timeout=5)
        if panel.tray_thread.is_alive():
            raise RuntimeError('The tray did not close after the remote stopped.')
    except Exception as exc:
        LOG.exception('Control panel failed')
        ctypes.windll.user32.MessageBoxW(None, str(exc), 'Laptop Remote', 0x10)
        raise
    finally:
        if owned:
            win32event.ReleaseMutex(mutex)
        mutex.Close()
        show_event.Close()


if __name__ == '__main__':
    main()
