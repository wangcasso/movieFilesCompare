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
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading


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
    def scan_folder(folder_path: str) -> List[VideoInfo]:
        """扫描文件夹中的所有视频文件"""
        videos = []
        folder = Path(folder_path)
        
        for ext in VideoScanner.VIDEO_EXTENSIONS:
            for video_file in folder.rglob(f'*{ext}'):
                try:
                    stat = video_file.stat()
                    video_info = VideoInfo(
                        file_path=str(video_file.absolute()),
                        file_name=video_file.stem,  # 不含扩展名
                        file_size=stat.st_size,
                        duration=VideoScanner._get_video_duration(str(video_file)),
                        folder_path=str(folder_path)
                    )
                    videos.append(video_info)
                except Exception as e:
                    print(f"读取文件失败 {video_file}: {e}")
        
        return videos
    
    @staticmethod
    def _get_video_duration(file_path: str) -> float:
        """获取视频时长（秒）"""
        try:
            # 尝试使用ffprobe
            import subprocess
            cmd = [
                'ffprobe', '-v', 'error', '-show_entries',
                'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except:
            pass
        
        # 如果ffprobe不可用，返回0（仅基于名称和大小比较）
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
    def duration_similarity(dur1: float, dur2: float) -> float:
        """计算视频时长的相似度 (0-1之间)"""
        if dur1 == 0 and dur2 == 0:
            return 1.0
        if dur1 == 0 or dur2 == 0:
            return 0.0
        
        max_dur = max(dur1, dur2)
        min_dur = min(dur1, dur2)
        
        return min_dur / max_dur


class ComparisonEngine:
    """比较引擎 - 核心逻辑"""
    
    def __init__(self, config: dict):
        self.config = config
        self.calculator = SimilarityCalculator()
    
    def find_duplicates(self, all_videos: List[VideoInfo]) -> List[List[VideoInfo]]:
        """查找重复的视频文件组"""
        duplicates = []
        used = set()
        
        # 获取配置参数
        use_name = self.config.get('use_name', True)
        use_size = self.config.get('use_size', True)
        use_duration = self.config.get('use_duration', True)
        name_threshold = self.config.get('name_threshold', 0.8)
        size_tolerance = self.config.get('size_tolerance', 0.95)  # 95%相似
        duration_tolerance = self.config.get('duration_tolerance', 0.95)  # 95%相似
        
        for i in range(len(all_videos)):
            if i in used:
                continue
            
            group = [all_videos[i]]
            
            for j in range(i + 1, len(all_videos)):
                if j in used:
                    continue
                
                video1 = all_videos[i]
                video2 = all_videos[j]
                
                is_match = True
                
                # 检查名称相似度
                if use_name:
                    name_sim = self.calculator.name_similarity(
                        video1.file_name, video2.file_name
                    )
                    if name_sim < name_threshold:
                        is_match = False
                
                # 检查大小相似度
                if use_size:
                    size_sim = self.calculator.size_similarity(
                        video1.file_size, video2.file_size
                    )
                    if size_sim < size_tolerance:
                        is_match = False
                
                # 检查时长相似度
                if use_duration:
                    dur_sim = self.calculator.duration_similarity(
                        video1.duration, video2.duration
                    )
                    if dur_sim < duration_tolerance:
                        is_match = False
                
                if is_match:
                    group.append(video2)
                    used.add(j)
            
            if len(group) > 1:
                duplicates.append(group)
                used.add(i)
        
        return duplicates


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
            'duration_tolerance': 0.95
        }
        
        if os.path.exists(ConfigManager.CONFIG_FILE):
            try:
                with open(ConfigManager.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return default_config
        
        return default_config


class VideoDuplicateFinderApp:
    """主应用程序界面"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("视频文件去重工具 v1.0")
        self.root.geometry("1000x700")
        
        # 数据存储
        self.folders = []
        self.all_videos = []
        self.duplicates = []
        self.config = ConfigManager.load_config()
        
        # 创建界面
        self._create_widgets()
        self._load_config_to_ui()
    
    def _create_widgets(self):
        """创建界面组件"""
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
            text="支持按名称、大小、时长多维度检测重复视频",
            font=("微软雅黑", 9),
            foreground="gray"
        )
        subtitle_label.pack()
        
        # 文件夹管理区域
        folder_frame = ttk.LabelFrame(self.root, text="📁 文件夹管理", padding="10")
        folder_frame.pack(fill=tk.X, padx=10, pady=5)
        
        btn_frame = ttk.Frame(folder_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(btn_frame, text="➕ 添加文件夹", command=self.add_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❌ 移除选中", command=self.remove_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="🗑️ 清空列表", command=self.clear_folders).pack(side=tk.LEFT, padx=5)
        
        # 文件夹列表
        list_frame = ttk.Frame(folder_frame)
        list_frame.pack(fill=tk.X, pady=5)
        
        self.folder_listbox = tk.Listbox(list_frame, height=4)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.folder_listbox.yview)
        self.folder_listbox.configure(yscrollcommand=scrollbar.set)
        
        self.folder_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 配置区域
        config_frame = ttk.LabelFrame(self.root, text="⚙️ 比较配置", padding="10")
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 比较选项
        option_frame = ttk.Frame(config_frame)
        option_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(option_frame, text="比较维度:", font=("微软雅黑", 10, "bold")).pack(anchor=tk.W)
        
        check_frame = ttk.Frame(option_frame)
        check_frame.pack(fill=tk.X, pady=5)
        
        self.use_name_var = tk.BooleanVar(value=True)
        self.use_size_var = tk.BooleanVar(value=True)
        self.use_duration_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(check_frame, text="✓ 视频名称", variable=self.use_name_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(check_frame, text="✓ 文件大小", variable=self.use_size_var).pack(side=tk.LEFT, padx=10)
        ttk.Checkbutton(check_frame, text="✓ 视频时长", variable=self.use_duration_var).pack(side=tk.LEFT, padx=10)
        
        # 相似度设置
        threshold_frame = ttk.Frame(config_frame)
        threshold_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(threshold_frame, text="相似度设置:", font=("微软雅黑", 10, "bold")).pack(anchor=tk.W)
        
        slider_frame = ttk.Frame(threshold_frame)
        slider_frame.pack(fill=tk.X, pady=5)
        
        # 名称相似度
        name_thresh_frame = ttk.Frame(slider_frame)
        name_thresh_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_thresh_frame, text="名称相似度阈值:", width=15).pack(side=tk.LEFT)
        self.name_threshold_var = tk.DoubleVar(value=0.8)
        name_scale = ttk.Scale(
            name_thresh_frame, 
            from_=0.5, to_=1.0, 
            variable=self.name_threshold_var,
            orient=tk.HORIZONTAL
        )
        name_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.name_thresh_label = ttk.Label(name_thresh_frame, text="80%", width=5)
        self.name_thresh_label.pack(side=tk.LEFT)
        name_scale.configure(command=lambda v: self.name_thresh_label.config(text=f"{int(float(v)*100)}%"))
        
        # 大小相似度
        size_thresh_frame = ttk.Frame(slider_frame)
        size_thresh_frame.pack(fill=tk.X, pady=2)
        ttk.Label(size_thresh_frame, text="大小相似度阈值:", width=15).pack(side=tk.LEFT)
        self.size_tolerance_var = tk.DoubleVar(value=0.95)
        size_scale = ttk.Scale(
            size_thresh_frame,
            from_=0.5, to_=1.0,
            variable=self.size_tolerance_var,
            orient=tk.HORIZONTAL
        )
        size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.size_thresh_label = ttk.Label(size_thresh_frame, text="95%", width=5)
        self.size_thresh_label.pack(side=tk.LEFT)
        size_scale.configure(command=lambda v: self.size_thresh_label.config(text=f"{int(float(v)*100)}%"))
        
        # 时长相似度
        dur_thresh_frame = ttk.Frame(slider_frame)
        dur_thresh_frame.pack(fill=tk.X, pady=2)
        ttk.Label(dur_thresh_frame, text="时长相似度阈值:", width=15).pack(side=tk.LEFT)
        self.duration_tolerance_var = tk.DoubleVar(value=0.95)
        dur_scale = ttk.Scale(
            dur_thresh_frame,
            from_=0.5, to_=1.0,
            variable=self.duration_tolerance_var,
            orient=tk.HORIZONTAL
        )
        dur_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.dur_thresh_label = ttk.Label(dur_thresh_frame, text="95%", width=5)
        self.dur_thresh_label.pack(side=tk.LEFT)
        dur_scale.configure(command=lambda v: self.dur_thresh_label.config(text=f"{int(float(v)*100)}%"))
        
        # 开始按钮
        action_frame = ttk.Frame(self.root, padding="10")
        action_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(
            action_frame,
            text="🚀 开始扫描",
            command=self.start_scan,
            style="Accent.TButton"
        )
        self.start_btn.pack(pady=10)
        
        # 进度条
        self.progress_var = tk.StringVar(value="就绪")
        self.progress_label = ttk.Label(action_frame, textvariable=self.progress_var)
        self.progress_label.pack()
        
        self.progress_bar = ttk.Progressbar(action_frame, mode='indeterminate')
        
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
        
        # 创建树形视图
        columns = ("分组", "文件名", "路径", "大小", "时长", "所属文件夹")
        self.result_tree = ttk.Treeview(result_list_frame, columns=columns, show="tree headings")
        
        self.result_tree.heading("#0", text="序号")
        self.result_tree.column("#0", width=50)
        
        for col in columns:
            self.result_tree.heading(col, text=col)
            if col == "文件名":
                self.result_tree.column(col, width=200)
            elif col == "路径":
                self.result_tree.column(col, width=250)
            elif col == "大小":
                self.result_tree.column(col, width=100)
            elif col == "时长":
                self.result_tree.column(col, width=80)
            else:
                self.result_tree.column(col, width=100)
        
        tree_scrollbar = ttk.Scrollbar(result_list_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=tree_scrollbar.set)
        
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 底部按钮
        bottom_frame = ttk.Frame(self.root, padding="10")
        bottom_frame.pack(fill=tk.X)
        
        ttk.Button(bottom_frame, text="💾 保存配置", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="📋 导出结果", command=self.export_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(bottom_frame, text="❌ 清除结果", command=self.clear_results).pack(side=tk.LEFT, padx=5)
    
    def _load_config_to_ui(self):
        """从配置加载到UI"""
        self.use_name_var.set(self.config.get('use_name', True))
        self.use_size_var.set(self.config.get('use_size', True))
        self.use_duration_var.set(self.config.get('use_duration', True))
        self.name_threshold_var.set(self.config.get('name_threshold', 0.8))
        self.size_tolerance_var.set(self.config.get('size_tolerance', 0.95))
        self.duration_tolerance_var.set(self.config.get('duration_tolerance', 0.95))
        
        # 更新标签
        self.name_thresh_label.config(text=f"{int(self.name_threshold_var.get()*100)}%")
        self.size_thresh_label.config(text=f"{int(self.size_tolerance_var.get()*100)}%")
        self.dur_thresh_label.config(text=f"{int(self.duration_tolerance_var.get()*100)}%")
    
    def add_folder(self):
        """添加文件夹"""
        folder = filedialog.askdirectory(title="选择要扫描的文件夹")
        if folder and folder not in self.folders:
            self.folders.append(folder)
            self.folder_listbox.insert(tk.END, folder)
    
    def remove_folder(self):
        """移除选中的文件夹"""
        selection = self.folder_listbox.curselection()
        if selection:
            index = selection[0]
            self.folders.pop(index)
            self.folder_listbox.delete(index)
    
    def clear_folders(self):
        """清空文件夹列表"""
        self.folders.clear()
        self.folder_listbox.delete(0, tk.END)
    
    def start_scan(self):
        """开始扫描"""
        if not self.folders:
            messagebox.showwarning("警告", "请先添加至少一个文件夹！")
            return
        
        # 禁用按钮
        self.start_btn.config(state=tk.DISABLED)
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.start()
        self.progress_var.set("正在扫描文件夹...")
        
        # 在后台线程中执行扫描
        thread = threading.Thread(target=self.scan_thread)
        thread.daemon = True
        thread.start()
    
    def scan_thread(self):
        """扫描线程"""
        try:
            # 扫描所有文件夹
            self.all_videos = []
            for i, folder in enumerate(self.folders):
                self.root.after(0, lambda: self.progress_var.set(f"正在扫描第 {i+1}/{len(self.folders)} 个文件夹..."))
                videos = VideoScanner.scan_folder(folder)
                self.all_videos.extend(videos)
            
            self.root.after(0, lambda: self.progress_var.set("正在分析重复文件..."))
            
            # 更新配置
            self.config = {
                'use_name': self.use_name_var.get(),
                'use_size': self.use_size_var.get(),
                'use_duration': self.use_duration_var.get(),
                'name_threshold': self.name_threshold_var.get(),
                'size_tolerance': self.size_tolerance_var.get(),
                'duration_tolerance': self.duration_tolerance_var.get()
            }
            
            # 执行比较
            engine = ComparisonEngine(self.config)
            self.duplicates = engine.find_duplicates(self.all_videos)
            
            # 更新UI
            self.root.after(0, self.display_results)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("错误", f"扫描失败: {str(e)}"))
        finally:
            self.root.after(0, self.scan_complete)
    
    def display_results(self):
        """显示结果"""
        # 清空之前的结果
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        
        # 显示统计信息
        total_videos = len(self.all_videos)
        duplicate_groups = len(self.duplicates)
        duplicate_files = sum(len(group) for group in self.duplicates)
        
        self.stats_label.config(
            text=f"共扫描 {total_videos} 个视频文件，发现 {duplicate_groups} 组重复文件，涉及 {duplicate_files} 个文件"
        )
        
        # 显示重复文件组
        for group_idx, group in enumerate(self.duplicates, 1):
            parent_id = self.result_tree.insert("", tk.END, text=str(group_idx), values=(group_idx, "---", "---", "---", "---", "---"))
            
            for video in group:
                self.result_tree.insert(
                    "", tk.END, text="",
                    values=(
                        "",
                        video.file_name,
                        video.file_path,
                        f"{video.get_size_mb():.2f} MB",
                        video.get_duration_str(),
                        video.folder_path
                    )
                )
    
    def scan_complete(self):
        """扫描完成"""
        self.start_btn.config(state=tk.NORMAL)
        self.progress_bar.stop()
        self.progress_bar.pack_forget()
        self.progress_var.set("扫描完成！")
    
    def save_config(self):
        """保存配置"""
        self.config = {
            'use_name': self.use_name_var.get(),
            'use_size': self.use_size_var.get(),
            'use_duration': self.use_duration_var.get(),
            'name_threshold': self.name_threshold_var.get(),
            'size_tolerance': self.size_tolerance_var.get(),
            'duration_tolerance': self.duration_tolerance_var.get()
        }
        ConfigManager.save_config(self.config)
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
                f.write(f"  - 时长相似度阈值: {int(self.config['duration_tolerance']*100)}%\n\n")
                
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
                        f.write(f"  视频时长: {video.get_duration_str()}\n")
                        f.write(f"  所属文件夹: {video.folder_path}\n")
                        f.write("\n")
            
            messagebox.showinfo("成功", f"结果已导出到:\n{file_path}")
        
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def clear_results(self):
        """清除结果"""
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.duplicates.clear()
        self.stats_label.config(text="尚未扫描")
        self.progress_var.set("就绪")
    
    @staticmethod
    def _get_current_time() -> str:
        """获取当前时间字符串"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """主函数"""
    root = tk.Tk()
    app = VideoDuplicateFinderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
