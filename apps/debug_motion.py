import os
import sys
import time
import yaml

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.motioncard.ltsmc_dll import LTSMCMotionCard
from drivers.motioncard.utils import full_axis_initialization, perform_homing


CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml")


def load_cfg():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_axis_unit(axis: int) -> str:
    return "°" if axis in (0, 1) else "mm"


def get_axis_test_distance(axis: int) -> float:
    return 1.0 if axis in (0, 1) else 2.0


def safe_stop(card: LTSMCMotionCard, axis: int):
    try:
        card.stop(axis, mode=1)
    except Exception:
        pass


def wait_axis_done(card: LTSMCMotionCard, axis: int, timeout: float = 20.0, poll: float = 0.05) -> bool:
    """
    等待单轴运动完成。
    仅把报警/急停/正负限位作为异常，ORG 不作为异常终止条件。
    """
    start = time.time()
    while time.time() - start < timeout:
        io_status = card.read_axis_io(axis)

        if io_status.get("alm"):
            safe_stop(card, axis)
            raise RuntimeError(f"轴 {axis} 触发伺服报警 ALM")

        if io_status.get("emg"):
            safe_stop(card, axis)
            raise RuntimeError(f"轴 {axis} 触发急停 EMG")

        if io_status.get("pel"):
            safe_stop(card, axis)
            raise RuntimeError(f"轴 {axis} 触发正限位 PEL")

        if io_status.get("nel"):
            safe_stop(card, axis)
            raise RuntimeError(f"轴 {axis} 触发负限位 NEL")

        if card.is_done(axis):
            return True

        time.sleep(poll)

    safe_stop(card, axis)
    return False


def move_abs_checked(card: LTSMCMotionCard, axis: int, target: float, timeout: float = 20.0) -> bool:
    unit = get_axis_unit(axis)
    print(f"  -> 轴 {axis} 绝对运动到 {target:+.3f}{unit}")
    card.move_abs(axis, target)
    ok = wait_axis_done(card, axis, timeout=timeout)
    pos = card.get_position(axis)
    if ok:
        print(f"  ✅ 轴 {axis} 到位，当前位置: {pos:+.3f}{unit}")
        return True

    print(f"  ❌ 轴 {axis} 运动超时，当前位置: {pos:+.3f}{unit}")
    return False


def home_all_axes(card: LTSMCMotionCard, axes: list[int]) -> bool:
    print("=== 第一步：依次初始化并回原点 ===")
    for axis in axes:
        print(f"\n--- 轴 {axis} 初始化 ---")
        if not full_axis_initialization(card, axis=axis):
            print(f"❌ 轴 {axis} 初始化失败")
            return False

        print(f"--- 轴 {axis} 回原点 ---")
        if not perform_homing(card, axis=axis, timeout=60.0):
            print(f"❌ 轴 {axis} 回原点失败")
            return False

        pos = card.get_position(axis)
        print(f"✅ 轴 {axis} 回原点完成，当前位置: {pos:+.3f}{get_axis_unit(axis)}")
        time.sleep(0.2)

    print("\n🎉 四个轴已全部完成回原点")
    return True


def test_axis_bidirectional(card: LTSMCMotionCard, axis: int) -> bool:
    distance = get_axis_test_distance(axis)
    unit = get_axis_unit(axis)

    print(f"\n=== 第二步：测试轴 {axis} 正负行程（{distance}{unit}）===")
    print(f"测试顺序：0 -> +{distance}{unit} -> 0 -> -{distance}{unit} -> 0")

    try:
        steps = [distance, 0.0, -distance, 0.0]
        for target in steps:
            if not move_abs_checked(card, axis, target, timeout=30.0):
                return False
            time.sleep(0.2)

        print(f"🎉 轴 {axis} 正负行程测试通过")
        return True

    except Exception as e:
        print(f"❌ 轴 {axis} 正负行程测试失败: {e}")
        safe_stop(card, axis)
        return False


def main():
    print("=== 四轴顺序回原点 + 正负步进测试 ===")

    card = None
    try:
        cfg = load_cfg()
        card = LTSMCMotionCard(cfg["motioncard"])

        axes = [0, 1, 2, 3]
        if not home_all_axes(card, axes):
            return

        print("\n=== 第三步：依次测试四个轴 ===")
        for axis in axes:
            if not test_axis_bidirectional(card, axis):
                print(f"\n❌ 测试在轴 {axis} 处中止")
                return

        print("\n🎉 全部测试完成：")
        print("   - 0 轴：+1° / -1° 测试完成")
        print("   - 1 轴：+1° / -1° 测试完成")
        print("   - 2 轴：+2 mm / -2 mm 测试完成")
        print("   - 3 轴：+2 mm / -2 mm 测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        if card is not None:
            try:
                card.disconnect()
                print("控制卡已断开连接")
            except Exception:
                pass


if __name__ == "__main__":
    main()
