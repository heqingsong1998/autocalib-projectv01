"""
六轴力传感器调试程序
重构版本 - 使用模块化驱动
"""
import os
import sys
import yaml
import time

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.sensors.utils import create_sensor, initialize_sensor


def load_config():
    """加载配置文件"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 
        "config", 
        "default.yaml"
    )
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    """主函数"""
    print("=== 六轴力传感器调试程序 ===")
    
    # Windows键盘支持
    try:
        import msvcrt
        has_kbd = True
    except ImportError:
        msvcrt = None
        has_kbd = False
        print("⚠️ 不支持键盘输入（非Windows系统）")
    
    try:
        # 加载配置
        config = load_config()
        sensor_config = config["sensor"]["m8128b1"]
        
        # 创建传感器对象
        sensor = create_sensor(sensor_config["type"], sensor_config)
        
        # 初始化传感器
        if not initialize_sensor(sensor):
            print("❌ 传感器初始化失败")
            return
        
        # 开始数据流
        if not sensor.start_stream():
            print("❌ 启动数据流失败")
            return
        
        print("运行中... 按 Z 清零，按 Q 退出")
        
        while True:
            # 处理键盘输入
            if has_kbd and msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch:
                    c = ch.decode(errors="ignore").lower()
                    if c == 'z':
                        print("\n=== 执行清零操作 ===")
                        sensor.zero_channels()
                        print("=== 清零操作完成 ===\n")
                    elif c == 'q':
                        print("退出程序")
                        break
            
            # 读取并显示数据
            data_list = sensor.read_data()
            for pkg_no, groups in data_list:
                for idx, (Fx, Fy, Fz, Mx, My, Mz) in enumerate(groups):
                    print(f"#{pkg_no:05d}[{idx}] "
                          f"Fx={Fx:8.4f} Fy={Fy:8.4f} Fz={Fz:8.4f}  "
                          f"Mx={Mx:8.4f} My={My:8.4f} Mz={Mz:8.4f}")
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    
    except Exception as e:
        print(f"❌ 程序运行失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            sensor.disconnect()
        except:
            pass


if __name__ == "__main__":
    main()