"""Debug launcher — traces withdraw/deiconify and catches silent errors."""
import traceback, sys, os
sys.path.insert(0, os.path.dirname(__file__))

print("=== debug_launch.py starting ===", flush=True)

import customtkinter as ctk
_orig_withdraw = ctk.CTk.withdraw
_orig_deiconify = ctk.CTk.deiconify

def _traced_withdraw(self, *a, **k):
    print("WITHDRAW called from:", flush=True)
    for line in traceback.format_stack(limit=6)[:-1]:
        print(line.strip(), flush=True)
    return _orig_withdraw(self, *a, **k)

def _traced_deiconify(self, *a, **k):
    print("DEICONIFY called from:", flush=True)
    for line in traceback.format_stack(limit=6)[:-1]:
        print(line.strip(), flush=True)
    result = _orig_deiconify(self, *a, **k)
    try:
        print(f"  After deiconify → state={self.state()} geometry={self.geometry()}", flush=True)
    except Exception as e:
        print(f"  Could not read state: {e}", flush=True)
    return result

ctk.CTk.withdraw = _traced_withdraw
ctk.CTk.deiconify = _traced_deiconify

print("Patches applied. Importing main...", flush=True)
try:
    import main
    print("main imported OK — entering mainloop", flush=True)
except Exception as e:
    print(f"CRASH during import/startup: {e}", flush=True)
    traceback.print_exc()
