"""macOS event submission. A successful post does not prove a UI changed."""
import ctypes as C
import math
class Point(C.Structure):
    _fields_=[("x",C.c_double),("y",C.c_double)]
class Size(C.Structure):
    _fields_=[("width",C.c_double),("height",C.c_double)]
class Rect(C.Structure):
    _fields_=[("origin",Point),("size",Size)]
_api=None
def api():
    global _api
    if _api is None:
        lib=C.CDLL("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.CGEventCreateMouseEvent.argtypes=[C.c_void_p,C.c_uint32,Point,C.c_uint32];lib.CGEventCreateMouseEvent.restype=C.c_void_p
        lib.CGEventCreateKeyboardEvent.argtypes=[C.c_void_p,C.c_uint16,C.c_bool];lib.CGEventCreateKeyboardEvent.restype=C.c_void_p
        lib.CGEventCreateScrollWheelEvent.argtypes=[C.c_void_p,C.c_uint32,C.c_uint32,C.c_int32];lib.CGEventCreateScrollWheelEvent.restype=C.c_void_p
        lib.CGEventSetFlags.argtypes=[C.c_void_p,C.c_uint64]
        lib.CGEventPost.argtypes=[C.c_uint32,C.c_void_p];lib.CGEventPost.restype=None
        lib.CFRelease.argtypes=[C.c_void_p];lib.CFRelease.restype=None
        lib.CGGetActiveDisplayList.argtypes=[C.c_uint32,C.POINTER(C.c_uint32),C.POINTER(C.c_uint32)]
        lib.CGGetActiveDisplayList.restype=C.c_int32
        lib.CGDisplayBounds.argtypes=[C.c_uint32];lib.CGDisplayBounds.restype=Rect
        lib.CGPreflightPostEventAccess.argtypes=[];lib.CGPreflightPostEventAccess.restype=C.c_bool
        _api=lib
    return _api
def allowed(a):
    if not a.CGPreflightPostEventAccess():raise RuntimeError("MACOS_INPUT_PERMISSION_REQUIRED")
def submit(a,event):
    if not event:raise RuntimeError("EVENT_CREATE_FAILED")
    try:a.CGEventPost(0,event)
    finally:a.CFRelease(event)
def on_display(a,x,y):
    if not all(math.isfinite(v) for v in (x,y)):return False
    ids=(C.c_uint32*64)();n=C.c_uint32()
    if a.CGGetActiveDisplayList(64,ids,C.byref(n))!=0:raise RuntimeError("DISPLAY_ENUMERATION_FAILED")
    for i in range(n.value):
        r=a.CGDisplayBounds(ids[i])
        if r.origin.x<=x<r.origin.x+r.size.width and r.origin.y<=y<r.origin.y+r.size.height:return True
    return False
def failure(exc):return {"ok":False,"code":str(exc),"submitted":False}
def click_xy(x,y):
    try:
        a=api();allowed(a)
        if not on_display(a,x,y):raise RuntimeError("COORDINATES_OUTSIDE_DISPLAYS")
        down=a.CGEventCreateMouseEvent(None,1,Point(x,y),0)
        up=a.CGEventCreateMouseEvent(None,2,Point(x,y),0)
        if not down or not up:
            if down:a.CFRelease(down)
            if up:a.CFRelease(up)
            raise RuntimeError("EVENT_CREATE_FAILED")
        try:a.CGEventPost(0,down);a.CGEventPost(0,up)
        finally:a.CFRelease(down);a.CFRelease(up)
        return {"ok":True,"code":"INPUT_SUBMITTED","data":{"x":x,"y":y,"method":"CGEvent","visually_verified":False}}
    except Exception as exc:return failure(exc)
KEYS={"a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,
      "q":12,"w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,
      "6":22,"5":23,"=":24,"9":25,"7":26,"-":27,"8":28,"0":29,"]":30,"o":31,
      "u":32,"[":33,"i":34,"p":35,"return":36,"enter":36,"l":37,"j":38,"'":39,
      "k":40,";":41,"\\":42,",":43,"/":44,"n":45,"m":46,".":47,"tab":48,
      "space":49,chr(96):50,"delete":51,"backspace":51,"escape":53,"esc":53,
      "home":115,"pageup":116,"forwarddelete":117,"end":119,"pagedown":121,
      "left":123,"right":124,"down":125,"up":126}
MODS={"cmd":1<<20,"command":1<<20,"shift":1<<17,"ctrl":1<<18,"control":1<<18,
      "alt":1<<19,"option":1<<19}
def parse_key(key):
    parts=key.lower().strip().split("+")
    if not parts or parts[-1] not in KEYS or any(p not in MODS for p in parts[:-1]):raise RuntimeError("BAD_KEY")
    flags=0
    for p in parts[:-1]:flags|=MODS[p]
    return KEYS[parts[-1]],flags
def press_key(key):
    try:
        number,flags=parse_key(key);a=api();allowed(a)
        down=a.CGEventCreateKeyboardEvent(None,number,True);up=a.CGEventCreateKeyboardEvent(None,number,False)
        if not down or not up:
            if down:a.CFRelease(down)
            if up:a.CFRelease(up)
            raise RuntimeError("EVENT_CREATE_FAILED")
        try:
            a.CGEventSetFlags(down,flags);a.CGEventSetFlags(up,flags)
            a.CGEventPost(0,down);a.CGEventPost(0,up)
        finally:a.CFRelease(down);a.CFRelease(up)
        return {"ok":True,"code":"INPUT_SUBMITTED","data":{"key":key,"method":"CGEvent","visually_verified":False}}
    except Exception as exc:return failure(exc)
def scroll_dy(dy):
    try:
        if type(dy) is not int or abs(dy)>10000:raise RuntimeError("SCROLL_RANGE")
        a=api();allowed(a)
        if dy:submit(a,a.CGEventCreateScrollWheelEvent(None,0,1,-dy))
        return {"ok":True,"code":"INPUT_SUBMITTED","data":{"dy":dy,"method":"CGEvent","visually_verified":False}}
    except Exception as exc:return failure(exc)
