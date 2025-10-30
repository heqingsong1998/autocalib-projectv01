import yaml
import os
import time
from typing import Dict, Any
from .base import MotionCard

def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "default.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def initialize_motion_control(card: MotionCard, axis: int) -> bool:
    """
    简化版运动控制初始化
    
    Args:
        card: 控制卡对象
        axis: 轴号
        
    Returns:
        True: 初始化成功, False: 初始化失败
    """
    print(f"=== 轴 {axis} 运动控制初始化 ===")
    
    try:
        # 加载配置
        cfg = load_config()
        axis_cfg = cfg["axes"][f"axis_{axis}"]
        
        # 检查是否已连接
        if not hasattr(card, "connected") or not card.connected:
            print("1. 连接运动控制卡...")
            ret = card.connect()
            print(f"连接返回值: {ret}")
            if ret == 0:
                print("✅ 运动控制卡连接成功")
                card.connected = True  # 标记为已连接
            else:
                print("❌ 运动控制卡连接失败")
                return False
        else:
            print("✅ 控制卡已连接，跳过连接操作")
        
        # 2. 设置脉冲模式
        print("2. 设置脉冲模式...")
        pulse_mode = axis_cfg["pulse_mode"]
        card.set_pulse_mode(axis, pulse_mode)
        print(f"✅ 脉冲模式设置完成: {pulse_mode}")
        
        # 3. 设置脉冲当量
        print("3. 设置脉冲当量...")
        equiv = axis_cfg["equiv"]
        card.set_equiv(axis, equiv)
        print(f"✅ 脉冲当量设置完成: {equiv} 脉冲/mm")
        
        # 4. 设置速度曲线
        print("4. 设置速度曲线...")
        profile = axis_cfg["profile"]
        card.set_profile(axis, 
                        profile["vmin"], 
                        profile["vmax"], 
                        profile["acc"], 
                        profile["dec"], 
                        profile["s_time"])
        print(f"✅ 速度曲线设置完成:")
        print(f"   起始速度: {profile['vmin']} mm/s")
        print(f"   最大速度: {profile['vmax']} mm/s")
        print(f"   加速度: {profile['acc']} mm/s²")
        print(f"   减速度: {profile['dec']} mm/s²")
        print(f"   S曲线时间: {profile['s_time']} s")
        
        print("🎉 运动控制初始化完成")
        return True
        
    except KeyError as e:
        print(f"❌ 配置文件缺少参数: {e}")
        return False
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return False


def setup_homing(card: MotionCard, axis: int) -> bool:
    """
    设置回原点逻辑
    
    Args:
        card: 控制卡对象
        axis: 轴号
        
    Returns:
        True: 设置成功, False: 设置失败
    """
    print(f"=== 轴 {axis} 回原点设置 ===")
    
    try:
        # 加载配置
        cfg = load_config()
        homing_cfg = cfg["axes"][f"axis_{axis}"]["homing"]
        
        # 1. 设置原点逻辑电平
        print("1. 设置原点逻辑电平...")
        org_logic = homing_cfg["org_logic"]
        filter_time = homing_cfg["filter_time"]
        card.set_home_logic(axis, org_logic, filter_time)
        print(f"✅ 原点逻辑设置完成: {org_logic} (滤波时间: {filter_time}ms)")
        
        # 2. 设置正极限逻辑电平
        print("2. 设置正极限逻辑电平...")
        pel_logic = homing_cfg["pel_logic"]
        pel_enable = homing_cfg["pel_enable"]
        card.set_el_mode(axis, pel_enable, pel_logic, 1)
        print(f"✅ 正极限设置完成: 使能={pel_enable}, 逻辑={pel_logic}")
        
        # 3. 设置回原点模式
        print("3. 设置回原点模式...")
        home_mode = homing_cfg["home_mode"]
        card.set_home_mode(axis,
                          home_mode["home_dir"],
                          home_mode["vel_mode"], 
                          home_mode["mode"],
                          home_mode["source"])
        print(f"✅ 回原点模式设置完成: 方向={home_mode['home_dir']}, 模式={home_mode['mode']}")
        
        # 4. 设置回原点速度参数
        print("4. 设置回原点速度参数...")
        home_profile = homing_cfg["home_profile"]
        card.set_home_profile(axis, 
                            home_profile["low_vel"],
                            home_profile["high_vel"], 
                            home_profile["acc_time"],
                            home_profile["dec_time"])
        print(f"✅ 回原点速度参数设置完成")
        
        print("🎉 回原点设置完成")
        return True
        
    except KeyError as e:
        print(f"❌ 回原点配置缺少参数: {e}")
        return False
    except Exception as e:
        print(f"❌ 回原点设置失败: {e}")
        return False
    
def check_and_home(card: MotionCard, axis: int) -> bool:
    """
    检查并执行回原点
    
    Args:
        card: 控制卡对象
        axis: 轴号
        
    Returns:
        True: 在原点或回原点成功, False: 回原点失败
    """
    print(f"=== 轴 {axis} 原点检查 ===")
    
    try:
        # 检查当前是否在原点
        io_status = card.read_axis_io(axis)
        position = card.get_position(axis)
        
        print(f"当前位置: {position:.3f} mm")
        print(f"原点状态: {'在原点' if io_status['org'] else '不在原点'}")
        
        if io_status['org']:
            print("✅ 已在原点位置")
            card.set_position(axis, 0.0)  # 清零位置寄存器
            return True
        else:
            print("⚠️ 不在原点位置")
            choice = input("是否执行回原点功能？(y/n): ").strip().lower()
            
            if choice == 'y':
                return perform_homing(card, axis)
            else:
                print("跳过回原点")
                return True
                
    except Exception as e:
        print(f"❌ 原点检查失败: {e}")
        return False

def perform_homing(card: MotionCard, axis: int, timeout: float = 30.0) -> bool:
    """
    执行回原点操作
    
    Args:
        card: 控制卡对象
        axis: 轴号
        timeout: 超时时间(秒)
        
    Returns:
        True: 回原点成功, False: 回原点失败
    """
    print(f"开始轴 {axis} 回原点...")
    
    try:
        card.home(axis)
        
        # 等待回原点完成
        start_time = time.time()
        while time.time() - start_time < timeout:
            if card.is_home_done(axis):
                pos = card.get_position(axis)
                print(f"✅ 回原点完成，位置: {pos:.3f} mm")
                
                # 清零位置寄存器
                card.set_position(axis, 0.0)
                final_pos = card.get_position(axis)
                print(f"📍 位置寄存器清零: {final_pos:.3f} mm")
                return True
            
            time.sleep(0.1)
        
        # 超时处理
        print("❌ 回原点超时")
        card.stop(axis, mode=1)
        return False
        
    except Exception as e:
        print(f"❌ 回原点失败: {e}")
        return False

def full_axis_initialization(card: MotionCard, axis: int) -> bool:
    """
    完整轴初始化（按照您的3步逻辑）
    
    Args:
        card: 控制卡对象
        axis: 轴号
        
    Returns:
        True: 全部初始化成功, False: 初始化失败
    """
    print(f"=== 轴 {axis} 完整初始化流程 ===")
    
    # 1. 先初始化运动控制卡
    print("步骤1: 初始化运动控制卡")
    if not initialize_motion_control(card, axis):
        print("❌ 运动控制初始化失败")
        return False
    
    # 2. 设置原点模式
    print("\n步骤2: 设置原点模式")
    if not setup_homing(card, axis):
        print("❌ 原点模式设置失败")
        return False
    
    # # 3. 执行回零
    # print("\n步骤3: 执行回零")
    # if not check_and_home(card, axis):
    #     print("❌ 回零失败")
    #     return False
    
    print("\n🎉 完整轴初始化成功")
    return True

#提取原点和正极限检测模块
def check_io_status(card: MotionCard, axis: int) -> str:
    """
    检查轴的IO状态，检测是否触发原点或正极限。
    
    Args:
        card: 控制卡对象
        axis: 轴号
    
    Returns:
        "org": 如果触发原点
        "pel": 如果触发正极限
        "ok": 如果未触发任何限制
    """
    io_status = card.read_axis_io(axis)
    
    if io_status['org']:
        print(f"🛑 触发原点信号！")
        return "org"
    elif io_status['pel']:
        print(f"🛑 触发正极限信号！")
        return "pel"
    return "ok"


def test_limit_switches(card: MotionCard, axis: int) -> bool:
    """
    测试指定轴的原点和正极限接近开关是否正常运行。
    
    Args:
        card: 控制卡对象
        axis: 轴号
        
    Returns:
        True: 测试通过
        False: 测试失败
    """
    print(f"=== 测试轴 {axis} 的接近开关信号 ===")
    
    try:
        # 检查原点信号
        io_status = card.read_axis_io(axis)
        print(io_status)
        org_status = io_status['org']
        pel_status = io_status['pel']
        
        print(f"原点信号状态: {'触发' if org_status else '未触发'}")
        print(f"正极限信号状态: {'触发' if pel_status else '未触发'}")
        
        # 测试原点信号
        if org_status:
            print(f"✅ 原点信号正常（已触发）")
        else:
            print(f"⚠️ 原点信号未触发，请检查接近开关或布线")
        
        # 测试正极限信号
        if pel_status:
            print(f"✅ 正极限信号正常（已触发）")
        else:
            print(f"⚠️ 正极限信号未触发，请检查接近开关或布线")
        
        # 如果两个信号都未触发，提示用户检查
        if not org_status and not pel_status:
            print(f"❌ 原点和正极限信号均未触发，请检查接近开关或布线")
            return False
        
        print(f"🎉 接近开关信号测试完成")
        return True
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False






def move_relative(card: MotionCard, axis: int, distance: float, direction: int, speed: float, timeout: float = 30.0) -> bool:
    """
    相对运动函数，支持控制距离、方向和速度。
    
    Args:
        card: 控制卡对象
        axis: 运动轴号
        distance: 运动距离(mm) - 正数
        direction: 运动方向 - 0=负向, 1=正向
        speed: 运动速度(mm/s)
        timeout: 运动超时时间(秒)
        
    Returns:
        True: 运动成功, False: 运动失败
    """
    # 根据方向确定实际移动距离
    actual_distance = distance if direction == 1 else -distance
    
    print(f"轴 {axis} 相对运动: {actual_distance:+.1f} mm，速度: {speed:.1f} mm/s")
    
    try:
        # 设置运动速度
        card.set_profile(axis, vmin=0.5, vmax=speed, acc=0.1, dec=0.1)  # 假设加减速时间为0.1秒

        # 获取起始位置
        start_pos = card.get_position(axis)
        card.move_rel(axis, actual_distance)
        
        # 等待运动完成，同时监控IO状态
        start_time = time.time()
        while time.time() - start_time < timeout:
            
            # 检查IO状态
            io_status = check_io_status(card, axis)
            if io_status == "org":
                current_pos = card.get_position(axis)
                print(f"🛑 运动中触发原点！位置: {current_pos:.3f} mm")
                card.stop(axis, mode=1)  # 急停
                
                choice = input("是否进入回原点模式？(y/n): ").strip().lower()
                if choice == 'y':
                    return perform_homing(card, axis)
                return False
            
            if io_status == "pel":
                current_pos = card.get_position(axis)
                print(f"🛑 运动中触发正极限！位置: {current_pos:.3f} mm")
                card.stop(axis, mode=1)  # 急停
                
                choice = input("是否进入回原点模式？(y/n): ").strip().lower()
                if choice == 'y':
                    return perform_homing(card, axis)
                return False
            
            # 检查运动是否正常完成
            if card.is_done(axis):
                end_pos = card.get_position(axis)
                print(f"✅ 运动完成，位置: {end_pos:.3f} mm")
                return True
            
            time.sleep(0.05)  # 50ms检查一次
        
        # 运动超时
        print(f"❌ 运动超时")
        card.stop(axis, mode=1)
        return False
        
    except Exception as e:
        print(f"❌ 相对运动失败: {e}")
        card.stop(axis, mode=1)
        return False


def move_absolute(card: MotionCard, axis: int, position: float, speed: float, timeout: float = 30.0) -> bool:
    """
    绝对运动函数，支持控制目标绝对位置和速度。
    
    Args:
        card: 控制卡对象
        axis: 运动轴号
        position: 目标绝对位置(mm)
        speed: 运动速度(mm/s)
        timeout: 运动超时时间(秒)
        
    Returns:
        True: 运动成功, False: 运动失败
    """
    print(f"轴 {axis} 绝对运动: 目标位置 {position:.3f} mm，速度: {speed:.1f} mm/s")
    
    try:
        # 设置运动速度
        card.set_profile(axis, vmin=0.5, vmax=speed, acc=0.1, dec=0.1)  # 假设加减速时间为0.1秒

        # 获取起始位置
        start_pos = card.get_position(axis)
        print(f"起始位置: {start_pos:.3f} mm")
        
        # 发送绝对运动指令
        card.move_abs(axis, position)
        print("运动指令已发送")
        
        # 等待运动完成，同时监控IO状态
        start_time = time.time()
        while time.time() - start_time < timeout:
            
            # 检查IO状态
            io_status = check_io_status(card, axis)
            if io_status == "org":
                current_pos = card.get_position(axis)
                print(f"🛑 运动中触发原点！位置: {current_pos:.3f} mm")
                card.stop(axis, mode=1)  # 急停
                
                choice = input("是否进入回原点模式？(y/n): ").strip().lower()
                if choice == 'y':
                    return perform_homing(card, axis)
                return False
            
            if io_status == "pel":
                current_pos = card.get_position(axis)
                print(f"🛑 运动中触发正极限！位置: {current_pos:.3f} mm")
                card.stop(axis, mode=1)  # 急停
                
                choice = input("是否进入回原点模式？(y/n): ").strip().lower()
                if choice == 'y':
                    return perform_homing(card, axis)
                return False
            
            # 检查运动是否正常完成
            if card.is_done(axis):
                end_pos = card.get_position(axis)
                print(f"✅ 运动完成，位置: {end_pos:.3f} mm")
                return True
            
            time.sleep(0.05)  # 50ms检查一次
        
        # 运动超时
        print(f"❌ 运动超时")
        card.stop(axis, mode=1)
        return False
        
    except Exception as e:
        print(f"❌ 绝对运动失败: {e}")
        card.stop(axis, mode=1)
        return False


def relative_motion_cam(card: MotionCard, master_axis: int, slave_axis: int,
                        distance: float, speed: float, direction: int) -> bool:
    """
    相对运动电子凸轮函数，用于配置电子凸轮并实现主轴和从轴的同步运动。
    
    Args:
        card: 控制卡对象
        master_axis: 主轴轴号
        slave_axis: 从轴轴号
        distance: 主轴的相对运动距离 (mm)，始终正值
        speed: 主轴的运动速度 (mm/s)，始终正值
        direction: 运动方向 - 0=负向, 1=正向
        
    Returns:
        True: 运动成功
        False: 运动失败
    """
    print(f"=== 配置电子凸轮: 主轴 {master_axis}, 从轴 {slave_axis}, 方向={direction} ===")
    
    try:
        # 1. 根据方向配置电子凸轮表
        if direction == 1:  # 正向
            master_pos = [0.0, distance]
            slave_pos  = [0.0, distance]
            print("使用正向凸轮表 [0, +L] → [0, +L]")
        else:  # 负向
            master_pos = [0.0, -distance]
            slave_pos  = [0.0, -distance]
            print("使用负向凸轮表 [0, -L] → [0, -L]")

        print("1. 配置电子凸轮表...")
        card.cam_load_table(master_axis, slave_axis, master_pos, slave_pos, src_mode=0)
        print("✅ 电子凸轮表配置完成")
        
        # 2. 启动从轴的电子凸轮跟随模式
        print("2. 启动从轴的电子凸轮跟随模式...")
        card.cam_start_follow(slave_axis)
        print("✅ 从轴进入电子凸轮跟随模式")
        
        # 3. 执行主轴的相对运动（方向通过 distance*sign 实现）
        move_dist = distance if direction == 1 else -distance
        print(f"3. 执行主轴的相对运动 {move_dist} mm...")
        if move_relative(card, master_axis, abs(distance), direction, speed):
            print("✅ 主轴相对运动完成")
            
            # 4. 停止电子凸轮模式
            print("4. 停止电子凸轮模式...")
            card.stop(slave_axis, mode=0)  # 停止从轴，退出跟随
            print("✅ 从轴电子凸轮模式已停止")
            
            return True
        else:
            print("❌ 主轴相对运动失败")
            return False
    
    except Exception as e:
        print(f"❌ 电子凸轮运动失败: {e}")
        card.stop(master_axis, mode=1)  # 停止主轴
        card.stop(slave_axis, mode=1)  # 停止从轴
        return False


def absolute_motion_cam(card: MotionCard, master_axis: int, slave_axis: int,
                        master_position: float, speed: float) -> bool:
    """
    电子凸轮绝对运动函数，用于配置电子凸轮并实现主轴和从轴的同步绝对运动（1:1）。
    
    Args:
        card: 控制卡对象
        master_axis: 主轴轴号
        slave_axis: 从轴轴号
        master_position: 主轴的目标绝对位置 (mm)
        speed: 主轴的运动速度 (mm/s)
        
    Returns:
        True: 运动成功
        False: 运动失败
    """
    print(f"=== 配置电子凸轮绝对运动: 主轴 {master_axis}, 从轴 {slave_axis} ===")
    
    try:
        # 1. 配置电子凸轮表（1:1 运动）
        print("1. 配置电子凸轮表...")
        master_pos = [0.0, master_position]
        slave_pos = [0.0, master_position]  # 从轴与主轴 1:1 运动
        card.cam_load_table(master_axis, slave_axis, master_pos, slave_pos, src_mode=0)
        print("✅ 电子凸轮表配置完成")
        
        # 2. 启动从轴的电子凸轮跟随模式
        print("2. 启动从轴的电子凸轮跟随模式...")
        card.cam_start_follow(slave_axis)
        print("✅ 从轴进入电子凸轮跟随模式")
        
        # 3. 执行主轴的绝对运动
        print(f"3. 执行主轴的绝对运动到 {master_position} mm...")
        if move_absolute(card, master_axis, position=master_position, speed=speed):
            print("✅ 主轴绝对运动完成")
            
            # 4. 停止电子凸轮模式
            print("4. 停止电子凸轮模式...")
            card.stop(slave_axis, mode=0)  # 停止从轴，退出跟随
            print("✅ 从轴电子凸轮模式已停止")
            
            return True
        else:
            print("❌ 主轴绝对运动失败")
            return False
    
    except Exception as e:
        print(f"❌ 电子凸轮绝对运动失败: {e}")
        card.stop(master_axis, mode=1)  # 停止主轴
        card.stop(slave_axis, mode=1)  # 停止从轴
        return False


    
def cam_home_mode(card: MotionCard, master_axis: int, slave_axis: int) -> bool:
    """
    电子凸轮回原点模式：
    指定主轴回原点，从轴一比一跟随运动。
    
    Args:
        card: 控制卡对象
        master_axis: 主轴轴号
        slave_axis: 从轴轴号
        
    Returns:
        True: 操作成功
        False: 操作失败
    """
    print(f"=== 电子凸轮回原点模式: 主轴 {master_axis}, 从轴 {slave_axis} ===")
    
    try:
        # 初始化主轴
        print(f"\n--- 初始化主轴 {master_axis} ---")
        if not initialize_motion_control(card, axis=master_axis):
            print(f"❌ 主轴 {master_axis} 初始化失败")
            return False
        if not setup_homing(card, axis=master_axis):
            print(f"❌ 主轴 {master_axis} 回原点逻辑设置失败")
            return False
        
        # 初始化从轴
        print(f"\n--- 初始化从轴 {slave_axis} ---")
        if not initialize_motion_control(card, axis=slave_axis):
            print(f"❌ 从轴 {slave_axis} 初始化失败")
            return False
        if not setup_homing(card, axis=slave_axis):
            print(f"❌ 从轴 {slave_axis} 回原点逻辑设置失败")
            return False
        
        # 配置电子凸轮表
        print("\n--- 配置电子凸轮表 ---")
        master_pos = [0.0, -1000.0]
        slave_pos = [0.0, -1000.0]  # 一比一运动
        card.cam_load_table(master_axis=master_axis, slave_axis=slave_axis, master_pos=master_pos, slave_pos=slave_pos, src_mode=0)
        print("✅ 电子凸轮表配置完成")
        
        # 启动从轴的电子凸轮跟随模式
        print("\n--- 启动从轴的电子凸轮跟随模式 ---")
        card.cam_start_follow(slave_axis=slave_axis)
        print("✅ 从轴进入电子凸轮跟随模式")
        
        # 主轴执行回原点操作
        print(f"\n--- 主轴 {master_axis} 执行回原点操作 ---")
        if not perform_homing(card, axis=master_axis):
            print(f"❌ 主轴 {master_axis} 回原点失败")
            return False
        
        
        
        # 停止电子凸轮模式
        print("\n--- 停止电子凸轮模式 ---")
        card.stop(slave_axis, mode=0)
        print("✅ 从轴电子凸轮模式已停止")

        
        print("🎉 电子凸轮回原点模式完成")
        return True
    
    except Exception as e:
        print(f"❌ 电子凸轮回原点模式失败: {e}")
        return False