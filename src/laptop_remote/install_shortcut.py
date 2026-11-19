"""Install the control-panel shortcut for this checkout, including its taskbar icon."""
from pathlib import Path

import pythoncom
from win32com.shell import shell, shellcon
from win32com.propsys import propsys, pscon

from .control_panel import APP_ID
from .settings import PYTHON, ROOT


def install(directory=None):
    desktop = Path(directory) if directory else Path(shell.SHGetFolderPath(0, shellcon.CSIDL_DESKTOPDIRECTORY, None, 0))
    destination = desktop / 'Laptop Remote.lnk'
    target = PYTHON.with_name('pythonw.exe')
    icon = ROOT / 'assets' / 'remote.ico'
    script = ROOT / '__main__.py'
    for path in (target, icon, script):
        if not path.is_file():
            raise FileNotFoundError(f'Required file is missing: {path}')
    shortcut = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    properties = shortcut.QueryInterface(propsys.IID_IPropertyStore)
    file = shortcut.QueryInterface(pythoncom.IID_IPersistFile)
    if destination.exists():
        file.Load(str(destination), 2)
        existing, _ = shortcut.GetPath(shell.SLGP_RAWPATH)
        if Path(existing) != target or properties.GetValue(pscon.PKEY_AppUserModel_ID).GetValue() != APP_ID:
            raise RuntimeError('The existing Laptop Remote shortcut points elsewhere. Rename it, then run setup again.')
    shortcut.SetPath(str(target))
    shortcut.SetArguments('-m laptop_remote')
    shortcut.SetWorkingDirectory(str(ROOT))
    shortcut.SetIconLocation(str(icon), 0)
    shortcut.SetDescription('Laptop Remote')
    properties.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID))
    properties.Commit()
    file.Save(str(destination), True)
    return destination


if __name__ == '__main__':
    print('Shortcut created:', install())
