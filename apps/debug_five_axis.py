"""
五轴USB-CAN传感器简化调试程序
"""
import os
import sys
import yaml
import time

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from drivers.wuzhou.utils import create_sensor, initialize_sensor, display_sensor_data


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
    print("=== 五轴传感器简化调试程序 ===")
    
    # Windows键盘支持
    try:
        import msvcrt
        has_kbd = True
        print("运行中... 按 Z 清零，按 Q 退出\n")
    except ImportError:
        msvcrt = None
        has_kbd = False
        print("⚠️ 不支持键盘输入（非Windows系统）\n")
    
    sensor = None
    
    try:
        # 加载配置并创建传感器
        config = load_config()
        sensor_config = config["sensor"]["wuzhou_five_axis"]
        sensor = create_sensor("wuzhou_five_axis", sensor_config)
        
        # 初始化传感器
        if not initialize_sensor(sensor):
            print("❌ 传感器初始化失败")
            return
        
        # 开始数据流
        if not sensor.start_stream():
            print("❌ 启动数据流失败")
            return
        
        print("✅ 开始显示数据...\n")
        
        frame_counter = 0
        while True:
            # 处理键盘输入
            if has_kbd and msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch:
                    c = ch.decode(errors="ignore").lower()
                    if c == 'z':
                        print("\n=== 清零传感器 ===")
                        sensor.zero_channels()
                        print("=== 清零完成 ===\n")
                    elif c == 'q':
                        print("\n退出程序")
                        break
            
            # 读取并显示数据
            data_list = sensor.read_data()
            for frame_no, groups in data_list:
                for idx, data_tuple in enumerate(groups):
                    display_sensor_data(frame_counter, data_tuple)
                    frame_counter += 1
            
            time.sleep(0.01)  # 防止CPU占用过高
    
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    
    except Exception as e:
        print(f"❌ 程序运行失败: {e}")
    
    finally:
        if sensor:
            try:
                sensor.stop_stream()
                sensor.disconnect()
                print("传感器连接已关闭")
            except:
                pass


if __name__ == "__main__":
    main()