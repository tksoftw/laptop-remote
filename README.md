# Laptop Remote

Control a Windows laptop from your phone: playback, volume, mouse, typing and custom key buttons. Optional screen preview with a crop/zoom editor.

## Setup

Requires **Windows 10/11 and Python 3.11+** on PATH. Connect the phone and laptop to the same trusted network.

1. Download and extract this repository, or clone it.
2. Open PowerShell in its folder and run:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe install_shortcut.py
   ```

3. Open **Laptop Remote** from your desktop, or run:

   ```powershell
   .\.venv\Scripts\pythonw.exe .\control_panel.py
   ```

Click **Pair**, then scan the QR with your phone. Save the page to your home screen if wanted. If the installed phone app needs pairing, use its **Scan QR code** button. Pairing is remembered.

## Use

- Minimize to keep running in the tray. Close the window or choose **Quit** to stop.
- Hold **Left click** or **Right click** with one finger while moving the joystick with another. Release to drop.
- Tap **Edit** beside **Keys** to add or change key combinations. Drag the key names up or down to reorder them. Changes save immediately. Buttons stay in rows of four and are saved on that phone.
- On the control screen, expand **Save to your phone** for **Advanced: Show screen**. **Crop** uses a still image; **Done** resumes the live preview.
- **Unpair all devices** revokes saved pairings.

The laptop must stay awake. Windows Firewall must allow Python on your trusted network; campus Wi-Fi may block device-to-device traffic. The local connection uses HTTP. Keep the QR private and use a network you trust. Elevated apps and Ctrl+Alt+Delete cannot be controlled.

Logs and the encrypted pairing key live in `%LOCALAPPDATA%\LaptopRemote`, outside this repository. Screen frames are not recorded.

## Development

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`vendor_qr.py` downloads the pinned ZXing reader and verifies its hash; third-party licenses are in `web/vendor`.
