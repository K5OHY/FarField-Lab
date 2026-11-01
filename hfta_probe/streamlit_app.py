"""Temporary hosting probe for the HFTA terrain engine. Not part of FarField Lab; safe to delete."""
import tempfile

import streamlit as st

import probe

st.title("HFTA engine hosting probe")
st.caption("Checks the CPU type, builds OpenHFTA with gfortran, and compares its output with reference numbers from an Intel/AMD Linux build.")
info = probe.machine_info()
st.json(info)
if info["machine"] not in ("x86_64", "AMD64"):
    st.error(f"CPU is {info['machine']}, not Intel/AMD. The engine's x87 build flags won't apply here.")

@st.cache_resource
def built():
    w = tempfile.mkdtemp()
    return probe.build(w)

with st.spinner("Downloading and building OpenHFTA..."):
    src, rc, secs, log = built()
st.write(f"make exit code **{rc}** in {secs} s")
if rc:
    st.code(log)
    st.stop()
rows, worst = probe.compare(src)
st.table(rows)
if worst <= 0.01:
    st.success(f"PASS: largest difference from the reference is {worst:.4f} dB.")
else:
    st.error(f"MISMATCH: largest difference from the reference is {worst:.4f} dB.")
