"""Action-only desktop transport. No operator signing and no unauthenticated fallback."""
import json, urllib.error, urllib.request
from pathlib import Path
import desktop_auth as A
BASE="http://127.0.0.1:8757"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise A.Refused("HTTP_REDIRECT_REFUSED")
class Client:
    def __init__(self,key_path,key_id="codex",base=BASE):
        A.need(base==BASE,"DESKTOP_BASE_CHANGED")
        self.base,self.key_path,self.key_id=base,Path(key_path),key_id
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def exchange(self,path,body=None,headers=None,timeout=90):
        raw=None if body is None else A.canonical(body)
        request=urllib.request.Request(self.base+path,data=raw,
            method="GET" if body is None else "POST",
            headers=dict({"Content-Type":"application/json","Accept":"application/json"},**(headers or {})))
        try:
            with self.opener.open(request,timeout=timeout) as response:
                return A.strict(response.read(A.MAX_BODY+1))
        except urllib.error.HTTPError as exc:
            return A.strict(exc.read(A.MAX_BODY+1))
    def call(self,path,body=None,timeout=90):
        A.need(("GET" if body is None else "POST",path) in A.ACTION_PATHS,"OPERATOR_SIGNATURE_REQUIRED")
        key=A.private_read(self.key_path,32)
        health=self.exchange("/health",timeout=timeout)
        A.need(health.get("auth_protocol")==A.VERSION and type(health.get("epoch")) is str,"AUTH_BRIDGE_REQUIRED")
        envelope=A.action_envelope(key,health["epoch"],"GET" if body is None else "POST",path,
                                   {} if body is None else body,self.key_id)
        return self.exchange(path,body,{"X-Assurance-Auth":A.b64(A.canonical(envelope))},timeout)
def bind_http(original,key_path,key_id="codex"):
    client=Client(key_path,key_id)
    def http_json(base,path,body=None,*,timeout=90.0):
        if base.rstrip("/")!=BASE:return original(base,path,body,timeout=timeout)
        try:return client.call(path,body,timeout)
        except A.Refused as exc:return {"ok":False,"code":str(exc),"retry":False}
        except Exception:return {"ok":False,"code":"DESKTOP_TRANSPORT_FAILED","retry":False}
    return http_json
