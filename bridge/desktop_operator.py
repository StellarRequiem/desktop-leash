"""Operator-only desktop approvals. Requires the installed user-presence signing helper."""
import argparse, datetime, hashlib, json, os, pathlib, subprocess, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
sys.path.insert(0,"/Users/llm01/mcp-assure/.venv/lib/python3.14/site-packages")
import desktop_auth as A
from desktop_client import Client
CONFIG=pathlib.Path("/Users/llm01/desktop-leash/profiles/desktop_auth.json")
OPERATOR=pathlib.Path("/Users/llm01/Library/Application Support/AssuranceMesh/DesktopProxy-v5/operator.json")
def approve(path,body,client,operator,*,signer_runner=subprocess.run):
    A.need(sys.stdin.isatty(),"OPERATOR_TTY_REQUIRED")
    expiry=datetime.datetime.fromisoformat(operator["profile_expires"]).replace(tzinfo=datetime.timezone.utc)
    A.need(expiry>datetime.datetime.now(datetime.timezone.utc),"SIGNER_PROFILE_EXPIRED_RENEWAL_REQUIRED")
    signer=pathlib.Path(operator["signer"])
    A.need(hashlib.sha256(signer.read_bytes()).hexdigest()==operator["signer_sha256"],"SIGNER_CHANGED")
    health=client.exchange("/health")
    A.need(health.get("auth_protocol")==A.VERSION,"AUTH_BRIDGE_REQUIRED")
    m=A.message(health["epoch"],"POST",path,"operator","operator",body)
    request={"message_bytes":A.b64(A.canonical(m)),"body_bytes":A.b64(A.canonical(body))}
    # Fixed, exact payload is printed by the signer before the OS approval prompt.
    fd,name=tempfile.mkstemp(prefix="desktop-approval-",suffix=".json")
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as f:f.write(A.canonical(request));f.flush();os.fsync(f.fileno())
        result=signer_runner([str(signer),"sign",operator["key_tag"],name],
                            stdout=subprocess.PIPE,text=True,timeout=180)
        A.need(result.returncode==0,"OPERATOR_SIGNATURE_NOT_GRANTED")
        signature=result.stdout.strip();A.unb64(signature)
        envelope={"message":m,"signature":signature}
        out=client.exchange(path,body,{"X-Assurance-Auth":A.b64(A.canonical(envelope))})
        A.need(out.get("ok") is True,"APPROVAL_NOT_EXECUTED:"+json.dumps(out))
        return out
    finally:os.unlink(name)
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("operation",choices=["status","arm","disarm","open-session","close-session","approve","reject"])
    parser.add_argument("--id");parser.add_argument("--ttl",type=int,default=0)
    args=parser.parse_args();os.umask(0o077)
    cfg=A.strict(A.private_read(CONFIG));operator=A.strict(A.private_read(OPERATOR))
    client=Client(cfg["client_key_path"],cfg["client_id"])
    if args.operation=="status":out=client.call("/v1/status")
    else:
        if args.operation in ("arm","disarm"):
            path="/v1/arm";body={"armed":args.operation=="arm","ttl":args.ttl}
        elif args.operation in ("open-session","close-session"):
            path="/v1/d4-session";body={"open":args.operation=="open-session","ttl":min(args.ttl or 300,300)}
        else:
            A.need(bool(args.id),"CONFIRM_ID_REQUIRED")
            status=client.call("/v1/status");A.need(status.get("ok") is True,"STATUS_UNAVAILABLE")
            rows=[r for r in status.get("pending_confirms",[]) if r["id"]==args.id]
            A.need(len(rows)==1,"CONFIRM_NOT_PENDING")
            target=rows[0]
            print("Queued action:",json.dumps(target["payload"],indent=2),flush=True)
            A.need(A.digest(target["payload"])==target["payload_sha256"],"PENDING_PAYLOAD_BINDING")
            path="/v1/confirm";body={"id":args.id,"ok":args.operation=="approve",
                                   "payload_sha256":target["payload_sha256"]}
        out=approve(path,body,client,operator)
    print(json.dumps(out,indent=2));return 0 if out.get("ok") else 2
if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:print("STOPPED: "+str(exc),file=sys.stderr);raise SystemExit(2)
