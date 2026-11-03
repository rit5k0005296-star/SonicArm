from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[1]
def read(name):return json.loads((R/'reports'/name).read_text())
a=read('implementation_acceptance.json');v=read('local_validation.json');p=read('manual_package_audit.json');c=read('rtl_v5_v6_comparison.json')
assert a['pass_'] and p['pass_'] and v['fcm_carry_mutation_rejected']
assert not a['actual_hardware'] and not a['production_signoff']
text=(R/'reports/utilization_routed.rpt').read_text()
usage={}
for label in ('Slice LUTs','Slice Registers','Slice','Block RAM Tile','DSPs'):
    match=re.search(r'^\|\s*'+label+r'\s*\|\s*([\d.]+)\s*\|[^\n]*',text,re.M)
    assert match,label
    cells=[x.strip() for x in match[0].strip('|').split('|')]
    usage[label]=dict(used=float(cells[1]),available=float(cells[4]),percent=float(cells[5]))
m=a['metrics']
head=next(x for x in c['cases'] if x['name']=='synthetic_3')
report=dict(version=6,actual_hardware=False,production_signoff=False,resource=usage,timing=m,
    local_validation_pass=True,manual_package_pass=True,accuracy_matched_claim=False,authentication_threshold=None,
    source_sha256=v['source_sha256'],archive_sha256=p['archive_sha256'],
    primary_board_comparison=['v5','cpu_int8'],cpu_sessions=57,logical_calls=dict(pointwise=55,FCM=12))
(R/'reports/release_summary.json').write_text(json.dumps(report,indent=2))
rows='\n'.join(f"|{k}|{x['used']:g}/{x['available']:g}|{x['percent']:.2f}%|" for k,x in usage.items())
content=f'''# FPGA-6：FCM持续重定量化与行打包

已完成电脑端新设计、验证、综合、实现和匹配手动测试包；尚未上板。
目标PYNQ-Z2 / xc7z020clg400-1，Vivado/Vitis 2025.2，PL 100 MHz。
Overlay仍为最小卷积测试系统，未集成完整音视频及机械臂外设。

## 交付

- `deploy/fpga_v6_manual_tests.zip`：手动测试包。
- `board_package/fpga_v6/01_v6_validation_and_benchmark.ipynb`：逐格运行入口。
- `deploy/cam_v6.bit` / `deploy/cam_v6.hwh`：本次源码重新构建的匹配产物。
- `DESIGN_V6.md`：接口、数值契约、资源预算、实现选择。
- `reports/release_summary.json`：最终状态、资源、时序与指纹。

将zip中的整个fpga_v6目录手动放入现有 `SonicArm/test_1/`，保留旁边
原有的完整 `fpga_v5/` 及test_1。先正确性，再逐层/PL剖析，再关闭详细剖析
做V6、当前V5、优化INT8 CPU同场测速；FP32 CPU可选。包内README给出步骤。
本次没有SSH、加载Overlay、写Samba或其他板端操作。

## 实际硬件修改

保持V5点卷积8×8阵列、57个CPU会话、55+12个逻辑调用和原有量化边界。
FCM用一个持续标量重定量化流水代替每8字节反复排空；预取残差，使用4 KiB
输出tile、4 KiB残差tile和1 KiB行carry，在同一行的时间块之间连续合并64位字。
仅行边界需要读改写，不增加MAC引擎，不改变主机密集字节布局。
INT16中心化、INT32累加、64位乘积、ties-to-even、饱和、LUT/残差保持不变。
CPU子图保持冻结；尚无ORT优化后逐算子实测，未据此贸然新增CAM融合。

## 已执行验证

- 110个真实点卷积、48个真实FCM及245/265/489/529帧首层和残差边界C参考。
- 两个内核HLS综合和C/RTL协同仿真；FCM实际生成3个DATAFLOW进程。
- FCM MAC、重定量化和行写循环II=1。HLS估计不替代最终STA。
- 12个独立AXI用例，检查背压时地址/数据保持、整数输出、保护区、调试关闭及写拍数。
- 1152个片段/保护字节用例；字节掩码和新增行carry的故障注入均被拒绝。
- 被动PL计数器及包装器RTL；当前IP接入和54组总线连线核对。
- 桌面原生C++/ORT完整录音回归，67层当前输入、调试开关、2051帧halo及CMA释放。
- 全新普通Vivado综合/实现、完整约束/CDC/DRC/STA检查、匹配bit/HWH、压缩包审计。

## 本地实现结果

WNS {m['wns_ns']:+.3f} ns，WHS {m['whs_ns']:+.3f} ns，WPWS {m['wpws_ns']:+.3f} ns；
TNS/THS/TPWS均为0。完整路由，零路由错误、零DRC错误。

|资源|使用/总量|占比|
|---|---:|---:|
{rows}

警告、约束检查和报告指纹见 `reports/implementation_acceptance.json`。
保留继承的PS7 DDR DQS参数提示及实际FIFO/BRAM/DSP工具警告，不宣称零警告或产品签核。

同一独立AXI测试台中，489帧Cin=1样例的V5/V6周期比为{head['v5_over_v6_cycles']:.3f}×，
输出端读取拍数 {head['v5']['output_read_beats']}→{head['v6']['output_read_beats']}，
写入拍数 {head['v5']['output_write_beats']}→{head['v6']['output_write_beats']}。
测试台是单未完成突发的字节RAM，不能用该倍率宣称板端DDR或整网提速。
全部12例及限制见 `reports/rtl_v5_v6_comparison.json`。

## 保留状态与复现

V5实测run_4c5e10fec13d43d9a055a4042888adb5的80条正式样本、24次剖析及包指纹
已独立核对，原始文件未修改。V6性能须待用户同板运行后才能确定。
原QDQ严格漂移、相对优化INT8 CPU质量门限失败，accuracy_matched_claim=false，
鉴权阈值未校准；工程正确性不能替代质量验收。

FPGA-1至FPGA-5保持原样；W:仍指向V5，V:独立指向V6。
`experiments/`保留II=2、宽地址乘法和工具Python环境冲突等中间报告，不混作最终证据。
外部Python改用-I隔离；修复记录见reports/python_environment_repair.json，未修改物理设计输入或手工清除Vivado状态。
主要复现脚本为run_native.ps1、run_hls.ps1、run_local_checks.ps1、
run_rtl_comparison.ps1、run_vivado.ps1和verify_local_evidence.py。
已有工程不能再次执行create；重建应使用新的隔离目录或明确保留旧证据后进行。
'''
(R/'README.md').write_text(content,encoding='utf8')
print('V6_RELEASE_REPORT_WRITTEN',usage)
