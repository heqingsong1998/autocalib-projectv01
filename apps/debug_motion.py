import os, sys, yaml, time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.motioncard.ltsmc_dll import LTSMCMotionCard
from drivers.motioncard.utils import (
    full_axis_initialization,
    move_relative,
    move_absolute,
    test_limit_switches,
    relative_motion_cam,
    check_and_home,
    cam_home_mode,
    initialize_motion_control,
    absolute_motion_cam
)

def load_cfg():
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "default.yaml"), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    print("=== 完整轴初始化功能测试 ===")
    
    try:
        cfg = load_cfg()
        card = LTSMCMotionCard(cfg["motioncard"])
        
  
        # 初始化 2 轴
        if full_axis_initialization(card, axis=2):
            print("✅ 0 轴初始化成功")
        else:
            print("❌ 0 轴初始化失败，无法进行电子凸轮测试")
            return
        #对2进行回零 
        print("\n执行回零")
        if not check_and_home(card, axis=2):
            print("❌ 回零失败")
            return False

        time.sleep(0.1)

        # 初始化 0 轴
        if full_axis_initialization(card, axis=0):
            print("✅ 0 轴初始化成功")
        else:
            print("❌ 0 轴初始化失败，无法进行电子凸轮测试")
            return
        
        # 初始化 1 轴
        if full_axis_initialization(card, axis=1):
            print("✅ 1 轴初始化成功")
        else:
            print("❌ 1 轴初始化失败，无法进行电子凸轮测试")
            return
        
        #测试电子凸轮回原点模式
        if cam_home_mode(card,0,1):
            print("🎉 电子凸轮回原点模式测试成功")
        else:
            print("❌ 电子凸轮回原点模式测试失败")
        time.sleep(0.1)
        #测试电子凸轮相对运动模式
        if relative_motion_cam(card,0,1,50.0,5.0,1):
            print("🎉 电子凸轮相对运动模式测试成功")
        else:
            print("❌ 电子凸轮相对运动模式测试失败")
        #测试电子凸轮相对运动模式
        time.sleep(0.1)
        if relative_motion_cam(card,0,1,20.0,5.0,0):
            print("🎉 电子凸轮相对运动模式测试成功")
        else:
            print("❌ 电子凸轮相对运动模式测试失败")
        #测试电子凸轮绝对运动模式
        time.sleep(0.1)
        if absolute_motion_cam(card,0,1,35.0,5.0):
            print("🎉 电子凸轮绝对运动模式测试成功")
        else:
            print("❌ 电子凸轮绝对运动模式测试失败")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        try:
            card.disconnect()
            print("控制卡已断开连接")
        except:
            pass

if __name__ == "__main__":
    main()

