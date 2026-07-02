from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
import json
import urllib.request
import urllib.parse

DIFY_URL = "http://192.168.0.25/v1/workflows/run"
DIFY_API_KEY = "app-5bydrmSy0xir3HouXIO3wQ9z"

DINGTALK_USER_MAP = {
    "ding-user-001": "E10001",
    "ding-user-002": "E10002",
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


CHECKIN_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>钉钉智能打卡</title>
  <style>
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7f9; color: #172033; }
    .wrap { max-width: 520px; margin: 0 auto; padding: 28px 18px; }
    h1 { margin: 8px 0 10px; font-size: 28px; }
    .sub { margin: 0 0 22px; color: #647084; line-height: 1.6; }
    .panel { background: #fff; border: 1px solid #e8ebf0; border-radius: 12px; padding: 18px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06); }
    label { display: block; margin: 14px 0 6px; color: #344054; font-size: 14px; }
    input, select { box-sizing: border-box; width: 100%; border: 1px solid #d0d5dd; border-radius: 8px; padding: 11px 12px; font-size: 16px; background: #fff; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    button { width: 100%; border: 0; border-radius: 9px; padding: 13px 14px; margin-top: 18px; font-size: 17px; font-weight: 700; color: #fff; background: #1677ff; }
    button:disabled { background: #98a2b3; }
    pre { white-space: pre-wrap; word-break: break-word; margin: 14px 0 0; padding: 12px; border-radius: 8px; background: #101828; color: #d1fadf; font-size: 13px; line-height: 1.5; }
    .hint { margin-top: 12px; color: #667085; font-size: 13px; line-height: 1.6; }
  </style>
</head>
<body>
  <main class="wrap">
    <h1>钉钉智能打卡</h1>
    <p class="sub">演示版页面：获取当前位置后，提交到中转后端，再转发给 Dify 工作流。</p>
    <section class="panel">
      <label for="userId">钉钉用户ID</label>
      <select id="userId">
        <option value="ding-user-001">ding-user-001 / E10001</option>
        <option value="ding-user-002">ding-user-002 / E10002</option>
      </select>
      <div class="row">
        <div><label for="lat">纬度</label><input id="lat" value="31.2304" /></div>
        <div><label for="lng">经度</label><input id="lng" value="121.4737" /></div>
      </div>
      <div class="row">
        <div><label for="accuracy">精度/米</label><input id="accuracy" value="30" /></div>
        <div><label for="checkType">打卡类型</label><select id="checkType"><option value="in">上班打卡</option><option value="out">下班打卡</option></select></div>
      </div>
      <button id="locateBtn" type="button">获取当前位置</button>
      <button id="checkinBtn" type="button">立即打卡</button>
      <p class="hint">如果手机拒绝定位权限，会使用页面里的默认演示坐标。</p>
      <pre id="result">等待操作...</pre>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    function setResult(value) {
      $("result").textContent = typeof value === "string" ? value : JSON.stringify(value, null, 2);
    }
    $("locateBtn").addEventListener("click", () => {
      if (!navigator.geolocation) {
        setResult("当前环境不支持浏览器定位，继续使用默认演示坐标。");
        return;
      }
      $("locateBtn").disabled = true;
      setResult("正在获取定位...");
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          $("lat").value = String(pos.coords.latitude);
          $("lng").value = String(pos.coords.longitude);
          $("accuracy").value = String(Math.round(pos.coords.accuracy || 30));
          $("locateBtn").disabled = false;
          setResult("定位已更新，可以点击立即打卡。");
        },
        (err) => {
          $("locateBtn").disabled = false;
          setResult("定位失败：" + err.message + "\n继续使用默认演示坐标。");
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
      );
    });
    $("checkinBtn").addEventListener("click", async () => {
      $("checkinBtn").disabled = true;
      setResult("正在提交打卡...");
      const payload = {
        dingtalk_user_id: $("userId").value,
        lat: $("lat").value,
        lng: $("lng").value,
        accuracy_m: $("accuracy").value,
        check_type: $("checkType").value,
        device_fingerprint: "dingtalk-web-demo"
      };
      try {
        const resp = await fetch("/api/dingtalk/checkin", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        setResult(data);
      } catch (err) {
        setResult("提交失败：" + err.message);
      } finally {
        $("checkinBtn").disabled = false;
      }
    });
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            self.send_html(200, CHECKIN_PAGE)
            return
        if parsed.path == "/health":
            self.send_json(200, {"ok": True, "service": "dingtalk-gateway", "time": now_iso()})
            return
        self.send_json(404, {"ok": False, "message": "not found"})

    def do_POST(self):
        if self.path != "/api/dingtalk/checkin":
            self.send_json(404, {"ok": False, "message": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(length).decode("utf-8"))

        ding_user_id = data.get("dingtalk_user_id")
        employee_no = DINGTALK_USER_MAP.get(ding_user_id)

        if not employee_no:
            self.send_json(403, {
                "ok": False,
                "message": "钉钉用户未绑定员工号",
                "dingtalk_user_id": ding_user_id
            })
            return

        dify_body = {
            "inputs": {
                "source_system": "dingtalk",
                "external_user_id": ding_user_id,
                "external_request_id": data.get("external_request_id", f"ding-{int(datetime.now().timestamp())}"),
                "employee_no": employee_no,
                "auth_token": "demo",
                "lat": str(data.get("lat")),
                "lng": str(data.get("lng")),
                "accuracy_m": str(data.get("accuracy_m", "30")),
                "client_ts": data.get("client_ts", now_iso()),
                "check_type": data.get("check_type", "in"),
                "device_fingerprint": data.get("device_fingerprint", "")
            },
            "response_mode": "blocking",
            "user": f"dingtalk:{ding_user_id}"
        }

        req = urllib.request.Request(
            DIFY_URL,
            data=json.dumps(dify_body).encode("utf-8"),
            headers={"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"},
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                self.send_json(200, {
                    "ok": True,
                    "message": "已转发到 Dify",
                    "debug_forwarded_identity": {
                        "dingtalk_user_id": ding_user_id,
                        "employee_no": employee_no,
                        "dify_user": f"dingtalk:{ding_user_id}"
                    },
                    "dify_result": result
                })
        except Exception as e:
            self.send_json(500, {"ok": False, "message": "调用 Dify 失败", "error": str(e)})

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 7000), Handler)
    print("DingTalk gateway running on http://0.0.0.0:7000")
    server.serve_forever()
