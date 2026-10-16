"""HTTP boundary and exact operator approval for a staged desktop bridge."""
import copy, hashlib, json, os, threading, time, uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import desktop_auth as A

class Controller:
    def __init__(self,namespace,auth,freeze_paths=()):
        self.ns,self.auth,self.freeze_paths=namespace,auth,tuple(map(Path,freeze_paths))
        self.lock=threading.RLock(); self.held=False
    def frozen(self):
        for p in self.freeze_paths:
            try: p.lstat(); return True
            except FileNotFoundError: pass
            except OSError: return True
        return False
    def health(self):
        return {"ok":True,"service":"desktop-leash","auth_protocol":A.VERSION,"epoch":self.auth.epoch}
    def status(self):
        out=self.ns["status_payload"]()
        with self.ns["_lock"]:
            pending=[{"id":p["id"],"action":p["action"],"payload":copy.deepcopy(p["payload"]),
                      "payload_sha256":A.digest(p["payload"]),"expires":p["expires"]}
                     for p in self.ns["_pending"].values()]
        out.update(auth_protocol=A.VERSION,caller_authenticated=True,operator_approval="SIGNED_USER_PRESENCE",
                   pending_confirms=pending,frozen=self.frozen(),held=self.held,action_routes_globally_enforced="UNKNOWN")
        return out
    def dispatch(self,method,path,body,envelope):
        with self.lock:
            who=self.auth.authorize(envelope,method,path,body)
            if method=="GET" and path=="/v1/status":
                A.need(not body,"GET_BODY"); return self.status()
            stopping=(path=="/v1/arm" and body.get("armed") is False or
                      path=="/v1/d4-session" and body.get("open") is False or
                      path=="/v1/confirm" and body.get("ok") is False)
            A.need(not self.frozen() or stopping,"FROZEN")
            A.need(not self.held or stopping,"BRIDGE_HELD_AFTER_UNCERTAINTY")
            # Evidence must be writable before any effect. Signatures, credentials and typed text are omitted.
            try: self.ns["_receipt"]("authenticated_request",dict(who,path=path,method=method))
            except Exception:
                self.held=True; raise
            if path=="/v1/action":
                A.need("confirm_id" not in body and "confirmed_id" not in body,"SIGNED_CONFIRM_ENDPOINT_REQUIRED")
                try: return self.ns["run_action"](body)
                except Exception:
                    self.held=True; raise
            if path=="/v1/arm":
                A.need(set(body)<= {"armed","ttl"} and type(body.get("armed")) is bool,"ARM_FIELDS")
                default=self.ns.get("ARM_TTL_SEC",900)
                ttl=body.get("ttl",default)
                A.need(type(ttl) is int and 0<=ttl<=86400,"ARM_TTL")
                # Arming always expires: ttl=0 ("forever", which Codex's pinned
                # activate_desktop_v7.py --restart still sends) maps to the finite default.
                if ttl==0: ttl=default
                snap=self.ns["_set_arm"](body["armed"],ttl)
                if not body["armed"]:
                    self.ns["set_d4_session"](open_session=False)
                    with self.ns["_lock"]: self.ns["_pending"].clear()
                return {"ok":True,"armed":snap["armed"],"until":snap["until"],"auth_protocol":A.VERSION}
            if path=="/v1/d4-session":
                A.need(set(body)<={"open","ttl"} and type(body.get("open")) is bool,"D4_FIELDS")
                ttl=body.get("ttl",300)
                A.need(type(ttl) is int and 1<=ttl<=300,"D4_TTL")
                if body["open"]: A.need(self.ns["_arm_active"](),"NOT_ARMED")
                return self.ns["set_d4_session"](open_session=body["open"],ttl=ttl)
            if path=="/v1/confirm":
                try: return self.confirm(body)
                except A.Refused: raise
                except Exception:
                    self.held=True; raise
            raise A.Refused("UNKNOWN_ROUTE")
    def confirm(self,body):
        A.need(set(body)=={"id","ok","payload_sha256"} and type(body["ok"]) is bool,"CONFIRM_FIELDS")
        A.need(type(body["id"]) is str and type(body["payload_sha256"]) is str,"CONFIRM_FIELDS")
        # Lock is shared by all authenticated actions. Pop once, before execution.
        with self.ns["_lock"]:
            p=self.ns["_pending"].get(body["id"])
            A.need(p is not None,"CONFIRM_UNKNOWN")
            A.need(self.ns["_now"]()<=p["expires"],"CONFIRM_EXPIRED")
            A.need(A.digest(p["payload"])==body["payload_sha256"],"CONFIRM_PAYLOAD_CHANGED")
        if body["ok"]:
            A.need(self.ns["_arm_active"](),"NOT_ARMED")
            A.need(self.ns["_d4_session_active"](),"D4_SESSION_CLOSED")
            A.need(self.ns["_input_policy_current"](),"INPUT_POLICY_CHANGED")
            ok,_=self.ns["_velocity_ok"]("input"); A.need(ok,"VELOCITY")
        self.ns["_receipt"]("operator_confirmation",{"id":body["id"],"approved":body["ok"],
                                                    "payload_sha256":body["payload_sha256"]})
        with self.ns["_lock"]: self.ns["_pending"].pop(body["id"])
        if not body["ok"]: return {"ok":True,"code":"CONFIRM_REJECTED"}
        job=str(uuid.uuid4())
        try: result=self.ns["_execute"](p["action"],copy.deepcopy(p["payload"]),job)
        except Exception:
            # Never retry after an input may have been submitted.
            self.held=True
            return {"ok":False,"code":"EXECUTION_OUTCOME_UNCERTAIN","id":job,"retry":False}
        self.ns["_receipt"]("result",{"id":job,"action":p["action"],
                                     "ok":result.get("ok"),"code":result.get("code")})
        return dict(result,id=job,action=p["action"],tier=4,confirm_id=body["id"])

def handler_for(controller):
    class Handler(BaseHTTPRequestHandler):
        protocol_version="HTTP/1.0"
        def setup(self):
            super().setup(); self.connection.settimeout(5)
        def log_message(self,*args): pass
        def reply(self,status,value):
            raw=A.canonical(value)
            self.send_response(status);self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)));self.send_header("Cache-Control","no-store")
            self.end_headers();self.wfile.write(raw)
        def one(self,name,default=None):
            values=self.headers.get_all(name,[])
            A.need(len(values)<=1,"DUPLICATE_HEADER")
            return values[0] if values else default
        def process(self,method):
            try:
                A.need(self.client_address[0] in ("127.0.0.1","::1"),"LOOPBACK_ONLY")
                A.need(self.one("Origin") is None,"BROWSER_ORIGIN_REFUSED")
                A.need(self.one("Transfer-Encoding") is None,"TRANSFER_ENCODING_REFUSED")
                n=self.one("Content-Length","0")
                A.need(n.isascii() and n.isdigit() and len(n)<=6,"CONTENT_LENGTH")
                n=int(n); A.need(n<=A.MAX_BODY,"BODY_SIZE")
                if method=="GET":
                    A.need(n==0,"GET_BODY")
                    body={}
                else:
                    A.need(self.one("Content-Type")=="application/json","CONTENT_TYPE")
                    raw=self.rfile.read(n); A.need(len(raw)==n,"SHORT_BODY")
                    body=A.strict(raw)
                if method=="GET" and self.path=="/health":
                    self.reply(200,controller.health());return
                auth=self.one("X-Assurance-Auth")
                A.need(auth is not None and len(auth)<=8192,"AUTH_REQUIRED")
                envelope=A.strict(A.unb64(auth))
                self.reply(200,controller.dispatch(method,self.path,body,envelope))
            except A.Refused as exc: self.reply(403,{"ok":False,"code":str(exc),"retry":False})
            except (ValueError,TypeError,UnicodeError,RecursionError):
                self.reply(400,{"ok":False,"code":"MALFORMED_REQUEST","retry":False})
            except Exception:
                self.reply(500,{"ok":False,"code":"REQUEST_OUTCOME_UNCERTAIN","retry":False})
        def do_GET(self):self.process("GET")
        def do_POST(self):self.process("POST")
    return Handler

def install(namespace,config_path,freeze_paths):
    A.need(namespace["REQUIRE_D4_CONFIRM"] and namespace["REQUIRE_D4_SESSION"],"OPERATOR_CONTROLS_REQUIRED")
    auth=A.from_config(config_path)
    controller=Controller(namespace,auth,freeze_paths)
    namespace["Handler"]=handler_for(controller)
    # Old unsigned sticky state is never an authenticated admission.
    with namespace["_lock"]:
        namespace["_arm"].update(armed=False,until=0,token="")
        namespace["_d4_session"].update(open=False,until=0)
        namespace["_pending"].clear()
    namespace["AUTH_CONTROLLER"]=controller
    return controller
