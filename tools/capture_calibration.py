import argparse
import csv
import re
import struct
import threading
import time
import os
from datetime import datetime
from pathlib import Path

import can


CAN_ID_HOST_COMMAND = 0x061
CAN_ID_CAL0 = 0x053
CAN_ID_CAL1 = 0x054
ADC_SUM_MAX = 4095 * 4

RAW_FIELDS = [
    "raw_iA",
    "raw_iR",
    "raw_vA",
    "raw_iB",
    "raw_vB",
    "raw_iWPT",
    "raw_vWPT",
]


def build_keepalive_frame() -> bytes:
    byte0 = 1  # enableDCDC=1
    referee_power_limit = 37
    referee_energy_buffer = 57
    active_charging_limit_ratio = 255
    data = struct.pack(
        "<BHHB",
        byte0,
        referee_power_limit,
        referee_energy_buffer,
        active_charging_limit_ratio,
    )
    return data + b"\x00\x00"


def parse_step_to_requirement(step: str) -> str:
    m_av = re.fullmatch(r"A([+-]?\d+(?:\.\d+)?)V", step, re.IGNORECASE)
    m_aa = re.fullmatch(r"A([+-]?\d+(?:\.\d+)?)A", step, re.IGNORECASE)
    m_b_no_v = re.fullmatch(r"B([+-]?\d+(?:\.\d+)?)A", step, re.IGNORECASE)
    m_b = re.fullmatch(r"B([+-]?\d+(?:\.\d+)?)A(\d+(?:\.\d+)?)V", step, re.IGNORECASE)

    if m_av:
        v = float(m_av.group(1))
        return f"CHASSIS 口供电 {v:g}V，其他口空载"
    if m_aa:
        i = float(m_aa.group(1))
        return f"CHASSIS 口供电 24V，REF 口恒流负载 {i:g}A（负值表示反向）"
    if m_b_no_v:
        i = float(m_b_no_v.group(1))
        return (
            f"CHASSIS 口供电 24V，CAP 口恒流负载 {i:g}A。"
            "该模式下 CAP 电压不稳，采样后按万用表实测值录入"
        )
    if m_b:
        i = float(m_b.group(1))
        v = float(m_b.group(2))
        return f"CHASSIS 口供电 24V，CAP 口恒流负载 {i:g}A（负值表示反向），并稳定在 {v:g}V"
    raise ValueError(
        "step 格式错误，示例: A24V, A-1.5A, B2A, B2A18.5V"
    )


def resolve_output_step(step: str, measured_cap_v: float = None) -> str:
    m_b_no_v = re.fullmatch(r"B([+-]?\d+(?:\.\d+)?)A", step, re.IGNORECASE)
    if not m_b_no_v:
        return step

    if measured_cap_v is not None:
        current = float(m_b_no_v.group(1))
        return f"B{current:g}A{measured_cap_v:g}V"

    while True:
        measured = input("  请输入万用表实测 CAP 电压(V): ").strip()
        try:
            measured_v = float(measured)
        except ValueError:
            print("  电压格式错误，请输入数字，例如 18.53")
            continue
        if measured_v <= 0.0:
            print("  电压应大于 0V，请重新输入")
            continue

        current = float(m_b_no_v.group(1))
        return f"B{current:g}A{measured_v:g}V"


def prompt_capture_start(step: str):
    """Return (should_quit, measured_cap_v_or_none)."""
    is_b_no_v = re.fullmatch(r"B([+-]?\d+(?:\.\d+)?)A", step, re.IGNORECASE) is not None

    while True:
        if is_b_no_v:
            prompt = "  配置完成后按回车开始采样；也可直接输入CAP电压(V)后回车 (q 退出): "
        else:
            prompt = "  配置完成后按回车开始采样 (q 退出): "

        choice = input(prompt).strip()
        lower = choice.lower()
        if lower == "q":
            return True, None

        if not is_b_no_v or choice == "":
            return False, None

        try:
            measured_v = float(choice)
        except ValueError:
            print("  输入格式错误：回车直接采样，或输入数字电压，例如 18.53")
            continue

        if measured_v <= 0.0:
            print("  电压应大于 0V，请重新输入")
            continue

        return False, measured_v


class CalibrationCapture:
    def __init__(self, port: str, baudrate: int, can_bitrate: int):
        self.bus = can.interface.Bus(
            interface="slcan",
            channel=port,
            ttyBaudrate=baudrate,
            bitrate=can_bitrate,
        )
        self.running = True
        self.keepalive_data = build_keepalive_frame()
        self.lock = threading.Lock()
        self.last_cal0 = None
        self.last_cal1 = None
        self.cal0_count = 0
        self.cal1_count = 0

    def start(self) -> None:
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.tx_thread = threading.Thread(target=self._tx_keepalive_loop, daemon=True)
        self.rx_thread.start()
        self.tx_thread.start()

    def stop(self) -> None:
        self.running = False
        self.rx_thread.join(timeout=1.0)
        self.tx_thread.join(timeout=1.0)
        self.bus.shutdown()

    def _rx_loop(self) -> None:
        while self.running:
            msg = self.bus.recv(timeout=0.2)
            if msg is None:
                continue
            if msg.arbitration_id == CAN_ID_CAL0 and msg.dlc == 8:
                vals = struct.unpack("<4H", msg.data)
                with self.lock:
                    self.last_cal0 = (time.time(), vals)
                    self.cal0_count += 1
            elif msg.arbitration_id == CAN_ID_CAL1 and msg.dlc == 8:
                vals = struct.unpack("<4H", msg.data)
                with self.lock:
                    self.last_cal1 = (time.time(), vals)
                    self.cal1_count += 1

    def _tx_keepalive_loop(self) -> None:
        while self.running:
            try:
                msg = can.Message(
                    arbitration_id=CAN_ID_HOST_COMMAND,
                    data=self.keepalive_data,
                    is_extended_id=False,
                    dlc=8,
                )
                self.bus.send(msg)
            except can.CanError:
                pass
            time.sleep(0.1)

    def get_one_sample(
        self,
        pair_timeout_s: float = 0.15,
        max_age_s: float = 0.25,
        min_timestamp: float = None,
    ):
        with self.lock:
            cal0 = self.last_cal0
            cal1 = self.last_cal1

        if cal0 is None or cal1 is None:
            return None

        now = time.time()
        t0, a = cal0
        t1, b = cal1
        if abs(t0 - t1) > pair_timeout_s:
            return None
        if max_age_s is not None and (now - t0 > max_age_s or now - t1 > max_age_s):
            return None
        if min_timestamp is not None and (t0 < min_timestamp or t1 < min_timestamp):
            return None

        signature = (t0, t1)
        sample = [a[0], a[1], a[2], a[3], b[0], b[1], b[2]]
        return signature, sample

    def capture_samples(self, n_samples: int, warmup_s: float, timeout_s: float):
        start_t = time.time()
        warmup_end = start_t + warmup_s
        seen_signatures = set()

        while time.time() < warmup_end:
            result = self.get_one_sample(min_timestamp=start_t)
            if result is not None:
                signature, _ = result
                seen_signatures.add(signature)
            time.sleep(0.005)

        rows = []
        deadline = time.time() + timeout_s
        while len(rows) < n_samples and time.time() < deadline:
            result = self.get_one_sample(min_timestamp=start_t)
            if result is not None:
                signature, sample = result
                if signature in seen_signatures:
                    time.sleep(0.002)
                    continue
                seen_signatures.add(signature)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                rows.append([now] + sample)
            time.sleep(0.002)

        return rows

    def probe_calibration_stream(self, duration_s: float = 2.0):
        start = time.time()
        with self.lock:
            cal0_start = self.cal0_count
            cal1_start = self.cal1_count

        pair_count = 0
        seen_signatures = set()
        while time.time() - start < duration_s:
            result = self.get_one_sample(min_timestamp=start)
            if result is not None:
                signature, _ = result
                if signature in seen_signatures:
                    time.sleep(0.01)
                    continue
                seen_signatures.add(signature)
                pair_count += 1
            time.sleep(0.01)

        with self.lock:
            cal0_delta = self.cal0_count - cal0_start
            cal1_delta = self.cal1_count - cal1_start

        return {
            "duration_s": duration_s,
            "cal0_frames": cal0_delta,
            "cal1_frames": cal1_delta,
            "pair_samples": pair_count,
        }


def save_rows(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp"] + RAW_FIELDS)
        writer.writerows(rows)


def summarize(rows):
    sums = [0.0] * 7
    for r in rows:
        for i in range(7):
            sums[i] += float(r[i + 1])
    means = [s / len(rows) for s in sums]
    return means


def detect_obvious_anomalies(rows):
    warnings = []
    if not rows:
        return warnings

    channel_values = {name: [] for name in RAW_FIELDS}
    for r in rows:
        for i, name in enumerate(RAW_FIELDS):
            channel_values[name].append(float(r[i + 1]))

    for name in RAW_FIELDS:
        values = channel_values[name]
        if not values:
            continue

        v_min = min(values)
        v_max = max(values)
        v_mean = sum(values) / len(values)
        v_range = v_max - v_min

        if v_max >= ADC_SUM_MAX - 8:
            warnings.append(f"{name}: 出现接近满量程值 ({v_max:.1f}/{ADC_SUM_MAX})")
        if v_min <= 8:
            warnings.append(f"{name}: 出现接近0值 ({v_min:.1f})")
        if v_mean >= ADC_SUM_MAX - 160 or v_mean <= 160:
            warnings.append(f"{name}: 均值接近量程边缘 (mean={v_mean:.1f})")
        if v_range >= 5000:
            warnings.append(f"{name}: 波动过大 (range={v_range:.1f})，可能接触不稳或工况未稳定")

    return warnings


def parse_steps(steps_arg: str):
    if not steps_arg:
        return [
            "A5V",
            "A10V",
            "A15V",
            "A20V",
            "A24V",
            "A-2A",
            "A-1A",
            "A0A",
            "A1A",
            "A2A",
            "B0A",
            "B1A",
            "B2A",
        ]
    return [s.strip() for s in steps_arg.split(",") if s.strip()]


def main():
    parser = argparse.ArgumentParser(description="Interactive calibration capture over CAN.")
    parser.add_argument("port", help="slcan serial port, e.g. COM3")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument(
        "--can-bitrate",
        type=int,
        default=1000000,
        help="CAN bitrate for slcan adapter (default: 1000000)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(Path(__file__).resolve().parents[1] / "debug" / "calibration"),
        help="output directory for captured csv files",
    )
    parser.add_argument("--samples", type=int, default=180, help="samples per step")
    parser.add_argument("--warmup", type=float, default=0.8, help="warmup seconds before sampling")
    parser.add_argument("--timeout", type=float, default=8.0, help="timeout seconds per step")
    parser.add_argument(
        "--steps",
        default="",
        help="comma-separated step list, e.g. A24V,A-1A,B2A18V",
    )
    args = parser.parse_args()

    steps = parse_steps(args.steps)
    if not steps:
        raise SystemExit("No steps configured")

    out_dir = Path(args.out_dir)

    capture = CalibrationCapture(args.port, args.baudrate, args.can_bitrate)
    capture.start()

    print("连接成功。正在监听 CAN ID 0x053/0x054 的校准数据。")
    print(f"slcan 串口波特率: {args.baudrate}, CAN 波特率: {args.can_bitrate}")

    print("每个步骤配置稳定后按回车开始采样，输入 'q' 退出。")
    
    if os.path.exists(out_dir):
        print("[WARN] 输出文件夹已存在，注意清理以前的文件")

    try:
        print("\n[测试步骤] 正在进行校准数据链路检测（2秒）...")
        probe = capture.probe_calibration_stream(2.0)
        print(
            "  检测结果: "
            f"0x053={probe['cal0_frames']} 帧, "
            f"0x054={probe['cal1_frames']} 帧, "
            f"成对样本={probe['pair_samples']}"
        )
        if probe["cal0_frames"] == 0 or probe["cal1_frames"] == 0:
            print("  [WARN] 未检测到完整校准数据流，请检查固件 CALIBRATION_MODE 或 CAN 参数")
        elif probe["pair_samples"] < 5:
            print("  [WARN] 成对样本较少，可能链路不稳定")
        else:
            print("  [OK] 校准数据流正常")

        for idx, step in enumerate(steps, start=1):
            requirement = parse_step_to_requirement(step)
            print(f"\n[{idx}/{len(steps)}] {step}")
            print(f"  要求: {requirement}")
            should_quit, measured_cap_v = prompt_capture_start(step)
            if should_quit:
                break

            rows = capture.capture_samples(args.samples, args.warmup, args.timeout)
            if not rows:
                print("  采样失败: 未收到有效成对校准帧，请检查 CAN 连接和固件 CALIBRATION_MODE")
                continue

            step_for_file = resolve_output_step(step, measured_cap_v)
            out_file = out_dir / f"{step_for_file}.csv"
            save_rows(out_file, rows)

            means = summarize(rows)
            mean_text = ", ".join(f"{name}={means[i]:.1f}" for i, name in enumerate(RAW_FIELDS))
            print(f"  已保存 {len(rows)} 条 -> {out_file}")
            print(f"  均值: {mean_text}")

            warnings = detect_obvious_anomalies(rows)
            for warning in warnings:
                print(f"  [WARN] {warning}")

    finally:
        capture.stop()


if __name__ == "__main__":
    main()
