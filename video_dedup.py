#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频文件去重工具
功能：比对多个文件夹内的视频文件是否重复
判定标准：视频时长、视频名称、视频大小（可单独或组合使用）
支持文件名相似度匹配
"""

import os
import sys
import json
import hashlib
import glob
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
from datetime import datetime


@dataclass
class VideoInfo:
    """视频文件信息"""
    file_path: str
    file_name: str
    file_size: int  # 字节
    duration: float  # 秒
    folder_path: str  # 所属文件夹
    
    def get_size_mb(self) -> float:
        """获取文件大小（MB）"""
        return self.file_size / (1024 * 1024)
    
    def get_duration_str(self) -> str:
        """获取格式化的时长字符串"""
        minutes = int(self.duration // 60)
        seconds = int(self.duration % 60)
        return f"{minutes}:{seconds:02d}"


class VideoScanner:
    """视频文件扫描器"""
    
    # 支持的 видео格式
    VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', 
                        '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.rmvb', '.rm'}
    
    @staticmethod
    def scan_folder(folder_path: str, progress_callback=None) -> List[VideoInfo]:
        """扫描文件夹中的所有视频文件"""
        videos = []
        folder = Path(folder_path)
        
        # 收集所有视频文件
        video_files = []
        for ext in VideoScanner.VIDEO_EXTENSIONS:
            video_files.extend(folder.rglob(f'*{ext}'))
        
        total_files = len(video_files)
        
        # 逐个处理
        for idx, video_file in enumerate(video_files):
            try:
                if progress_callback:
                    progress_callback(idx + 1, total_files, f"正在扫描: {video_file.name}")
                
                stat = video_file.stat()
                duration = VideoScanner._get_video_duration(str(video_file))
                
                # 记录时长获取状态（减少日志输出，避免影响性能）
                # 只在每50个文件或出错时输出
                if duration > 0 and (idx + 1) % 50 == 0:
                    if progress_callback:
                        progress_callback(idx + 1, total_files, f"已扫描 {idx+1}/{total_files} 个文件")
                
                video_info = VideoInfo(
                    file_path=str(video_file.absolute()),
                    file_name=video_file.stem,  # 不含扩展名
                    file_size=stat.st_size,
                    duration=duration,
                    folder_path=str(folder_path)
                )
                videos.append(video_info)
            except Exception as e:
                error_msg = f"读取文件失败 {video_file}: {e}"
                print(error_msg)
                if progress_callback:
                    progress_callback(idx + 1, total_files, error_msg, is_error=True)
        
        return videos
    
    @staticmethod
    def _get_video_duration(file_path: str) -> float:
        """获取视频时长（秒）- 多种方法尝试"""
        # 方法1: 尝试使用mutagen库（最快，推荐）
        try:
            import mutagen
            
            audio = mutagen.File(file_path)
            if audio and audio.info and hasattr(audio.info, 'length'):
                duration = audio.info.length
                if duration > 0:
                    return duration
        except:
            pass  # mutagen未安装或其他错误
        
        # 方法2: 尝试使用ffprobe（最准确）
        try:
            import subprocess
            
            # 尝试不同的ffprobe命令格式
            commands = [
                # 标准命令
                ['ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                 file_path],
                # Windows兼容命令
                ['ffprobe.exe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                 file_path],
            ]
            
            for cmd in commands:
                try:
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        duration = float(result.stdout.strip())
                        if duration > 0:
                            return duration
                except Exception:
                    continue
                    
        except Exception:
            pass
        
        # 方法3: 尝试使用mediainfo命令行工具
        try:
            import subprocess
            cmd = ['mediainfo', '--Output=General;%Duration%', file_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                duration_ms = int(result.stdout.strip())
                if duration_ms > 0:
                    return duration_ms / 1000.0
        except:
            pass
        
        # 方法4: 尝试使用opencv（如果已安装）
        try:
            import cv2
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                cap.release()
                if fps > 0 and frame_count > 0:
                    duration = frame_count / fps
                    return duration
        except:
            pass  # opencv未安装或其他错误
        
        # 所有方法都失败，返回0
        return 0.0


class SimilarityCalculator:
    """相似度计算器"""
    
    @staticmethod
    def name_similarity(name1: str, name2: str) -> float:
        """计算两个文件名的相似度 (0-1之间)"""
        from difflib import SequenceMatcher
        
        # 转换为小写进行比较
        name1_lower = name1.lower()
        name2_lower = name2.lower()
        
        # 使用SequenceMatcher计算相似度
        return SequenceMatcher(None, name1_lower, name2_lower).ratio()
    
    @staticmethod
    def size_similarity(size1: int, size2: int) -> float:
        """计算文件大小的相似度 (0-1之间)"""
        if size1 == 0 and size2 == 0:
            return 1.0
        if size1 == 0 or size2 == 0:
            return 0.0
        
        max_size = max(size1, size2)
        min_size = min(size1, size2)
        
        return min_size / max_size
    
    @staticmethod
    def duration_match(dur1: float, dur2: float, tolerance_seconds: float = 2.0) -> bool:
        """检查视频时长是否在允许误差范围内（按秒比较）"""
        if dur1 == 0 and dur2 == 0:
            return True
        if dur1 == 0 or dur2 == 0:
            return False
        
        # 直接比较秒数差值
        return abs(dur1 - dur2) <= tolerance_seconds


class ComparisonEngine:
    """比较引擎 - 核心逻辑（优化版）"""
    
    def __init__(self, config: dict):
        self.config = config
        self.calculator = SimilarityCalculator()
        self._stop_flag = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # 默认运行状态
    
    def stop(self):
        """停止扫描"""
        self._stop_flag = True
    
    def pause(self):
        """暂停扫描"""
        self._pause_event.clear()
    
    def resume(self):
        """恢复扫描"""
        self._pause_event.set()
    
    def is_stopped(self):
        """检查是否已停止"""
        return self._stop_flag
    
    def find_duplicates(self, all_videos: List[VideoInfo], progress_callback=None) -> List[List[VideoInfo]]:
        """查找重复的视频文件组（优化版）"""
        duplicates = []
        used = set()
        self._stop_flag = False
        self._pause_event.set()
        
        # 获取配置参数
        use_name = self.config.get('use_name', True)
        use_size = self.config.get('use_size', True)
        use_duration = self.config.get('use_duration', True)
        name_threshold = self.config.get('name_threshold', 0.8)
        size_tolerance = self.config.get('size_tolerance', 0.95)
        duration_tolerance_seconds = self.config.get('duration_tolerance_seconds', 2.0)
        
        total_videos = len(all_videos)
        
        if progress_callback:
            progress_callback(0, total_videos, "正在建立索引...")
        
        # 优化1: 预过滤 - 按文件大小分组（大小差异太大的不可能是重复文件）
        size_groups = self._group_by_size(all_videos, size_tolerance)
        
        if progress_callback:
            progress_callback(total_videos // 4, total_videos, f"建立索引完成，分为 {len(size_groups)} 个大小组")
        
        # 优化2: 在每个大小组内进行详细比较
        processed = 0
        group_count = len(size_groups)
        
        for group_idx, size_group in enumerate(size_groups):
            # 检查停止和暂停
            if self._stop_flag:
                if progress_callback:
                    progress_callback(processed, total_videos, "扫描已停止", is_info=True)
                return duplicates
            
            self._pause_event.wait()
            
            if len(size_group) < 2:
                processed += len(size_group)
                continue
            
            # 在这个大小组内查找重复
            sub_duplicates = self._find_duplicates_in_group(
                size_group, used, 
                use_name, use_size, use_duration,
                name_threshold, size_tolerance, duration_tolerance_seconds,
                progress_callback, processed, total_videos
            )
            duplicates.extend(sub_duplicates)
            processed += len(size_group)
            
            # 更新进度
            if progress_callback and group_idx % 10 == 0:
                progress_pct = total_videos // 4 + (processed / total_videos * 75)
                progress_callback(progress_pct, total_videos, 
                                f"正在比对第 {group_idx+1}/{group_count} 组 ({len(size_group)} 个文件)")
        
        return duplicates
    
    def _group_by_size(self, videos: List[VideoInfo], size_tolerance: float) -> List[List[VideoInfo]]:
        """按文件大小分组，减少比较次数"""
        # 创建大小桶（每个桶范围是 ±5%）
        size_buckets = {}
        
        for video in videos:
            if video.file_size == 0:
                bucket_key = 0
            else:
                # 使用对数刻度分桶，避免大文件和小文件混在一起
                import math
                bucket_key = int(math.log2(video.file_size) * 10)
            
            if bucket_key not in size_buckets:
                size_buckets[bucket_key] = []
            size_buckets[bucket_key].append(video)
        
        return list(size_buckets.values())
    
    def _find_duplicates_in_group(
        self, group: List[VideoInfo], 
        used: set,
        use_name: bool, use_size: bool, use_duration: bool,
        name_threshold: float, size_tolerance: float, duration_tolerance_seconds: float,
        progress_callback, processed_offset: int, total_videos: int
    ) -> List[List[VideoInfo]]:
        """在单个大小组内查找重复文件"""
        duplicates = []
        local_used = set()
        
        # 优化3: 如果启用了名称比较，先按名称首字母分组
        if use_name:
            name_groups = self._group_by_name_prefix(group)
        else:
            name_groups = [group]
        
        for name_group in name_groups:
            if self._stop_flag:
                break
            
            self._pause_event.wait()
            
            if len(name_group) < 2:
                continue
            
            # 在名称组内进行两两比较
            for i in range(len(name_group)):
                if self._stop_flag:
                    break
                
                self._pause_event.wait()
                
                idx_i = id(name_group[i])
                if idx_i in local_used or idx_i in used:
                    continue
                
                current_group = [name_group[i]]
                
                for j in range(i + 1, len(name_group)):
                    if self._stop_flag:
                        break
                    
                    self._pause_event.wait()
                    
                    idx_j = id(name_group[j])
                    if idx_j in local_used or idx_j in used:
                        continue
                    
                    video1 = name_group[i]
                    video2 = name_group[j]
                    
                    # ★ 强匹配规则：时长和大小完全相等，直接判定为重复（无视其他条件）
                    if (video1.duration > 0 and video2.duration > 0 and 
                        abs(video1.duration - video2.duration) < 0.01 and  # 时长几乎完全相同（误差<0.01秒）
                        video1.file_size == video2.file_size):  # 大小完全相同
                        current_group.append(video2)
                        local_used.add(idx_j)
                        used.add(idx_j)
                        continue
                    
                    # 快速比较：先比较最便宜的指标
                    is_match = True
                    
                    # 优先比较大小（最快）
                    if use_size:
                        size_sim = self.calculator.size_similarity(
                            video1.file_size, video2.file_size
                        )
                        if size_sim < size_tolerance:
                            is_match = False
                    
                    # 然后比较时长（较快）
                    if is_match and use_duration:
                        if not self.calculator.duration_match(
                            video1.duration, video2.duration, duration_tolerance_seconds
                        ):
                            is_match = False
                    
                    # 最后比较名称（最慢，放在最后）
                    if is_match and use_name:
                        name_sim = self.calculator.name_similarity(
                            video1.file_name, video2.file_name
                        )
                        if name_sim < name_threshold:
                            is_match = False
                    
                    if is_match:
                        current_group.append(video2)
                        local_used.add(idx_j)
                        used.add(idx_j)
                
                if len(current_group) > 1:
                    duplicates.append(current_group)
                    local_used.add(idx_i)
                    used.add(idx_i)
        
        return duplicates
    
    def _group_by_name_prefix(self, videos: List[VideoInfo]) -> List[List[VideoInfo]]:
        """按文件名前缀分组，进一步减少比较次数"""
        name_groups = {}
        
        for video in videos:
            # 取前3个字符作为分组键（可以根据需要调整）
            prefix = video.file_name[:3].lower() if len(video.file_name) >= 3 else video.file_name.lower()
            if prefix not in name_groups:
                name_groups[prefix] = []
            name_groups[prefix].append(video)
        
        return list(name_groups.values())


class ConfigManager:
    """配置管理器"""
    
    CONFIG_FILE = "config.json"
    
    @staticmethod
    def save_config(config: dict):
        """保存配置"""
        with open(ConfigManager.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def load_config() -> dict:
        """加载配置"""
        default_config = {
            'use_name': True,
            'use_size': True,
            'use_duration': True,
            'name_threshold': 0.8,
            'size_tolerance': 0.95,
            'duration_tolerance_seconds': 2.0,  # 改为秒数
            'last_folder_path': "",  # ★ 新增：上次选择的文件夹路径
            'folders': []  # ★ 新增：已选择的文件夹列表
        }
        
        if os.path.exists(ConfigManager.CONFIG_FILE):
            try:
                with open(ConfigManager.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 兼容旧配置
                    if 'duration_tolerance' in loaded and 'duration_tolerance_seconds' not in loaded:
                        loaded['duration_tolerance_seconds'] = 2.0
                    # 确保有last_folder_path字段
                    if 'last_folder_path' not in loaded:
                        loaded['last_folder_path'] = ""
                    # 确保有folders字段
                    if 'folders' not in loaded:
                        loaded['folders'] = []
                    return loaded
            except Exception as e:
                print(f"加载配置文件失败: {e}")
                return default_config
        
        return default_config
    
    @staticmethod
    def save_last_folder_path(path: str):
        """保存上次选择的文件夹路径"""
        config = ConfigManager.load_config()
        config['last_folder_path'] = path
        ConfigManager.save_config(config)
    
    @staticmethod
    def save_folders(folders: list):
        """保存已选择的文件夹列表"""
        config = ConfigManager.load_config()
        config['folders'] = folders
        ConfigManager.save_config(config)


class VideoDuplicateFinderApp:
    """主应用程序界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("视频文件去重工具 v2.0")
        self.root.geometry("1200x800")
        
        # 数据存储
        self.folders = []
        self.all_videos = []
        self.duplicates = []
        self.config = ConfigManager.load_config()
        
        # ★ 如果配置文件不存在，立即创建一个（确保后续可以保存）
        if not os.path.exists(ConfigManager.CONFIG_FILE):
            ConfigManager.save_config(self.config)
            print("[DEBUG] 创建了默认配置文件")
        
        # 扫描控制
        self.scan_thread = None
        self.comparison_engine = None
        self.scan_start_time = None
        
        # 文件夹选择记忆（从配置文件加载）
        self.last_folder_path = self.config.get('last_folder_path', "")  # ★ 从配置文件加载上次路径
        
        # ★ 加载已保存的文件夹列表
        saved_folders = self.config.get('folders', [])
        if saved_folders:
            self.folders = saved_folders
            print(f"[DEBUG] 从配置文件加载了 {len(saved_folders)} 个文件夹")
        else:
            print("[DEBUG] 没有保存的文件夹列表")
        
        # 调试日志：确认配置加载
        if self.last_folder_path:
            print(f"[DEBUG] 从配置文件加载 last_folder_path: {self.last_folder_path}")
        else:
            print("[DEBUG] last_folder_path 为空，使用默认值")
        
        # 创建界面
        self._create_widgets()
        self._load_config_to_ui()
        
        # 检测可用的视频信息工具
        self._check_video_tools()
    
    def _check_video_tools(self):
        """检测可用的视频信息获取工具"""
        self.log_message("=" * 60, "INFO")
        self.log_message("正在检测视频时长获取工具...", "INFO")
        
        tools_status = []
        
        # 检查 ffprobe
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-version'],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                self.log_message(f"✓ ffprobe 可用: {version_line}", "INFO")
                tools_status.append(("ffprobe", True, version_line))
            else:
                self.log_message("✗ ffprobe 未找到或无法执行", "WARNING")
                tools_status.append(("ffprobe", False, "未安装"))
        except FileNotFoundError:
            self.log_message("✗ ffprobe 未安装", "WARNING")
            tools_status.append(("ffprobe", False, "未安装"))
        except Exception as e:
            self.log_message(f"✗ ffprobe 检测失败: {e}", "ERROR")
            tools_status.append(("ffprobe", False, str(e)))
        
        # 检查 mediainfo
        try:
            import subprocess
            result = subprocess.run(
                ['mediainfo', '--Version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.log_message(f"✓ mediainfo 可用", "INFO")
                tools_status.append(("mediainfo", True, "已安装"))
            else:
                self.log_message("✗ mediainfo 未找到", "WARNING")
                tools_status.append(("mediainfo", False, "未安装"))
        except FileNotFoundError:
            self.log_message("✗ mediainfo 未安装", "WARNING")
            tools_status.append(("mediainfo", False, "未安装"))
        except Exception as e:
            self.log_message(f"✗ mediainfo 检测失败: {e}", "ERROR")
            tools_status.append(("mediainfo", False, str(e)))
        
        # 检查 mutagen
        try:
            import mutagen
            self.log_message(f"✓ mutagen 库可用 (版本: {mutagen.version_string})", "INFO")
            tools_status.append(("mutagen", True, mutagen.version_string))
        except ImportError:
            self.log_message("✗ mutagen 库未安装", "WARNING")
            self.log_message("  安装命令: pip install mutagen", "INFO")
            tools_status.append(("mutagen", False, "未安装"))
        except Exception as e:
            self.log_message(f"✗ mutagen 检测失败: {e}", "ERROR")
            tools_status.append(("mutagen", False, str(e)))
        
        # 检查 opencv
        try:
            import cv2
            self.log_message(f"✓ OpenCV 库可用 (版本: {cv2.__version__})", "INFO")
            tools_status.append(("opencv", True, cv2.__version__))
        except ImportError:
            self.log_message("✗ OpenCV 库未安装", "WARNING")
            self.log_message("  安装命令: pip install opencv-python", "INFO")
            tools_status.append(("opencv", False, "未安装"))
        except Exception as e:
            self.log_message(f"✗ OpenCV 检测失败: {e}", "ERROR")
            tools_status.append(("opencv", False, str(e)))
        
        # 总结
        available_tools = [name for name, available, _ in tools_status if available]
        self.log_message("=" * 60, "INFO")
        
        if available_tools:
            self.log_message(f"✓ 可用的工具: {', '.join(available_tools)}", "INFO")
            self.log_message("视频时长获取功能正常", "INFO")
        else:
            self.log_message("✗ 警告：没有找到任何视频时长获取工具！", "ERROR")
            self.log_message("所有视频的时长将显示为 0:00", "WARNING")
            self.log_message("", "INFO")
            self.log_message("建议安装以下任一工具：", "INFO")
            self.log_message("1. FFmpeg (包含ffprobe) - 推荐", "INFO")
            self.log_message("   下载: https://ffmpeg.org/download.html", "INFO")
            self.log_message("2. mutagen Python库", "INFO")
            self.log_message("   命令: pip install mutagen", "INFO")
            self.log_message("3. MediaInfo", "INFO")
            self.log_message("   下载: https://mediaarea.net/en/MediaInfo", "INFO")
            self.log_message("", "INFO")
            self.log_message("注意：如果没有这些工具，程序仍可通过文件名和大小进行比对", "INFO")
        
        self.log_message("=" * 60, "INFO")
    
    def _create_widgets(self):
        """创建界面组件"""
        # 初始化配置变量（用于弹窗和主界面共享）
        self.use_name_var = tk.BooleanVar(value=True)
        self.use_size_var = tk.BooleanVar(value=True)
        self.use_duration_var = tk.BooleanVar(value=True)
        self.name_threshold_var = tk.DoubleVar(value=0.8)
        self.size_tolerance_var = tk.DoubleVar(value=0.95)
        self.duration_tolerance_seconds_var = tk.DoubleVar(value=2.0)
        
        # 标题
        title_frame = ttk.Frame(self.root, padding="10")
        title_frame.pack(fill=tk.X)
        
        title_label = ttk.Label(
            title_frame, 
            text="🎬 视频文件去重工具",
            font=("微软雅黑", 18, "bold")
        )
        title_label.pack()
        
        subtitle_label = ttk.Label(
            title_frame,
            text="支持按名称、大小、时长多维度检测重复视频 | 时长容差: ±2秒",
            font=("微软雅黑", 9),
            foreground="gray"
        )
        subtitle_label.pack()
        
        # 顶部工具栏（简化版）
        toolbar_frame = ttk.Frame(self.root, padding="5")
        toolbar_frame.pack(fill=tk.X)
        
        # 左侧：文件夹管理按钮
        left_toolbar = ttk.Frame(toolbar_frame)
        left_toolbar.pack(side=tk.LEFT)
        
        ttk.Button(left_toolbar, text="📁 管理文件夹", command=self.show_folder_manager).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_toolbar, text="⚙️ 比较配置", command=self.show_config_dialog).pack(side=tk.LEFT, padx=2)
        
        # 右侧：状态显示
        self.folder_count_var = tk.StringVar(value="未选择文件夹")
        ttk.Label(left_toolbar, textvariable=self.folder_count_var, font=("微软雅黑", 9), foreground="gray").pack(side=tk.LEFT, padx=10)
        
        # 开始/暂停/停止按钮
        action_frame = ttk.Frame(self.root, padding="10")
        action_frame.pack(fill=tk.X)
        
        btn_action_frame = ttk.Frame(action_frame)
        btn_action_frame.pack(pady=5)
        
        self.start_btn = ttk.Button(
            btn_action_frame,
            text="🚀 开始扫描",
            command=self.start_scan,
            style="Accent.TButton"
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(
            btn_action_frame,
            text="⏸️ 暂停",
            command=self.pause_scan,
            state=tk.DISABLED
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(
            btn_action_frame,
            text="⏹️ 停止",
            command=self.stop_scan,
            state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度信息
        progress_info_frame = ttk.Frame(action_frame)
        progress_info_frame.pack(fill=tk.X, pady=5)
        
        self.progress_status_var = tk.StringVar(value="就绪")
        ttk.Label(progress_info_frame, textvariable=self.progress_status_var, font=("微软雅黑", 10)).pack(anchor=tk.W)
        
        self.progress_detail_var = tk.StringVar(value="")
        ttk.Label(progress_info_frame, textvariable=self.progress_detail_var, font=("微软雅黑", 9), foreground="gray").pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(action_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(self.root, text="📋 程序日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        log_text_frame = ttk.Frame(log_frame)
        log_text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_text_frame, height=6, wrap=tk.WORD, font=("Consolas", 9))
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 结果显示区域
        result_frame = ttk.LabelFrame(self.root, text="📊 扫描结果", padding="10")
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 统计信息
        stats_frame = ttk.Frame(result_frame)
        stats_frame.pack(fill=tk.X, pady=5)
        
        self.stats_label = ttk.Label(
            stats_frame,
            text="尚未扫描",
            font=("微软雅黑", 10),
            foreground="blue"
        )
        self.stats_label.pack()
        
        # 结果列表
        result_list_frame = ttk.Frame(result_frame)
        result_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建带复选框的树形视图（缩略图使用image列）
        columns = ("选择", "分组", "所属文件夹", "文件名", "大小", "时长")
        self.result_tree = ttk.Treeview(result_list_frame, columns=columns, show="tree headings")
        
        self.result_tree.heading("#0", text="缩略图")
        self.result_tree.column("#0", width=100, anchor=tk.CENTER)
        
        for col in columns:
            self.result_tree.heading(col, text=col)
            if col == "选择":
                self.result_tree.column(col, width=60, anchor=tk.CENTER)
            elif col == "文件名":
                self.result_tree.column(col, width=280)
            elif col == "所属文件夹":
                self.result_tree.column(col, width=220)
            elif col == "大小":
                self.result_tree.column(col, width=100)
            elif col == "时长":
                self.result_tree.column(col, width=90)
            elif col == "分组":
                self.result_tree.column(col, width=70)
        
        tree_scrollbar = ttk.Scrollbar(result_list_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 存储缩略图的字典 {item_id: photo_image}
        self.thumbnails = {}
        
        # 绑定点击事件用于复选框切换
        self.result_tree.bind('<Button-1>', self.on_tree_click)
        
        # 底部按钮
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        # 左侧：配置和导出
        left_btn_frame = ttk.Frame(bottom_frame)
        left_btn_frame.pack(side=tk.LEFT)
        
        ttk.Button(left_btn_frame, text="💾 保存配置", command=self.save_config).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_btn_frame, text="📋 导出结果", command=self.export_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_btn_frame, text="❌ 清除结果", command=self.clear_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(left_btn_frame, text="🗑️ 清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=2)
        
        # 右侧：文件操作（需要选中文件）
        right_btn_frame = ttk.Frame(bottom_frame)
        right_btn_frame.pack(side=tk.RIGHT)
        
        ttk.Label(right_btn_frame, text="选中文件后操作:", font=("微软雅黑", 9), foreground="gray").pack(side=tk.LEFT, padx=5)
        
        self.open_file_btn = ttk.Button(
            right_btn_frame, 
            text="📂 打开文件位置", 
            command=self.open_selected_file_location,
            state=tk.DISABLED
        )
        self.open_file_btn.pack(side=tk.LEFT, padx=2)
        
        self.delete_file_btn = ttk.Button(
            right_btn_frame, 
            text="🗑️ 删除选中文件", 
            command=self.delete_selected_file,
            state=tk.DISABLED
        )
        self.delete_file_btn.pack(side=tk.LEFT, padx=2)
        
        # 绑定树形视图双击事件
        self.result_tree.bind('<Double-1>', self.on_tree_double_click)  # 双击打开
    
    def _load_config_to_ui(self):
        """从配置加载到UI"""
        self.use_name_var.set(self.config.get('use_name', True))
        self.use_size_var.set(self.config.get('use_size', True))
        self.use_duration_var.set(self.config.get('use_duration', True))
        self.name_threshold_var.set(self.config.get('name_threshold', 0.8))
        self.size_tolerance_var.set(self.config.get('size_tolerance', 0.95))
        self.duration_tolerance_seconds_var.set(self.config.get('duration_tolerance_seconds', 2.0))
        
        # 更新文件夹计数显示
        if self.folders:
            self.folder_count_var.set(f"已选择 {len(self.folders)} 个文件夹")
    
    def add_folder(self):
        """添加文件夹"""
        # 使用上次选择的路径作为初始目录
        initial_dir = self.last_folder_path if self.last_folder_path else ""
        print(f"[DEBUG] 打开文件夹对话框，initial_dir: {initial_dir}")  # ★ 调试日志
        
        folder = filedialog.askdirectory(
            title="选择要扫描的文件夹",
            initialdir=initial_dir
        )
        
        if folder:
            print(f"[DEBUG] 用户选择了: {folder}")  # ★ 调试日志
            print(f"[DEBUG] folder类型: {type(folder)}")  # ★ 调试日志
            
            # ★ 记忆本次选择的路径（用于下次打开）并持久化保存
            parent_path = os.path.dirname(folder)
            self.last_folder_path = parent_path
            print(f"[DEBUG] 父目录: {parent_path}")  # ★ 调试日志
            print(f"[DEBUG] 保存 last_folder_path: {self.last_folder_path}")  # ★ 调试日志
            
            ConfigManager.save_last_folder_path(self.last_folder_path)  # ★ 保存到配置文件
            print(f"[DEBUG] 已调用 save_last_folder_path")  # ★ 调试日志
            
            # 验证保存结果
            import time
            time.sleep(0.1)  # 等待文件写入
            if os.path.exists(ConfigManager.CONFIG_FILE):
                with open(ConfigManager.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    print(f"[DEBUG] 配置文件中的路径: {saved_config.get('last_folder_path')}")
            
            if folder not in self.folders:
                self.folders.append(folder)
                self.folder_listbox.insert(tk.END, folder)
                self.log_message(f"已添加文件夹: {folder}")
            else:
                self.log_message(f"文件夹已存在: {folder}", "WARNING")
    
    def remove_folder(self):
        """移除选中的文件夹"""
        selection = self.folder_listbox.curselection()
        if selection:
            index = selection[0]
            removed = self.folders.pop(index)
            self.folder_listbox.delete(index)
            self.log_message(f"已移除文件夹: {removed}")
    
    def clear_folders(self):
        """清空文件夹列表"""
        count = len(self.folders)
        self.folders.clear()
        self.folder_listbox.delete(0, tk.END)
        self.log_message(f"已清空 {count} 个文件夹")
    
    def log_message(self, message: str, level: str = "INFO"):
        """记录日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)  # 自动滚动到底部
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("日志已清空")
    
    def start_scan(self):
        """开始扫描"""
        if not self.folders:
            messagebox.showwarning("警告", "请先添加至少一个文件夹！")
            return
        
        # 重置状态
        self.duplicates = []
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.stats_label.config(text="扫描中...")
        
        # 禁用/启用按钮
        self.start_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL)
        self.pause_btn.config(text="⏸️ 暂停")
        
        # 初始化进度条
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = 100
        
        # 记录开始时间
        self.scan_start_time = time.time()
        
        # 在后台线程中执行扫描
        self.scan_thread = threading.Thread(target=self.scan_thread_func)
        self.scan_thread.daemon = True
        self.scan_thread.start()
        
        self.log_message("开始扫描...", "START")
    
    def pause_scan(self):
        """暂停/恢复扫描"""
        if self.comparison_engine:
            if self.pause_btn.cget('text') == "⏸️ 暂停":
                self.comparison_engine.pause()
                self.pause_btn.config(text="▶️ 恢复")
                self.log_message("扫描已暂停", "PAUSE")
            else:
                self.comparison_engine.resume()
                self.pause_btn.config(text="⏸️ 暂停")
                self.log_message("扫描已恢复", "RESUME")
    
    def stop_scan(self):
        """停止扫描"""
        if self.comparison_engine:
            self.comparison_engine.stop()
            self.log_message("正在停止扫描...", "STOP")
    
    def scan_thread_func(self):
        """扫描线程"""
        try:
            # 阶段1: 扫描所有文件夹
            self.all_videos = []
            total_folders = len(self.folders)
            
            # 创建比较引擎（用于控制暂停/停止）
            self.comparison_engine = ComparisonEngine(self.config)
            
            for i, folder in enumerate(self.folders):
                # 检查是否停止
                if self.comparison_engine.is_stopped():
                    self.root.after(0, lambda: self.log_message("扫描已停止", "INFO"))
                    self.root.after(0, self.scan_complete)
                    return
                
                def scan_progress(current, total, msg, is_error=False):
                    # 检查暂停
                    if self.comparison_engine:
                        self.comparison_engine._pause_event.wait()
                    
                    folder_progress = (i + current / total) / total_folders * 50  # 扫描阶段占50%
                    self.root.after(0, lambda p=folder_progress, m=msg: self.update_progress(p, m))
                    if is_error:
                        self.root.after(0, lambda m=msg: self.log_message(m, "ERROR"))
                    else:
                        self.root.after(0, lambda m=msg: self.log_message(m, "SCAN"))
                
                self.root.after(0, lambda idx=i+1, tot=total_folders: self.log_message(f"扫描第 {idx}/{tot} 个文件夹...", "SCAN"))
                videos = VideoScanner.scan_folder(folder, progress_callback=scan_progress)
                self.all_videos.extend(videos)
                
                self.root.after(0, lambda v=len(videos): self.log_message(f"该文件夹找到 {v} 个视频文件", "INFO"))
            
            if self.comparison_engine.is_stopped():
                self.root.after(0, self.scan_complete)
                return
            
            self.root.after(0, lambda: self.log_message(f"扫描完成，共找到 {len(self.all_videos)} 个视频文件", "INFO"))
            self.root.after(0, lambda: self.update_progress(50, "正在分析重复文件..."))
            
            # 阶段2: 执行比较
            self.config = {
                'use_name': self.use_name_var.get(),
                'use_size': self.use_size_var.get(),
                'use_duration': self.use_duration_var.get(),
                'name_threshold': self.name_threshold_var.get(),
                'size_tolerance': self.size_tolerance_var.get(),
                'duration_tolerance_seconds': self.duration_tolerance_seconds_var.get()
            }
            
            # 更新配置
            self.comparison_engine.config = self.config
            
            def compare_progress(processed, total, msg, is_info=False):
                compare_progress_pct = 50 + (processed / total * 50)  # 比较阶段占50%
                self.root.after(0, lambda p=compare_progress_pct, m=msg: self.update_progress(p, m))
                if not is_info:
                    elapsed = time.time() - self.scan_start_time if self.scan_start_time else 0
                    if processed > 0:
                        estimated_total = elapsed / (processed / total)
                        remaining = estimated_total - elapsed
                        eta = datetime.now().timestamp() + remaining
                        eta_str = datetime.fromtimestamp(eta).strftime("%H:%M:%S")
                        detail = f"已处理: {processed}/{total} | 已用时: {int(elapsed)}秒 | 预计完成: {eta_str}"
                        self.root.after(0, lambda d=detail: self.progress_detail_var.set(d))
            
            self.duplicates = self.comparison_engine.find_duplicates(
                self.all_videos, 
                progress_callback=compare_progress
            )
            
            # 更新UI
            self.root.after(0, self.display_results)
            
        except Exception as e:
            error_msg = f"扫描失败: {str(e)}"
            self.root.after(0, lambda: self.log_message(error_msg, "ERROR"))
            self.root.after(0, lambda: messagebox.showerror("错误", error_msg))
        finally:
            self.root.after(0, self.scan_complete)
    
    def update_progress(self, percentage: float, status: str):
        """更新进度"""
        self.progress_bar['value'] = percentage
        self.progress_status_var.set(status)
    
    def display_results(self):
        """显示结果"""
        # 清空之前的结果和缩略图
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.thumbnails.clear()
        
        # 显示统计信息
        total_videos = len(self.all_videos)
        duplicate_groups = len(self.duplicates)
        duplicate_files = sum(len(group) for group in self.duplicates)
        
        stats_text = f"共扫描 {total_videos} 个视频文件，发现 {duplicate_groups} 组重复文件，涉及 {duplicate_files} 个文件"
        self.stats_label.config(text=stats_text)
        
        self.log_message(stats_text, "RESULT")
        
        # 检查时长获取情况
        videos_with_duration = sum(1 for v in self.all_videos if v.duration > 0)
        videos_without_duration = sum(1 for v in self.all_videos if v.duration == 0)
        self.log_message(f"时长统计: {videos_with_duration} 个文件有时长, {videos_without_duration} 个文件时长为0", "INFO")
        
        if videos_without_duration > 0:
            self.log_message("⚠️ 警告：部分视频无法获取时长，请安装视频处理工具", "WARNING")
            self.log_message("  推荐安装: pip install mutagen opencv-python Pillow", "INFO")
        
        # 显示重复文件组
        self.log_message("正在生成缩略图...", "INFO")
        thumbnail_count = 0
        
        for group_idx, group in enumerate(self.duplicates, 1):
            # 分组标题行（只显示一次分组号）
            parent_id = self.result_tree.insert(
                "", tk.END, 
                text="📁",  # 序号显示在#0列
                values=("", "📁", "---", "---", "---", "---"),  # 选择列为空
                tags=("group_header",)
            )
            
            for idx_in_group, video in enumerate(group, 1):
                # ★ 优化：只为确认重复的文件生成缩略图
                thumbnail = self._generate_thumbnail(video.file_path)
                thumbnail_count += 1
                
                # ★ 插入文件行：只有当thumbnail是PhotoImage对象时才使用image参数
                if isinstance(thumbnail, object) and hasattr(thumbnail, '_PhotoImage__photo'):
                    # 是有效的PhotoImage对象
                    item_id = self.result_tree.insert(
                        "", tk.END,
                        text="",  # 文本留空
                        image=thumbnail,  # ✓ 使用图片
                        values=(
                            "☐",  # 未选中状态的复选框
                            "",  # 分组（空，因为父行已显示）
                            video.folder_path,  # 所属文件夹
                            video.file_name,  # 文件名
                            f"{video.get_size_mb():.2f} MB",  # 大小
                            video.get_duration_str()  # 时长
                        ),
                        tags=("duplicate_file", video.file_path)  # ★ 同时保存样式标记和完整路径
                    )
                else:
                    # thumbnail是字符串（如"🎬"），不使用image参数
                    item_id = self.result_tree.insert(
                        "", tk.END,
                        text=thumbnail,  # ✓ 使用文本emoji
                        values=(
                            "☐",  # 未选中状态的复选框
                            "",  # 分组（空，因为父行已显示）
                            video.folder_path,  # 所属文件夹
                            video.file_name,  # 文件名
                            f"{video.get_size_mb():.2f} MB",  # 大小
                            video.get_duration_str()  # 时长
                        ),
                        tags=("duplicate_file", video.file_path)  # ★ 同时保存样式标记和完整路径
                    )
                
                # 存储文件路径到item_id的映射，用于后续操作
                self.result_tree.item(item_id, tags=(video.file_path,))
        
        # 配置标签样式 - 高亮显示相同的时长和大小
        self.result_tree.tag_configure("group_header", background="#E8F4FD", foreground="#1976D2", font=("微软雅黑", 9, "bold"))
        self.result_tree.tag_configure("duplicate_file", background="#FFF3E0", foreground="#E65100")
        
        # ★ 设置行高以适应缩略图显示
        style = ttk.Style()
        style.configure("Treeview", rowheight=65)  # 增加行高以容纳80x60的缩略图
        
        self.log_message(f"缩略图生成完成，共生成 {thumbnail_count} 个", "INFO")
        self.log_message(f"结果展示完成，共 {duplicate_groups} 组重复文件", "INFO")
    
    def _generate_thumbnail(self, file_path: str) -> str:
        """生成视频首帧缩略图（带缓存和重试机制）"""
        # 检查缓存
        if file_path in self.thumbnails:
            return self.thumbnails[file_path]
        
        try:
            import cv2
            from PIL import Image, ImageTk
            
            # 使用OpenCV读取视频
            cap = cv2.VideoCapture(file_path)
            if not cap.isOpened():
                self.log_message(f"无法打开视频文件: {os.path.basename(file_path)}", "WARNING")
                return "🎬"
            
            # ★ 尝试多次读取，避免黑色帧
            frame = None
            max_attempts = 5
            
            for attempt in range(max_attempts):
                ret, temp_frame = cap.read()
                if not ret or temp_frame is None:
                    break
                
                # 检查是否为全黑帧
                if cv2.countNonZero(cv2.cvtColor(temp_frame, cv2.COLOR_BGR2GRAY)) > 100:
                    frame = temp_frame
                    break
                
                # 如果是黑色帧，继续尝试下一帧
                if attempt < max_attempts - 1:
                    continue
            
            cap.release()
            
            if frame is None:
                self.log_message(f"无法获取有效帧: {os.path.basename(file_path)}", "WARNING")
                return "🎬"
            
            # 转换颜色空间 (BGR -> RGB)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # 转换为PIL Image
            image = Image.fromarray(frame_rgb)
            
            # 调整大小为 80x60 (保持宽高比)
            width, height = image.size
            aspect_ratio = width / height
            new_width = 80
            new_height = int(new_width / aspect_ratio)
            if new_height > 60:
                new_height = 60
                new_width = int(new_height * aspect_ratio)
            
            image = image.resize((new_width, new_height), Image.LANCZOS)
            
            # 转换为Tkinter PhotoImage
            photo = ImageTk.PhotoImage(image)
            
            # 存储引用防止被垃圾回收
            self.thumbnails[file_path] = photo
            
            return photo
            
        except ImportError:
            # 如果没有安装必要的库，返回图标
            return "🎬"
        except Exception as e:
            # 如果生成失败，返回图标并记录日志
            self.log_message(f"缩略图生成失败 {os.path.basename(file_path)}: {str(e)[:50]}", "WARNING")
            return "🎬"
    
    def scan_complete(self):
        """扫描完成"""
        self.start_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.DISABLED, text="⏸️ 暂停")
        self.stop_btn.config(state=tk.DISABLED)
        self.progress_status_var.set("扫描完成！")
        self.progress_detail_var.set("")
        self.progress_bar['value'] = 0  # ★ 重置进度条
        
        elapsed = time.time() - self.scan_start_time if self.scan_start_time else 0
        self.log_message(f"扫描完成，总用时: {int(elapsed)}秒", "COMPLETE")
    
    def save_config(self):
        """保存配置"""
        self.config = {
            'use_name': self.use_name_var.get(),
            'use_size': self.use_size_var.get(),
            'use_duration': self.use_duration_var.get(),
            'name_threshold': self.name_threshold_var.get(),
            'size_tolerance': self.size_tolerance_var.get(),
            'duration_tolerance_seconds': self.duration_tolerance_seconds_var.get()
        }
        ConfigManager.save_config(self.config)
        self.log_message("配置已保存", "INFO")
        messagebox.showinfo("成功", "配置已保存！")
    
    def export_results(self):
        """导出结果"""
        if not self.duplicates:
            messagebox.showwarning("警告", "没有可导出的结果！")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="导出结果",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("CSV文件", "*.csv")]
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("视频文件去重报告\n")
                f.write("=" * 80 + "\n\n")
                
                f.write(f"扫描时间: {self._get_current_time()}\n")
                f.write(f"扫描文件夹数: {len(self.folders)}\n")
                f.write(f"总视频数: {len(self.all_videos)}\n")
                f.write(f"重复组数: {len(self.duplicates)}\n\n")
                
                f.write("配置信息:\n")
                f.write(f"  - 使用名称比较: {'是' if self.config['use_name'] else '否'}\n")
                f.write(f"  - 使用大小比较: {'是' if self.config['use_size'] else '否'}\n")
                f.write(f"  - 使用时长比较: {'是' if self.config['use_duration'] else '否'}\n")
                f.write(f"  - 名称相似度阈值: {int(self.config['name_threshold']*100)}%\n")
                f.write(f"  - 大小相似度阈值: {int(self.config['size_tolerance']*100)}%\n")
                f.write(f"  - 时长容差: {self.config.get('duration_tolerance_seconds', 2.0)}秒\n\n")
                
                f.write("=" * 80 + "\n")
                f.write("重复文件列表:\n")
                f.write("=" * 80 + "\n\n")
                
                for idx, group in enumerate(self.duplicates, 1):
                    f.write(f"\n【第 {idx} 组】\n")
                    f.write("-" * 80 + "\n")
                    
                    for video in group:
                        f.write(f"  文件名: {video.file_name}\n")
                        f.write(f"  完整路径: {video.file_path}\n")
                        f.write(f"  文件大小: {video.get_size_mb():.2f} MB\n")
                        f.write(f"  视频时长: {video.get_duration_str()} ({video.duration:.2f}秒)\n")
                        f.write(f"  所属文件夹: {video.folder_path}\n")
                        f.write("\n")
            
            self.log_message(f"结果已导出到: {file_path}", "EXPORT")
            messagebox.showinfo("成功", f"结果已导出到:\n{file_path}")
        
        except Exception as e:
            error_msg = f"导出失败: {str(e)}"
            self.log_message(error_msg, "ERROR")
            messagebox.showerror("错误", error_msg)
    
    def clear_results(self):
        """清除结果"""
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.duplicates.clear()
        self.stats_label.config(text="尚未扫描")
        self.progress_status_var.set("就绪")
        self.progress_detail_var.set("")
        self.progress_bar['value'] = 0
        self.log_message("结果已清除", "INFO")
    
    def on_tree_double_click(self, event):
        """树形视图双击事件 - 用默认程序打开文件"""
        print(f"[DEBUG] ========== 双击事件触发 ==========")  # ★ 调试日志
        
        # 获取点击的项
        item = self.result_tree.identify_row(event.y)
        if not item:
            print(f"[DEBUG] 未找到点击的item")  # ★ 调试日志
            return
        
        print(f"[DEBUG] 点击的item ID: {item}")  # ★ 调试日志
        
        values = self.result_tree.item(item, 'values')
        print(f"[DEBUG] values: {values}")  # ★ 调试日志
        
        if not values or len(values) < 4:
            print(f"[DEBUG] values无效或长度不足")  # ★ 调试日志
            return
        
        # 新列顺序：选择(0), 分组(1), 所属文件夹(2), 文件名(3), 大小(4), 时长(5)
        checkbox = values[0]
        group = values[1]
        folder_path = values[2]
        file_name = values[3]
        
        print(f"[DEBUG] checkbox={checkbox}, group={group}")  # ★ 调试日志
        print(f"[DEBUG] folder_path={folder_path}, file_name={file_name}")  # ★ 调试日志
        
        if folder_path == "---" or file_name == "---":
            print(f"[DEBUG] 检测到分组标题行，拒绝操作")  # ★ 调试日志
            messagebox.showwarning("提示", "请选择具体的文件，而不是分组标题")
            return
        
        # ★ 优先从tags中获取完整路径（最可靠）
        tags = self.result_tree.item(item, 'tags')
        print(f"[DEBUG] tags: {tags}")  # ★ 调试日志
        print(f"[DEBUG] tags类型: {type(tags)}, 长度: {len(tags) if tags else 0}")  # ★ 调试日志
        
        if tags and len(tags) > 1:
            actual_path = tags[1]  # tags[0]是样式标记，tags[1]是文件路径
            print(f"[DEBUG] ✓ 从tags获取路径: {actual_path}")  # ★ 调试日志
            print(f"[DEBUG] 路径是否存在: {os.path.exists(actual_path)}")  # ★ 调试日志
            self.log_message(f"双击打开: {file_name}", "INFO")
        else:
            print(f"[DEBUG] ✗ tags无效，使用备用方案")  # ★ 调试日志
            # 备用方案：使用glob查找
            import glob
            matching_files = glob.glob(os.path.join(folder_path, file_name + ".*"))
            if not matching_files:
                print(f"[DEBUG] glob未找到文件")  # ★ 调试日志
                messagebox.showerror("错误", f"未找到文件: {file_name}")
                return
            actual_path = matching_files[0]
            print(f"[DEBUG] ✓ 从glob获取路径: {actual_path}")  # ★ 调试日志
        
        try:
            # ★ 用默认程序打开文件（不需要勾选复选框）
            print(f"[DEBUG] 准备打开文件: {actual_path}")  # ★ 调试日志
            if os.name == 'nt':  # Windows
                os.startfile(actual_path)
                print(f"[DEBUG] ✓ 已调用 os.startfile")  # ★ 调试日志
                self.log_message(f"已打开文件: {file_name}", "INFO")
            elif os.name == 'posix':  # macOS/Linux
                import subprocess
                subprocess.Popen(['xdg-open', actual_path])
                self.log_message(f"已打开文件: {file_name}", "INFO")
        except Exception as e:
            print(f"[DEBUG] ✗ 打开失败: {e}")  # ★ 调试日志
            self.log_message(f"打开文件失败: {e}", "ERROR")
            messagebox.showerror("错误", f"打开文件失败:\n{e}")
        
        print(f"[DEBUG] ========== 双击事件结束 ==========\n")  # ★ 调试日志
    
    def open_selected_file_location(self):
        """打开选中文件的位置（使用复选框）"""
        # 获取所有勾选的文件
        selected_items = []
        for item in self.result_tree.get_children():
            values = self.result_tree.item(item, 'values')
            if values and values[0] == "☑" and values[2] != "---":  # 检查所属文件夹列
                selected_items.append(item)
        
        if not selected_items:
            messagebox.showwarning("提示", "请先勾选要打开的文件")
            return
        
        opened_count = 0
        for item_id in selected_items:
            values = self.result_tree.item(item_id, 'values')
            if not values or len(values) < 4:
                continue
            
            # 新列顺序：选择(0), 分组(1), 所属文件夹(2), 文件名(3), 大小(4), 时长(5)
            folder_path = values[2]
            file_name = values[3]
            
            if folder_path == "---" or file_name == "---":
                continue
            
            try:
                import subprocess
                import glob
                
                # 查找实际文件
                matching_files = glob.glob(os.path.join(folder_path, file_name + ".*"))
                if matching_files:
                    actual_path = matching_files[0]
                    if os.name == 'nt':  # Windows
                        subprocess.Popen(f'explorer /select,"{actual_path}"')
                        opened_count += 1
                else:
                    self.log_message(f"未找到文件: {file_name}", "WARNING")
            
            except Exception as e:
                self.log_message(f"打开失败 {file_name}: {e}", "ERROR")
        
        if opened_count > 0:
            self.log_message(f"已打开 {opened_count} 个文件位置", "INFO")
        else:
            messagebox.showwarning("提示", "没有可打开的文件")
    
    def delete_selected_file(self):
        """批量删除选中的文件（使用复选框，只确认一次）"""
        # 获取所有勾选的文件
        files_to_delete = []
        for item in self.result_tree.get_children():
            values = self.result_tree.item(item, 'values')
            if values and values[0] == "☑" and values[2] != "---":  # 检查所属文件夹列
                # 新列顺序：选择(0), 分组(1), 所属文件夹(2), 文件名(3), 大小(4), 时长(5)
                folder_path = values[2]
                file_name = values[3]
                file_size = values[4]
                
                if folder_path == "---" or file_name == "---":
                    continue
                
                # ★ 从tags中获取完整文件路径（更可靠）
                tags = self.result_tree.item(item, 'tags')
                if tags and len(tags) > 0:
                    actual_path = tags[0]
                    self.log_message(f"准备删除: {file_name} -> {actual_path}", "INFO")
                    files_to_delete.append((item, actual_path, file_name, file_size))
                else:
                    # 备用方案：使用glob查找
                    import glob
                    matching_files = glob.glob(os.path.join(folder_path, file_name + ".*"))
                    if matching_files:
                        actual_path = matching_files[0]
                        files_to_delete.append((item, actual_path, file_name, file_size))
        
        if not files_to_delete:
            messagebox.showwarning("提示", "请先勾选要删除的文件")
            return
        
        # 只显示一次确认对话框，列出所有文件
        confirm_msg = f"⚠️ 警告：此操作将永久删除 {len(files_to_delete)} 个文件！\n\n"
        
        # 如果文件数量少，列出详细信息
        if len(files_to_delete) <= 10:
            for _, path, name, size in files_to_delete:
                confirm_msg += f"• {name} ({size})\n"
            confirm_msg += "\n"
        else:
            confirm_msg += f"（共 {len(files_to_delete)} 个文件，仅显示前10个）\n\n"
            for _, path, name, size in files_to_delete[:10]:
                confirm_msg += f"• {name} ({size})\n"
            confirm_msg += f"... 等 {len(files_to_delete) - 10} 个文件\n\n"
        
        confirm_msg += "确定要删除这些文件吗？"
        
        result = messagebox.askyesno(
            "确认批量删除",
            confirm_msg,
            icon=messagebox.WARNING
        )
        
        if not result:
            self.log_message("取消批量删除操作", "INFO")
            return
        
        # 执行批量删除
        deleted_count = 0
        failed_count = 0
        
        for item_id, file_path, file_name, file_size in files_to_delete:
            try:
                self.log_message(f"正在删除: {file_path}", "INFO")
                if os.path.exists(file_path):
                    # 尝试移动到回收站
                    try:
                        from send2trash import send2trash
                        send2trash(file_path)
                        self.log_message(f"已移至回收站: {file_name}", "INFO")
                    except ImportError:
                        # 直接删除
                        os.remove(file_path)
                        self.log_message(f"已永久删除: {file_name}", "WARNING")
                    
                    # 从树形视图中移除
                    self.result_tree.delete(item_id)
                    deleted_count += 1
                else:
                    self.log_message(f"文件不存在: {file_path}", "ERROR")
                    failed_count += 1
            
            except PermissionError:
                self.log_message(f"无法删除（被占用）: {file_name}", "ERROR")
                failed_count += 1
            except Exception as e:
                self.log_message(f"删除失败 {file_name}: {e}", "ERROR")
                failed_count += 1
        
        # 只显示一次总结消息
        summary_msg = f"删除完成\n\n成功: {deleted_count} 个文件"
        if failed_count > 0:
            summary_msg += f"\n失败: {failed_count} 个文件"
        summary_msg += "\n\n提示: 安装 send2trash 库可启用回收站功能\npip install send2trash"
        
        self.log_message(f"批量删除完成: 成功{deleted_count}, 失败{failed_count}", "INFO")
        messagebox.showinfo("删除完成", summary_msg)
        
        # 更新统计信息
        if deleted_count > 0:
            self.update_stats_after_delete(deleted_count)
    
    def update_stats_after_delete(self, deleted_count: int):
        """删除文件后更新统计信息"""
        import os
        
        # 重新计算重复组数（新列顺序：选择(0), 分组(1), 所属文件夹(2), ...）
        remaining_items = len([item for item in self.result_tree.get_children() 
                              if self.result_tree.item(item, 'values')[2] != "---"])
        
        duplicate_groups = len([item for item in self.result_tree.get_children() 
                               if self.result_tree.item(item, 'values')[2] == "---"])
        
        total_videos = len(self.all_videos) - deleted_count  # 减去已删除的文件
        self.all_videos = [v for v in self.all_videos if os.path.exists(v.file_path)]
        
        stats_text = f"共扫描 {total_videos} 个视频文件，发现 {duplicate_groups} 组重复文件，涉及 {remaining_items} 个文件"
        self.stats_label.config(text=stats_text)
        self.log_message(f"统计信息已更新: {stats_text}", "INFO")
    
    def on_tree_click(self, event):
        """处理树形视图点击事件（复选框切换）"""
        # 获取点击的项
        item = self.result_tree.identify_row(event.y)
        if not item:
            return
        
        # 获取点击的列
        column = self.result_tree.identify_column(event.x)
        
        # 如果点击的是"选择"列（第1列，column='#1'）
        if column == '#1':
            values = self.result_tree.item(item, 'values')
            if not values or len(values) < 1:
                return
            
            checkbox = values[0]
            
            # 切换复选框状态
            if checkbox == "☐":
                new_checkbox = "☑"
            elif checkbox == "☑":
                new_checkbox = "☐"
            else:
                return  # 分组标题，不处理
            
            # 更新显示
            new_values = list(values)
            new_values[0] = new_checkbox
            self.result_tree.item(item, values=tuple(new_values))
            
            # 更新按钮状态
            self.update_button_state()
    
    def update_button_state(self):
        """根据选中状态更新按钮"""
        # 统计选中的文件数量
        selected_count = 0
        for item in self.result_tree.get_children():
            values = self.result_tree.item(item, 'values')
            if values and values[0] == "☑" and values[2] != "---":  # 检查所属文件夹列
                selected_count += 1
        
        if selected_count > 0:
            self.open_file_btn.config(state=tk.NORMAL)
            self.delete_file_btn.config(state=tk.NORMAL)
            if selected_count > 1:
                self.delete_file_btn.config(text=f"🗑️ 删除选中({selected_count})")
            else:
                self.delete_file_btn.config(text="🗑️ 删除选中文件")
        else:
            self.open_file_btn.config(state=tk.DISABLED)
            self.delete_file_btn.config(state=tk.DISABLED)
            self.delete_file_btn.config(text="️ 删除选中文件")
    
    @staticmethod
    def _get_current_time() -> str:
        """获取当前时间字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def show_folder_manager(self):
        """显示文件夹管理弹窗"""
        dialog = tk.Toplevel(self.root)
        dialog.title("📁 文件夹管理")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 说明标签
        ttk.Label(
            main_frame,
            text="选择要扫描的文件夹（支持多个文件夹）",
            font=("微软雅黑", 10, "bold")
        ).pack(anchor=tk.W, pady=5)
        
        # 文件夹列表
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        folder_listbox = tk.Listbox(list_frame, font=("微软雅黑", 9))
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=folder_listbox.yview)
        folder_listbox.configure(yscrollcommand=scrollbar.set)
        
        # 加载现有文件夹
        for folder in self.folders:
            folder_listbox.insert(tk.END, folder)
        
        folder_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        def add_folder():
            initial_dir = self.last_folder_path if self.last_folder_path else ""
            print(f"[DEBUG] 打开文件夹对话框，initial_dir: {initial_dir}")  # ★ 调试日志
            
            folder = filedialog.askdirectory(
                title="选择要扫描的文件夹",
                initialdir=initial_dir
            )
            
            if folder:
                print(f"[DEBUG] 用户选择了: {folder}")  # ★ 调试日志
                
                # ★ 记忆本次选择的路径（用于下次打开）并持久化保存
                self.last_folder_path = os.path.dirname(folder)
                print(f"[DEBUG] 保存 last_folder_path: {self.last_folder_path}")  # ★ 调试日志
                
                ConfigManager.save_last_folder_path(self.last_folder_path)  # ★ 保存到配置文件
                print(f"[DEBUG] 已调用 save_last_folder_path")  # ★ 调试日志
                
                if folder not in self.folders:
                    self.folders.append(folder)
                    folder_listbox.insert(tk.END, folder)
                    
                    # ★ 保存文件夹列表到配置文件
                    ConfigManager.save_folders(self.folders)
                    print(f"[DEBUG] 已保存 {len(self.folders)} 个文件夹到配置文件")
                    
                    self.log_message(f"已添加文件夹: {folder}")
                    self.folder_count_var.set(f"已选择 {len(self.folders)} 个文件夹")
                else:
                    messagebox.showwarning("提示", "文件夹已存在")
        
        def remove_folder():
            selection = folder_listbox.curselection()
            if selection:
                index = selection[0]
                removed = self.folders.pop(index)
                folder_listbox.delete(index)
                
                # ★ 保存更新后的文件夹列表
                ConfigManager.save_folders(self.folders)
                print(f"[DEBUG] 已保存 {len(self.folders)} 个文件夹到配置文件")
                
                self.log_message(f"已移除文件夹: {removed}")
                self.folder_count_var.set(f"已选择 {len(self.folders)} 个文件夹")
            else:
                messagebox.showwarning("提示", "请先选择要移除的文件夹")
        
        def clear_folders():
            if messagebox.askyesno("确认", f"确定要清空所有 {len(self.folders)} 个文件夹吗？"):
                self.folders.clear()
                folder_listbox.delete(0, tk.END)
                
                # ★ 保存空的文件夹列表
                ConfigManager.save_folders(self.folders)
                print("[DEBUG] 已清空文件夹列表并保存到配置文件")
                
                self.log_message("已清空文件夹列表")
                self.folder_count_var.set("未选择文件夹")
        
        ttk.Button(btn_frame, text="➕ 添加文件夹", command=add_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="➖ 移除选中", command=remove_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="🗑️ 清空全部", command=clear_folders).pack(side=tk.LEFT, padx=2)
        
        # 关闭按钮
        ttk.Button(btn_frame, text="✓ 完成", command=dialog.destroy).pack(side=tk.RIGHT, padx=2)
        
        # 更新状态
        self.folder_count_var.set(f"已选择 {len(self.folders)} 个文件夹")
    
    def show_config_dialog(self):
        """显示比较配置弹窗"""
        dialog = tk.Toplevel(self.root)
        dialog.title("⚙️ 比较配置")
        dialog.geometry("500x450")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 主框架
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 标题
        ttk.Label(
            main_frame,
            text="视频相似度检测配置",
            font=("微软雅黑", 12, "bold")
        ).pack(anchor=tk.W, pady=5)
        
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 比较维度
        ttk.Label(main_frame, text="比较维度:", font=("微软雅黑", 10, "bold")).pack(anchor=tk.W)
        
        check_frame = ttk.Frame(main_frame)
        check_frame.pack(fill=tk.X, pady=10, padx=20)
        
        use_name_var = tk.BooleanVar(value=self.use_name_var.get())
        use_size_var = tk.BooleanVar(value=self.use_size_var.get())
        use_duration_var = tk.BooleanVar(value=self.use_duration_var.get())
        
        ttk.Checkbutton(check_frame, text="✓ 视频名称", variable=use_name_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(check_frame, text="✓ 文件大小", variable=use_size_var).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(check_frame, text="✓ 视频时长", variable=use_duration_var).pack(anchor=tk.W, pady=2)
        
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 相似度设置
        ttk.Label(main_frame, text="相似度阈值:", font=("微软雅黑", 10, "bold")).pack(anchor=tk.W)
        
        slider_frame = ttk.Frame(main_frame)
        slider_frame.pack(fill=tk.X, pady=10, padx=20)
        
        # 名称相似度
        name_thresh_frame = ttk.Frame(slider_frame)
        name_thresh_frame.pack(fill=tk.X, pady=5)
        ttk.Label(name_thresh_frame, text="名称相似度:", width=12).pack(side=tk.LEFT)
        name_threshold_var = tk.DoubleVar(value=self.name_threshold_var.get())
        name_scale = ttk.Scale(
            name_thresh_frame, 
            from_=0.5, to_=1.0, 
            variable=name_threshold_var,
            orient=tk.HORIZONTAL
        )
        name_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        name_label = ttk.Label(name_thresh_frame, text=f"{int(name_threshold_var.get()*100)}%", width=5)
        name_label.pack(side=tk.LEFT)
        name_scale.configure(command=lambda v: name_label.config(text=f"{int(float(v)*100)}%"))
        
        # 大小相似度
        size_thresh_frame = ttk.Frame(slider_frame)
        size_thresh_frame.pack(fill=tk.X, pady=5)
        ttk.Label(size_thresh_frame, text="大小相似度:", width=12).pack(side=tk.LEFT)
        size_tolerance_var = tk.DoubleVar(value=self.size_tolerance_var.get())
        size_scale = ttk.Scale(
            size_thresh_frame,
            from_=0.5, to_=1.0,
            variable=size_tolerance_var,
            orient=tk.HORIZONTAL
        )
        size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        size_label = ttk.Label(size_thresh_frame, text=f"{int(size_tolerance_var.get()*100)}%", width=5)
        size_label.pack(side=tk.LEFT)
        size_scale.configure(command=lambda v: size_label.config(text=f"{int(float(v)*100)}%"))
        
        # 时长容差
        dur_tol_frame = ttk.Frame(slider_frame)
        dur_tol_frame.pack(fill=tk.X, pady=5)
        ttk.Label(dur_tol_frame, text="时长容差(秒):", width=12).pack(side=tk.LEFT)
        duration_tolerance_var = tk.DoubleVar(value=self.duration_tolerance_seconds_var.get())
        dur_scale = ttk.Scale(
            dur_tol_frame,
            from_=0, to=10,
            variable=duration_tolerance_var,
            orient=tk.HORIZONTAL
        )
        dur_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        dur_label = ttk.Label(dur_tol_frame, text=f"{duration_tolerance_var.get():.1f}秒", width=8)
        dur_label.pack(side=tk.LEFT)
        dur_scale.configure(command=lambda v: dur_label.config(text=f"{float(v):.1f}秒"))
        
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        # 说明文本
        info_text = (
            "💡 提示:\n"
            "• 名称相似度: 文件名相似程度（0.5-1.0）\n"
            "• 大小相似度: 文件大小差异容忍度\n"
            "• 时长容差: 允许的时间误差范围（秒）\n"
            "• 建议至少勾选2个比较维度以提高准确性"
        )
        ttk.Label(
            main_frame,
            text=info_text,
            font=("微软雅黑", 9),
            foreground="gray",
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=10)
        
        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        def save_config():
            # 保存配置到主界面变量
            self.use_name_var.set(use_name_var.get())
            self.use_size_var.set(use_size_var.get())
            self.use_duration_var.set(use_duration_var.get())
            self.name_threshold_var.set(name_threshold_var.get())
            self.size_tolerance_var.set(size_tolerance_var.get())
            self.duration_tolerance_seconds_var.set(duration_tolerance_var.get())
            
            # 更新标签显示
            self.name_thresh_label.config(text=f"{int(name_threshold_var.get()*100)}%")
            self.size_thresh_label.config(text=f"{int(size_tolerance_var.get()*100)}%")
            self.dur_tol_label.config(text=f"{duration_tolerance_var.get():.1f}秒")
            
            self.log_message("配置已更新", "INFO")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="💾 保存配置", command=save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ 取消", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)


def main():
    """主函数"""
    root = tk.Tk()
    app = VideoDuplicateFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
































