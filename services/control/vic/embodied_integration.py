"""Authenticated gateway to the independently running Tabletop8 service."""
import os
import re
import httpx
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from starlette.background import BackgroundTask


def install_embodied(app):
    socket = os.getenv('VIC_EMBODIED_SOCKET')
    base = os.getenv('VIC_EMBODIED_BASE', 'http://127.0.0.1:18664').rstrip('/')
    key = os.getenv('VIC_EMBODIED_KEY', '')
    def client():
        return httpx.AsyncClient(base_url=base, transport=httpx.AsyncHTTPTransport(uds=socket) if socket else None,
                                 timeout=httpx.Timeout(360, connect=5), follow_redirects=False)
    async def dashboard():
        if not key:raise HTTPException(503, '具身服务尚未连接')
        try:
            async with client() as c:
                r=await c.get('/');r.raise_for_status();return r.text
        except httpx.HTTPError as e:raise HTTPException(503, '具身服务暂不可达，请稍后重试') from e

    @app.get('/embodied-sim/')
    async def page(request:Request):
        app.state.review_access(request)
        html=await dashboard()
        html=re.sub(r'<script>(.*?)</script>', '<script src="/embodied-sim/dashboard.js"></script>', html, flags=re.S)
        # Authentication is handled by the portal; the upstream key never enters HTML.
        html=html.replace('<style>', '<style>#key,#connect,label:has(#key),img:not([src]){display:none} .portal-back{display:block;padding:12px;background:#edf5f2;color:#205a49}</style><style>')
        html=html.replace('<h1>', '<a class="portal-back" href="/review?kind=embodied">← 返回任务审阅 · 具身服务每次运行一个任务，请勿结束他人的任务</a><h1>')
        return HTMLResponse(html)

    @app.get('/embodied-sim/dashboard.js')
    async def script(request:Request):
        app.state.review_access(request)
        html=await dashboard()
        match=re.search(r'<script>(.*?)</script>',html,re.S)
        if not match:raise HTTPException(502,'具身控制台资源不完整')
        js=match.group(1)
        js=js.replace("fetch(path,", "fetch('/embodied-sim'+path,")
        js=js.replace(".src='/actor/'", ".src='/embodied-sim/actor/'").replace("location.origin+'/actor/'", "location.origin+'/embodied-sim/actor/'")
        # Use the portal cookie; no credential is kept in the native page.
        js=re.sub(r"\.\.\.\(control\?\{'Authorization':[^}]+\}:\{\}\)", '', js)
        js+='\n(async()=>{await el("connect").onclick();const q=new URLSearchParams(location.search);if(q.has("task"))el("task").value=q.get("task");if(["A","B","C"].includes(q.get("variant")))el("variant").value=q.get("variant");el("key").closest("label")?.setAttribute("hidden","");const preview=()=>{if(!sid){el("demo").src="/review-api/media/embodied/"+encodeURIComponent(el("task").value)+"/"+el("variant").value;el("demo").preload="metadata";}};el("task").onchange=preview;el("variant").onchange=preview;el("session").textContent="创建或接入任务后显示当前仿真画面。";preview();})();'
        return Response(js,media_type='text/javascript')

    @app.api_route('/embodied-sim/{path:path}', methods=['GET','POST'])
    async def proxy(path:str, request:Request):
        control=re.fullmatch(r'control/(tasks|status|sessions|results/[A-Za-z0-9_-]+|execution/[A-Za-z0-9_-]+)',path)
        actor=re.fullmatch(r'actor/[A-Za-z0-9_-]+/(observe|action|submit|demo|demo-frames)',path)
        public=path in ('health','client/hosted.py','client/prompt.txt')
        if not (control or actor or public):raise HTTPException(404,'Unknown embodied endpoint')
        if not actor:app.state.review_access(request)
        if request.method=='POST' and not (path=='control/sessions' or actor and path.endswith(('/action','/submit'))):
            raise HTTPException(405,'Method not allowed')
        if not key:raise HTTPException(503,'具身服务尚未连接')
        headers={k:v for k,v in request.headers.items() if k.lower() in ('content-type','range','if-range')}
        if control:headers['Authorization']='Bearer '+key
        c=client()
        try:
            upstream=await c.send(c.build_request(request.method,'/'+path,headers=headers,content=await request.body(),params=request.query_params),stream=True)
        except httpx.HTTPError as e:
            await c.aclose();raise HTTPException(503,'具身服务暂不可达，请稍后重试') from e
        async def close():await upstream.aclose();await c.aclose()
        out={k:v for k,v in upstream.headers.items() if k.lower() in ('content-type','content-length','content-range','accept-ranges','etag','last-modified')}
        return StreamingResponse(upstream.aiter_raw(),status_code=upstream.status_code,headers=out,background=BackgroundTask(close))
