import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
TEMP_ROOT=ROOT/"tests"
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
overlay=load("overlay",ROOT/"pynq-overlay-audit/scripts/overlay_audit.py")
overlay_session=load("overlay_session",ROOT/"pynq-overlay-audit/scripts/overlay_session.py")
driver=load("driver",ROOT/"pynq-ip-driver/scripts/generate_driver.py")
data=load("data",ROOT/"pynq-data-path/scripts/data_path_check.py")
dma_transfer=load("dma_transfer",ROOT/"pynq-data-path/scripts/dma_transfer.py")
validation=load("validation",ROOT/"pynq-validation/scripts/validate_evidence.py")
report=load("report",ROOT/"pynq-validation/scripts/collect_report.py")
class Suite(unittest.TestCase):
    def test_missing_hwh(self): self.assertEqual(overlay.audit("missing.hwh")["status"],"FAIL")
    def test_bad_xml(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            p=Path(d)/"x.hwh"; p.write_text("<bad>"); self.assertEqual(overlay.audit(p)["status"],"FAIL")
    def test_hwh_without_manifest(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            h=Path(d)/"x.hwh"; b=Path(d)/"x.bit"; h.write_text("<ROOT><MEMRANGE INSTANCE='ip0' BASEVALUE='0x40000000' HIGHVALUE='0x40000fff'/></ROOT>"); b.write_bytes(b"bit")
            r=overlay.audit(h,b); self.assertEqual(r["status"],"PASS"); self.assertEqual(r["evidence"]["identity"],"NO_MANIFEST")
    def test_overlap_and_hash_mismatch(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            d=Path(d); h=d/"x.hwh"; b=d/"x.bit"; m=d/"manifest.json"
            h.write_text("<ROOT><M INSTANCE='a' BASEVALUE='0x1000' HIGHVALUE='0x1fff'/><M INSTANCE='b' BASEVALUE='0x1800' HIGHVALUE='0x2fff'/></ROOT>"); b.write_bytes(b"bit")
            m.write_text(json.dumps({"hwh":{"sha256":"bad"},"bit":{"sha256":"bad"}}))
            r=overlay.audit(h,b,m); self.assertEqual(r["status"],"FAIL"); self.assertTrue(any("ADDRESS_OVERLAP" in x for x in r["issues"])); self.assertTrue(any("HASH_MISMATCH" in x for x in r["issues"]))
    def test_driver_contract(self):
        c=json.loads((ROOT/"pynq-ip-driver/examples/add_ip_contract.json").read_text()); code,errors=driver.generate(c,"case"); self.assertFalse(errors); compile(code,"generated.py","exec")
    def test_unknown_register(self):
        c={"name":"x","base_address":0,"address_range":4096,"registers":[{"name":"bad-name","offset":0,"width":32,"access":"rw"}]}; self.assertTrue(driver.validate(c))
    def test_data_paths(self):
        self.assertEqual(data.check({"kind":"hls_m_axi","length_bytes":64,"alignment_bytes":64,"cache_policy":"n/a"})["status"],"PASS")
        self.assertEqual(data.check({"kind":"axi_dma","length_bytes":63,"alignment_bytes":64,"cache_policy":"x"})["status"],"FAIL")
        self.assertIn("TRANSFER_TIMEOUT",data.check({"kind":"axi_dma","length_bytes":64,"alignment_bytes":64,"cache_policy":"x"},True)["issues"])
    def test_golden(self):
        self.assertTrue(validation.golden([1,2],[1,2],1e-6,1e-5)[0]); self.assertFalse(validation.golden([1],[1,2],1e-6,1e-5)[0])
    def test_overlay_session(self):
        class IP: register_map={"CTRL":0}
        class FakeOverlay:
            def __init__(self,path,download=False): self.ip_dict={"core":{"phys_addr":0x40000000}}; self.core=IP(); self.download=download
        s=overlay_session.OverlaySession("design.bit",["core"],FakeOverlay)
        self.assertEqual(s.open(download=True).download,True)
        self.assertIn("CTRL",s.register_map("core"))
    def test_overlay_missing_ip(self):
        class FakeOverlay:
            def __init__(self,path,download=False): self.ip_dict={}
        with self.assertRaises(overlay_session.OverlayVerificationError):
            overlay_session.OverlaySession("x.bit",["missing"],FakeOverlay).open()
    def test_dma_exchange_and_cache(self):
        class Buffer:
            nbytes=64; device_address=0x1000; coherent=False
            def __init__(self): self.events=[]
            def flush(self): self.events.append("flush")
            def invalidate(self): self.events.append("invalidate")
        class Channel:
            idle=True
            def __init__(self): self.calls=[]
            def transfer(self,b,nbytes=0): self.calls.append(nbytes)
        class DMA:
            sendchannel=Channel(); recvchannel=Channel()
        tx,rx=Buffer(),Buffer(); result=dma_transfer.DmaTransfer(DMA(),alignment=64).exchange(tx,rx)
        self.assertEqual(result["bytes"],64); self.assertEqual(tx.events,["flush"]); self.assertEqual(rx.events,["invalidate"])
    def test_dma_alignment_failure(self):
        class Buffer: nbytes=64; device_address=3; coherent=True
        class Channel:
            idle=True
            def transfer(self,b,nbytes=0): pass
        class DMA: sendchannel=Channel(); recvchannel=Channel()
        with self.assertRaises(dma_transfer.DmaTransferError): dma_transfer.DmaTransfer(DMA(),alignment=4).exchange(Buffer(),Buffer())
    def test_report_collection(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as d:
            d=Path(d); timing=d/"timing.rpt"; util=d/"util.rpt"; bench=d/"bench.json"
            timing.write_text("WNS(ns) TNS(ns)\n 0.123 -0.000\n")
            util.write_text("| Slice LUTs | 100 | 53200 |\n| Slice Registers | 200 | 106400 |\n| Block RAM Tile | 2 | 140 |\n| DSPs | 3 | 220 |\n")
            bench.write_text(json.dumps({"latency_ms":[1,2,3,4]}))
            result=report.collect(timing,util,bench)
            self.assertEqual(result["status"],"PASS"); self.assertEqual(result["artifacts"]["benchmark"]["median_ms"],2.5)
            self.assertEqual(result["artifacts"]["utilization"]["dsp"]["used"],3.0)
if __name__=="__main__": unittest.main()
