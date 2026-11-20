"""Native Windows folder picker. No PowerShell, Tk, or Python installation needed."""
import ctypes
from ctypes import wintypes


def choose_folder(initial=''):
    shell=ctypes.windll.shell32;ole=ctypes.windll.ole32;user=ctypes.windll.user32
    callback_type=ctypes.WINFUNCTYPE(ctypes.c_int,wintypes.HWND,wintypes.UINT,wintypes.LPARAM,wintypes.LPARAM)
    class BrowseInfo(ctypes.Structure):
        _fields_=[('owner',wintypes.HWND),('root',ctypes.c_void_p),('display',wintypes.LPWSTR),('title',wintypes.LPCWSTR),('flags',wintypes.UINT),('callback',callback_type),('param',wintypes.LPARAM),('image',ctypes.c_int)]
    initial_buffer=ctypes.create_unicode_buffer(initial)
    user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.SendMessageW.restype=ctypes.c_ssize_t
    user.SetForegroundWindow.argtypes=[wintypes.HWND]
    @callback_type
    def callback(hwnd,message,param,data):
        if message==1:
            if initial:user.SendMessageW(hwnd,0x467,1,ctypes.cast(initial_buffer,ctypes.c_void_p).value)
            user.SetForegroundWindow(hwnd)
        return 0
    shell.SHBrowseForFolderW.argtypes=[ctypes.POINTER(BrowseInfo)];shell.SHBrowseForFolderW.restype=ctypes.c_void_p
    shell.SHGetPathFromIDListW.argtypes=[ctypes.c_void_p,wintypes.LPWSTR];shell.SHGetPathFromIDListW.restype=wintypes.BOOL
    ole.CoTaskMemFree.argtypes=[ctypes.c_void_p]
    result=ole.CoInitializeEx(None,2)
    if result not in (0,1):raise ValueError('无法打开系统文件夹窗口，请手动填写路径')
    try:
        display=ctypes.create_unicode_buffer(32768)
        # Structure fields require a pointer; function arguments alone allow
        # implicit conversion of a ctypes Unicode array.
        info=BrowseInfo(None,None,ctypes.cast(display,wintypes.LPWSTR),'选择 High_SC 的 HTML 保存文件夹',0x51,callback,0,0)
        pidl=shell.SHBrowseForFolderW(ctypes.byref(info))
        if not pidl:return None
        try:
            path=ctypes.create_unicode_buffer(32768)
            if not shell.SHGetPathFromIDListW(pidl,path):raise ValueError('请选择磁盘上的文件夹')
            return path.value
        finally:ole.CoTaskMemFree(pidl)
    finally:ole.CoUninitialize()
