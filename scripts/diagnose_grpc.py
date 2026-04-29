#!/usr/bin/env python3
"""diagnose_grpc.py — analyse gRPC pcaps with subprocess tshark calls"""
import subprocess, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCAP_DIR = os.path.join(ROOT, "metrics", "raw", "pcaps")

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return r.stdout.strip()

def tshark_sum(pcap, extra=""):
    cmd = f'tshark -r "{pcap}" -d tcp.port==50051,http2 {extra} -T fields -e http2.length 2>/dev/null'
    out = run(cmd)
    if not out:
        return 0
    return sum(int(x) for line in out.split('\n') for x in line.split(',') if x.strip().isdigit())

def tcp_sum(pcap, extra=""):
    cmd = f'tshark -r "{pcap}" -d tcp.port==50051,http2 {extra} -T fields -e tcp.len 2>/dev/null'
    out = run(cmd)
    if not out:
        return 0
    return sum(int(x) for x in out.split('\n') if x.strip().isdigit())

sizes = [32, 64, 128, 512, 1024, 8192, 65536, 524288]

print(f"{'size':>8} {'wire':>8} {'ALL_h2':>8} {'DATA':>8} {'HDRS':>8} {'SETT':>8} {'WINUP':>8} {'GOAWAY':>8} {'data_client':>12} {'data_server':>12}")
print("-" * 120)

for sz in sizes:
    pcap = os.path.join(PCAP_DIR, f"grpc_{sz}.pcap")
    if not os.path.exists(pcap):
        print(f"{sz:>8} MISSING")
        continue
    
    wire = tcp_sum(pcap)
    all_h2 = tshark_sum(pcap)
    data = tshark_sum(pcap, '-Y "http2.type==0"')
    hdrs = tshark_sum(pcap, '-Y "http2.type==1"')
    sett = tshark_sum(pcap, '-Y "http2.type==4"')
    winup = tshark_sum(pcap, '-Y "http2.type==8"')
    goaway = tshark_sum(pcap, '-Y "http2.type==7"')
    data_cli = tshark_sum(pcap, '-Y "tcp.dstport==50051 and http2.type==0"')
    data_srv = tshark_sum(pcap, '-Y "tcp.srcport==50051 and http2.type==0"')
    
    print(f"{sz:>8} {wire:>8} {all_h2:>8} {data:>8} {hdrs:>8} {sett:>8} {winup:>8} {goaway:>8} {data_cli:>12} {data_srv:>12}")

print()
print("--- REST comparison ---")
print(f"{'size':>8} {'wire':>8} {'body(CL)':>10} {'req_tcp':>10} {'rsp_tcp':>10}")
print("-" * 60)

for sz in sizes:
    pcap = os.path.join(PCAP_DIR, f"rest_{sz}.pcap")
    if not os.path.exists(pcap):
        print(f"{sz:>8} MISSING")
        continue
    
    wire_cmd = f'tshark -r "{pcap}" -T fields -e tcp.len 2>/dev/null'
    wire = sum(int(x) for x in run(wire_cmd).split('\n') if x.strip().isdigit())
    
    cl_cmd = f'tshark -r "{pcap}" -Y "http.content_length" -T fields -e http.content_length 2>/dev/null'
    cl_out = run(cl_cmd)
    body = sum(int(x) for x in cl_out.split('\n') if x.strip().isdigit()) if cl_out else 0
    
    req_cmd = f'tshark -r "{pcap}" -Y "tcp.dstport==8080" -T fields -e tcp.len 2>/dev/null'
    req = sum(int(x) for x in run(req_cmd).split('\n') if x.strip().isdigit())
    
    rsp_cmd = f'tshark -r "{pcap}" -Y "tcp.srcport==8080" -T fields -e tcp.len 2>/dev/null'
    rsp = sum(int(x) for x in run(rsp_cmd).split('\n') if x.strip().isdigit())
    
    print(f"{sz:>8} {wire:>8} {body:>10} {req:>10} {rsp:>10}")
