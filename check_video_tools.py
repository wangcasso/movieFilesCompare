#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频时长获取工具诊断脚本
用于检查系统中可用的视频信息获取工具
"""

import sys
import subprocess

def check_ffprobe():
    """检查 ffprobe"""
    print("=" * 60)
    print("检查 ffprobe...")
    try:
        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✓ ffprobe 可用: {version_line}")
            
            # 测试实际文件
            print("\n测试获取视频时长...")
            test_cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                sys.argv[1] if len(sys.argv) > 1 else 'test.mp4'
            ]
            print(f"命令: {' '.join(test_cmd)}")
            return True
        else:
            print("✗ ffprobe 存在但执行失败")
            return False
    except FileNotFoundError:
        print("✗ ffprobe 未找到")
        print("\n安装方法:")
        print("1. 下载 FFmpeg: https://ffmpeg.org/download.html")
        print("2. 解压后将 bin 目录添加到系统 PATH")
        print("3. 重启命令行窗口")
        return False
    except Exception as e:
        print(f"✗ 检测失败: {e}")
        return False

def check_mediainfo():
    """检查 mediainfo"""
    print("\n" + "=" * 60)
    print("检查 mediainfo...")
    try:
        result = subprocess.run(
            ['mediainfo', '--Version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✓ mediainfo 可用")
            return True
        else:
            print("✗ mediainfo 存在但执行失败")
            return False
    except FileNotFoundError:
        print("✗ mediainfo 未找到")
        print("\n安装方法:")
        print("下载: https://mediaarea.net/en/MediaInfo")
        return False
    except Exception as e:
        print(f"✗ 检测失败: {e}")
        return False

def check_mutagen():
    """检查 mutagen"""
    print("\n" + "=" * 60)
    print("检查 mutagen Python库...")
    try:
        import mutagen
        print(f"✓ mutagen 可用 (版本: {mutagen.version_string})")
        
        # 测试读取文件
        if len(sys.argv) > 1:
            print(f"\n测试读取文件: {sys.argv[1]}")
            try:
                audio = mutagen.File(sys.argv[1])
                if audio and audio.info:
                    print(f"✓ 成功读取，时长: {audio.info.length:.2f}秒")
                else:
                    print("✗ 无法读取文件信息")
            except Exception as e:
                print(f"✗ 读取失败: {e}")
        
        return True
    except ImportError:
        print("✗ mutagen 未安装")
        print("\n安装命令: pip install mutagen")
        return False
    except Exception as e:
        print(f"✗ 检测失败: {e}")
        return False

def check_opencv():
    """检查 opencv"""
    print("\n" + "=" * 60)
    print("检查 OpenCV Python库...")
    try:
        import cv2
        print(f"✓ OpenCV 可用 (版本: {cv2.__version__})")
        
        # 测试读取文件
        if len(sys.argv) > 1:
            print(f"\n测试读取文件: {sys.argv[1]}")
            cap = cv2.VideoCapture(sys.argv[1])
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                duration = frame_count / fps if fps > 0 else 0
                print(f"✓ 成功读取")
                print(f"  FPS: {fps}")
                print(f"  帧数: {frame_count}")
                print(f"  时长: {duration:.2f}秒")
                cap.release()
            else:
                print("✗ 无法打开文件")
                cap.release()
        
        return True
    except ImportError:
        print("✗ OpenCV 未安装")
        print("\n安装命令: pip install opencv-python")
        return False
    except Exception as e:
        print(f"✗ 检测失败: {e}")
        return False

def main():
    print("视频时长获取工具诊断")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        print(f"测试文件: {sys.argv[1]}")
    else:
        print("提示: 可以传入一个视频文件路径进行测试")
        print("用法: python check_video_tools.py video.mp4")
    
    results = {
        'ffprobe': check_ffprobe(),
        'mediainfo': check_mediainfo(),
        'mutagen': check_mutagen(),
        'opencv': check_opencv()
    }
    
    print("\n" + "=" * 60)
    print("总结:")
    print("=" * 60)
    
    available = [name for name, status in results.items() if status]
    unavailable = [name for name, status in results.items() if not status]
    
    if available:
        print(f"✓ 可用的工具: {', '.join(available)}")
        print("\n你的程序应该能够正常获取视频时长！")
    else:
        print("✗ 没有找到任何可用的工具")
        print("\n建议安装以下任一工具：")
        print("1. FFmpeg (推荐) - 包含ffprobe")
        print("   下载: https://ffmpeg.org/download.html")
        print("2. mutagen (最简单)")
        print("   命令: pip install mutagen")
        print("3. MediaInfo")
        print("   下载: https://mediaarea.net/en/MediaInfo")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
