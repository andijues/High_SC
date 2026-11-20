"""Drive only the folder dialog owned by a specified test process.

Used for native integration tests, never for controlling unrelated windows.
"""
import ctypes
from ctypes import wintypes
import threading
import time


def call_with_dialog_action(call, pid, cancel=False, timeout=20):
    """Run call() while a helper selects/cancels its actual native dialog."""
    user=ctypes.WinDLL('user32',use_last_error=True)
    enum_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user.EnumWindows.argtypes=[enum_type,wintypes.LPARAM]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user.GetDlgItem.argtypes=[wintypes.HWND,ctypes.c_int];user.GetDlgItem.restype=wintypes.HWND
    user.IsWindowEnabled.argtypes=[wintypes.HWND];user.IsWindowEnabled.restype=wintypes.BOOL
    user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
    user.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    finished=threading.Event();state={'sent':False,'error':''}
    def drive():
        deadline=time.monotonic()+timeout
        dialog=None
        while not finished.is_set():
            windows=[]
            @enum_type
            def visit(hwnd,param):
                owner=wintypes.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
                if owner.value==pid:
                    name=ctypes.create_unicode_buffer(256);user.GetClassNameW(hwnd,name,256)
                    if name.value=='#32770':windows.append(hwnd)
                return True
            user.EnumWindows(visit,0)
            if windows:
                dialog=windows[0]
                # Keep test-owned dialogs from obscuring the user's work.
                user.ShowWindow(dialog,0)
                button=user.GetDlgItem(dialog,2 if cancel else 1)
                if button and user.IsWindowEnabled(button):
                    state['sent']=bool(user.PostMessageW(dialog,0x111,2 if cancel else 1,0))
                    return
            if time.monotonic()>deadline:
                state['error']='Native test dialog was not ready'
                if dialog:user.PostMessageW(dialog,0x111,2,0)
                return
            time.sleep(.05)
    driver=threading.Thread(target=drive,daemon=True);driver.start()
    try:result=call()
    finally:finished.set();driver.join(timeout=3)
    if state['error']:raise AssertionError(state['error'])
    if not state['sent']:raise AssertionError('The real native dialog was not opened')
    return result
