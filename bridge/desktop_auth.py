"""Authenticated desktop requests. No OS input, enrollment or network at import."""
import base64, hashlib, hmac, json, math, os, re, secrets, stat, threading, time
from pathlib import Path
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

VERSION="assurance-desktop-v2"
MAX_BODY=65536
OPERATOR_PATHS=frozenset({"/v1/arm","/v1/confirm","/v1/d4-session"})
ACTION_PATHS=frozenset({("GET","/v1/status"),("POST","/v1/action")})
class Refused(ValueError): pass
def need(condition, code):
    if not condition: raise Refused(code)
def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()
def digest(value): return hashlib.sha256(canonical(value)).hexdigest()
def _pairs(items):
    value={}
    for k,v in items:
        need(k not in value,"DUPLICATE_JSON_KEY")
        value[k]=v
    return value
def strict(raw):
    need(isinstance(raw,(bytes,str)) and len(raw)<=MAX_BODY,"BODY_SIZE")
    def bad(_): raise Refused("NONFINITE_JSON")
    try: value=json.loads(raw,object_pairs_hook=_pairs,parse_constant=bad)
    except Refused: raise
    except (ValueError,UnicodeError,RecursionError): raise Refused("INVALID_JSON")
    need(type(value) is dict,"OBJECT_REQUIRED")
    def walk(v,depth=0):
        need(depth<=32,"JSON_DEPTH")
        if isinstance(v,float): need(math.isfinite(v),"NONFINITE_JSON")
        if isinstance(v,dict):
            for x in v.values(): walk(x,depth+1)
        if isinstance(v,list):
            for x in v: walk(x,depth+1)
    walk(value)
    return value
def b64(raw): return base64.b64encode(raw).decode("ascii")
def unb64(value):
    need(type(value) is str and len(value)<=MAX_BODY,"INVALID_BASE64")
    try: return base64.b64decode(value,validate=True)
    except ValueError: raise Refused("INVALID_BASE64")
def private_read(path, maximum=MAX_BODY):
    p=Path(path)
    need(p.is_absolute(),"ABSOLUTE_PATH_REQUIRED")
    for parent in [p.parent,*p.parent.parents]:
        need(not parent.is_symlink(),"SYMLINK_PARENT")
    flags=os.O_RDONLY|os.O_NOFOLLOW
    fd=os.open(p,flags)
    try:
        s=os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink==1,"PRIVATE_FILE_TYPE")
        need(s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,"PRIVATE_FILE_MODE")
        need(s.st_size<=maximum,"PRIVATE_FILE_SIZE")
        raw=os.read(fd,maximum+1)
        need(len(raw)==s.st_size,"PRIVATE_FILE_CHANGED")
        return raw
    finally: os.close(fd)
def message(epoch,method,path,role,key_id,body,issued=None,nonce=None):
    return {"version":VERSION,"epoch":epoch,"method":method,"path":path,
            "role":role,"key_id":key_id,"body_sha256":digest(body),
            "issued":int(time.time()) if issued is None else issued,
            "nonce":secrets.token_hex(24) if nonce is None else nonce}
def action_envelope(key,epoch,method,path,body,key_id="codex",issued=None,nonce=None):
    m=message(epoch,method,path,"action",key_id,body,issued,nonce)
    return {"message":m,"signature":b64(hmac.digest(key,canonical(m),"sha256"))}
class Authenticator:
    def __init__(self,action_keys,operator_key,*,epoch=None,clock=time.time,capacity=4096,guard=lambda:None):
        need(type(action_keys) is dict and action_keys,"ACTION_KEYS_REQUIRED")
        need(all(re.fullmatch(r"[a-zA-Z0-9_-]{1,40}",k) and isinstance(v,bytes) and len(v)==32
                 for k,v in action_keys.items()),"INVALID_ACTION_KEYS")
        self.actions=dict(action_keys)
        self.operator=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),operator_key)
        self.epoch=epoch or secrets.token_hex(32)
        self.clock,self.capacity,self.guard=clock,capacity,guard
        self.lock=threading.Lock(); self.seen={}; self.clock_high_water=clock()
    def authorize(self,envelope,method,path,body):
        self.guard()
        need(type(envelope) is dict and set(envelope)=={"message","signature"},"AUTH_FIELDS")
        m=envelope["message"]
        need(type(m) is dict and set(m)=={"version","epoch","method","path","role","key_id",
                                        "body_sha256","issued","nonce"},"SIGNED_FIELDS")
        need(m["version"]==VERSION and m["epoch"]==self.epoch,"AUTH_EPOCH")
        need(m["method"]==method and m["path"]==path and m["body_sha256"]==digest(body),"AUTH_BINDING")
        need(type(m["issued"]) is int and abs(self.clock()-m["issued"])<=30,"AUTH_EXPIRED")
        need(type(m["nonce"]) is str and re.fullmatch("[0-9a-f]{48}",m["nonce"]),"AUTH_NONCE")
        sig=unb64(envelope["signature"])
        role=m["role"]
        if role=="action":
            need((method,path) in ACTION_PATHS,"OPERATOR_SIGNATURE_REQUIRED")
            key=self.actions.get(m["key_id"])
            need(key is not None,"UNKNOWN_CLIENT")
            need(hmac.compare_digest(sig,hmac.digest(key,canonical(m),"sha256")),"BAD_SIGNATURE")
        elif role=="operator":
            need(m["key_id"]=="operator" and method=="POST" and path in OPERATOR_PATHS,"OPERATOR_SCOPE")
            try: self.operator.verify(sig,canonical(m),ec.ECDSA(hashes.SHA256()))
            except (InvalidSignature,ValueError): raise Refused("BAD_SIGNATURE")
        else: raise Refused("AUTH_ROLE")
        # Admission and consumption are atomic. Failed downstream execution never replays.
        with self.lock:
            now=self.clock()
            need(now>=self.clock_high_water,"CLOCK_MOVED_BACKWARD")
            self.clock_high_water=now
            self.seen={k:t for k,t in self.seen.items() if now<=t+30}
            k=(role,m["key_id"],m["nonce"])
            need(k not in self.seen,"AUTH_REPLAY")
            need(len(self.seen)<self.capacity,"AUTH_CAPACITY")
            self.seen[k]=m["issued"]
        return {"role":role,"key_id":m["key_id"],"request_sha256":digest(m)}
CLIENT_ID_RE=r"[a-zA-Z0-9_-]{1,40}"
def _clients(config):
    """Legacy single client plus optional action_clients list. Disabled entries are placeholders."""
    out=[(config["client_id"],config["client_key_path"])]
    extra=config.get("action_clients",[])
    need(type(extra) is list and len(extra)<=16,"ACTION_CLIENTS")
    for c in extra:
        need(type(c) is dict and set(c)<={"client_id","client_key_path","enabled","note"},"ACTION_CLIENT_FIELDS")
        need(type(c.get("client_id")) is str and re.fullmatch(CLIENT_ID_RE,c["client_id"]),"ACTION_CLIENT_ID")
        need(type(c.get("enabled")) is bool,"ACTION_CLIENT_ENABLED")
        if not c["enabled"]: continue
        need(type(c.get("client_key_path")) is str,"ACTION_CLIENT_KEY_PATH")
        out.append((c["client_id"],c["client_key_path"]))
    ids=[i for i,_ in out]; paths=[p for _,p in out]
    need(len(set(ids))==len(ids),"DUPLICATE_CLIENT_ID")
    need(len(set(paths))==len(paths),"SHARED_CLIENT_KEY")
    return out
def from_config(path):
    raw=private_read(path); config=strict(raw)
    base={"version","client_id","client_key_path","operator_public_key"}
    need(base<=set(config)<=base|{"action_clients"},"CONFIG_FIELDS")
    need(config["version"]==VERSION,"CONFIG_VERSION")
    clients=_clients(config)
    keys={}
    for cid,kp in clients:
        try: keys[cid]=private_read(kp,32)
        except FileNotFoundError: raise Refused("ACTION_KEY_MISSING:"+cid)
        need(len(keys[cid])==32,"ACTION_KEY_LENGTH:"+cid)
    need(len(set(keys.values()))==len(keys),"SHARED_CLIENT_KEY")
    def guard():
        need(private_read(path)==raw and all(private_read(kp,32)==keys[cid] for cid,kp in clients),"AUTH_CONFIG_CHANGED")
    return Authenticator(keys,unb64(config["operator_public_key"]),guard=guard)
