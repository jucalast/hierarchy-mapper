try:
    import win32com.client
    import pythoncom
    print("HAS_PYWIN32: True")
except ImportError:
    print("HAS_PYWIN32: False")
