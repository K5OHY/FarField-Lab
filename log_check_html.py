"""The look of the Log analysis page: HTML and SVG built from the tables in log_check.py. Colors are fixed mid-tones that read on both the
light and the dark theme, and every block of text takes the page's own color, so nothing here follows the theme by hand."""
from html import escape

import numpy as np
import pandas as pd

import log_foundations as lf
from log_check import BALANCE_MIN, CONTINENT_NAMES, DX_FIRST, DX_MILES, DXCC_ENTITIES, CQ_ZONES, HABIT_SHARE, HIGH_DB, NEAR_REGIONS, SPLIT_KM, bands_top_down, pota_notes

BLUE, TEAL, AMBER = "#5B8CFF", "#19B5AE", "#F0A020"

CSS = """<style>
.lc{--b:#5B8CFF;--t:#19B5AE;--a:#F0A020;--g:#2FBF8A;--w:#F26B2A;--lane:rgba(128,128,128,.14);--line:rgba(128,128,128,.30);--soft:rgba(128,128,128,.07);line-height:1.45}
.lc *{box-sizing:border-box}
.lc .muted{opacity:.68}
.lc-tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:4px 0 14px}
.lc-tile{border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--soft)}
.lc-tile .n{font-size:32px;font-weight:750;letter-spacing:-.02em;line-height:1.05}.lc-tile .n small{font-size:14px;font-weight:600;opacity:.65;margin-left:4px}
.lc-tile .l{font-weight:600;margin-top:2px}.lc-tile .s{font-size:12.5px;opacity:.68;margin-top:2px}
.lc-card{border:1px solid var(--line);border-radius:16px;padding:16px 18px;margin:12px 0;background:var(--soft)}
.lc-card h4{margin:0 0 2px;font-size:17px}.lc-card .sub{font-size:13px;opacity:.68;margin:0 0 10px}
.lc-legend{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12.5px;opacity:.78;margin:0 0 10px}
.lc-legend i{display:inline-block;width:11px;height:11px;vertical-align:-2px;margin-right:5px;border-radius:3px}
.lc-legend i.pg{border-radius:50%;border:2.5px solid var(--a)}.lc-legend i.ac{border-radius:50%;background:var(--t)}
.lc-legend i.dia{width:9px;height:9px;border-radius:0;transform:rotate(45deg);margin-right:7px;background:currentColor}
.lc-bh,.lc-brow{display:grid;grid-template-columns:44px minmax(110px,.8fr) 78px minmax(260px,2.4fr);gap:16px;align-items:center}
.lc-bh{font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65;padding-bottom:8px;border-bottom:1px solid var(--line)}
.lc-brow{padding:10px 0;border-bottom:1px solid var(--line)}.lc-brow:last-child{border-bottom:0}
.lc-bname{font-size:18px;font-weight:750}
.lc-cont{display:grid;grid-template-columns:auto 1fr;align-items:baseline;gap:4px 7px}
.lc-cont .bar{grid-column:1/-1;height:9px;background:var(--lane);border-radius:9px;overflow:hidden}.lc-cont .bar i{display:block;height:100%;background:var(--b);border-radius:9px}
.lc-cont small{grid-column:1/-1;font-size:11.5px;opacity:.7}
.lc-rh,.lc-rr{display:grid;grid-template-columns:minmax(160px,1.5fr) 96px 78px 110px 100px minmax(120px,1.2fr) 96px;gap:12px;align-items:center}
.lc-rh{font-size:11.5px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65;padding-bottom:8px;border-bottom:1px solid var(--line)}
.lc-rr{padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}.lc-rr:last-child{border-bottom:0}
.lc-rr .rn{font-weight:650}.lc-rr .rn em{font-style:normal;font-size:10.5px;font-weight:700;letter-spacing:.06em;color:var(--a);border:1px solid var(--a);border-radius:99px;padding:1px 6px;margin-left:7px}
.lc-rr .dim{opacity:.55}.lc-rr small{opacity:.65}
.lc-share{display:grid;grid-template-columns:1fr 40px;align-items:center;gap:8px}.lc-share div{height:8px;background:var(--lane);border-radius:8px;overflow:hidden}.lc-share i{display:block;height:100%;background:var(--t);border-radius:8px}
.lc-cont b,.lc-sk b{font-size:17px}.lc-cont span,.lc-sk span{font-size:12px;opacity:.68}.lc-sk{display:flex;flex-direction:column;line-height:1.15}
.lc-dumb{position:relative;height:38px}
.lc-dumb:before{content:"";position:absolute;left:0;right:0;top:11px;height:2px;background:var(--lane);border-radius:2px}
.lc-dumb .g50{position:absolute;left:50%;top:5px;width:1px;height:14px;background:var(--line)}
.lc-dumb .gap{position:absolute;top:10px;height:4px;border-radius:4px;background:linear-gradient(90deg,var(--a),var(--t));opacity:.6}
.lc-dumb u{position:absolute;top:12px;width:14px;height:14px;border-radius:50%;transform:translate(-50%,-50%);text-decoration:none}
.lc-dumb .pg{border:3px solid var(--a);background:Canvas}.lc-dumb .ac{background:var(--t)}
.lc-dumb .cap{position:absolute;left:0;top:23px;font-size:12px;opacity:.78;white-space:nowrap}.lc-dumb .cap s{text-decoration:none;color:var(--a);font-weight:700}.lc-dumb .cap strong{color:var(--t)}
.lc-dumb.none{font-size:12.5px;opacity:.6;line-height:38px}
.lc-str{display:grid;grid-template-columns:1fr 84px;align-items:center;gap:10px}
.lc-sv{display:flex;flex-direction:column;align-items:flex-end;line-height:1.2}.lc-sv small{font-size:11px;opacity:.65;white-space:nowrap;font-weight:400}
.lc-axs{position:relative;height:14px;font-size:11px;font-weight:400;text-transform:none;letter-spacing:0}.lc-axs span{position:absolute;top:0;transform:translateX(-50%);white-space:nowrap}
.lc-sbar{position:relative;height:12px;background:var(--lane);border-radius:9px}.lc-sbar i{position:absolute;top:0;height:100%;border-radius:9px}
.lc-sbar .g{position:absolute;top:1px;bottom:1px;width:1px;background:currentColor;opacity:.2}
.lc-legend i.lg-pos{background:var(--b);border-radius:6px;width:20px;height:9px}.lc-legend i.lg-neg{background:var(--a);border-radius:6px;width:20px;height:9px}
.lc-legend i.lg-box{border:1.5px solid currentColor;opacity:.7;border-radius:4px;width:20px;height:11px;box-sizing:border-box}.lc-legend i.lg-thin{background:var(--b) repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 3px,transparent 3px 6px);border-radius:6px;width:20px;height:9px;opacity:.7}
.lc-sbar .pos{background:var(--b)}.lc-sbar .neg{background:var(--a)}
.lc-sbar .thin{opacity:.6;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 3px,transparent 3px 6px)}
.lc-steps{margin:4px 0 8px;padding-left:20px}.lc-steps li{margin:6px 0;font-size:13.5px;line-height:1.45}
.lc-sbar u{position:absolute;top:-2px;height:16px;border:1.5px solid currentColor;border-radius:4px;opacity:.55;text-decoration:none;box-sizing:border-box}
.lc-sbar .z{position:absolute;top:-3px;width:2px;height:18px;background:currentColor;opacity:.5}.lc-str b{font-size:14px;text-align:right}
.lc-str.none{font-size:12.5px;opacity:.6}
.lc-bnote{grid-column:1/-1;font-size:12.5px;line-height:1.4;padding:6px 10px;border-radius:7px;background:var(--lane)}.lc-bnote b{font-weight:700}
.lc-bsplit{grid-column:1/-1;font-size:12px;opacity:.72;margin-top:-4px}
.lc-note{font-size:12.5px;font-weight:600;padding:4px 10px;border-radius:99px;justify-self:start;border:1px solid var(--line)}
.lc-note.good{color:var(--g);border-color:var(--g)}.lc-note.warn{color:var(--w);border-color:var(--w)}
.lc-swim{overflow-x:auto}.lc-chart{min-width:640px}
.lc-lane{display:grid;grid-template-columns:70px 1fr;gap:4px;margin-bottom:8px}
.lc-lab{padding-top:34px;text-align:right;padding-right:6px}.lc-lab b{display:block;font-size:14px;line-height:1.1}.lc-lab span{font-size:11px;opacity:.6}
.lc-plot{position:relative;height:88px;background:var(--lane);border-radius:8px;overflow:hidden}
.lc-mid{position:absolute;left:4px;right:4px;top:56px;height:1.5px;background:var(--line)}
.lc-tick{position:absolute;top:0;bottom:0;width:0;border-left:1px dashed var(--line)}
.lc-b{position:absolute;border-radius:2.5px;background:var(--b)}.lc-b.rep{background:var(--a)}
.lc-s{position:absolute;border-radius:1.5px;background:var(--t);opacity:.55}
.lc-d{position:absolute;z-index:3;width:10px;height:10px;transform:rotate(45deg);background:currentColor;border:1.5px solid Canvas;margin-left:-5px}
.lc-kl{position:absolute;z-index:3;font-size:12.5px;font-weight:700;white-space:nowrap}
.lc-ph{font-size:12.5px;font-weight:650;opacity:.75;margin:10px 0 6px 74px}
.lc-chart + .lc-chart{margin-top:14px}
.lc-axis{position:relative;height:22px;margin-left:74px}.lc-axis span{position:absolute;top:2px;transform:translateX(-50%);font-size:12px;opacity:.65}
.lc-lad{display:grid;grid-template-columns:118px repeat(var(--k),1fr);align-items:center}
.lc-lad .cl .n{font-weight:500;font-size:11px;opacity:.55;margin-left:6px}
.lc-lad .hd{font-size:12px;opacity:.65;text-align:center;padding-bottom:4px}
.lc-lad .cl{font-size:12.5px;font-weight:650;padding:3px 0 3px 8px;height:30px;line-height:24px}
.lc-lad .cd{position:relative;height:30px;display:flex;align-items:center;justify-content:center}
.lc-lad .zb{background:var(--lane)}
.lc-lad .cd.ln:before{content:"";position:absolute;left:0;right:0;top:50%;height:2px;margin-top:-1px;background:var(--a);opacity:.75}
.lc-lad .cd.l0:before{left:50%}.lc-lad .cd.l1:before{right:50%}
.lc-lad .cd i{position:relative;width:13px;height:13px;border-radius:50%;background:var(--b);border:2.2px solid var(--a)}
.lc-cgw{overflow-x:auto;margin-top:8px}
.lc-cg{display:grid;grid-template-columns:42px repeat(var(--k),minmax(0,1fr));gap:4px;align-items:stretch;min-width:calc(42px + var(--k) * 44px)}
.lc-cg.dense .th span{display:none}.lc-cg.dense .th b{font-size:10.5px}.lc-cg.dense .cell .p{font-size:11.5px}
.lc-cg.dense .cell em{font-size:9px;padding:0 4px 0 3px;right:1px;bottom:1px}
.lc-cg .th{text-align:center;line-height:1.2}.lc-cg .th b{display:block;font-size:12.5px}.lc-cg .th span{font-size:10.5px;opacity:.6}
.lc-cg .bl{display:flex;align-items:center;font-weight:700;font-size:13.5px}
.lc-cg .cell{position:relative;height:48px;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid var(--line)}
.lc-cg .cell .p{font-size:15px;font-weight:700}
.lc-cg .cell.few{background:repeating-linear-gradient(135deg,transparent 0 5px,rgba(128,128,128,.28) 5px 6px)}.lc-cg .cell.few .p{opacity:.45;font-weight:500}
.lc-cg .cell em{position:absolute;right:3px;bottom:2px;font-style:normal;font-size:10.5px;font-weight:700;background:Canvas;color:CanvasText;border-radius:99px;padding:0 6px 0 4px;display:flex;align-items:center;gap:3px;border:1px solid var(--line)}
.lc-cg .cell em i{display:inline-block;width:7px;height:7px;background:var(--a);transform:rotate(45deg);border:1px solid Canvas}
.lc-ramp{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:12px 0 4px;font-size:12px;opacity:.8}
.lc-ramp b{display:inline-block;width:130px;height:9px;border-radius:6px;background:linear-gradient(90deg,rgba(32,178,170,.15),rgba(32,178,170,.95));vertical-align:middle;margin:0 6px}
.lc-says{margin:12px 0 0;padding-left:20px}.lc-says li{margin:6px 0;font-size:14px}
.lc-dx .cell{height:auto;min-height:66px;padding:5px 2px;flex-direction:column;gap:3px;background:transparent}.lc-dx .cell .p{line-height:1}
.lc-dx .cell.s3{background:rgba(32,178,170,.88)}.lc-dx .cell.s3 .p{color:#04201e}
.lc-dx .cell.s1{background:rgba(32,178,170,.40)}
.lc-dx .cell.none .p{opacity:.35;font-weight:500}
.lc-dx .cell.sparse{background:repeating-linear-gradient(45deg,transparent 0 3px,rgba(128,128,128,.16) 3px 4px);border-style:dashed}.lc-dx .cell.sparse .p{opacity:.55;font-weight:500}
.bc{border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:10px 0}.bc h5{margin:0 0 4px;font-size:16px;font-weight:600}.bc h5 small{font-size:12px;font-weight:400;opacity:.6;margin-left:8px}
.bc-body{position:relative}.bc-act{position:absolute;left:104px;right:0;top:0;bottom:0;pointer-events:none}.bc-act i{position:absolute;top:0;bottom:0;border-radius:4px;background:currentColor;opacity:.09}
.bc-row{display:grid;grid-template-columns:104px minmax(0,1fr);align-items:center;margin-top:2px}.bc-lab{font-size:12px;opacity:.78}.bc-lab i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;background:var(--c)}
.bc-trk{position:relative;height:17px;background-image:linear-gradient(90deg,var(--line) 0 1px,transparent 1px);background-size:calc(100% / var(--n)) 100%}
.bc-bar{position:absolute;top:4px;height:9px;border-radius:4px;background:var(--c)}.bc-bar.p{opacity:.38}
.bc-thin{position:absolute;top:4px;height:9px;border-radius:4px;border:1px dashed currentColor;opacity:.45;box-sizing:border-box}
.bc-tick{position:absolute;top:5px;width:2px;height:8px;background:currentColor;opacity:.45}
.bc-dot{z-index:2;position:absolute;top:3px;width:10px;height:10px;margin-left:-5px;border-radius:50%;border:2px solid Canvas;box-sizing:content-box;background:var(--c)}
.bc-ring{position:absolute;top:2px;width:9px;height:9px;margin-left:-6px;border-radius:50%;border:2px solid #3b82f6;box-sizing:content-box;background:Canvas}
.bc-none{font-size:12px;opacity:.55;line-height:17px;padding-left:4px}
.bc-ax{position:relative;height:15px;margin-top:3px}.bc-ax span{position:absolute;font-size:11px;opacity:.6;transform:translateX(-50%)}
.bc p{margin:8px 0 0;font-size:14px}.bc p.sub{font-size:12.5px;margin:3px 0 0}
.lc-dx .m{display:flex;flex-wrap:wrap;gap:3px;align-items:center;justify-content:center;min-height:15px}
.lc-dx .cell em{position:static}.lc-dx .cell em.st{color:var(--a);padding:0 4px}
.lc-dx .cell em u{display:inline-block;width:3px;height:3px;border-radius:50%;background:Canvas;border:2px solid #3b82f6;box-sizing:content-box}
.lc-cg .grp{grid-column:1/-1;font-size:12px;font-weight:600;opacity:.7;margin:8px 0 0}
.lc-key{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin:10px 0 0;font-size:12px;opacity:.85}
.lc-key .sw{display:inline-flex;align-items:center;gap:6px}.lc-key .sw b{display:inline-block;width:22px;height:13px;border-radius:4px;border:1px solid var(--line)}
.lc-reg{border-collapse:collapse;width:100%;font-size:13.5px}.lc-reg td,.lc-reg th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}
.lc-reg th{font-weight:600;font-size:12px;opacity:.7}.lc-reg small{opacity:.65}
.lc-kp{position:absolute;bottom:6px;border-radius:2px 2px 0 0}.lc-storm{position:absolute;left:0;right:0;height:0;border-top:1px dashed rgb(230,120,40);opacity:.8}
.lc-fl{position:absolute;top:50%;border-radius:50%;border:1px solid Canvas}.lc-fn{position:absolute;top:2px;transform:translateX(-50%);font-size:10.5px;font-weight:700;opacity:.8;pointer-events:none}
.lc-fnone{position:absolute;left:8px;top:50%;transform:translateY(-50%);font-size:12px;opacity:.55}
.lc-fl{cursor:help}.lc-fl:focus{outline:2px solid rgb(32,178,170);outline-offset:2px}
.lc-kq{position:absolute;bottom:6px;background:var(--a);border-radius:1.5px 1.5px 0 0}
.lc-card a{color:inherit;text-decoration:underline}
[id^="sec-"]{scroll-margin-top:72px}
.lc-hl{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:18px;margin-top:10px}.lc-hl h5{margin:0 0 6px;font-size:14px}
.lc-hl table{width:100%;border-collapse:collapse;font-size:13px}.lc-hl td,.lc-hl th{padding:4px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.lc-hl th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;opacity:.65;font-weight:700}.lc-hl td.n{text-align:right;font-variant-numeric:tabular-nums}
.lc-hl .hb{display:block;height:8px;border-radius:5px;background:var(--b);min-width:2px}.lc-hl .hb.new{background:var(--t);margin-top:2px}
.lc-hl .none{opacity:.55;font-size:13px}
.dv-look{display:grid;grid-template-columns:46px 1fr;gap:12px;align-items:start;padding:8px 0;border-top:1px solid var(--line)}.dv-look:first-of-type{border-top:0}
.dv-look b{font-size:17px}.dv-look div{font-size:14.5px}
.dv-row{display:grid;grid-template-columns:92px 1fr;align-items:center;margin-top:7px}.dv-row.top{margin-top:2px}
.dv-lab{color:inherit;opacity:.65;font-size:12.5px}.dv-name{font-weight:800;font-size:16px}
.lc-take{margin:6px 0 10px;padding:10px 12px;border-left:3px solid var(--t);background:rgba(32,178,170,.07);border-radius:0 8px 8px 0;font-size:14.5px}
.lc-rrow{display:grid;grid-template-columns:170px 1fr;gap:14px;padding:12px 0;border-top:1px solid var(--line)}.lc-rwho{display:flex;flex-direction:column;gap:4px;align-items:flex-start;font-size:13px}.lc-rwho .m{font-size:12px;opacity:.65}
.lc-rhead{font-size:16px;margin-bottom:3px}.lc-rline{display:flex;flex-wrap:wrap;gap:4px 6px;align-items:center;margin:3px 0;font-size:13px}.lc-rline .lab{width:150px;opacity:.65;font-size:12px}
.lc-rsup{font-size:12px;opacity:.68;margin-top:8px}.lc-rfoot{font-size:12.5px;opacity:.68;margin:12px 0 2px}
.lc-rg{display:inline-block;border-radius:99px;padding:1px 10px;font-size:12.5px}.lc-rg.on{background:rgba(32,178,170,.18);border:1px solid rgba(32,178,170,.55)}.lc-rg.off{opacity:.65;border:1px dashed var(--line)}
@media (max-width:700px){.lc-rrow{grid-template-columns:1fr}.lc-rline .lab{width:100%}}
.dv-bandkey{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 2px;font-size:.85rem}.dv-bandkey b{font-weight:600;margin-right:2px}
.dv-chip{display:inline-block;padding:0 9px;border-radius:7px;font-weight:800;line-height:1.5;border:1px solid rgba(128,128,128,.55)}
.dv-strip{position:relative;height:28px;border-radius:7px;overflow:hidden;background:var(--lane)}
.dv-seg{position:absolute;top:0;height:100%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12.5px;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.7);border-right:1px solid rgba(0,0,0,.3);overflow:hidden}
.dv-seg.none{background:repeating-linear-gradient(45deg,transparent 0 6px,rgba(128,128,128,.14) 6px 12px);color:inherit;opacity:.6;font-weight:500;text-shadow:none}
.dv-track{position:relative;height:28px;background:var(--lane);border-radius:7px}
.dv-tk{position:absolute;top:0;bottom:0;width:1px;background:var(--line)}
.dv-bar{position:absolute;top:4px;height:20px;border-radius:5px;box-shadow:inset 0 0 0 1px rgba(128,128,128,.6)}.dv-bar.pale{opacity:.4}
.dv-tri{position:absolute;top:2px;width:0;height:0;transform:translateX(-50%);z-index:2;cursor:default}
.dv-tri::before{content:"\\25b3";position:absolute;left:-10px;top:-1px;font-size:20px;line-height:24px;font-weight:700;color:#fff;text-shadow:0 0 2px #000,0 0 3px #000}
.dv-sel{position:absolute;top:1px;bottom:1px;border:1.5px dashed rgba(255,255,255,.8);border-radius:6px;box-shadow:0 0 0 1px rgba(0,0,0,.5);pointer-events:none;z-index:1}
.dv-ring{position:absolute;top:6px;width:14px;height:14px;border-radius:50%;border:2.5px solid #fff;box-shadow:0 0 0 1px rgba(0,0,0,.55)}
.dv-dot{position:absolute;top:5px;width:16px;height:16px;border-radius:50%;background:#fff;border:3px solid;z-index:3}
.dv-dot.multi{font-style:normal;width:auto;min-width:16px;padding:0 3px;box-sizing:content-box;border-radius:11px;color:#111;font-size:11.5px;font-weight:800;line-height:16px;text-align:center;cursor:default}
.dv-call{position:absolute;top:-3px;font-size:11.5px;font-weight:700;background:rgba(20,24,32,.88);color:#fff;padding:1px 5px;border-radius:5px;z-index:4;white-space:nowrap}
.dv-call.r{margin-left:12px}.dv-call.l{transform:translateX(calc(-100% - 12px))}
.dv-axis{position:relative;height:20px;margin-left:92px;font-size:12px;opacity:.7}.dv-axis span{position:absolute;transform:translateX(-50%);top:4px}
.dv-key{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;margin:10px 0 4px}
.dv-ki{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;border:1px solid var(--line);border-radius:9px}.dv-ki .mk{flex:0 0 28px;display:flex;justify-content:center;padding-top:2px}
.dv-ki b{display:block;font-size:13.5px}.dv-ki span{font-size:12.5px;opacity:.78;line-height:1.35}.dv-ki .mk i{margin:0}
.dv-more{margin:8px 0 2px}.dv-more summary{cursor:pointer;font-size:13px;opacity:.78}.dv-more[open] summary{margin-bottom:2px}
.dv-row.sel .dv-chip{box-shadow:0 0 0 2px #fff,0 0 0 3px rgba(0,0,0,.5)}
.dv-track.two{height:56px}.dv-track.two .dv-bar{top:4px;height:48px}.dv-track.two .dv-tri{top:2px}.dv-track.two .dv-dot{top:31px}
.dv-track.two.lab{height:80px}.dv-track.two.lab .dv-bar{height:72px}.dv-track.two.lab .dv-call{top:57px;margin-left:0;transform:translateX(-50%)}
.dv-legend{display:flex;gap:22px;flex-wrap:wrap;font-size:13px;opacity:.8;margin-top:10px;align-items:center}.dv-legend i{display:inline-block;vertical-align:middle;margin-right:7px}
.dv-sw{width:26px;height:12px;border-radius:4px;background:linear-gradient(90deg,#8a8f98 0 60%,#4a4e55 60%)}.dv-ld{width:14px;height:14px;border-radius:50%;background:#fff;border:3px solid #8a8f98}
.dv-lt{display:inline-block;width:16px;height:16px;position:relative;vertical-align:middle;margin-right:7px}
.dv-lt::before{content:"\\25b3";position:absolute;left:-1px;top:-4px;font-size:20px;line-height:24px;font-weight:700;color:#fff;text-shadow:0 0 2px #000,0 0 3px #000}
.lc-sec{margin:30px 0 6px;padding-top:14px;border-top:1px solid var(--line)}.lc-sec h3{margin:0;font-size:23px;line-height:1.25}.lc-sec p{margin:3px 0 0;font-size:14px;opacity:.7}
.lc-glance{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:0 0 14px}
.lc-glance a{display:block;border:1px solid var(--line);border-radius:14px;padding:12px 14px;background:var(--soft);text-decoration:none;color:inherit}
.lc-glance a:hover{border-color:rgb(32,178,170)}.lc-glance .k{display:block;font-size:11px;font-weight:700;letter-spacing:.08em;opacity:.65;text-transform:uppercase}
.lc-glance b{display:block;margin-top:4px;font-size:14px;line-height:1.35;font-weight:600}.lc-glance .go{display:block;margin-top:6px;font-size:12px;opacity:.6}
.lc-hero{border:1px solid var(--line);border-left:6px solid rgb(32,178,170);border-radius:14px;padding:16px 20px;margin:0 0 12px}
.lc-hero .k{font-size:11px;font-weight:700;letter-spacing:.08em;opacity:.65}.lc-hero h3{margin:2px 0 6px;font-size:24px;line-height:1.2}
.lc-hero p{margin:0;font-size:15px}.lc-hero p.s{margin-top:6px;font-weight:600}
.lc-reg .dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:rgb(32,178,170);margin-right:6px}.lc-reg .no{opacity:.35}
.lc-two{display:grid;grid-template-columns:minmax(280px,1.05fr) 1fr;gap:20px;align-items:start}
.lc-facts{display:grid;gap:10px}.lc-fact{border:1px solid var(--line);border-radius:12px;padding:10px 13px}
.lc-fact .h{font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;opacity:.65}.lc-fact .b{font-size:14.5px;margin-top:2px}
.lc-fact.warn{border-color:var(--w)}.lc-fact.warn .h{color:var(--w);opacity:1}
@media (max-width:820px){.lc-rh{display:none}.lc-rr{grid-template-columns:1fr 1fr}.lc-rr .rn{grid-column:1/-1}.lc-rr [data-l]:before{content:attr(data-l) ": ";opacity:.6}
.lc-tiles{grid-template-columns:repeat(2,1fr)}.lc-two{grid-template-columns:1fr}
.lc-bh{display:none}.lc-brow{grid-template-columns:48px 1fr;grid-template-areas:"n c" "n s";gap:6px 12px}
.lc-bname{grid-area:n}.lc-cont{grid-area:c}.lc-sk{display:none}.lc-str{grid-area:s}}
</style>"""


def pct(x):
    return f"{x * 100:.0f}%"


def _tile(number, color, label, small, unit="", title=""):
    return (f'<div class="lc-tile"' + (f' title="{escape(title)}"' if title else "") + f'><div class="n" style="color:var({color})">{number}{f"<small>{unit}</small>" if unit else ""}</div>'
            f'<div class="l">{label}</div><div class="s">{small}</div></div>')


RATE_NOTE = ("Contacts divided by the time between them, counting only gaps of 30 minutes or less, so a break is not counted as slow operating. "
             "It is an estimate: a log does not say when you were actually on the air.")


def tiles_html(s, repeats):
    """Four tiles: contacts, the estimated active rate, the bands worked, and the stations that came back on another band."""
    where = f"{s['stations']} stations"
    if s["states"]:
        where += f" · {s['states']} states or provinces"
    bands = s["bands"]
    span = bands[0] if len(bands) == 1 else f"{bands[0]} down to {bands[-1]}"
    return ('<div class="lc"><div class="lc-tiles">'
            + _tile(s["contacts"], "--b", "contacts", escape(where))
            + _tile("–" if np.isnan(s["per_hour"]) else f"{s['per_hour']:.0f}", "--t", "estimated active rate",
                    f"busiest hour {s['best_hour']} contacts, from {s['best_hour_start']:%H:%M}Z" + (" · pauses over 30 min not counted" if s["on_air_hours"] else ""),
                    "" if np.isnan(s["per_hour"]) else "/ hour", RATE_NOTE)
            + _tile(len(bands), "--a", "bands worked", escape(span))
            + _tile(repeats, "--g", "came back on another band", "stations worked on 2 or more bands")
            + '</div></div>')


ENTITY_ROWS = 12      # the countries shown at first; the rest are under a 'Show more' box


def worked_tiles_html(w):
    """A second row of tiles: DXCC entities, continents, US states and CQ zones, each against the whole it is part of."""
    n = w["n_entities"]
    away = int((w["ents"]["cont"] != w["home"]).sum())
    tiles = [_tile(n, "--b", "DXCC entities worked", f"{away} outside {escape(CONTINENT_NAMES.get(w['home'], 'your continent'))}" if away else "all on your continent",
                   f"of {DXCC_ENTITIES}", "")]
    seen = len(w["continents"])
    tiles.append(_tile(seen, "--t", "continents", "all six: WAC" if seen == 6 else "missing " + escape(", ".join(w["missing_continents"])), "of 6"))
    if w["has_us"]:
        miss = w["missing_states"]
        tiles.append(_tile(len(w["states"]), "--a", "US states", ("all 50: WAS" if not miss else f"missing {', '.join(miss)}" if len(miss) <= 6 else f"{len(miss)} to go")
                           + (f" · {len(w['provinces'])} Canadian provinces" if w["has_ca"] else ""), "of 50"))
    if w["cq"] is not None:
        tiles.append(_tile(len(w["cq"]), "--g", "CQ zones", f"{w['itu']} ITU zones" if w["itu"] is not None else "", f"of {CQ_ZONES}"))
    return '<div class="lc" style="margin-top:12px"><div class="lc-tiles">' + "".join(tiles) + "</div></div>"


def _ent_rows(w, bands, first, rows):
    out = []
    for key, r in w["ents"].iloc[first:first + rows].iterrows():
        dots = "".join(f'<td>{"&#9679;" if b in r["bands"] else "<span class=\"no\">&middot;</span>"}</td>' for b in bands)
        out.append(f'<tr><td><b>{escape(str(r["name"]))}</b> <small>{escape(str(r["cont"]))}</small></td><td>{int(r["contacts"])}</td>{dots}</tr>')
    return "".join(out)


def worked_html(w, bands, rows=ENTITY_ROWS, first=0):
    """The countries worked, with the contacts and a dot for each band, those outside the home continent first; `first` and `rows` pick the stretch
    of the list shown (the rest wait under a 'Show more' box)."""
    head = "<tr><th>Country</th><th>Contacts</th>" + "".join(f"<th>{escape(b)}</th>" for b in bands) + "</tr>"
    table = f'<div class="lc-cgw"><table class="lc-reg">{head}{_ent_rows(w, bands, first, rows)}</table></div>'
    if first:
        return '<div class="lc">' + table + "</div>"
    counts = " · ".join(f"{escape(b)} {n}" for b, n in w["per_band"].items())
    return ('<div class="lc"><div class="lc-card"><h4>What you worked</h4>'
            f'<p class="sub">{w["n_entities"]} DXCC entities in this log, those outside {escape(CONTINENT_NAMES.get(w["home"], "your continent"))} first. A dot means the country was '
            'worked on that band. This is what the log says, not what is confirmed by LoTW or the ARRL.</p>' + table
            + f'<p class="sub" style="margin-top:8px"><b>{w["band_countries"]} band-countries</b> (each country counted once per band): {counts}.</p></div></div>')


def still_to_work_html(w):
    """What is still missing, for the stretch of the log: continents, US states, Canadian provinces and CQ zones. Empty when nothing is missing."""
    items = []
    if w["missing_continents"]:
        items.append(f"<li><b>Continents ({len(w['missing_continents'])}):</b> {escape(', '.join(w['missing_continents']))}</li>")
    if w["has_us"] and w["missing_states"]:
        items.append(f"<li><b>US states ({len(w['missing_states'])}):</b> {escape(', '.join(w['missing_states']))}</li>")
    if w["has_ca"] and w["missing_provinces"]:
        items.append(f"<li><b>Canadian provinces and territories ({len(w['missing_provinces'])}):</b> {escape(', '.join(w['missing_provinces']))}</li>")
    if w["missing_cq"]:
        items.append(f"<li><b>CQ zones ({len(w['missing_cq'])}):</b> {escape(', '.join(str(z) for z in w['missing_cq']))}</li>")
    return '<div class="lc"><ul class="lc-says">' + "".join(items) + "</ul></div>" if items else ""


def _teal(share):
    """A teal that deepens with the share of receivers that would hear you."""
    return f"rgba(32,178,170,{0.12 + 0.80 * float(share) ** 1.6:.2f})"


def _local_time(s, tz_name):
    """The time of a slot in the visitor's time zone, as HH:MM, or an empty string when there is none or it is not a zone."""
    from zoneinfo import ZoneInfo
    try:
        return f"{pd.Timestamp(s).tz_localize('UTC').astimezone(ZoneInfo(tz_name)):%H:%M}" if tz_name else ""
    except Exception:
        return ""


def _near(grid):
    """'500 km (311 miles)': the radius the WSPR transmitters were taken from, as the grid carries it (300 miles for a grid made before the radius
    could be chosen)."""
    km = (grid.attrs.get("evidence") or {}).get("radius_km") or 300 * lf.KM_PER_MILE
    return lf.radius_text(km)


def _near_words(grid, text):
    """`text` with its 'within 300 miles of you' made to say the radius that was really used."""
    return text.replace("within 300 miles of you", f"within {_near(grid)} of you")


def _evidence_line(grid):
    """How much WSPR the DX picture rests on, so a thin picture looks thin: the reports, the transmitters near you, the stations that decoded
    them and how far away the farthest was."""
    ev = grid.attrs.get("evidence") or {}
    if not ev.get("reports"):
        return ""
    far = round(ev["farthest_km"] / 1.609344, -2)
    thin = " That is few transmitters, so the picture is thin." if ev["transmitters"] < 5 else ""
    return (f'<p class="sub"><b>The evidence:</b> {ev["reports"]:,} WSPR reports from {ev["transmitters"]} transmitter{"s" if ev["transmitters"] != 1 else ""} within {_near(grid)} of you, decoded by '
            f'{ev["receivers"]:,} stations as far away as {far:,.0f} miles.{thin}</p>')


def _runs_text(slots, stamp):
    """The half hours in `slots` as windows ('13:30-15:00, 18:00-20:30'): half hours that do not follow each other are separate windows."""
    from log_check import _slot_windows
    step = pd.Timedelta(minutes=30)
    runs = _slot_windows(slots)
    text = ", ".join(f"{stamp(a)}&ndash;{stamp(b + step)}" for a, b in runs[:3])
    return text + (f", and {len(runs) - 3} more" if len(runs) > 3 else "")


DX_VIEWS = {"estimate": "Estimate for my station", "observed": "What WSPR showed"}


def dx_windows_html(grid, notes, power_w, mode="CW", tz_name=None, view="estimate"):
    """When DX was there while you were on the air: a box for each band and half hour. In the 'observed' view it counts the WSPR stations
    DX_MILES or more away that decoded WSPR transmitters near you; in the 'estimate' view, those that looked strong enough to hear a signal like
    yours. Your contacts (diamond), contacts outside North America (star) and skimmers that far away that spotted you (a ring) sit on top, and
    the lines that say it in words follow. Bands you did not work come after the ones you did."""
    miles = f"{DX_MILES:,}"
    observed = view == "observed"
    first = grid.drop_duplicates("band")
    flags = dict(zip(first["band"], first["worked"])) if "worked" in first else {b: True for b in first["band"]}
    all_bands = [b for b in first["band"] if flags[b]] + [b for b in first["band"] if not flags[b]]
    panels = []
    for panel, d in grid.groupby("panel"):
        slots = sorted(d["slot"].unique())
        by = {(r.band, r.slot): r for r in d.itertuples()}
        head = "<div></div>" + "".join(f'<div class="th"><b>{pd.Timestamp(s):%H:%M}</b>'
                                       + (f"<span>{_local_time(s, tz_name)} local</span>" if _local_time(s, tz_name) else "") + "</div>" for s in slots)
        cells, in_group = [], False
        for b in all_bands:
            if not flags[b] and not in_group:
                cells.append('<div class="grp">Bands you did not work</div>')
                in_group = True
            cells.append(f'<div class="bl">{escape(b)}</div>')
            for s in slots:
                r = by[(b, s)]
                n = r.dx_heard if observed else r.dx_good
                kind = "s3" if n >= 3 else "s1" if n >= 1 else ("few" if (not observed and r.dx_heard > 0) else "none")
                marks = (f'<em><i></i>{r.contacts}</em>' if r.contacts else "") + ('<em class="st" title="a contact outside North America">&#9733;</em>' if r.dx_contacts else "") \
                    + ('<em title="a skimmer that far away spotted you"><u></u></em>' if r.rbn_far else "")
                tip = (f"{b} {pd.Timestamp(s):%H:%M}Z: {r.dx_heard} WSPR stations over {miles} miles decoded WSPR near you; {r.contacts} contacts" if observed else
                       f"{b} {pd.Timestamp(s):%H:%M}Z: {r.dx_good} WSPR stations over {miles} miles estimated strong enough for {power_w:g} W; {r.dx_heard} that far "
                       f"decoded WSPR near you; {r.contacts} contacts")
                cells.append(f'<div class="cell {kind}" title="{escape(tip)}"><span class="p">{n if n else "&ndash;"}</span>'
                             f'<span class="m">{marks}</span></div>')
        title = f'<p class="sub" style="margin:14px 0 0"><b>{pd.Timestamp(slots[0]):%a %d %b}</b> (UTC)</p>' if grid["panel"].nunique() > 1 else ""
        dense = " dense" if len(slots) > 10 else ""
        panels.append(title + f'<div class="lc-cgw"><div class="lc-cg lc-dx{dense}" style="--k:{len(slots)}">{head}{"".join(cells)}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(lead)}</b> {escape(rest)}</li>" for lead, rest in notes) + "</ul>") if notes else ""
    if observed:
        heading = "Band conditions while you were on the air: what WSPR showed"
        intro = (f'<p class="sub">What WSPR showed. Each box counts the WSPR stations over {miles} miles from you that decoded WSPR transmitters near you in the hour up to '
                 'the end of that half hour. Nothing is assumed about your power or mode. It counts different stations, not reports. '
                 '(A WSPR station here is a receiver, not an RBN skimmer.)</p>')
        reading = ('<p class="sub"><b>How to read it:</b> read across a row to follow a band over time. A dash means no station that far decoded WSPR near you. '
                   'Bands have different numbers of stations, so use the counts to compare hours, not to rank bands.</p>')
        key = ('<div class="lc-key"><span class="sw"><b style="background:rgba(32,178,170,.88)"></b>3 or more decoded WSPR</span>'
               '<span class="sw"><b style="background:rgba(32,178,170,.40)"></b>1 or 2</span><span class="sw"><b></b>none that far</span></div>')
        caveat = ('<p class="sub" style="margin-top:10px">This is what was decoded, with no estimate in it. WSPR only covers stations within 300 miles of you, and a band with few '
                  'transmitters there has thin evidence. ')
    else:
        heading = f"Band conditions while you were on the air: estimate for {power_w:g} W"
        intro = (f'<p class="sub">An estimate of when a signal like yours could have reached more than {miles} miles. Each box counts the WSPR stations over {miles} miles '
                 f'from you that decoded WSPR transmitters near you in the hour up to the end of that half hour and looked strong enough to hear {power_w:g} W using '
                 f'{escape(mode)} (their reports restated to your power, with 3 dB to spare). It counts different stations, not reports. '
                 '(A WSPR station here is a receiver, not an RBN skimmer.)</p>')
        reading = ('<p class="sub"><b>How to read it:</b> read across a row to follow a band over time. A dash means no station that far looked strong enough; '
                   'a striped box means stations that far decoded WSPR, but none looked strong enough. Bands have different numbers of stations, so use the counts to '
                   'compare hours, not to rank bands.</p>')
        key = ('<div class="lc-key"><span class="sw"><b style="background:rgba(32,178,170,.88)"></b>3 or more look strong enough</span>'
               '<span class="sw"><b style="background:rgba(32,178,170,.40)"></b>1 or 2</span>'
               '<span class="sw"><b style="background:repeating-linear-gradient(135deg,transparent 0 5px,rgba(128,128,128,.4) 5px 6px)"></b>decoded WSPR, none strong enough</span>'
               '<span class="sw"><b></b>no reports that far</span></div>')
        caveat = ('<p class="sub" style="margin-top:10px">"Strong enough" is an estimate: each station\'s WSPR reports are restated to your power and compared with what the mode needs, '
                  'assuming an ordinary antenna. It tends to run high, so use it to compare bands and hours, not to promise a contact. WSPR only covers stations within 300 miles '
                  'of you, and a band with few of them has thin evidence. ')
    return (f'<div class="lc"><div class="lc-card"><h4>{escape(heading)}</h4>' + intro + reading + _evidence_line(grid) + "".join(panels) + key
            + '<div class="lc-key"><span class="sw"><span style="display:inline-block;width:8px;height:8px;background:var(--a);transform:rotate(45deg)"></span> contacts in that half hour</span>'
              '<span class="sw"><span style="color:var(--a);font-weight:700">&#9733;</span> a contact outside North America</span>'
              f'<span class="sw"><span style="display:inline-block;width:3px;height:3px;border-radius:50%;background:Canvas;border:2px solid #3b82f6"></span> an RBN skimmer over {miles} miles away spotted you</span></div>'
            + says + _near_words(grid, caveat)
            + 'RBN has far fewer skimmers than WSPR has receivers, especially outside North America and Europe: a ring is proof you were heard that far, but no ring says nothing. '
              'These lines say what was seen in the data, not what you should have done.</p></div></div>')


def openings_html(cells, grid=None, tz_name=None, view="estimate"):
    """How you used the openings, as the answer first: a one-sentence headline and a box for each band and time bin, read for the destination
    `cells` (log_openings.opening_cells) was made for, with a short key. The shading is WSPR path evidence to that destination (receivers there that
    decoded WSPR near you in the 'observed' view, that looked strong enough for you in the 'estimate' view); a dashed box has too little WSPR behind it
    to say, a striped one has stations that decoded WSPR but none strong enough, and a blank one has no reports from there. On top: a diamond when you
    were active on the band in that box, a star when you logged a contact with the destination, and a ring when a skimmer there spotted you (RBN, only
    where it applies). The statement for each box is in its tooltip. How to read it, and what it rests on, is openings_explain_html."""
    from log_openings import openings_headline, rbn_sentence, where_forms
    where = cells.attrs.get("where") or where_forms("sector", None)
    observed = view == "observed"
    first = cells.drop_duplicates("band")
    flags = dict(zip(first["band"], first["worked"]))
    all_bands = [b for b in first["band"] if flags[b]] + [b for b in first["band"] if not flags[b]]
    panels = []
    for panel, d in cells.groupby("panel"):
        slots = sorted(d["slot"].unique())
        by = {(r.band, r.slot): r for r in d.itertuples()}
        head = "<div></div>" + "".join(f'<div class="th"><b>{pd.Timestamp(s):%H:%M}</b>'
                                       + (f"<span>{_local_time(s, tz_name)} local</span>" if _local_time(s, tz_name) else "") + "</div>" for s in slots)
        out, in_group = [], False
        for b in all_bands:
            if not flags[b] and not in_group:
                out.append('<div class="grp">Bands you did not work</div>')
                in_group = True
            out.append(f'<div class="bl">{escape(b)}</div>')
            for s in slots:
                r = by[(b, s)]
                kind = {"evidence": "s3" if r.n >= 3 else "s1", "below threshold": "few", "insufficient coverage": "sparse"}.get(r.state, "none")
                glyph = str(r.n) if r.state == "evidence" else "?" if r.state == "insufficient coverage" else "&ndash;"
                marks = ((f'<em><i></i>{r.active}</em>' if r.active else "")
                         + ('<em class="st" title="a contact with the destination">&#9733;</em>' if r.with_dest else "")
                         + ('<em title="a skimmer there spotted you"><u></u></em>' if r.rbn_state == "evidence" else ""))
                tip = f"{b} {pd.Timestamp(s):%H:%M}Z, {r.state}. {r.text} {rbn_sentence(r.rbn_state, r.rbn_n, where, r.rbn_why)}"
                out.append(f'<div class="cell {kind}" title="{escape(tip)}"><span class="p">{glyph}</span><span class="m">{marks}</span></div>')
        title = f'<p class="sub" style="margin:14px 0 0"><b>{pd.Timestamp(slots[0]):%a %d %b}</b> (UTC)</p>' if cells["panel"].nunique() > 1 else ""
        dense = " dense" if len(slots) > 10 else ""
        panels.append(title + f'<div class="lc-cgw"><div class="lc-cg lc-dx{dense}" style="--k:{len(slots)}">{head}{"".join(out)}</div></div>')
    headline = openings_headline(cells)
    key = ('<div class="lc-key"><span class="sw"><b style="background:rgba(32,178,170,.88)"></b>3 or more stations</span>'
           '<span class="sw"><b style="background:rgba(32,178,170,.40)"></b>1 or 2</span>'
           + ('' if observed else '<span class="sw"><b style="background:repeating-linear-gradient(135deg,transparent 0 5px,rgba(128,128,128,.4) 5px 6px)"></b>decoded WSPR, none strong enough</span>')
           + '<span class="sw"><b style="border-style:dashed;background:repeating-linear-gradient(45deg,transparent 0 3px,rgba(128,128,128,.25) 3px 4px)"></b>too little WSPR to say</span>'
             '<span class="sw"><b></b>no reports from there</span>'
             '<span class="sw"><span style="display:inline-block;width:8px;height:8px;background:var(--a);transform:rotate(45deg)"></span> you were active</span>'
             f'<span class="sw"><span style="color:var(--a);font-weight:700">&#9733;</span> a contact with {escape(where["with"])}</span>'
             f'<span class="sw"><span style="display:inline-block;width:3px;height:3px;border-radius:50%;background:Canvas;border:2px solid #3b82f6"></span> an RBN skimmer {escape(where["skimmers"])} spotted you</span></div>')
    return ('<div class="lc"><div class="lc-card"><h4>How you used the openings</h4>'
            + (f'<p style="margin:0 0 6px;font-size:15px"><b>{escape(headline)}</b></p>' if headline else "")
            + "".join(panels) + key + '</div></div>')


CONTINENT_COLOURS = {"EU": "#2a78d6", "AF": "#eb6834", "AS": "#1baf7a", "OC": "#6250d6", "SA": "#e87ba4"}


def _hour_ticks(first, last, step_min):
    """Where to put time labels under a card: on the hour (or every 2 or 4 hours for a long stretch), as minutes from `first`."""
    total = (last - first).total_seconds() / 60
    every = 60 if total <= 480 else 120 if total <= 960 else 240
    t = first.ceil(f"{every}min")
    out = []
    while t <= last:
        out.append(t)
        t += pd.Timedelta(minutes=every)
    return out


def band_cards_html(tl, tz_name=None):
    """The band-by-band timeline (log_openings.band_timeline): one card for each band you worked, highest band first, on a time axis in UTC. In a card:
    a row for each distant continent with a bar for each time bin in which receivers there decoded WSPR near you (solid for two or more receiving
    stations, pale for one: one receiving station is limited evidence, not a weak signal), a small ring where an RBN skimmer there spotted you (only
    where RBN applies), your contacts as ticks and, for a distant continent, a dot, shading for your logged activity (first to last contact, split at
    pauses), a mark for any bin with too little WSPR to say anything, and one finding in words. There is no callsign on the chart, so nothing overlaps:
    each dot carries its call, time and continent in its tooltip, and the calls are listed under the card."""
    from log_openings import ACTIVITY_GAP_MIN, LANE_COLOURS, LANES
    names, observed = tl.get("lane_names") or lf.CONTINENT_NAMES, tl["metric"] == "heard"
    order, colours, word = tl.get("lane_order") or list(LANES), tl.get("lane_colours") or LANE_COLOURS, tl.get("lane_word", "continent")
    power_w, mode = tl.get("power_w") or 0, tl.get("mode", "CW")
    legend_swatches = "".join(f'<span style="--c:{colours[c]};margin-right:12px"><span class="bc-lab" style="display:inline"><i></i>{names[c]}</span></span>' for c in order)
    meaning = (f"Bars: receiving stations in that {word} that decoded WSPR transmitters near you. Nothing is assumed about your station." if observed else
               f"Bars: receiving stations in that {word} that decoded WSPR transmitters near you and, restated to {power_w:g} W in {escape(mode)}, looked strong enough to hear you.")
    legend = (f'<p class="sub" style="margin:0 0 4px">{legend_swatches}</p>'
              f'<p class="sub">{meaning} <b>Solid bar:</b> two or more receiving stations. <b>Pale bar:</b> one receiving station, which is limited evidence, not a weak signal. '
              f'<b>Dot:</b> a contact in that {word}. <b>Small tick:</b> any other contact. <b>Ring:</b> an RBN skimmer there spotted you. '
              f'<b>Shading:</b> logged activity on the band, from the first to the last contact, split where there was a pause of more than {ACTIVITY_GAP_MIN} minutes; '
              'it is when contacts were logged, not when you were listening or calling.</p>'
              + (f'<p class="sub">{escape(tl["rbn_line"])}</p>' if tl.get("rbn_line") and not tl["rbn_line"].startswith("RBN skimmers") else ""))
    out = []
    many = len(tl["panels"]) > 1
    for panel in tl["panels"]:
        slots, step = panel["slots"], pd.Timedelta(minutes=panel["bin_min"])
        n, start, end = len(slots), slots[0], slots[-1] + step
        total = (end - start).total_seconds() / 60
        pct = lambda t: (pd.Timestamp(t) - start).total_seconds() / 60 / total * 100
        if many:
            out.append(f'<p class="sub" style="margin:14px 0 0"><b>{start:%a %d %b}</b> (UTC)</p>')
        for card in panel["cards"]:
            acts = "".join(f'<i style="left:{pct(a) - 0.6:.2f}%;width:{max(pct(b) - pct(a), 0) + 1.2:.2f}%" title="Logged activity on {card["band"]}: {a:%H:%M} to {b:%H:%M} UTC, {k} contact{"s" if k != 1 else ""}"></i>'
                           for a, b, k in card["spans"])
            ticks, dots = "", ""
            for c in card["contacts"]:
                x = pct(c["time"])
                if c["cont"] and word != "direction":        # in the directions picture each contact is drawn in its own lane, so the top row has ticks only
                    dots += f'<i class="bc-dot" style="--c:{colours[c["cont"]]};left:{x:.2f}%" title="{escape(c["call"])}, {pd.Timestamp(c["time"]):%H:%M} UTC, {names[c["cont"]]}"></i>'
                else:
                    ticks += f'<i class="bc-tick" style="left:{x:.2f}%"></i>'
            rows = f'<div class="bc-row"><div class="bc-lab">Your contacts</div><div class="bc-trk" style="--n:{n}">{ticks}{dots}</div></div>'
            for c, cells_ in card["lanes"].items():
                bars = rings = ""
                for i, x in enumerate(cells_):
                    left, width = i / n * 100 + 0.35, 100 / n - 0.7
                    if x["n"] >= 1:
                        what = (f"{x['n']} receiving station{'s' if x['n'] != 1 else ''} in {names[c]} decoded WSPR near you" if observed else
                                f"{x['n']} receiving station{'s' if x['n'] != 1 else ''} in {names[c]} looked strong enough to hear {power_w:g} W ({x['heard']} decoded WSPR near you)")
                        bars += f'<i class="bc-bar{"" if x["n"] >= 2 else " p"}" style="left:{left:.2f}%;width:{width:.2f}%" title="{x["slot"]:%H:%M}\u2013{x["slot"] + step:%H:%M} UTC: {what}"></i>'
                    if x["rbn"]:
                        rings += (f'<i class="bc-ring" style="left:{(i + 0.5) / n * 100:.2f}%" title="RBN: {escape(", ".join(x["rbn"][:6]))} in {names[c]} spotted you, '
                                  f'{x["slot"]:%H:%M}\u2013{x["slot"] + step:%H:%M} UTC"></i>')
                if word == "direction":
                    for k in card["contacts"]:
                        if k["cont"] == c:
                            rings += (f'<i class="bc-dot" style="--c:{colours[c]};left:{pct(k["time"]):.2f}%" title="{escape(k["call"])}, {pd.Timestamp(k["time"]):%H:%M} UTC, '
                                      f'{names[c]}"></i>')
                empty = "" if bars or rings else '<span class="bc-none">no reports from there</span>'
                rows += f'<div class="bc-row" style="--c:{colours[c]}"><div class="bc-lab"><i></i>{names[c]}</div><div class="bc-trk" style="--n:{n}">{bars}{rings}{empty}</div></div>'
            # a card with no distant-continent lane has no note inside the chart: the sentence under it already says so, in the same words
            if card["thin"]:
                thin = "".join(f'<i class="bc-thin" style="left:{pct(s) + 0.35:.2f}%;width:{100 / n - 0.7:.2f}%" title="{s:%H:%M}\u2013{s + step:%H:%M} UTC: too little WSPR near you to say anything"></i>' for s in card["thin"])
                rows += f'<div class="bc-row"><div class="bc-lab">Too little WSPR</div><div class="bc-trk" style="--n:{n}">{thin}</div></div>'
            ax = "".join(f'<span style="left:{pct(t):.2f}%">{t:%H:%M}</span>' for t in _hour_ticks(start, end, panel["bin_min"]))
            rows += f'<div class="bc-row"><div class="bc-lab">UTC</div><div class="bc-ax">{ax}</div></div>'
            shown_calls = card["worked"][:8]
            more = f" and {len(card['worked']) - len(shown_calls)} more" if len(card["worked"]) > len(shown_calls) else ""
            calls = ("<p class=\"sub\">Contacts there: " + ", ".join(f"{escape(call)} ({names[cont]})" for call, cont in shown_calls) + more + ".</p>") if card["worked"] else ""
            out.append(f'<div class="bc"><h5>{card["band"]}<small>{(str(len(card["contacts"])) + " contact" + ("s" if len(card["contacts"]) != 1 else "")) if card.get("worked_band", True) else "not worked"}</small></h5>'
                       f'<div class="bc-body"><div class="bc-act">{acts}</div>{rows}</div><p>{escape(card["finding"])}</p>{calls}</div>')
    notes = []
    kinds = {"path": [], "none": [], "thin": []}
    for band, kind in tl["idle"]:
        kinds[kind].append(band)
    from log_openings import _join
    if kinds["path"]:
        notes.append(f"{_join(kinds['path'])}: you logged no contact; nearby WSPR showed a path to a distant continent.")
    if kinds["none"]:
        notes.append(f"{_join(kinds['none'])}: you logged no contact; nearby WSPR showed no path to a distant continent.")
    if kinds["thin"]:
        notes.append(f"{_join(kinds['thin'])}: too little WSPR near you to say anything.")
    foot = ('<p class="sub">' + " ".join(escape(x) for x in notes) + "</p>") if notes else ""
    note = (f'<p class="sub">Time bins are {tl["bin_min"]} minutes, each judged on the hour of WSPR up to its end, so a bar shows roughly when a path was there, '
            'not the exact moment it opened or closed.</p>')
    head = f'<p style="margin:0 0 8px;font-size:15px"><b>{escape(tl["headline"])}</b></p>' if tl.get("headline") else ""
    return '<div class="lc"><div class="lc-card"><h4>How you used the openings, band by band</h4>' + head + legend + "".join(out) + foot + note + '</div></div>'


def band_cards_explain_html(tl, grid=None):
    """The folded explanation for the band timeline: what it counts, what it does not claim, and the evidence line behind it."""
    from log_openings import where_forms
    min_km = tl.get("min_km") or 0
    far = f"at least {min_km * 0.621371:,.0f} miles ({min_km:,.0f} km) from you" if min_km else "at any distance"
    observed = tl["metric"] == "heard"
    what = ("decoded WSPR transmitters near you" if observed else f"decoded WSPR transmitters near you and looked strong enough to hear {tl.get('power_w') or 0:g} W "
            "(their reports restated to your power, with 3 dB to spare)")
    intro = (f'<p class="sub">Each card is a band you logged contacts on. A bar counts the WSPR receiving stations in one continent, {far}, that {what}, in the hour up to the end of '
             'each time bin. It counts different stations, not reports. It is evidence about paths near you, not a score for your operating, and it does not say what you should have done.</p>')
    limits = ('<p class="sub">The shading and the dots come from your log alone: it holds the contacts you made, not the time you spent listening, calling without an answer or resting. '
              'WSPR only covers stations near you as transmitters, so a bin with few of them is marked as having too little WSPR, not drawn as empty. '
              'RBN carries CW and RTTY only and spots you only while you call CQ, so a ring is proof you were heard there, and no ring says little. '
              'Click through to the evidence under the cards for the stations, distances, times, spots and contacts behind any bar.</p>')
    return '<div class="lc">' + intro + limits + (_evidence_line(grid) if grid is not None else "") + '</div>'


def openings_explain_html(cells, grid=None, view="estimate"):
    """How to read the openings grid, and what it rests on: what the shading and the marks are, the distance and destination in words, the evidence line
    (the WSPR reports, transmitters and stations behind it) and the limits. It is the folded piece under the grid."""
    from log_openings import where_forms
    where, observed = cells.attrs.get("where") or where_forms("sector", None), view == "observed"
    power_w = cells.attrs.get("power_w") or 0
    min_km = cells.attrs.get("min_km") or 0
    far = f"at least {min_km * 0.621371:,.0f} miles ({min_km:,.0f} km) from you" if min_km else "at any distance"
    scope = f"in {where['to']} and {far}" if cells.attrs.get("dest") else far
    what = ("decoded WSPR transmitters near you" if observed else f"decoded WSPR transmitters near you and looked strong enough to hear {power_w:g} W "
            "(their reports restated to your power, with 3 dB to spare)")
    intro = (f'<p class="sub">Each box is a band in one time bin (UTC). The shading counts the WSPR stations {escape(scope)} that {what}, in the hour up to the end '
             'of the box. It counts different stations, not reports. It is evidence about the path, not a score for your operating, and it does not say what you should have done.</p>')
    reading = ('<p class="sub"><b>How to read it:</b> the shading is the path, the marks are you. A diamond means you were active on the band in that box, a star that you '
               f'logged a contact with {escape(where["with"])}, and a ring that an RBN skimmer {escape(where["skimmers"])} spotted you. Read across a row to follow a band over time. '
               'Hover over a box for its statement.</p>')
    caveat = ('<p class="sub">WSPR only covers stations near you as transmitters, and a box with few of them says nothing, which is why it is dashed and not blank. '
              'RBN carries CW and RTTY only and spots you only while you call CQ, so a ring is proof you were heard there, and no ring says little: RBN has far fewer skimmers than WSPR has receivers.</p>')
    return '<div class="lc">' + intro + reading + (_evidence_line(grid) if grid is not None else "") + caveat + '</div>'


def dx_regions_html(grid, view="estimate"):
    """Where DX reached, by band: for each band and region, the most WSPR stations over DX_MILES away in one half hour (those that decoded WSPR near you
    in the 'observed' view, those that looked strong enough for you in the 'estimate' view) and the windows in which there were any. Half hours that do
    not follow each other are separate windows. Empty when there was nothing to show."""
    observed = view == "observed"
    col = "dx_regions_heard" if observed and "dx_regions_heard" in grid.columns else "dx_regions"
    seen = {k for d in grid[col] for k in d}
    if not seen:
        return ""
    regions = [r for r in DX_FIRST if r in seen] + sorted(seen - set(DX_FIRST))
    many = grid["panel"].nunique() > 1
    stamp = (lambda t: f"{t:%d %b %H:%M}") if many else (lambda t: f"{t:%H:%M}")
    rows = []
    for band in list(grid.drop_duplicates("band")["band"]):
        d = grid[grid["band"] == band].sort_values("slot")
        tds = []
        for reg in regions:
            hits = [(s, r[reg]) for s, r in zip(d["slot"], d[col]) if r.get(reg, 0) > 0]
            if hits:
                best = max(n for _, n in hits)
                tds.append(f'<td><span class="dot" style="opacity:{0.35 + 0.65 * min(best / 3, 1):.2f}"></span>{best} <small>{_runs_text([s for s, _ in hits], stamp)}</small></td>')
            else:
                tds.append('<td><span class="no">&ndash;</span></td>')
        n, x = int(d["contacts"].sum()), int(d["dx_contacts"].sum())
        mine = f"{n}" if n else '<span class="no">not worked</span>'
        rows.append(f"<tr><td><b>{escape(band)}</b></td>{''.join(tds)}<td>{mine}" + (f" <small>({x} outside North America)</small>" if x else "") + "</td></tr>")
    what = "decoded WSPR transmitters near you" if observed else "looked strong enough to hear you"
    return ('<div class="lc"><div class="lc-card"><h4>Where DX reached, by band</h4>'
            f'<p class="sub">The most WSPR stations over {DX_MILES:,} miles away that {what} in one half hour, by region, with the windows in which there were any (UTC). '
            'Half hours that do not follow each other are listed as separate windows.</p><div class="lc-cgw"><table class="lc-reg"><tr><th>Band</th>'
            + "".join(f"<th>{escape(r)}</th>" for r in regions) + "<th>Your contacts</th></tr>" + "".join(rows) + "</table></div></div></div>")


def conditions_html(grid, notes, power_w, mode="CW", tz_name=None):
    """The picture of how open each band looked while you were on the air: a box for each band and half hour, shaded by the share of nearby
    WSPR receivers that would have heard you, with your contacts on top, and the lines that say it in words. `tz_name` (the visitor's time
    zone) adds the local time under each UTC time."""
    from zoneinfo import ZoneInfo
    all_bands = list(grid.drop_duplicates("band")["band"])
    panels = []
    for panel, d in grid.groupby("panel"):
        slots = sorted(d["slot"].unique())
        by = {(r.band, r.slot): r for r in d.itertuples()}
        bands = [b for b in all_bands if d.loc[d["band"] == b, "contacts"].sum() > 0 or d.loc[d["band"] == b, "share"].notna().any()]   # no empty rows

        def local(s):
            try:
                return f"{pd.Timestamp(s).tz_localize('UTC').astimezone(ZoneInfo(tz_name)):%H:%M}" if tz_name else ""
            except Exception:
                return ""
        head = "<div></div>" + "".join(f'<div class="th"><b>{pd.Timestamp(s):%H:%M}</b>' + (f"<span>{local(s)} local</span>" if local(s) else "") + "</div>"
                                       for s in slots)
        cells = []
        for b in bands:
            cells.append(f'<div class="bl">{escape(b)}</div>')
            for s in slots:
                r = by[(b, s)]
                pill = f'<em><i></i>{r.contacts}</em>' if r.contacts else ""
                if np.isnan(r.share):
                    cells.append(f'<div class="cell few" title="{escape(b)} {pd.Timestamp(s):%H:%M}Z: only {r.receivers} WSPR stations, too few to say; '
                                 f'{r.contacts} contacts"><span class="p">&ndash;</span>{pill}</div>')
                else:
                    cells.append(f'<div class="cell" style="background:{_teal(r.share)}" title="{escape(b)} {pd.Timestamp(s):%H:%M}Z: {r.good} of {r.receivers} '
                                 f'WSPR stations would hear you; {r.contacts} contacts"><span class="p">{pct(r.share)}</span>{pill}</div>')
        title = f'<p class="sub" style="margin:14px 0 0"><b>{pd.Timestamp(slots[0]):%a %d %b}</b> (UTC)</p>' if grid["panel"].nunique() > 1 else ""
        dense = " dense" if len(slots) > 10 else ""
        panels.append(title + f'<div class="lc-cgw"><div class="lc-cg{dense}" style="--k:{len(slots)}">{head}{"".join(cells)}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(lead)}</b> {escape(rest)}</li>" for lead, rest in notes) + "</ul>") if notes else ""
    return ('<div class="lc"><div class="lc-card"><h4>How open each band looked: percent of stations that could hear you</h4>'
            f'<p class="sub">An estimate for your station at {power_w:g} W using {escape(mode)}. Each box is the percentage of the stations that decoded WSPR near you on '
            'that band that would also have decoded a signal like yours, in the hour up to the end of each half hour. Your contacts are the amber diamonds.</p>'
            + '<p class="sub"><b>How to read it:</b> read across each row to follow that band over time. Different bands have different numbers of '
              'stations behind them, so the percentages of different bands are not comparable with each other.</p>'
            + "".join(panels)
            + '<div class="lc-ramp"><span>fewer<b></b>more stations would hear you</span><span>hatched: too few WSPR stations to say</span>'
              '<span><span style="display:inline-block;width:8px;height:8px;background:var(--a);transform:rotate(45deg)"></span> contacts in that half hour</span></div>'
            + says
            + '<p class="sub" style="margin-top:10px">An estimate from WSPR transmitters within ' + _near(grid) + ' of you, restated to your power. Use it to compare a band with itself over time '
              'and one hour with another. It is not an exact chance of a contact (the percentages run high), and bands cannot be fairly compared with each other: '
              'a band with many distant stations, such as 20m, tends to show a lower share.</p>'
            '</div></div>')


def balance_html(bal):
    """Who hears whom, by band: the average S they gave you and you gave them, the difference in dB, and a plain reading. Empty when no
    contact carries a report both ways."""
    if bal.empty:
        return ""
    rows = []
    for r in bal.itertuples():
        diff = f"{r.diff_db:+.0f} dB" if r.n >= BALANCE_MIN and r.habit < HABIT_SHARE else "&ndash;"
        label = f"<b>{escape(r.band)}</b>"
        rows.append(f"<tr><td>{label}</td><td>{r.n}</td><td>S{r.got:.1f}</td><td>S{r.gave:.1f}</td><td>{diff}</td><td>{escape(r.reading)}</td></tr>")
    return ('<div class="lc"><div class="lc-card"><h4>Do they hear you as well as you hear them?</h4>'
            '<p class="sub">From the reports in your log. A report is the S in RST (579 is S7); one S-unit is about 6 dB. A positive difference means the stations '
            'you worked gave you stronger reports than you gave them. Many operators send a 9 out of habit, and a difference can come from their antenna, their noise or their '
            'habits as easily as from your station, so this is a rough picture, not a measurement. A band needs at least '
            f'{BALANCE_MIN} contacts with a report both ways before it says anything.</p>'
            '<div class="lc-cgw"><table class="lc-reg"><tr><th>Band</th><th>Contacts with reports both ways</th><th>They gave you</th><th>You gave them</th>'
            '<th>Difference</th><th>Reading</th></tr>' + "".join(rows) + "</table></div></div></div>")


KP_COLOURS = ("rgb(76,175,80)", "rgb(230,161,23)", "rgb(210,80,80)")


def flare_title(cls, peak, detail, log):
    """The hover text of a flare: its class and what that means for HF, when it began, peaked and ended, the active region it came from, and how many of your
    contacts the log shows between its beginning and its end (a count, nothing more: it says nothing about cause)."""
    from space_weather import flare_level
    parts = [f"{cls} flare" + (f": {flare_level(cls)}." if flare_level(cls) else ".")]
    begin, end = (detail or {}).get("begin"), (detail or {}).get("end")
    when = f"Peak {peak:%H:%M}Z"
    if begin is not None:
        when = f"Began {begin:%H:%M}Z. " + when
    if end is not None:
        when += f". Ended {end:%H:%M}Z" + (f" ({int(round((end - begin).total_seconds() / 60))} min in all)" if begin is not None else "")
    parts.append(when + ".")
    if (detail or {}).get("region"):
        parts.append(f"Active region {detail['region']}.")
    if begin is not None and end is not None and len(log):
        n = int(((log["time"] >= begin) & (log["time"] <= end)).sum())
        parts.append(f"Your log has {n} contact{'s' if n != 1 else ''} between its beginning and its end.")
    return " ".join(parts)


def space_weather_html(wx, log, notes):
    """The space weather over the session: Kp in 3 hour steps, the flares at their peak, and your contacts in the same hours, with the lines
    that say it in words. Empty when nothing could be read."""
    from log_check import space_span
    if not (wx.get("kp") or wx.get("flux") or wx.get("flares")):
        return ""
    start, end = space_span(log)
    minutes = (end - start).total_seconds() / 60
    left = lambda t: max(0.0, min(100.0, (t - start).total_seconds() / 60 / minutes * 100))
    ticks_t = list(_ticks(start, end))
    ticks = "".join(f'<i class="lc-tick" style="left:{left(t):.3f}%"></i>' for t in ticks_t)
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t:%H:%M}Z</span>' for t in ticks_t)
    kp = ""
    for t, v in wx.get("kp") or []:
        a, b = max(t, start), min(t + pd.Timedelta(hours=3), end)
        colour = KP_COLOURS[0 if v < 3 else 1 if v < 5 else 2]
        kp += (f'<i class="lc-kp" style="left:{left(a):.3f}%;width:calc({left(b) - left(a):.3f}% - 2px);height:{max(3.0, v / 9 * 44):.1f}px;background:{colour}" '
               f'title="Kp {v:.1f}, the three hours from {t:%H:%M}Z"></i>')
    flares = ""
    details = wx.get("flare_details") or {}
    for t, c in wx.get("flares") or []:
        size = {"X": 18, "M": 15}.get(c[:1], 11)
        colour = {"X": "rgb(210,80,80)", "M": "rgb(230,161,23)"}.get(c[:1], "rgb(140,140,140)")
        flares += (f'<i class="lc-fl" tabindex="0" style="left:{left(t):.3f}%;width:{size}px;height:{size}px;margin:{-size / 2:.1f}px 0 0 {-size / 2:.1f}px;background:{colour}" '
                   f'title="{escape(flare_title(c, t, details.get(t), log))}"></i>')
        if c[:1] in ("M", "X"):                    # the bigger flares carry their class beside the dot, so they can be read without hovering
            flares += f'<span class="lc-fn" style="left:{left(t):.3f}%">{escape(c)}</span>'
    if not flares:
        note = "No flares were listed for these hours." if wx.get("flares") is not None else "NOAA no longer lists flares for these hours."
        flares = f'<span class="lc-fnone">{note}</span>' + ""
    slot = log.assign(slot=log["time"].dt.floor("30min")).groupby("slot").size()
    top = max(int(slot.max()), 1) if len(slot) else 1
    bars = "".join(f'<i class="lc-kq" style="left:{left(t):.3f}%;width:calc({30 / minutes * 100:.3f}% - 1px);height:{max(2.0, n / top * 30):.1f}px" '
                   f'title="{n} contacts, {t:%H:%M}Z"></i>' for t, n in slot.items())
    lane = lambda label, body, h: (f'<div class="lc-lane"><div class="lc-lab" style="padding-top:{h // 2 - 8}px"><b>{label}</b></div>'
                                   f'<div class="lc-plot" style="height:{h}px">{ticks}{body}</div></div>')
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(a)}</b> {escape(b)}</li>" for a, b in notes) + "</ul>") if notes else ""
    storm = f'<i class="lc-storm" style="top:{50 - 5 / 9 * 44:.1f}px" title="Kp 5: a geomagnetic storm"></i>'
    return ('<div class="lc"><div class="lc-card"><h4>Space weather during your session</h4>'
            '<p class="sub">Kp is the worldwide measure of magnetic disturbance (0 is calm, 5 and above is a storm), shown in three-hour steps; the dots are solar flares at '
            'their peak (grey C, amber M, red X). Your contacts are along the bottom. These are worldwide figures: they say whether something unusual was going on, '
            'not what worked near you. Times are UTC.</p>'
            '<div class="lc-chart">' + lane("Kp", kp + storm, 56) + lane("Flares", flares, 40) + lane("Contacts", bars, 40)
            + f'<div class="lc-axis">{axis}</div></div>' + says + '</div></div>')


def _pota_date(text):
    try:
        return f"{pd.Timestamp(text):%d %b %Y}"
    except Exception:
        return ""


def park_facts_html(card):
    """About the park, from POTA's record of it: what it is and where, who first activated and first hunted it, how many stations have hunted
    it, the totals, and a link to its own website. Empty when POTA has no record of the park."""
    p, totals = card["park"], card.get("stats") or {}
    if not p:
        return ""
    where = ", ".join(x for x in (card["kind"], card["where"], f"grid {p['grid6']}" if p.get("grid6") else "") if x)
    facts = [escape(where)] if where else []
    if p.get("firstActivator"):
        facts.append(f"First activated by <b>{escape(str(p['firstActivator']))}</b>, {_pota_date(p.get('firstActivationDate'))}")
    if p.get("firstHunter"):
        facts.append(f"First hunted by <b>{escape(str(p['firstHunter']))}</b>, {_pota_date(p.get('firstHuntDate'))}")
    if p.get("uniqueHunters"):
        facts.append(f"{int(p['uniqueHunters']):,} different stations have hunted it")
    if totals.get("contacts"):
        facts.append(f"{int(totals['contacts']):,} contacts logged there in all; {int(totals['activations'])} of {int(totals['attempts'])} activations "
                     "reached the 10 QSOs POTA needs")
    site = str(p.get("website") or "")
    if site.startswith(("http://", "https://")):
        facts.append(f'<a href="{escape(site, quote=True)}" target="_blank" rel="noopener noreferrer">the park\'s own website</a>')
    return ('<div class="lc"><div class="lc-card"><h4>About the park</h4><ul class="lc-says">' + "".join(f"<li>{f}</li>" for f in facts) + "</ul></div></div>") if facts else ""


def summit_facts_html(card):
    """About the summit, from SOTA's record of it: where it is, how high, its points, who first activated it (from the list), and a link to its
    page on the SOTA website. Empty when SOTA has no record of the summit."""
    p = card["park"]
    if not p:
        return ""
    facts = []
    if card["where"]:
        facts.append(escape(card["where"]))
    if p.get("altM"):
        facts.append(f"{int(p['altM']):,} m ({int(p.get('altFt') or 0):,} ft) high" + (f" \u00b7 grid {escape(str(p['locator']))}" if p.get("locator") else ""))
    if p.get("points") is not None:
        facts.append(f"{int(p['points'])} points" + (f" plus {int(p['bonusPoints'])} bonus" if p.get("bonusPoints") else ""))
    if card["first"]:
        facts.append(f"First activation listed: <b>{escape(card['first'][0])}</b>, {card['first'][1]:%d %b %Y}")
    facts.append(f'<a href="https://www.sota.org.uk/Summit/{escape(card["ref"], quote=True)}" target="_blank" rel="noopener noreferrer">this summit on the SOTA website</a>')
    return '<div class="lc"><div class="lc-card"><h4>About the summit</h4><ul class="lc-says">' + "".join(f"<li>{f}</li>" for f in facts) + "</ul></div></div>"


def highlights_html(first, far, lines, dated=False):
    """The session's highlights: a few plain sentences, then when each other continent first answered and the farthest contact on each band (log_highlights has the
    tables). With `dated` (a log over more than one UTC day) the times carry their day. Empty when there is nothing to show."""
    if not (len(first) or len(far)):
        return ""
    from log_highlights import _hm
    clock = "%d %b %H:%M" if dated else "%H:%M"
    says = ('<ul class="lc-says">' + "".join(f"<li>{escape(x)}</li>" for x in lines) + "</ul>") if lines else ""
    if len(first):
        rows = "".join(f"<tr><td><b>{escape(r.name)}</b></td><td>{escape(r.call)}</td><td>{r.band}</td><td>{r.time:{clock}}</td><td class=\"n\">{escape(_hm(r.since)) if r.since >= 1 else 'first'}</td></tr>"
                       for r in first.itertuples())
        a = f'<div><h5>When each other continent first answered</h5><table><tr><th>Continent</th><th>Station</th><th>Band</th><th>UTC</th><th>Into the session</th></tr>{rows}</table></div>'
    else:
        a = '<div><h5>When each other continent first answered</h5><p class="none">No contact outside your own continent.</p></div>'
    def far_row(r):
        who = ", ".join(r.calls[:3]) + (f" and {len(r.calls) - 3} more" if len(r.calls) > 3 else "") if r.approx else r.call
        rough = (f'<br><small title="Placed only by country, so the distance is rough and it does not take the place of the contact above">farther, by country only: '
                 f'{escape(r.rough_place)} ~{r.rough_km:,.0f} km</small>' if r.rough_km == r.rough_km and not r.approx else "")
        if r.approx and r.precise_call:
            rough = (f'<br><small title="The farthest contact placed by a grid, a park or a summit">farthest placed precisely: {escape(r.precise_call)} '
                     f'{r.precise_km:,.0f} km</small>')
        return (f"<tr><td><b>{r.band}</b></td><td>{escape(who)}</td><td>{escape(r.place)}</td>"
                f"<td class=\"n\">{'~' if r.approx else ''}{r.km:,.0f} km{rough}</td></tr>")
    rows = "".join(far_row(r) for r in far.itertuples())
    b = f'<div><h5>The farthest contact on each band</h5><table><tr><th>Band</th><th>Station</th><th>Where</th><th>Distance</th></tr>{rows}</table></div>' if len(far) else ""
    return (f'<div class="lc"><div class="lc-card" id="sec-highlights"><h4>Session highlights</h4>{says}<div class="lc-hl">{a}{b}</div></div></div>')


def band_chip(band, colour):
    """A band's name as a chip in the band's own colour with black or white lettering, whichever reads better on it. A band's colour is the one the RBN website uses, and some
    of those (15m is dark grey, 20m dark purple) cannot be read as lettering on a dark page, nor the pale ones on a light page; on a chip they can be, on both."""
    h = str(colour).lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) if len(h) == 6 else (0.5, 0.5, 0.5)
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    luminance = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    ink = "#000" if luminance > 0.18 else "#fff"
    return f'<span class="dv-chip" style="background:{colour};color:{ink}">{escape(band)}</span>'


def band_key_html(bands):
    """The key to a chart whose bars are coloured by band: "Band" and a chip for each of (band, colour). Drawn once by the page, above the charts, so no chart has to carry
    a key of its own and every chart has the same height."""
    return '<div class="dv-bandkey"><b>Band</b>' + "".join(band_chip(b, c) for b, c in bands) + "</div>"


CONTACT_CLUSTER_PCT = 2.0      # contacts closer together than this share of a lane (about 12 minutes of a 4 hour stretch) are drawn as one marker with a count, as their dots would overlap


def contact_clusters(contacts, pct):
    """The contacts of one lane gathered into markers: a list of (position in percent, [contacts]). A marker starts at a contact and takes the ones that follow it within
    CONTACT_CLUSTER_PCT, so two markers are never closer than that and none sits on another."""
    out = []
    for k in sorted(contacts, key=lambda c: pd.Timestamp(c["time"])):
        at = pct(k["time"])
        if out and at - out[-1][0] < CONTACT_CLUSTER_PCT:
            out[-1][1].append(k)
        else:
            out.append((at, [k]))
    return out


def source_key_html(name):
    """The three sources the destination chart draws, each with its mark and the one thing it can establish, so the difference is on the page beside the chart: your log shows
    what you did, RBN shows who decoded you, and the nearby WSPR shows who decoded other transmitters near you."""
    n = escape(name)
    return ('<div class="dv-key">'
            f'<div class="dv-ki"><span class="mk"><i class="dv-ld"></i></span><div><b>Your log</b><span>you completed a contact with {n}</span></div></div>'
            f'<div class="dv-ki"><span class="mk"><i class="dv-lt"></i></span><div><b>RBN</b><span>a skimmer in {n} decoded your signal</span></div></div>'
            f'<div class="dv-ki"><span class="mk"><i class="dv-sw"></i></span><div><b>Nearby WSPR</b><span>a receiver in {n} decoded another transmitter near you (pale: one receiver)</span></div></div>'
            '</div>')


NOTES_SHOWN = 2        # the notes about your contacts that a day's chart shows as sentences; the rest are folded under it


def panel_notes_html(panel, colours, keep=NOTES_SHOWN):
    """The notes under one day's chart: the lines about bands on which you made contact with the destination are written out (the first `keep`), and every other line, a path or a
    skimmer on a band with no contact, is folded into one closed line saying how many and on which bands, so the chart leads and the text is only what you did. `panel` is one of
    log_openings.destination_views' panels."""
    has_contact = {lane["band"] for lane in panel["lanes"] if lane["contacts"]}
    shown, folded = [], []
    for band, text in panel["lines"]:
        (shown if band in has_contact and len(shown) < keep else folded).append((band, text))
    line = lambda b, t: f'<div class="dv-look"><b>{band_chip(b, colours.get(b, "#888"))}</b><div>{escape(t)}</div></div>'
    html = "".join(line(b, t) for b, t in shown)
    if folded:
        bands = ", ".join(dict.fromkeys(b for b, _ in folded))
        n = len(folded)
        paths = all("paths appeared" in t or "path" in t.split(";")[0] for _, t in folded) and all(b not in has_contact for b, _ in folded)
        label = f"{n} path{'s' if n != 1 else ''} with no contact on that band ({bands})" if paths else f"{n} more note{'s' if n != 1 else ''} ({bands})"
        html += f'<details class="dv-more"><summary>{escape(label)}</summary>{"".join(line(b, t) for b, t in folded)}</details>'
    return html


def destination_html(view, tl, colours=None, empty=(), limit_note="", selected=None):
    """One destination as a picture of the reported paths and your contacts: the plain idea in a sentence, the few lines worth a look and, for each stretch of the log, a
    strip of your logged activity above a lane for each band that has something to show: a bar where the nearby WSPR showed a path to the destination (pale for one
    receiving station), a filled circle for a contact with it, a hollow triangle where an RBN skimmer there spotted you. `view` is one of log_openings.destination_views,
    `tl` the timeline it came from; `selected` is the (band, time) the details below the chart describe, drawn as a dashed outline. Under it, what has nothing to
    show and why."""
    from log_openings import _join
    if colours is None:
        from ui_common import BAND_COLORS as colours
    name, many = view["name"], len(view["panels"]) > 1
    power_w, mode, observed = tl.get("power_w") or 0, tl.get("mode", "CW"), tl["metric"] == "heard"
    out = []
    for panel in view["panels"]:
        slots, step = panel["slots"], pd.Timedelta(minutes=panel["bin_min"])
        start, end = slots[0], slots[-1] + step
        span = (end - start).total_seconds()
        pct = lambda t: (pd.Timestamp(t) - start).total_seconds() / span * 100
        ticks, axis = "", ""
        for t in _hour_ticks(start, end, panel["bin_min"]):
            ticks += f'<i class="dv-tk" style="left:{pct(t):.2f}%"></i>'
            axis += f'<span style="left:{pct(t):.2f}%">{t:%H:%M}</span>'
        strip = ""
        for a, b, band in panel["strip"]:
            w = pct(b) - pct(a)
            if band:
                strip += f'<div class="dv-seg" style="left:{pct(a):.2f}%;width:{w:.2f}%;background:{colours.get(band, "#888")}" title="Logged contacts on {band}, {a:%H:%M}\u2013{b:%H:%M} UTC">{band if w > 4 else ""}</div>'
            else:
                strip += f'<div class="dv-seg none" style="left:{pct(a):.2f}%;width:{w:.2f}%" title="No contact logged, {a:%H:%M}\u2013{b:%H:%M} UTC">{"no contacts logged" if w > 14 else ""}</div>'
        lanes = ""
        for lane in panel["lanes"]:
            colour, band = colours.get(lane["band"], "#888"), lane["band"]
            marks = ""
            for x in lane["cells"]:
                left, width = pct(x["slot"]), 100 / len(slots)
                if x["n"] >= 1:
                    what = (f"{x['n']} receiving station{'s' if x['n'] != 1 else ''} in {name} decoded WSPR near you" if observed else
                            f"{x['n']} receiving station{'s' if x['n'] != 1 else ''} in {name} looked strong enough to hear {power_w:g} W")
                    marks += (f'<i class="dv-bar{"" if x["n"] >= 2 else " pale"}" style="left:{left:.2f}%;width:calc({width:.2f}% - 2px);background:{colour}" '
                              f'title="{band}, {x["slot"]:%H:%M}\u2013{x["slot"] + step:%H:%M} UTC: {what}"></i>')
                if x["rbn"]:
                    marks += f'<i class="dv-tri" style="left:{left + width / 2:.2f}%" title="{band}, {x["slot"]:%H:%M}\u2013{x["slot"] + step:%H:%M} UTC: RBN skimmers in {escape(name)} spotted you"></i>'
            last_label = -100.0
            clusters = contact_clusters(lane["contacts"], pct)
            for at, group in clusters:
                side = "r" if at < 78 else "l"
                if len(group) == 1:
                    k = group[0]
                    marks += f'<i class="dv-dot" style="left:calc({at:.2f}% - 11px);border-color:{colour}" title="{escape(k["call"])}, {pd.Timestamp(k["time"]):%H:%M} UTC, {band}"></i>'
                    if len(clusters) <= 3 and at - last_label > 9:                     # a crowded lane has no labels (the callsign is on hover), so none overlap
                        marks += f'<span class="dv-call {side}" style="left:{at:.2f}%">{escape(k["call"])} {pd.Timestamp(k["time"]):%H:%M}</span>'
                        last_label = at
                else:                                                                  # contacts too close to draw apart: one marker with how many, and who on hover
                    who = "\n".join(f'{pd.Timestamp(k["time"]):%H:%M}  {k["call"]}' for k in group[:15]) + (f"\nand {len(group) - 15} more" if len(group) > 15 else "")
                    first, last = pd.Timestamp(group[0]["time"]), pd.Timestamp(group[-1]["time"])
                    marks += (f'<i class="dv-dot multi" style="left:calc({at:.2f}% - 11px);border-color:{colour}" '
                              f'title="{len(group)} contacts on {band}, {first:%H:%M}\u2013{last:%H:%M} UTC\n{escape(who)}">{len(group) if len(group) < 100 else "99+"}</i>')
            if selected is not None and selected[0] == band and start <= pd.Timestamp(selected[1]) < end:
                marks += f'<i class="dv-sel" style="left:{pct(selected[1]):.2f}%;width:calc({100 / len(slots):.2f}% - 2px)" title="The window the details below describe"></i>'
            note = "" if lane["worked_band"] else f' <span class="dv-lab" style="font-size:11px;font-weight:400">not worked</span>'
            on = selected is not None and selected[0] == band
            two = bool(lane["contacts"]) and any(x["rbn"] for x in lane["cells"])          # a lane with contacts and skimmers has a row for each, so a dot never covers a triangle
            labelled = two and len(clusters) <= 3 and any(len(g) == 1 for _, g in clusters)   # and a row of its own for the callsign labels, so one never covers a neighbour
            lanes += (f'<div class="dv-row{" sel" if on else ""}"><div class="dv-name">{band_chip(band, colour)}{note}</div>'
                      f'<div class="dv-track{" two" if two else ""}{" lab" if labelled else ""}">{ticks}{marks}</div></div>')
        head = f'<p class="sub" style="margin:10px 0 4px"><b>{pd.Timestamp(slots[0]):%a %d %b %Y}</b> (UTC)</p>' if many else ""
        out.append(head + f'<div class="dv-row top"><div class="dv-lab" title="The band with the most logged contacts in each quarter hour. A gap means no contact was logged, not that you were off the air.">Logged activity</div><div class="dv-strip">{strip}</div></div>{lanes}<div class="dv-axis">{axis}</div>' + panel_notes_html(panel, colours))
    nothing = ""
    if empty:
        nothing += f"Not shown: {_join(empty)} (no nearby WSPR path, no RBN skimmer and no contact there). "
    if limit_note:
        nothing += limit_note + " "
    legend = ""
    estimate = ("what WSPR showed" if observed else f"an estimate for {power_w:g} W in {escape(mode)}")
    idea = (f'<p class="sub" style="margin:0 0 6px">Nearby WSPR stations act as test signals from your area. When receivers in {escape(name)} decode them, that shows a path from where you were '
            f'(read as {estimate}). A bar says a path was reported. It does not say whether a contact was possible, or what you were doing at the time.</p>')
    rbn = f'<p class="sub">{escape(tl["rbn_line"])}</p>' if tl.get("rbn_line") and not str(tl["rbn_line"]).startswith("RBN skimmers") else ""
    return (f'<div class="lc"><div class="lc-card" id="sec-openings"><h4>{escape(name)}: reported paths and your contacts</h4>{idea}'
            + source_key_html(name)
            + '<div style="margin-top:12px">' + "".join(out) + "</div>" + legend
            + (f'<p class="sub" style="margin-top:8px">The details below describe <b>{escape(str(selected[0]))}, {pd.Timestamp(selected[1]):%H:%M} to {(pd.Timestamp(selected[1]) + pd.Timedelta(minutes=tl["bin_min"])):%H:%M} UTC</b> '
               '(the dashed outline). Change it under <i>Details for one band and time</i>.</p>' if selected is not None else "")
            + f'<p class="sub" style="margin-top:8px">{escape(nothing.strip())} Each bar covers {tl["bin_min"]} minutes, judged on the hour of WSPR up to its end.</p>{rbn}</div></div>')


def with_id(html, ident):
    """`html` with an id on its first card or hero, so a link in the page can jump to it. Unchanged when it has neither."""
    for start in ('<div class="lc-card">', '<div class="lc-hero">'):
        if start in html:
            return html.replace(start, start[:-1] + f' id="{ident}">', 1)
    return html


def section_heading_html(ident, title, note=""):
    """A heading that opens a group of sections of the page, with an id so a link can jump to it and, optionally, one line saying what the group answers."""
    return f'<div class="lc"><div class="lc-sec" id="{escape(ident)}"><h3>{escape(title)}</h3>' + (f"<p>{escape(note)}</p>" if note else "") + "</div></div>"


def glance_html(items, foot=""):
    """A row of short findings, each a link to the part of the page it comes from. `items` are (label, sentence, anchor) and a sentence may be empty
    (that finding is left out). Empty when there are none."""
    cards = "".join(f'<a href="#{escape(anchor)}"><span class="k">{escape(label)}</span><b>{escape(text)}</b><span class="go">Jump there ↓</span></a>'
                    for label, text, anchor in items if text)
    return f'<div class="lc"><div class="lc-glance">{cards}</div>{foot}</div>' if cards else ""


def pota_banner_html(card):
    """The headline of the park or summit card, large: the best day of the log against every activation listed, and where you stand among its
    activators. Empty when no day of the log has a rank."""
    from log_check import pota_headline
    h = pota_headline(card)
    if h is None:
        return ""
    label = f"{card.get('program', 'POTA')} {card.get('noun', 'park').upper()} "
    return ('<div class="lc"><div class="lc-hero" id="sec-park"><div class="k">' + escape(label + card["ref"]) + f'</div><h3>{escape(h["title"])}</h3><p>{escape(h["line"])}</p>'
            + (f'<p class="s">{escape(h["standing"])}</p>' if h["standing"] else "") + "</div></div>")


def pota_html(card):
    """How a park or summit compares: a few counts, one line for each activation in the log and for everything under your callsign, and two short
    tables: the top activators and the biggest activations. SOTA lists QSOs only, so its tables have no mode columns."""
    noun, program = card.get("noun", "park"), card.get("program", "POTA")
    modes = program == "POTA"
    tiles = ('<div class="lc-tiles">' + _tile(f"{card['n_acts']:,}", "--b", f"activations at this {noun}", f"listed by {program}")
             + _tile(f"{card['n_activators']:,}", "--t", "activators", "different stations")
             + _tile(f"{card['yours_listed']:,}", "--a", "your activations here", f"listed under {escape(card['me'])}") + "</div>")
    says = ("<ul class=\"lc-says\">" + "".join(f"<li><b>{escape(a)}</b> {escape(b)}</li>" for a, b in pota_notes(card)) + "</ul>") if card["rows"] else ""
    act = card["top_activators"]
    rows_a = "".join(f"<tr><td>{escape(str(who))}" + (" <small>(you)</small>" if who == card["me"] else "")
                     + f"</td><td>{int(r.activations):,}</td><td>{int(r.qsos):,}</td>" + (f"<td>{int(r.cw):,}</td>" if modes else "") + "</tr>" for who, r in act.iterrows())
    table_a = (f'<p class="sub" style="margin-top:12px"><b>The {noun}\'s top activators</b> (by QSOs listed)</p><div class="lc-cgw"><table class="lc-reg"><tr><th>Station</th>'
               '<th>Activations</th><th>QSOs</th>' + ("<th>CW QSOs</th>" if modes else "") + '</tr>' + rows_a + "</table></div>") if len(act) else ""
    top = card["top"]
    rows = "".join(f"<tr><td>{r.date:%d %b %Y}</td><td>{escape(r.call)}" + (" <small>(you)</small>" if r.who == card["me"] else "")
                   + f"</td><td>{r.total:,}</td>" + (f"<td>{r.cw:,}</td><td>{r.phone:,}</td><td>{r.data:,}</td>" if modes else "") + "</tr>" for r in top.itertuples())
    table = (f'<p class="sub" style="margin-top:12px"><b>The biggest activations listed for this {noun}</b></p><div class="lc-cgw"><table class="lc-reg"><tr><th>Date</th><th>Station</th>'
             '<th>QSOs</th>' + ("<th>CW</th><th>Phone</th><th>Data</th>" if modes else "") + '</tr>' + rows + "</table></div>") if len(top) else ""
    return (f'<div class="lc"><div class="lc-card"><h4>How this {noun} compares: ' + escape(f"{card['ref']} {card['name']}".strip()) + "</h4>"
            f'<p class="sub">Counts from {program}\'s public activation list, as the activators uploaded them, so they can be out of date. '
            f'An activation is one UTC day at the {noun}. Ranks are by QSOs, with the most first; a tie shares a rank.</p>' + tiles + says + table_a + table + '</div></div>')


def signal_example(table):
    """One real match from the table of receiving stations (log_check.match_table) to work the arithmetic through: a station matched once, so that the
    numbers add up exactly, and of those the one whose result is nearest the middle of all the results, so the example is a typical one and not the most extreme.
    None when there is no such row."""
    from log_check import TYPICAL_OFFSET_DB
    if table is None or len(table) == 0:
        return None
    once = table[table["Matches"] == 1]
    if len(once) == 0:
        return None
    col = "Above (+) or below (-) the estimate (dB)"
    middle = float(table[col].median()) if col in table else 0.0
    r = once.iloc[(once[col] - middle).abs().argsort().iloc[0]] if col in once else once.iloc[0]
    obs, est = float(r["RBN report (dB)"]), float(r["Estimated from WSPR (dB)"])
    return {"band": r["Band"], "rx": r["Receiving station"], "obs": obs, "est": est, "diff": obs - est, "after": obs - est - TYPICAL_OFFSET_DB}


def signal_math_html(power_w, mode, offset_db, example=None, thresholds=None):
    """How a bar is worked out, step by step, and what the power and the mode do to it: the power moves every estimate (and so every bar, the other way) dB for dB; the
    mode does not enter the bars at all, only the 'looked strong enough' test of the openings. `example` is one real match (signal_example)."""
    import math
    dbm = 10 * math.log10(max(power_w, 1e-6) * 1000)
    tx_w, tx_snr = 5, -20.0
    tx_dbm = 10 * math.log10(tx_w * 1000)
    restated = tx_snr + (dbm - tx_dbm)
    real = ""
    if example:
        real = (f'<p class="sub"><b>One match from your log:</b> {escape(str(example["rx"]))} on {escape(str(example["band"]))}. The skimmer reported you at {example["obs"]:g} dB. '
                f'The WSPR estimate for {power_w:g} W at that receiver was {example["est"]:g} dB. The difference is {example["obs"]:g} \u2212 ({example["est"]:g}) = {example["diff"]:+.1f} dB, '
                f'and taking off the {offset_db:g} dB reference leaves <b>{example["after"]:+.1f} dB</b>. A band\'s bar is the middle of such results across its skimmers, each counted once.</p>')
    modes = ", ".join(f"{m} {t:+g} dB" for m, t in (thresholds or {}).items() if m in ("CW", "SSB", "FT8"))
    return ('<h5 style="margin:10px 0 4px">How a bar is worked out</h5><ol class="lc-steps">'
            f'<li><b>Restate each WSPR report to your power.</b> A WSPR transmitter near you gives its power in its report, and a receiver gives the signal-to-noise ratio (SNR) it decoded it at. '
            f'The estimate for you is that SNR plus the difference between your power and the transmitter\'s, in dB: SNR + 10 \u00d7 log\u2081\u2080(your watts \u00f7 its watts). '
            f'For example, a {tx_w} W ({tx_dbm:.0f} dBm) transmitter decoded at {tx_snr:g} dB becomes {tx_snr:g} + ({dbm:.0f} \u2212 {tx_dbm:.0f}) = {restated:+.0f} dB for your {power_w:g} W ({dbm:.0f} dBm). '
            'Transmitters declare their own power, and it is not checked.</li>'
            '<li><b>Take the middle estimate for each receiving station</b> that also spotted you, over the stretch of the log (its reports from the hour before the middle of the stretch).</li>'
            '<li><b>Take the skimmer\'s middle reported SNR of you</b> over the same stretch.</li>'
            f'<li><b>Subtract, then take off the reference.</b> RBN report \u2212 WSPR estimate, minus {offset_db:g} dB, because an ordinary station reads about {offset_db:g} dB higher on RBN than on WSPR '
            '(the two services measure noise differently). That fixed correction is the only thing added or taken off by hand; it is not tied to power or mode.</li>'
            '<li><b>Count each skimmer once.</b> A skimmer’s results across stretches (and names of one callsign) are reduced to their middle; a band’s bar is the middle across its skimmers, and the line through it is the middle half of them.</li></ol>'
            + real +
            f'<p class="sub"><b>Power.</b> You entered {power_w:g} W, so ' + (f'every estimate is {10 * math.log10(power_w / 100):+.1f} dB from what a 100 W station would get. ' if power_w != 100 else
                                                                         'the estimates are the ones a 100 W station would get, the power the reference was found for. ')
            + 'A different power moves every estimate by the '
            'same number of dB (doubling it adds 3 dB), and so moves every bar the other way by that amount. It has to be the power you ran, or the bars are shifted by the difference.</p>'
            f'<p class="sub"><b>Mode.</b> The bars do not use it: the comparison reads your {escape(mode)} contacts, because RBN hears only CW and RTTY, and takes off the same reference whatever you ran. '
            'Mode matters in the openings above, where a receiver counts as having looked strong enough to hear you when its estimate is above the mode\'s threshold'
            + (f' ({escape(modes)}, in 2,500 Hz)' if modes else "") + '; changing the mode there changes which receivers count, not these bars.</p>')


def signal_intro_html(offset_db, overall=None, power_w=None):
    """The opening of the signal comparison, short, so the result comes first: what the bars are, that the reference is experimental, and the overall result with
    how many matches and different receiving stations it rests on and the spread. The steps, the power, the mode and a worked example are in signal_method_html."""
    line = ""
    if overall is not None and overall.get("stronger_db") is not None and overall["stronger_db"] == overall["stronger_db"]:
        rx = overall.get("match_rx", overall.get("matches"))
        spread = overall.get("spread_db")
        line = (f'<p style="margin:2px 0 0;font-size:15px"><b>Overall {overall["stronger_db"]:+.0f} dB</b> from {rx} skimmers ({overall["matches"]} matches)'
                + (f"; the receivers spread {spread:.1f} dB" if spread is not None and spread == spread and overall["matches"] > 2 else "") + ".</p>")
    reference = f"{power_w:g} W" if power_w else "your power"
    return ('<div class="lc"><div class="lc-card" id="sec-signal"><h4>Signal comparison: RBN skimmers against the nearby WSPR reference</h4>'
            f'<p class="sub"><b>Experimental.</b> Each bar below is how far the skimmers\' reports of you sat above (blue) or below (amber) what the WSPR stations near you would give at the same '
            f'receivers, restated to {reference}; the line through a bar is where the middle half of its skimmers fell. The reference is an estimate with a fixed {offset_db:.0f} dB correction '
            'between RBN and WSPR, not an established benchmark, and a bar says how you were heard, not how your antenna performs.</p>' + line + '</div></div>')


def signal_method_html(power_w, mode, offset_db, example=None, thresholds=None):
    """How the signal comparison is worked out, for the folded box under the bars: in plain words first (what is matched, what a match and a skimmer are, what the bar and its
    outline show, what it cannot tell), then the steps, what the power and the mode do, and one real match."""
    return ('<div class="lc"><div class="lc-card" style="border:0;padding:0;margin:0;background:none" id="sec-signal-method">'
            '<h5 style="margin:2px 0 4px">In plain words</h5>'
            '<ul class="lc-steps">'
            '<li><b>The question.</b> Were your signals stronger or weaker at the skimmers than a typical station’s would be, judged by WSPR?</li>'
            '<li><b>The test transmitters.</b> WSPR stations near you act as test signals. Each WSPR report gives the transmitter’s power and how strongly a receiver decoded it, so '
            'it can be restated to <i>your</i> power: an estimate of the signal a station at your power, set up like your neighbours, shows at that receiver.</li>'
            '<li><b>Which skimmers count.</b> Only a skimmer that spotted you <i>and</i> also decoded those WSPR neighbours in the same stretch of your log (an unbroken run of contacts on '
            'one band). That is a <b>match</b>: one receiving station in one stretch, with its estimate (the middle of what it decoded from your neighbours in the hour before) '
            'beside what it reported for you.</li>'
            '<li><b>One skimmer, one vote.</b> A skimmer heard in two stretches, or listed under two names of one callsign (K5TR and K5TR-1), makes several matches but is one skimmer: its '
            'matches are reduced to their middle before anything is counted. Nodes with a <i>-1</i> or <i>-4</i> after a callsign are treated as that callsign.</li>'
            '<li><b>The bar</b> is the middle skimmer (the median), how far above (blue) or below (amber) the estimate the skimmers reported you. <b>The outline</b> is the middle half of the '
            'skimmers: a quarter fell below its left end, a quarter above its right end. A wide outline means the skimmers disagreed, so the single figure is shaky; a narrow one means '
            'they agreed. With fewer than 8 skimmers the bar is striped, and under 3 there is no bar.</li>'
            f'<li><b>What it cannot tell.</b> The reference is experimental. It is other people’s stations, and the page corrects for their power, not their antennas, so a better antenna than theirs reads high and a '
            f'worse one reads low, and a band at +15 dB or more gets a note saying so. Skimmers and WSPR receivers are also different equipment, so an ordinary station reads about {offset_db:.0f} dB '
            'higher on RBN than on WSPR (found from two checks of stations whose power is known), and that is taken off. It is a hint about how you were heard, not a '
            'measurement of your antenna.</li></ul>' + signal_math_html(power_w, mode, offset_db, example, thresholds) + '</div></div>')


def band_table_html(bands, min_contacts=3):
    """One row per band: contacts, skimmers, and strength against the nearby WSPR reference. A band with fewer than `min_contacts` contacts is left
    out of the rows and named underneath, because one contact says nothing."""
    few = bands[bands["contacts"] < min_contacts]
    bands = bands[bands["contacts"] >= min_contacts]
    top = max(int(bands["contacts"].max()), 1) if len(bands) else 1
    rows = []
    for r in bands.itertuples():
        zero = 15 / 35 * 100
        if np.isnan(r.stronger_db):
            strength = f'<div class="lc-str none">{"too few matches" if r.matches else "no matches"}</div>'
        else:
            pos = (np.clip(r.stronger_db, -15, 20) + 15) / 35 * 100
            left, width = (zero, pos - zero) if r.stronger_db >= 0 else (pos, zero - pos)
            q1, q3 = getattr(r, "q1", float("nan")), getattr(r, "q3", float("nan"))
            spread = ""
            if not (np.isnan(q1) or np.isnan(q3)):
                a, b = (np.clip(q1, -15, 20) + 15) / 35 * 100, (np.clip(q3, -15, 20) + 15) / 35 * 100
                spread = f'<u style="left:{a:.1f}%;width:{max(b - a, 0.8):.1f}%" title="The middle half of the skimmers ran from {q1:+.1f} to {q3:+.1f} dB"></u>'
            strength = (f'<div class="lc-str" title="{r.matches} match{"es" if r.matches != 1 else ""}: {getattr(r, "match_rx", r.matches)} skimmer{"s" if getattr(r, "match_rx", r.matches) != 1 else ""} that spotted you and also decoded WSPR near you, each counted once (a skimmer heard in two stretches of the log, or under two names of one callsign, is several matches but one skimmer)">'
                        f'<div class="lc-sbar"><em class="g" style="left:14.3%"></em><em class="g" style="left:71.4%"></em><em class="z" style="left:{zero:.1f}%"></em>'
                        f'<i class="{"pos" if r.stronger_db >= 0 else "neg"}{" thin" if r.thin else ""}" style="left:{left:.1f}%;width:{width:.1f}%"></i>{spread}</div>'
                        f'<div class="lc-sv"><b>{r.stronger_db:+.1f} dB</b><small>{getattr(r, "match_rx", r.matches)} skimmer{"s" if getattr(r, "match_rx", r.matches) != 1 else ""}</small></div></div>')
        notes = ""
        if not np.isnan(r.stronger_db) and r.stronger_db >= HIGH_DB:
            notes += (f'<div class="lc-bnote"><b>{r.band} reads well above the WSPR reference ({r.stronger_db:+.1f} dB).</b> The usual reason is a better antenna than most of the WSPR stations '
                      'near you have: the page corrects for their power but not their antenna. Check that the power above is what you ran. The spread of the skimmers (the outline) '
                      'is the better guide than the single figure.</div>')
        near, far = getattr(r, "near_db", float("nan")), getattr(r, "far_db", float("nan"))
        if not (np.isnan(near) or np.isnan(far)):
            km = int(SPLIT_KM)
            notes += (f'<div class="lc-bsplit">Skimmers under {km:,} km ({km / 1.609344:,.0f} mi): <b>{near:+.1f} dB</b> ({r.near_n}) &middot; farther: <b>{far:+.1f} dB</b> ({r.far_n})</div>')
        extra = getattr(r, "other", 0)
        other = f'<small title="Contacts in other modes are in the log but RBN cannot hear them, so they are not compared">+{extra} other mode{"s" if extra != 1 else ""}</small>' if extra else ""
        rows.append(f'<div class="lc-brow"><div class="lc-bname">{r.band}</div>'
                    f'<div class="lc-cont"><b>{r.contacts}</b><span>CW contacts</span><div class="bar"><i style="width:{r.contacts / top * 100:.1f}%"></i></div>{other}</div>'
                    f'<div class="lc-sk"><b>{r.skimmers}</b><span>skimmers</span></div>{strength}{notes}</div>')
    return ('<div class="lc"><div class="lc-card"><h4>What RBN skimmers heard on each band</h4>'
            '<p class="sub">What you worked, how many skimmers heard you, and how their reports compare with the nearby WSPR reference at your power.</p>'
            '<div class="lc-legend"><span><i class="lg-pos"></i>blue: RBN reports above the WSPR reference</span><span><i class="lg-neg"></i>amber: below it</span>'
            '<span><i class="lg-box"></i>outline: where the middle half of the skimmers fell</span><span><i class="lg-thin"></i>striped: few skimmers</span></div>'
            '<div class="lc-bh"><div>Band</div><div>Contacts</div><div>Skimmers</div><div>Against the WSPR reference'
            '<div class="lc-str"><div class="lc-axs"><span style="left:14.3%">−10</span><span style="left:42.86%">0</span><span style="left:71.4%">+10</span><span style="right:0;left:auto;transform:none">+20 dB</span></div><span></span></div></div></div>'
            + "".join(rows)
            + (f'<p class="sub" style="margin-top:10px">Not shown, with fewer than {min_contacts} CW contacts: '
               + ", ".join(f"{r.band} ({r.contacts} CW" + (f", {r.other} other" if getattr(r, "other", 0) else "") + ")" for r in few.itertuples()) + ".</p>" if len(few) else "")
            + '</div></div>')


MIN_SKIMMERS = 3      # fewer skimmers than this in a region and no share is shown, as the page shows no figure under 3 WSPR receivers


def regions_html(regions, band):
    """One band by region: the contacts, stations worked, the skimmers on the band and how many spotted you, and what the Band conditions
    page said. DX regions come first and are tagged. A region with fewer than three WSPR receivers behind it has no page figure."""
    d = regions[regions["band"] == band]
    d = d[(d["contacts"] > 0) | (d["on_band"] > 0)]
    if d.empty:
        return '<div class="lc"><p class="muted">Nothing to show for this band.</p></div>'
    rows = []
    for r in d.itertuples():
        dx = r.region not in NEAR_REGIONS
        tag = "<em>DX</em>" if dx else ""
        contacts = f"{r.contacts}" + (f' <small>({r.cw} CW)</small>' if r.cw != r.contacts else "")
        if 0 < r.on_band < MIN_SKIMMERS:
            shared = (f'<span class="dim" title="Only {r.on_band} skimmer{"s" if r.on_band != 1 else ""} on the band in this region, too few for a '
                      f'share: a few skimmers cannot say whether the path was open">too few skimmers</span>')
        elif r.on_band:
            share = r.spotted / r.on_band
            shared = f'<div class="lc-share"><div><i style="width:{share * 100:.0f}%"></i></div><b>{share * 100:.0f}%</b></div>'
        else:
            shared = '<span class="dim">no skimmers on the band</span>'
        if np.isnan(r.page):
            page = f'<span class="dim" title="Fewer than 3 WSPR receivers in this region, so the page has no figure ({r.wspr_receivers} here)">greyed</span>'
        else:
            page = f'{pct(r.page)} <small>({r.wspr_receivers} WSPR rx)</small>'
        rows.append(f'<div class="lc-rr"><div class="rn">{escape(r.region)}{tag}</div><div data-l="Contacts">{contacts}</div>'
                    f'<div data-l="Stations">{r.stations}</div><div data-l="Skimmers on the band">{r.on_band}</div>'
                    f'<div data-l="Spotted you">{r.spotted}</div><div data-l="Share spotted">{shared}</div><div data-l="Page said">{page}</div></div>')
    return ('<div class="lc"><div class="lc-card"><h4>' + escape(band) + ' by region</h4>'
            '<p class="sub">Contacts are all modes; the skimmers and the page are for CW. Skimmers are counted once each across the whole log.</p>'
            '<div class="lc-rh"><div>Region</div><div>Contacts</div><div>Stations</div><div>Skimmers on the band</div><div>Spotted you</div>'
            '<div>Share spotted</div><div>Page said</div></div>' + "".join(rows) + '</div></div>')


def _ticks(t0, t1):
    span = (t1 - t0).total_seconds() / 60
    step = 15 if span <= 90 else 30 if span <= 200 else 60
    t = t0.ceil(f"{step}min")
    while t <= t1:
        yield t
        t += pd.Timedelta(minutes=step)


UP, DOWN, GAP = 50, 26, 2.5           # pixels: room above a lane's line for blocks, room below it for spots, space between blocks
PANEL_GAP_H = 4                       # a pause this long in the log starts a new chart, so a log over several days is not squeezed into one
SLOTS = (2, 3, 5, 10, 15, 30, 60)     # minutes a block can stack over; the shortest one that keeps a block readable is used
MIN_BLOCK_PX, LANE_PX = 5, 820        # a block is at least about this many pixels wide on a lane about this wide


def _slot_minutes(span_min):
    for m in SLOTS:
        if m / max(span_min, 1) * LANE_PX >= MIN_BLOCK_PX:
            return m
    return SLOTS[-1]


def _panels(log):
    """The log cut into stretches of activity, wherever there is a pause of PANEL_GAP_H hours or more."""
    t = log["time"]
    return [g for _, g in log.groupby((t.diff() > pd.Timedelta(hours=PANEL_GAP_H)).cumsum())]


def _panel_html(part, spots, rep, follow, title, marked, follow_bands=None):
    """One chart: a lane for each band used in `part`. `marked` is a one-item list that remembers whether the follower's label is drawn;
    `follow_bands` is how many bands the follower was worked on in the whole log."""
    bands = bands_top_down(part)
    span = ((part["time"].max() - part["time"].min()).total_seconds() / 60) + 12
    step = _slot_minutes(span)
    freq = f"{step}min"
    t0, t1 = part["time"].min().floor(freq) - pd.Timedelta(minutes=6), part["time"].max().ceil(freq) + pd.Timedelta(minutes=6)
    minutes = (t1 - t0).total_seconds() / 60
    slot = part.assign(slot=part["time"].dt.floor(freq))
    tallest = max(int(slot.groupby(["band", "slot"]).size().max()), 1)
    up = UP if tallest <= 4 else min(104, 11 * tallest)     # a lane grows when a slot holds many contacts
    mid, height = up + 6, up + 6 + DOWN + 6
    bh = max(3.0, min(12.0, (up - GAP * (tallest - 1)) / tallest))
    gap = GAP if bh > 4 else 1.0
    sp = pd.Series(dtype=int)
    if spots is not None and len(spots):
        k = spots[(spots["time"] >= t0) & (spots["time"] <= t1) & spots["band"].isin(bands)]
        sp = k.assign(slot=k["time"].dt.floor(freq)).groupby(["band", "slot"]).size()
    mx = max(int(sp.max()), 1) if len(sp) else 1
    left = lambda t: (t - t0).total_seconds() / 60 / minutes * 100
    width = f"max(3px, calc({step / minutes * 100:.4f}% - 1.4px))"
    ticks = "".join(f'<i class="lc-tick" style="left:{left(t):.3f}%"></i>' for t in _ticks(t0, t1))
    lanes = []
    for band in bands:
        n = int((part["band"] == band).sum())
        parts = [f'<div class="lc-mid" style="top:{mid}px"></div>', ticks]
        if len(sp) and band in sp.index.get_level_values(0):
            for t, c in sp[band].items():
                parts.append(f'<i class="lc-s" style="left:{left(t):.3f}%;width:{width};top:{mid + 3}px;height:{max(2, c / mx * DOWN):.1f}px" '
                             f'title="{c} RBN spots on {band}, {t:%H:%M}Z"></i>')
        for t, g in slot[slot["band"] == band].groupby("slot"):
            for j, r in enumerate(g.sort_values("time").itertuples()):
                top = mid - 3 - (j + 1) * bh - j * gap
                came_back = r.call in rep
                parts.append(f'<i class="lc-b{" rep" if came_back else ""}" style="left:{left(t):.3f}%;width:{width};top:{top:.1f}px;height:{bh:.1f}px" '
                             f'title="{escape(r.call)} · {band} · {r.time:%H:%M}Z{" · came back on another band" if came_back else ""}"></i>')
                if follow and r.call == follow:
                    parts.append(f'<i class="lc-d" style="left:{left(t) + step / 2 / minutes * 100:.3f}%;top:{top - 13:.1f}px" title="{escape(follow)}"></i>')
                    if not marked[0]:
                        parts.append(f'<span class="lc-kl" style="left:calc({left(t):.3f}% + 14px);top:{top - 15:.1f}px">{escape(follow)}: '
                                     f'worked you on {follow_bands or part.loc[part["call"] == follow, "band"].nunique()} bands</span>')
                        marked[0] = True
        lanes.append(f'<div class="lc-lane"><div class="lc-lab" style="padding-top:{mid - 22}px"><b>{band}</b><span>{n} contact{"s" if n != 1 else ""}</span></div>'
                     f'<div class="lc-plot" style="height:{height}px">{"".join(parts)}</div></div>')
    axis = "".join(f'<span style="left:{left(t):.3f}%">{t:%H:%M}Z</span>' for t in _ticks(t0, t1))
    return (f'<div class="lc-chart"><div class="lc-ph">{title} · blocks stack in {step} minute slots</div>{"".join(lanes)}'
            f'<div class="lc-axis">{axis}</div></div>')


def speed_line(log, spots):
    """One plain sentence on how fast you sent: the typical CW speed the skimmers measured, the range most spots fall in, and, only when it
    really changed during the session, how. Most operators send at one speed, so this is a number and not a chart. Empty when the spots carry
    no CW speed (RTTY, WSPR, or spots pasted without one) or too few to say."""
    import cw_speed
    overall = cw_speed.summary(spots) if spots is not None and len(spots) else None
    if overall is None:
        return ""
    low, high = round(overall["low"]), round(overall["high"])
    text = (f"**Sending speed: {overall['median']:.0f} wpm.** "
            + (f"The skimmers measured about {low} wpm for most spots." if low == high else f"The skimmers measured {low} to {high} wpm for most spots.")
            + " That is their measurement, not what you set.")
    s = cw_speed.cw_speeds(spots)
    stretches = s.assign(slot=s["time"].dt.floor("15min")).groupby("slot").agg(v=("speed", "median"), n=("speed", "size"))
    firm = stretches[stretches["n"] >= 3]
    if len(firm) >= 2 and firm["v"].max() - firm["v"].min() >= 3:
        fast, slow = firm["v"].idxmax(), firm["v"].idxmin()
        text += (f" It changed during the session: about {firm.at[slow, 'v']:.0f} wpm around {slow:%H:%M}Z and up to "
                 f"{firm.at[fast, 'v']:.0f} wpm around {fast:%H:%M}Z.")
    return text


def afternoon_html(log, spots):
    """The session as one chart for each stretch of activity (a pause of four hours or more starts another). One lane per band: above
    its line, one block for each contact, stacked in short time slots (amber for a station that came back on another band); below it,
    the RBN spots in the same slots. Times are UTC. Built of positioned boxes, not SVG, because the page sanitizer removes SVG."""
    rep, follow, marked = set(repeat_calls(log)), pick_follower(log), [False]
    panels = _panels(log)
    charts = []
    for part in panels:
        a, z = part["time"].min(), part["time"].max()
        title = (f"{a:%a %d %b}, {a:%H:%M}Z to {z:%H:%M}Z" if a.date() == z.date() else f"{a:%a %d %b} {a:%H:%M}Z to {z:%a %d %b} {z:%H:%M}Z")
        charts.append(_panel_html(part, spots, rep, follow, title, marked, int(log.loc[log["call"] == follow, "band"].nunique()) if follow else None))
    legend = ('<div class="lc-legend"><span><i style="background:var(--b)"></i>one block = one contact (stacked in short time slots)</span>'
              '<span><i style="background:var(--a)"></i>that station came back on another band</span>'
              '<span><i style="background:var(--t);opacity:.55"></i>RBN spots below the line (same slots)</span>'
              + (f'<span><i class="dia"></i>{escape(follow)}</span>' if follow else "") + '</div>')
    return ('<div class="lc"><div class="lc-card"><h4>The session</h4><p class="sub">Your contacts and the spots, band by band, in time order (UTC)'
            + (f"; the log has {len(panels)} stretches of activity, each drawn on its own" if len(panels) > 1 else "") + '.</p>'
            + legend + f'<div class="lc-swim">{"".join(charts)}</div></div></div>')


def repeat_calls(log):
    """The calls worked on more than one band."""
    k = log.groupby("call")["band"].nunique()
    return list(k[k > 1].index)


def pick_follower(log):
    """The station that came back on the most bands, if it was three or more; it gets a line through the chart."""
    k = log.groupby("call")["band"].nunique().sort_values(ascending=False)
    return k.index[0] if len(k) and k.iloc[0] >= 3 else None


LADDER_ROWS = 12      # the stations shown at first; the rest are under a "Show more" box


def ladder_html(rep, bands, rows=LADDER_ROWS, first=0):
    """A dot for each band a repeat station was worked on, joined by a line, with the number of bands beside the callsign. Shows `rows`
    stations from number `first` on."""
    cells = ['<div class="hd" style="text-align:left;padding-left:8px">station · bands</div>' + "".join(f'<div class="hd">{b}</div>' for b in bands)]
    for i, (call, r) in enumerate(rep.iloc[first:first + rows].iterrows()):
        idx = [bands.index(b) for b in r["bands"] if b in bands]
        lo, hi = min(idx), max(idx)
        z = " zb" if i % 2 == 0 else ""
        row = [f'<div class="cl{z}">{escape(call)}<span class="n" title="worked on {r["k"]} bands">{r["k"]}</span></div>']
        for j, b in enumerate(bands):
            cls = "cd" + z + (" ln" if lo <= j <= hi else "") + (" l0" if j == lo else "") + (" l1" if j == hi else "")
            dot = f'<i title="{escape(call)} · {b}"></i>' if j in idx else ""
            row.append(f'<div class="{cls}">{dot}</div>')
        cells.append("".join(row))
    return f'<div class="lc-lad" style="--k:{len(bands)}">' + "".join(cells) + "</div>"


def _fact(head, body, tone=""):
    return f'<div class="lc-fact {tone}"><div class="h">{head}</div><div class="b">{body}</div></div>'


_NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}


def followers_headline(rep):
    """One sentence on how many stations worked you on how many bands: '8 stations worked you on three bands; another 25 on two.'"""
    if not len(rep):
        return "Nobody was worked on more than one band."
    parts = []
    for i, (k, n) in enumerate(rep["k"].value_counts().sort_index(ascending=False).items()):
        word = _NUMBER_WORDS.get(int(k), str(k))
        parts.append(f"{n} station{'s' if n != 1 else ''} worked you on {word} bands" if i == 0 else f"another {n} on {word}")
    return "; ".join(parts) + "."


def ladder_rest_html(log, first=LADDER_ROWS):
    """The stations of the ladder after the first `first`, for a 'Show more' box under it."""
    from log_check import repeat_stations
    rep = repeat_stations(log)
    return '<div class="lc">' + ladder_html(rep, bands_top_down(log), rows=len(rep), first=first) + "</div>"


def _long_time(minutes):
    """A length of time in plain words: '41.5 minutes' under an hour, else '11 h 25 min'."""
    if minutes != minutes:
        return "none"
    if minutes < 60:
        return f"{minutes:.0f} minutes"
    h, m = divmod(int(round(minutes)), 60)
    return f"{h} h" if m == 0 else f"{h} h {m:02d} min"


def _approx_km(km):
    """A distance as the page writes a rough one: to the nearest 100 km once it is over 1,000."""
    return f"{round(km, -2):,.0f}" if km >= 1000 else f"{round(km, -1):,.0f}"


def _utc(t):
    return "" if pd.isna(t) else f"{t:%H:%M}"


def _span_utc(a, b):
    """Two times as one stretch, '17:04–17:08 UTC', each with its date when they are on different days, so a log over two days does not read as ending before it began."""
    if pd.isna(a) or pd.isna(b):
        return "none"
    if a.date() == b.date():
        return f"{a:%H:%M}–{b:%H:%M} UTC"
    return f"{a:%d %b %H:%M} to {b:%d %b %H:%M} UTC"


def _days_text(days):
    return ", ".join(f"{pd.Timestamp(d):%d %b}" for d in days)


def _reach_band_html(r, colours, open_it):
    """One band of the "Where RBN heard you" card: a chip, the count of skimmers that reported you, how far, and where, with the regional counts folded under it."""
    from log_reach import region_label
    band = r["band"]
    who = (f'<div class="lc-rwho">{band_chip(band, colours.get(band, "#888888"))}<span>{r["contacts"]} contact{"s" if r["contacts"] != 1 else ""}</span>'
           f'<span class="m">First to last logged contact {_span_utc(r["first_contact"], r["last_contact"])}</span>'
           + (f'<span class="m">{r["other_mode"]} more in other modes, which RBN cannot hear</span>' if r["other_mode"] else "") + "</div>")
    if r["state"] == "unavailable":
        why = (f"RBN has no file for {_days_text(r['missing_days'])} yet, so the half hours with your {band} contacts cannot be counted."
               if r["missing_days"] else "The list of skimmers that were reporting could not be read, so these half hours cannot be counted.")
        return f'<div class="lc-rrow">{who}<div class="lc-rmain"><div class="lc-rhead">No RBN data for {band}</div><div class="lc-rsup">{escape(why)}</div></div></div>'
    half = f"{r['windows']} half hour{'s' if r['windows'] != 1 else ''}"
    if r["state"] == "no_activity":
        return (f'<div class="lc-rrow">{who}<div class="lc-rmain"><div class="lc-rhead">No skimmer reported any station on {band} in the {half} with your logged CW contacts</div>'
                '<div class="lc-rsup">There is nothing to set your reports against for those half hours: RBN has no reports on this band then, from you or from anyone else.</div></div></div>')
    n = r["reporters"]
    head = f'<b>{n} skimmer{"s" if n != 1 else ""}</b> reported you on {band}'
    lines = []
    if r["farthest"]:
        km, call, region = r["farthest"]
        lines.append(f'<div class="lc-rline"><span class="lab">Farthest report</span>{escape(call)} · ~{_approx_km(km)} km · {escape(region_label(region))}</div>')
        names = [region_label(k) for k, (h, _) in sorted(r["regions"].items(), key=lambda kv: (-kv[1][0], kv[0])) if h]
        lines.append(f'<div class="lc-rline"><span class="lab">Reports from</span>{escape(", ".join(names))}</div>')
    elif n:
        lines.append('<div class="lc-rline"><span class="lab">Farthest report</span>not known: no skimmer that reported you has a place in the skimmer list</div>')
    else:
        lines.append(f'<div class="lc-rline">{r["active"]} skimmer{"s" if r["active"] != 1 else ""} reported other stations on {band} in the {half} with your logged CW contacts.</div>')
    on = "".join(f'<span class="lc-rg on"><b>{escape(region_label(k))}</b> {h} of {a}</span>' for k, (h, a) in sorted(r["regions"].items(), key=lambda kv: (-kv[1][0], -kv[1][1])) if h)
    off = "".join(f'<span class="lc-rg off">{escape(region_label(k))} 0 of {a}</span>' for k, (h, a) in sorted(r["regions"].items(), key=lambda kv: -kv[1][1]) if not h)
    nobody = '<span class="lc-rg off">none</span>'
    spot_span = _span_utc(r["first_spot"], r["last_spot"]) if r["spots_total"] else "none"
    detail = (f'<div class="lc-rline"><span class="lab">Reports from</span>{on or nobody}</div>'
              f'<div class="lc-rline"><span class="lab">No RBN reports from</span>{off or nobody}</div>'
              f'<div class="lc-rsup">{r["active"]} skimmer{"s" if r["active"] != 1 else ""} reported any station on {band} in the {half} with your logged CW contacts, you included; '
              f'{n} of them reported you ({r["reports"]} report{"s" if r["reports"] != 1 else ""}). Your first and last spot on {band} over the whole log: '
              f'{spot_span} ({r["spots_total"]} in all).</div>')
    return (f'<div class="lc-rrow">{who}<div class="lc-rmain"><div class="lc-rhead">{head}</div>{"".join(lines)}'
            f'<details class="dv-more"{" open" if open_it else ""}><summary>Regional breakdown</summary>{detail}</details></div></div>')


def reach_takeaway(rows):
    """The sentence or two over the card: the farthest report of any band, and the busiest band's reports all being from North America when that is so."""
    from log_reach import overall, region_label
    facts = overall(rows)
    best = facts["farthest_band"]
    if best is None:
        return "No skimmer reported you in the half hours with your logged CW contacts." if any(r["state"] == "ok" for r in rows) else ""
    km, call, region = best["farthest"]
    text = f'Your farthest RBN report was on {best["band"]}: {call} in {region_label(region)}, approximately {_approx_km(km)} km away.'
    if facts["busiest"]:
        text += f' Your {facts["busiest"]["band"]} reports came from North America.'
    return text


def reach_html(rows, colours, total_spots=0, total_skimmers=0):
    """The "Where RBN heard you" card: for each band with logged CW contacts, how many skimmers reported you, how far, and where, from RBN, counted over the half hours that
    hold a logged CW contact on the band (log_reach.reach_by_band). The band with the farthest report is open. Empty text when there are no rows."""
    if not rows:
        return ""
    best = max((x for x in rows if x["farthest"]), key=lambda x: x["farthest"][0], default=None)
    take = reach_takeaway(rows)
    colours = colours or {}
    sub = ("The Reverse Beacon Network skimmers that reported you, band by band, and where they are. Each count covers the half hours that hold a logged CW contact on that band; "
           "a skimmer is counted once per band." + (f" Over the whole log, {total_spots:,} RBN spots of you came from {total_skimmers} skimmers." if total_spots else ""))
    foot = ("These counts show where RBN skimmers reported you, not everywhere you could be heard. A skimmer is active when it reported any station on the band in those half hours, "
            "you included. A spot says a skimmer decoded you and a contact says you logged someone: neither says when you were calling or listening. Times are UTC.")
    return ('<div class="lc"><div class="lc-card"><h4>Where RBN heard you</h4>'
            f'<p class="sub">{escape(sub)}</p>' + (f'<div class="lc-take">{escape(take)}</div>' if take else "")
            + "".join(_reach_band_html(r, colours, r is best) for r in rows) + f'<p class="lc-rfoot">{escape(foot)}</p></div></div>')


def followers_html(log, summary, rows=LADDER_ROWS):
    """The ladder of the stations worked on more than one band, the most bands first, beside a few notes written from the log."""
    from log_check import repeat_stations, same_band_repeats
    rep = repeat_stations(log)
    facts = []
    far = log[(log["cont"] != "") & (log["cont"] != "NA")]
    if len(far):
        names = ", ".join(f"<b>{escape(r.call)}</b> ({r.band})" for r in far.head(6).itertuples())
        facts.append(_fact("Outside North America", names + (f" and {len(far) - 6} more" if len(far) > 6 else "")))
    spans_days = log["time"].dt.date.nunique() > 1
    when = f"{summary['best_hour_start']:%d %b %H:%M}Z" if spans_days else f"{summary['best_hour_start']:%H:%M}Z"
    facts.append(_fact("Busiest stretch", f"<b>{summary['best_hour']} contacts</b> in the hour from {when}. "
                                        f"Longest quiet gap: {_long_time(summary['longest_gap_min'])}."))
    if summary["park_to_park"] or summary.get("park_same"):
        same = summary.get("park_same", 0)
        text = (f"<b>{summary['park_to_park']} contact{'s' if summary['park_to_park'] != 1 else ''}</b> with {summary['parks']} other park{'s' if summary['parks'] != 1 else ''}"
                if summary["park_to_park"] else "No contact named another park")
        facts.append(_fact("Park to park", text + (f"; {same} more named your own park." if same else ".")))
    if summary.get("summit_to_summit"):
        facts.append(_fact("Summit to summit", f"<b>{summary['summit_to_summit']} contacts</b> with {summary['summits']} summit{'s' if summary['summits'] != 1 else ''}."))
    dupes = same_band_repeats(log)
    if dupes:
        facts.append(_fact("Worked twice on a band", f"{dupes} station{'s were' if dupes != 1 else ' was'} logged more than once on the same band."))
    ladder = ladder_html(rep, bands_top_down(log), rows) if len(rep) else '<p class="muted">Nobody was worked on more than one band.</p>'
    return ('<div class="lc"><div class="lc-card"><h4>Who followed you</h4>'
            f'<p class="sub">{followers_headline(rep)}</p>'
            f'<div class="lc-two"><div>{ladder}</div><div class="lc-facts">{"".join(facts)}</div></div></div></div>')
