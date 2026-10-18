"""Buduje wersję PWA (aplikacja na telefon) z arabeska.html do folderu docs/.

Uruchom po każdej zmianie w arabeska.html:  python build_pwa.py
"""
import hashlib
import json
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "docs"
SRC = (ROOT / "arabeska.html").read_text(encoding="utf-8")
ACCENT = "#A3305A"
BG = "#F3F2F7"

OUT.mkdir(exist_ok=True)
(OUT / "icons").mkdir(exist_ok=True)


def icon(size, maskable=False):
    img = Image.new("RGB", (size, size), ACCENT)
    d = ImageDraw.Draw(img)
    font_path = "C:/Windows/Fonts/georgiai.ttf"
    scale = 0.52 if maskable else 0.68
    font = ImageFont.truetype(font_path, int(size * scale))
    box = d.textbbox((0, 0), "A", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), "A", font=font, fill="#FFFFFF")
    return img


icon(192).save(OUT / "icons/icon-192.png")
icon(512).save(OUT / "icons/icon-512.png")
icon(512, maskable=True).save(OUT / "icons/maskable-512.png")
icon(180).save(OUT / "icons/apple-touch-icon.png")

manifest = {
    "name": "Arabeska",
    "short_name": "Arabeska",
    "description": "Twój dziennik baletowy: klasy, treningi z timerem i postępy.",
    "lang": "pl",
    "id": "/arabeska/app",
    "start_url": "./?source=pwa",
    "scope": "./",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": BG,
    "theme_color": ACCENT,
    "icons": [
        {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}
(OUT / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

# Konfiguracja Firebase (publiczne identyfikatory projektu, nie hasło) — firebase-config.json obok tego pliku.
cfg_path = ROOT / "firebase-config.json"
firebase_cfg = json.dumps(json.loads(cfg_path.read_text(encoding="utf-8"))) if cfg_path.exists() else "null"

# Logowanie Google + Firestore; aplikacja korzysta z tego przez window.ARABESKA_AUTH.
auth_js = """
(function(){
  var cfg=window.FIREBASE_CONFIG;if(!cfg)return;
  var ls=[],st={user:null,ready:false,failed:false,ref:null};
  var A=window.ARABESKA_AUTH={
    get user(){return st.user},get ready(){return st.ready},get failed(){return st.failed},
    onChange:function(cb){ls.push(cb);if(st.ready)cb(st.ref)},
    signIn:function(){return Promise.reject({code:'not-ready'})},
    signOut:function(){return Promise.resolve()}
  };
  function emit(){ls.forEach(function(cb){cb(st.ref)})}
  function load(src){return new Promise(function(res,rej){var s=document.createElement('script');s.src=src;s.onload=res;s.onerror=rej;document.head.appendChild(s)})}
  var B='https://www.gstatic.com/firebasejs/10.12.2/';
  load(B+'firebase-app-compat.js').then(function(){return Promise.all([load(B+'firebase-auth-compat.js'),load(B+'firebase-firestore-compat.js')])}).then(function(){
    firebase.initializeApp(cfg);
    var auth=firebase.auth(),db=firebase.firestore();
    auth.setPersistence(firebase.auth.Auth.Persistence.LOCAL).catch(function(){});
    A.signIn=function(){var p=new firebase.auth.GoogleAuthProvider();p.setCustomParameters({prompt:'select_account'});
      return auth.signInWithPopup(p).catch(function(e){if(e&&(e.code==='auth/popup-blocked'||e.code==='auth/operation-not-supported-in-this-environment'))return auth.signInWithRedirect(p);throw e})};
    A.signOut=function(){return auth.signOut()};
    auth.onAuthStateChanged(function(u){st.user=u?{email:u.email,name:u.displayName}:null;st.ready=true;st.ref=u?db.collection('users').doc(u.uid):null;emit()});
  }).catch(function(){st.ready=true;st.failed=true;emit()});
})();
"""

head = f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="{ACCENT}">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<style>:root{{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0;font:14px system-ui,sans-serif}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
<script>window.FIREBASE_CONFIG={firebase_cfg};</script>
<script>{auth_js}</script>
</head>
<body>
"""
tail = """
<script>
if('serviceWorker' in navigator){window.addEventListener('load',()=>navigator.serviceWorker.register('sw.js').catch(()=>{}))}
</script>
<script>
/* Przycisk instalacji: pasek na górze strony, gdy Chrome pozwala zainstalować aplikację. */
(function(){
  var standalone=window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  if(standalone)return;
  var bar=null,evt=null;
  function hide(){if(bar){bar.remove();bar=null}}
  function show(){
    if(bar)return;
    bar=document.createElement('div');
    bar.setAttribute('role','region');bar.setAttribute('aria-label','Instalacja aplikacji');
    bar.style.cssText='display:flex;align-items:center;gap:10px;padding:10px max(16px,env(safe-area-inset-left,0px));background:#A3305A;color:#fff;font:15px/1.4 system-ui,sans-serif';
    var txt=document.createElement('span');txt.style.flex='1';txt.textContent='Zainstaluj Arabeskę: ikona na ekranie i działanie offline.';
    var b=document.createElement('button');b.type='button';b.textContent='Zainstaluj';
    b.style.cssText='font:inherit;font-weight:600;border:0;border-radius:8px;padding:7px 14px;background:#fff;color:#A3305A;cursor:pointer';
    var x=document.createElement('button');x.type='button';x.textContent='×';x.setAttribute('aria-label','Zamknij');
    x.style.cssText='font:20px/1 system-ui;border:0;background:none;color:#fff;cursor:pointer;padding:4px 6px';
    b.onclick=function(){if(!evt)return;var e=evt;evt=null;e.prompt();e.userChoice.finally(hide)};
    x.onclick=hide;
    bar.append(txt,b,x);document.body.prepend(bar);
  }
  window.addEventListener('beforeinstallprompt',function(e){e.preventDefault();evt=e;show()});
  window.addEventListener('appinstalled',hide);
})();
</script>
</body>
</html>
"""
index = head + SRC + tail
(OUT / "index.html").write_text(index, encoding="utf-8")

version = hashlib.sha1((index + json.dumps(manifest)).encode("utf-8")).hexdigest()[:10]
sw = """const CACHE='arabeska-%s';
const SHELL=['./','index.html','manifest.webmanifest','icons/icon-192.png','icons/icon-512.png','icons/maskable-512.png','icons/apple-touch-icon.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(SHELL)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  const r=e.request;if(r.method!=='GET')return;
  const u=new URL(r.url);
  if(r.mode==='navigate'){
    e.respondWith(fetch(r).then(res=>{const cp=res.clone();caches.open(CACHE).then(c=>c.put('index.html',cp));return res}).catch(()=>caches.match('index.html')));return;
  }
  if(u.origin===location.origin||u.hostname.endsWith('fonts.googleapis.com')||u.hostname.endsWith('fonts.gstatic.com')||(u.hostname==='www.gstatic.com'&&u.pathname.startsWith('/firebasejs/'))){
    e.respondWith(caches.match(r).then(hit=>{const net=fetch(r).then(res=>{if(res&&(res.ok||res.type==='opaque')){const cp=res.clone();caches.open(CACHE).then(c=>c.put(r,cp))}return res}).catch(()=>hit);return hit||net}));
  }
});
""" % version
(OUT / "sw.js").write_text(sw, encoding="utf-8")
(OUT / ".nojekyll").write_text("", encoding="utf-8")
print("Zbudowano docs/ (wersja", version + ")")
