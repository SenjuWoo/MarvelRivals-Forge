"""Fake fmodel-mcp stdio server: newline JSON-RPC, enough tools for mrforge mesh export."""
import json
import os
import sys
from pathlib import Path

ARCHIVE = os.environ.get("FAKE_MCP_ARCHIVE", "pakchunkCharacter-Windows.utoc")
cfg = json.load(open(sys.argv[sys.argv.index("--config") + 1], encoding="utf-8"))
out_root = Path(cfg["outputRoot"])
jobs = {}


def reply(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def tool(name, a):
    if name == "fmodel_open_game":
        d = Path(a["options"]["directory"])
        assert d.is_dir() and str(d.resolve()) in [str(Path(r).resolve()) for r in cfg["inputRoots"]], "directory not allowed"
        assert a["options"]["aesKeys"], "no key"
        return {"sessionId": "s1", "mountedArchives": len(list(d.glob("*.utoc")))}
    if name == "fmodel_search_assets":
        q = a["query"]
        return {"items": [{"path": f"Marvel/Content/Marvel/Characters/1061/1061303/Meshes/{q}.uasset", "archive": ARCHIVE}]}
    if name == "fmodel_start_export":
        p = a["request"]["paths"][0]
        od = out_root / f"export-{len(jobs)}"
        f = od / "converted" / p.replace(".uasset", ".uemodel")
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"UEMODEL")
        m = od / "converted" / "Marvel/Content/Marvel/Characters/1061/1061303/Materials/MI_A.json"
        m.parent.mkdir(parents=True, exist_ok=True)
        m.write_text("{}", encoding="utf-8")
        jid = f"j{len(jobs)}"
        jobs[jid] = {"jobId": jid, "state": "completed", "outputDirectory": str(od), "files": [str(f), str(m)], "path": p}
        return {"jobId": jid, "state": "queued"}
    if name == "fmodel_job_status":
        return {k: v for k, v in jobs[a["jobId"]].items() if k != "files"}
    if name == "fmodel_job_results":
        j = jobs[a["jobId"]]
        return {"results": {"items": [{"path": j["path"], "success": True, "files": j["files"]}]}}
    if name == "fmodel_close_game":
        return {"closed": True}
    raise KeyError(name)


for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if msg["method"] == "initialize":
        reply(msg["id"], {"protocolVersion": msg["params"]["protocolVersion"], "serverInfo": {"name": "fake", "version": "0"}})
    elif msg["method"] == "tools/call":
        try:
            reply(msg["id"], {"structuredContent": tool(msg["params"]["name"], msg["params"]["arguments"])})
        except Exception as e:
            reply(msg["id"], {"isError": True, "content": [{"type": "text", "text": str(e)}]})
