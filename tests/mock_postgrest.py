"""시험용 최소 PostgREST 흉내 서버 (실제 PostgreSQL에 연결).

수집기가 쓰는 기능만 구현: insert(중복 무시/병합), select(eq·gte·lt·is·and·order·Range), rpc.
필터 문법이 실제 PostgREST와 다르면 여기서 오류가 나도록 엄격하게 해석한다.
"""
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

import psycopg
from psycopg.types.json import Jsonb

DSN = sys.argv[1]
PORT = int(sys.argv[2])
OBJ = {}   # 시험용 Storage: 경로 → (바이트, 생성 시각)
KEY = "test-service-key"
OPS = {"eq": "=", "gte": ">=", "lt": "<", "gt": ">", "lte": "<="}
IDENT = re.compile(r"^[a-z_]+$")


def cond(col, expr, args):
    assert IDENT.match(col), col
    op, _, val = expr.partition(".")
    if op == "is":
        assert val in ("null", "true", "false")
        return f"{col} is {val}"
    if op == "ilike":
        args.append(val.replace("*", "%"))
        return f"{col} ilike %s"
    assert op in OPS, f"지원하지 않는 연산자 {op}"
    args.append(val)
    return f"{col} {OPS[op]} %s"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        if self.headers.get("apikey") != KEY or self.headers.get("Authorization") != f"Bearer {KEY}":
            self._send(401, {"message": "bad key"})
            return False
        return True

    def _send(self, code, obj=None, headers=None):
        body = b"" if obj is None else json.dumps(obj, default=str, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _storage(self, method):
        import datetime as _dt
        p = urlsplit(self.path).path
        if method == "GET":
            name = p.split("/object/authenticated/backups/", 1)[1]
            if name not in OBJ:
                return self._send(404, {"message": "not found"})
            self.send_response(200); self.end_headers(); self.wfile.write(OBJ[name][0]); return
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if method == "POST":
            name = p.split("/object/backups/", 1)[1]
            if name in OBJ and self.headers.get("x-upsert") != "true":
                return self._send(409, {"message": "exists"})
            OBJ[name] = (body, _dt.datetime.now(_dt.timezone.utc).isoformat())
            return self._send(200, {"Key": f"backups/{name}"})
        if method == "DELETE":
            for n in json.loads(body)["prefixes"]:
                OBJ.pop(n, None)
            return self._send(200, [])

    def do_DELETE(self):
        if self._auth():
            self._storage("DELETE")

    def do_GET(self):
        if not self._auth():
            return
        if self.path.startswith("/storage/v1/"):
            return self._storage("GET")
        u = urlsplit(self.path)
        table = u.path.split("/rest/v1/")[1]
        assert IDENT.match(table)
        q = parse_qsl(u.query, keep_blank_values=True)
        cols, where, args, order = "*", [], [], ""
        lim = off = None
        for k, v in q:
            if k == "limit":
                lim = int(v)
            elif k == "offset":
                off = int(v)
            elif k == "select":
                cols = ",".join(c for c in v.split(",") if IDENT.match(c) or c == "*")
            elif k == "order":
                col, *rest = v.split(".")
                assert IDENT.match(col)
                order = f" order by {col} {'desc' if 'desc' in rest else 'asc'}"
            elif k == "and":
                assert v.startswith("(") and v.endswith(")"), v
                for part in v[1:-1].split(","):
                    c, _, e = part.partition(".")
                    where.append(cond(c, e, args))
            else:
                where.append(cond(k, v, args))
        rng = self.headers.get("Range", "0-999")
        a, b = map(int, rng.split("-"))
        if lim is not None:
            a, b = (off or 0), (off or 0) + lim - 1
        wsql = (" where " + " and ".join(where) if where else "")
        sql = f"select {cols} from {table}" + wsql + order + f" offset {a} limit {b - a + 1}"
        with psycopg.connect(DSN) as c, c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
            hdr = {}
            if "count=exact" in self.headers.get("Prefer", ""):
                cur.execute(f"select count(*) as n from {table}" + wsql, args)
                hdr["Content-Range"] = f"{a}-{a + len(rows) - 1}/{cur.fetchone()['n']}"
            self._send(200, rows, hdr)

    def do_POST(self):
        if not self._auth():
            return
        if self.path.startswith("/storage/v1/"):
            return self._storage("POST")
        if self.path.endswith("/rpc/backup_objects"):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            return self._send(200, [{"name": n, "bytes": len(b), "created_at": t} for n, (b, t) in sorted(OBJ.items())])
        u = urlsplit(self.path)
        path = u.path.split("/rest/v1/")[1]
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with psycopg.connect(DSN) as c, c.cursor(row_factory=psycopg.rows.dict_row) as cur:
            if path.startswith("rpc/"):
                fn = path[4:]
                assert IDENT.match(fn)
                names = list(data.keys())
                vals = [Jsonb(v) if isinstance(v, (list, dict)) else v for v in data.values()]
                cur.execute(f"select {fn}(" + ",".join(f"{n} => %s" for n in names) + ") as r", vals)
                self._send(200, cur.fetchone()["r"])
                return
            table = path
            q = dict(parse_qsl(u.query))
            prefer = self.headers.get("Prefer", "")
            rows = data if isinstance(data, list) else [data]
            if len({frozenset(r.keys()) for r in rows}) > 1:   # 실제 PostgREST와 같게: 묶음 안 행의 열 구성이 다르면 거부
                self._send(400, {"code": "PGRST102", "message": "All object keys must match"})
                return
            out = []
            for r in rows:
                cols = list(r.keys())
                vals = [Jsonb(v) if isinstance(v, dict) else v for v in r.values()]
                sql = f"insert into {table} ({','.join(cols)}) values ({','.join(['%s'] * len(cols))})"
                if "on_conflict" in q:
                    if "ignore-duplicates" in prefer:
                        sql += f" on conflict ({q['on_conflict']}) do nothing"
                    elif "merge-duplicates" in prefer:
                        sql += f" on conflict ({q['on_conflict']}) do update set " + ",".join(f"{x}=excluded.{x}" for x in cols)
                sql += " returning *"
                cur.execute(sql, vals)
                out.extend(cur.fetchall())
            self._send(201, out if "return=representation" in prefer else None)


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
