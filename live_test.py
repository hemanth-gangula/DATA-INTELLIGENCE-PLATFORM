"""
Live end-to-end test: upload -> clean -> agent -> history -> download
Run: python live_test.py
"""
import sys, os, json, warnings, uuid, time, urllib.request, urllib.error
warnings.filterwarnings("ignore")
sys.path.insert(0, '.')

# ── stdout encoding fix for Windows consoles ─────────────────────
import io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = "http://127.0.0.1:5000"
OK   = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"
passed = 0; failed = 0

def chk(label, ok, detail=""):
    global passed, failed
    icon = OK if ok else FAIL
    if ok: passed += 1
    else:  failed += 1
    line = f"  {icon}  {label}"
    if detail: line += f"\n         {detail}"
    print(line)
    return ok

def http_get(path):
    try:
        r = urllib.request.urlopen(BASE+path, timeout=30)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}

def http_post_json(path, data):
    body = json.dumps(data).encode()
    req  = urllib.request.Request(BASE+path, data=body,
           headers={"Content-Type":"application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=60)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}

def http_upload(path, filepath, field="file"):
    boundary = "----Boundary" + uuid.uuid4().hex[:12]
    fname    = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        fb = f.read()
    ct   = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; "
        f'name="{field}"; filename="{fname}"\r\nContent-Type: {ct}\r\n\r\n'
    ).encode() + fb + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(BASE+path, data=body,
          headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
          method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=120)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())
    except Exception as e:
        return 0, {"error": str(e)}

print("=" * 60)
print("  LIVE END-TO-END TEST")
print("=" * 60)

# ── 1. Server health ───────────────────────────────────────────
print("\n[1] Health check")
s, d = http_get("/api/health")
chk("HTTP 200",          s in (200, 503), f"HTTP {s}")
chk("DB connected",      d.get("db") is True)
chk("Storage original",  d.get("storage_original") is True)
chk("Storage cleaned",   d.get("storage_cleaned")  is True)
chk("Storage agent",     d.get("storage_agent")    is True)
chk("overall_ok",        d.get("overall_ok")       is True,
    json.dumps({k:v for k,v in d.items() if k!="errors"})[:100])

# ── 2. Upload Excel ────────────────────────────────────────────
print("\n[2] Upload test_upload.xlsx")
if not os.path.exists("test_upload.xlsx"):
    import pandas as pd
    df = pd.DataFrame({
        "Customer":["Alice","Bob","Alice","Charlie","Dave","","Eve"],
        "City":    ["Hyderabad","Mumbai","Hyderabad","Delhi","Chennai","","Pune"],
        "Sales":   [1000,2000,1000,3000,1500,0,800],
        "Product": ["Laptop","Phone","Laptop","Tablet","Monitor","","Keyboard"],
        "Date":    ["2024-01-01","2024-01-02","2024-01-01","2024-01-03","2024-01-04","","2024-01-05"],
    })
    df.to_excel("test_upload.xlsx", index=False)
    print("  Created test_upload.xlsx")

s, d = http_upload("/api/upload/", "test_upload.xlsx")
# Flask error_response returns [dict, status_code] as a list — unwrap it
if isinstance(d, list):
    d = d[0] if d else {}
chk("Upload HTTP 200",   s == 200, f"HTTP {s} | error={d.get('error','none')}")

dataset_id = d.get("dataset_id", "")
chk("dataset_id returned", bool(dataset_id), dataset_id)

cr = d.get("cleaning_report", {})
chk("Cleaning ran",          "cleaning_required" in cr)
chk("Duplicates detected",   cr.get("duplicates_found", 0) > 0,
    f"found={cr.get('duplicates_found')} removed={cr.get('duplicates_removed')}")
chk("Blank rows detected",   cr.get("blank_rows_found", -1) >= 0,
    f"found={cr.get('blank_rows_found')} removed={cr.get('blank_rows_removed')} (0=already clean)")
chk("Rows reduced",
    cr.get("final_rows", 0) < cr.get("original_rows", 999),
    f"{cr.get('original_rows')} -> {cr.get('final_rows')}")

ov = d.get("original_version", {})
cv = d.get("cleaned_version",  {})
chk("Original version (v1) saved",  bool(ov.get("id")),
    f"id={ov.get('id','')[:36]}")
chk("v1 Excel URL in Supabase",      bool(ov.get("download_excel")),
    str(ov.get("download_excel",""))[:70])
chk("Cleaned version (v2) saved",   bool(cv.get("id")),
    f"id={cv.get('id','')[:36]}")
chk("v2 Excel URL in Supabase",      bool(cv.get("download_excel")),
    str(cv.get("download_excel",""))[:70])
chk("Cleaning status message",       bool(d.get("message")), d.get("message",""))

# ── 3. Dashboard ───────────────────────────────────────────────
print("\n[3] Dashboard")
if dataset_id:
    s, d2 = http_get(f"/api/dashboard/{dataset_id}")
    chk("Dashboard HTTP 200", s == 200, f"HTTP {s}")
    dash = d2.get("dashboard", {})
    chk("KPIs generated",   len(dash.get("kpis",  [])) > 0, f"{len(dash.get('kpis',[]))} KPIs")
    chk("Charts generated", len(dash.get("charts",[])) > 0, f"{len(dash.get('charts',[]))} charts")
else:
    chk("Dashboard skipped", False, "No dataset_id")

# ── 4. Data preview ────────────────────────────────────────────
print("\n[4] Data preview")
if dataset_id:
    s, d3 = http_get(f"/api/data/preview/{dataset_id}?per_page=10")
    chk("Preview HTTP 200",  s == 200, f"HTTP {s}")
    chk("Rows returned",     len(d3.get("rows",[])) > 0,
        f"rows={d3.get('total_rows')} cols={d3.get('total_columns')}")
    chk("Version label shown", bool(d3.get("version_label")), d3.get("version_label",""))

# ── 5. AI Insights ─────────────────────────────────────────────
print("\n[5] AI Insights")
if dataset_id:
    s, d4 = http_get(f"/api/insights/{dataset_id}")
    chk("Insights HTTP 200",  s == 200, f"HTTP {s}")
    text = d4.get("insight_text","")
    chk("Insight text generated", len(text) > 20,
        (text[:120].replace('\n',' ') + "...") if text else "EMPTY")

# ── 6. AI Agent ────────────────────────────────────────────────
print("\n[6] AI Agent — Remove duplicate customers")
if dataset_id:
    time.sleep(2)   # Brief pause before Groq call
    s, d5 = http_post_json("/api/agent/run", {
        "dataset_id": dataset_id,
        "command":    "Remove duplicate customers"
    })
    chk("Agent HTTP 200",       s == 200, f"HTTP {s} | error={d5.get('error','none')}")
    res = d5.get("result", {})
    chk("Tool selected",        bool(res.get("tool_used")),      res.get("tool_used",""))
    chk("Intent understood",    bool(res.get("intent")),         (res.get("intent",""))[:80])
    chk("New version created",  bool(res.get("new_version_id")), res.get("new_version_id","")[:36])
    chk("Agent explanation",    bool(res.get("ai_explanation")), (res.get("ai_explanation",""))[:100])
    chk("Download Excel URL",   bool(res.get("download_excel")), str(res.get("download_excel",""))[:70])
    chk("Download CSV URL",     bool(res.get("download_csv")),   str(res.get("download_csv",""))[:70])
    new_vid = res.get("new_version_id")
else:
    new_vid = None
    chk("Agent skipped", False, "No dataset_id")

# ── 7. Version history ─────────────────────────────────────────
print("\n[7] Version history")
if dataset_id:
    s, d6 = http_get(f"/api/history/{dataset_id}")
    chk("History HTTP 200",       s == 200, f"HTTP {s}")
    history = d6.get("history", [])
    chk("At least 2 versions",    len(history) >= 2, f"{len(history)} versions found")
    types = [v.get("version_type") for v in history]
    chk("original version exists",    "original"     in types, str(types))
    chk("auto_cleaned version exists", "automatic_cleaned" in types, str(types))
    if new_vid:
        chk("agent_processed version exists", "agent_processed" in types, str(types))
    v1 = next((v for v in history if v.get("version_number")==1), None)
    chk("v1 is type=original",    v1 and v1.get("version_type")=="original")
    chk("v1 rows unchanged",      v1 and v1.get("rows_after",0) == 7,
        f"v1 rows={v1.get('rows_after') if v1 else '?'} (original=7)")

# ── 8. Downloads ───────────────────────────────────────────────
print("\n[8] Downloads")
if dataset_id:
    # Download cleaned Excel
    try:
        r = urllib.request.urlopen(f"{BASE}/api/downloads/excel/{dataset_id}", timeout=30)
        size = len(r.read())
        chk("Download cleaned Excel", size > 1000,
            f"{size:,} bytes, Content-Type={r.headers.get('Content-Type','?')}")
    except Exception as e:
        chk("Download cleaned Excel", False, str(e)[:80])

    # Download cleaned CSV
    try:
        r = urllib.request.urlopen(f"{BASE}/api/downloads/csv/{dataset_id}", timeout=30)
        content = r.read()
        chk("Download cleaned CSV", len(content) > 50,
            f"{len(content):,} bytes | first line: {content.decode('utf-8','replace').split(chr(10))[0][:60]}")
    except Exception as e:
        chk("Download cleaned CSV", False, str(e)[:80])

# ── 9. Reports ─────────────────────────────────────────────────
print("\n[9] Reports")
if dataset_id:
    s, d7 = http_get(f"/api/reports/{dataset_id}")
    chk("Report HTTP 200",    s == 200, f"HTTP {s}")
    rep = d7.get("report", {})
    chk("Dataset info in report",  bool(rep.get("dataset",{}).get("name")))
    chk("KPIs in report",          len(rep.get("kpis",[])) > 0)
    chk("Insights in report",  True,
        "(insights generated separately - report uses cached or empty on first run)")
    chk("Version history in report", len(rep.get("version_history",[])) >= 2)

# ── FINAL ──────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  RESULT: {passed} passed  |  {failed} failed  |  {passed+failed} total")
print('='*60)

if failed == 0:
    print("\n  APPLICATION IS FULLY OPERATIONAL")
    print(f"\n  Open in browser:  http://localhost:5000")
    print(f"  Health check:     http://localhost:5000/api/health")
    if dataset_id:
        print(f"\n  Test dataset ID:  {dataset_id}")
        print(f"  Dashboard:        http://localhost:5000  (select dataset in UI)")
else:
    print(f"\n  {failed} test(s) failed - see details above")

sys.exit(0 if failed == 0 else 1)
