#!/bin/sh
# Regenera images/NN.png de un post: ./render.sh 2026/2026-10-01-slug
# Requiere playwright (npx playwright install chromium). Cada <section class="s" id="sN"> es una lámina.
set -e
cd "$(dirname "$0")"
node -e '
const {chromium}=require("playwright");
(async()=>{const d=process.argv[1],b=await chromium.launch(),p=await b.newPage({viewport:{width:1100,height:1400}});
await p.goto("file://"+process.cwd()+"/"+d+"/slides.html");await p.evaluate(()=>document.fonts.ready);
const n=await p.locator(".s").count();
for(let i=1;i<=n;i++)await p.locator("#s"+i).screenshot({path:`${d}/images/0${i}.png`});
await b.close()})()' "$1"
