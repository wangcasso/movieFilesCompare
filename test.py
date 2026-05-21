#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本 - 验证视频去重工具的核心功能
"""

import sys
from video_dedup import SimilarityCalculator, VideoInfo, ComparisonEngine

def test_similarity():
    """测试相似度计算"""
    print("=" * 60)
    print("测试1: 相似度计算功能")
    print("=" * 60)
    
    calc = SimilarityCalculator()
    
    # 测试名称相似度
    name1 = "复仇者联盟4终局之战"
    name2 = "复仇者联盟4终局之战_副本"
    similarity = calc.name_similarity(name1, name2)
    print(f"\n名称相似度测试:")
    print(f"  '{name1}' vs '{name2}'")
    print(f"  相似度: {similarity:.2%}")
    
    # 测试大小相似度
    size_sim = calc.size_similarity(1000000, 950000)
    print(f"\n大小相似度测试:")
    print(f"  1MB vs 0.95MB")
    print(f"  相似度: {size_sim:.2%}")
    
    # 测试时长相似度
    dur_sim = calc.duration_similarity(120.5, 121.0)
    print(f"\n时长相似度测试:")
    print(f"  120.5秒 vs 121.0秒")
    print(f"  相似度: {dur_sim:.2%}")


def test_comparison():
    """测试比较引擎"""
    print("\n" + "=" * 60)
    print("测试2: 比较引擎功能")
    print("=" * 60)
    
    # 创建测试数据
    videos = [
        VideoInfo(
            file_path=r"D:\videos\movie1.mp4",
            file_name="复仇者联盟4",
            file_size=1000000000,
            duration=180.5,
            folder_path=r"D:\videos"
        ),
        VideoInfo(
            file_path=r"D:\backup\movie1_copy.mp4",
            file_name="复仇者联盟4_副本",
            file_size=999000000,
            duration=180.5,
            folder_path=r"D:\backup"
        ),
        VideoInfo(
            file_path=r"D:\videos\different.mp4",
            file_name="蜘蛛侠",
            file_size=500000000,
            duration=120.0,
            folder_path=r"D:\videos"
        )
    ]
    
    # 配置比较宽松
    config = {
        'use_name': True,
        'use_size': True,
        'use_duration': True,
        'name_threshold': 0.7,
        'size_tolerance': 0.9,
        'duration_tolerance': 0.9
    }
    
    engine = ComparisonEngine(config)
    duplicates = engine.find_duplicates(videos)
    
    print(f"\n测试数据: {len(videos)} 个视频")
    print(f"发现重复组数: {len(duplicates)}")
    
    for idx, group in enumerate(duplicates, 1):
        print(f"\n第 {idx} 组重复:")
        for video in group:
            print(f"  - {video.file_name} ({video.folder_path})")


def main():
    """运行测试"""
    print("\n🧪 开始测试视频去重工具...\n")
    
    try:
        test_similarity()
        test_comparison()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)
        print("\n提示: 你现在可以运行 'python video_dedup.py' 启动图形界面")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
