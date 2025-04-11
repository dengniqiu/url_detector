import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog
import threading
import queue
import requests
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urlparse
import pandas as pd

# 设置请求超时时间和请求头
TIMEOUT = 5
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# 结果队列
result_queue = queue.Queue()

# 检测URL状态和标题的函数
# 检测URL状态和标题的函数
def check_url(url, index):
    # 确保URL以http://或https://开头
    if not url.startswith('http://') and not url.startswith('https://'):  
        url = 'http://' + url
    
    try:
        start_time = time.time()
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, verify=False)
        elapsed_time = time.time() - start_time
        
        status_code = response.status_code
        
        # 尝试获取网站标题和检测验证码
        title = "无标题"
        has_captcha = "否"
        try:
            # 检测响应内容的编码
            if response.encoding.lower() == 'iso-8859-1':
                # 尝试从内容中检测编码
                possible_encoding = response.apparent_encoding
                if possible_encoding and possible_encoding.lower() != 'iso-8859-1':
                    response.encoding = possible_encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text.strip()
                
            # 检测验证码输入框
            # 1. 查找包含"验证码"或"captcha"关键词的输入框
            captcha_inputs = soup.find_all('input', attrs={'name': re.compile(r'captcha|verify|验证码', re.I)})
            captcha_inputs += soup.find_all('input', attrs={'id': re.compile(r'captcha|verify|验证码', re.I)})
            captcha_inputs += soup.find_all('input', attrs={'placeholder': re.compile(r'captcha|verify|验证码', re.I)})
            
            # 2. 查找包含验证码关键词的标签
            captcha_labels = soup.find_all(['label', 'span', 'div', 'p'], text=re.compile(r'验证码|captcha|verify code', re.I))
            
            # 3. 查找验证码图片
            captcha_images = soup.find_all('img', attrs={'src': re.compile(r'captcha|verify|验证码', re.I)})
            captcha_images += soup.find_all('img', attrs={'alt': re.compile(r'captcha|verify|验证码', re.I)})
            captcha_images += soup.find_all('img', attrs={'id': re.compile(r'captcha|verify|验证码', re.I)})
            captcha_images += soup.find_all('img', attrs={'class': re.compile(r'captcha|verify|验证码', re.I)})
            
            if captcha_inputs or captcha_labels or captcha_images:
                has_captcha = "是"
        except Exception as e:
            title = f"解析错误: {str(e)}"
        
        result = {
            'index': index,
            'url': url,
            'status': status_code,
            'title': title,
            'has_captcha': has_captcha,
            'time': f"{elapsed_time:.2f}秒"
        }
    except requests.exceptions.Timeout:
        result = {
            'index': index,
            'url': url,
            'status': '超时',
            'title': '请求超时',
            'has_captcha': '未知',
            'time': f"{TIMEOUT}秒+"
        }
    except requests.exceptions.ConnectionError:
        result = {
            'index': index,
            'url': url,
            'status': '连接错误',
            'title': '无法连接到服务器',
            'has_captcha': '未知',
            'time': '-'
        }
    except Exception as e:
        result = {
            'index': index,
            'url': url,
            'status': '错误',
            'title': str(e),
            'has_captcha': '未知',
            'time': '-'
        }
    
    # 将结果放入队列
    result_queue.put(result)

# 主应用类
class URLDetectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("URL批量检测探测器")
        self.root.geometry("800x600")
        self.root.resizable(True, True)
        
        # 设置样式
        self.style = ttk.Style()
        self.style.configure("TButton", font=("微软雅黑", 10))
        self.style.configure("TLabel", font=("微软雅黑", 10))
        
        # 创建主框架
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 输入区域
        input_frame = ttk.LabelFrame(main_frame, text="输入URL列表（每行一个URL）", padding="5")
        input_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.url_input = scrolledtext.ScrolledText(input_frame, height=8)
        self.url_input.pack(fill=tk.BOTH, expand=True)
        
        # 控制区域
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        # 线程数选择
        ttk.Label(control_frame, text="线程数:").pack(side=tk.LEFT, padx=5)
        self.thread_var = tk.StringVar(value="10")
        thread_spinbox = ttk.Spinbox(control_frame, from_=1, to=50, textvariable=self.thread_var, width=5)
        thread_spinbox.pack(side=tk.LEFT, padx=5)
        
        # 检测按钮
        self.detect_btn = ttk.Button(control_frame, text="开始检测", command=self.start_detection)
        self.detect_btn.pack(side=tk.LEFT, padx=20)
        
        # 清空按钮
        self.clear_btn = ttk.Button(control_frame, text="清空结果", command=self.clear_results)
        self.clear_btn.pack(side=tk.LEFT, padx=5)
        
        # 导出按钮
        self.export_btn = ttk.Button(control_frame, text="导出Excel", command=self.export_to_excel)
        self.export_btn.pack(side=tk.LEFT, padx=5)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 状态标签
        self.status_label = ttk.Label(main_frame, text="就绪")
        self.status_label.pack(anchor=tk.W, pady=2)
        
        # 结果区域
        result_frame = ttk.LabelFrame(main_frame, text="检测结果", padding="5")
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 创建滚动条框架
        scroll_frame = ttk.Frame(result_frame)
        scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        # 定义表格列
        columns = ("序号", "URL", "状态码", "标题", "验证码", "响应时间")
        
        # 创建表格
        self.result_tree = ttk.Treeview(scroll_frame, columns=columns, show="headings", selectmode="extended")
        
        # 设置列宽和标题，并添加排序功能
        self.result_tree.heading("序号", text="序号", command=lambda: self.treeview_sort_column("序号", False))
        self.result_tree.heading("URL", text="URL", command=lambda: self.treeview_sort_column("URL", False))
        self.result_tree.heading("状态码", text="状态码", command=lambda: self.treeview_sort_column("状态码", False))
        self.result_tree.heading("标题", text="标题", command=lambda: self.treeview_sort_column("标题", False))
        self.result_tree.heading("验证码", text="验证码", command=lambda: self.treeview_sort_column("验证码", False))
        self.result_tree.heading("响应时间", text="响应时间", command=lambda: self.treeview_sort_column("响应时间", False))
        
        self.result_tree.column("序号", width=50, anchor=tk.CENTER)
        self.result_tree.column("URL", width=250)
        self.result_tree.column("状态码", width=80, anchor=tk.CENTER)
        self.result_tree.column("标题", width=250)
        self.result_tree.column("验证码", width=60, anchor=tk.CENTER)
        self.result_tree.column("响应时间", width=80, anchor=tk.CENTER)
        
        # 添加垂直滚动条
        v_scrollbar = ttk.Scrollbar(scroll_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        # 添加水平滚动条
        h_scrollbar = ttk.Scrollbar(scroll_frame, orient=tk.HORIZONTAL, command=self.result_tree.xview)
        
        # 配置表格的滚动条
        self.result_tree.configure(yscroll=v_scrollbar.set, xscroll=h_scrollbar.set)
        
        # 放置表格和滚动条
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # 配置grid权重，使表格能够随窗口大小调整
        scroll_frame.grid_rowconfigure(0, weight=1)
        scroll_frame.grid_columnconfigure(0, weight=1)
        
        # 绑定右键菜单
        self.create_context_menu()
        
        # 用于存储检测线程
        self.detection_threads = []
        self.is_detecting = False
        self.update_timer = None
    
    def export_to_excel(self):
        """导出检测结果到Excel文件"""
        # 检查是否有数据可导出
        if not self.result_tree.get_children():
            messagebox.showinfo("提示", "没有数据可导出")
            return
        
        # 打开文件保存对话框
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx"), ("所有文件", "*.*")],
            title="保存Excel文件"
        )
        
        if not file_path:
            return  # 用户取消了保存
        
        try:
            # 获取所有数据
            data = []
            for item in self.result_tree.get_children():
                values = self.result_tree.item(item, "values")
                data.append({
                    "序号": values[0],
                    "URL": values[1],
                    "状态码": values[2],
                    "标题": values[3],
                    "验证码": values[4],
                    "响应时间": values[5]
                })
            
            # 创建DataFrame并导出
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False, engine="openpyxl")
            
            messagebox.showinfo("导出成功", f"已成功导出 {len(data)} 条记录到 {file_path}")
        except Exception as e:
            messagebox.showerror("导出错误", f"导出过程中发生错误: {str(e)}")
    
    def create_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="复制URL", command=lambda: self.copy_cell("URL"))
        self.context_menu.add_command(label="复制标题", command=lambda: self.copy_cell("标题"))
        self.context_menu.add_command(label="复制验证码信息", command=lambda: self.copy_cell("验证码"))
        self.context_menu.add_command(label="复制所有信息", command=self.copy_row)
        
        self.result_tree.bind("<Button-3>", self.show_context_menu)
    
    def show_context_menu(self, event):
        # 获取点击的行
        item = self.result_tree.identify_row(event.y)
        if item:
            # 检查是否已经选中了多个项目
            if not self.result_tree.selection() or item not in self.result_tree.selection():
                # 如果没有选中项或点击的项不在选中项中，则设置新的选中项
                self.result_tree.selection_set(item)
            # 显示上下文菜单
            self.context_menu.post(event.x_root, event.y_root)
    
    def copy_cell(self, column):
        selected_items = self.result_tree.selection()
        if selected_items:
            copied_text = []
            for item in selected_items:
                item_text = self.result_tree.item(item, "values")
                column_index = {"序号": 0, "URL": 1, "状态码": 2, "标题": 3, "验证码": 4, "响应时间": 5}[column]
                copied_text.append(str(item_text[column_index]))
            
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(copied_text))
            messagebox.showinfo("复制成功", f"已复制{len(selected_items)}个{column}到剪贴板")
    
    def copy_row(self):
        selected_items = self.result_tree.selection()
        if selected_items:
            copied_rows = []
            for item in selected_items:
                item_text = self.result_tree.item(item, "values")
                text = "\t".join([str(x) for x in item_text])
                copied_rows.append(text)
            
            self.root.clipboard_clear()
            self.root.clipboard_append("\n".join(copied_rows))
            messagebox.showinfo("复制成功", f"已复制{len(selected_items)}行数据到剪贴板")
    
    def treeview_sort_column(self, column, reverse):
        """点击列标题排序"""
        # 获取所有项目
        l = [(self.result_tree.set(k, column), k) for k in self.result_tree.get_children('')]
        
        # 尝试将值转换为数字进行排序（对于序号、状态码等数字列）
        try:
            # 对于序号列，确保按数字排序
            if column == "序号":
                l.sort(key=lambda t: int(t[0]) if t[0].isdigit() else float('inf'), reverse=reverse)
            # 对于响应时间列，提取数字部分进行排序
            elif column == "响应时间":
                l.sort(key=lambda t: float(t[0].replace("秒", "").replace("+", "")) if t[0] != "-" else float('inf'), reverse=reverse)
            # 对于其他可能包含数字的列
            elif column == "状态码":
                l.sort(key=lambda t: int(t[0]) if t[0].isdigit() else t[0], reverse=reverse)
            # 对于文本列，按字符串排序
            else:
                l.sort(reverse=reverse)
        except Exception:
            # 如果转换失败，按字符串排序
            l.sort(reverse=reverse)
        
        # 重新排列项目
        for index, (val, k) in enumerate(l):
            self.result_tree.move(k, '', index)
        
        # 反转排序方向
        self.result_tree.heading(column, command=lambda: self.treeview_sort_column(column, not reverse))
    
    def clear_results(self):
        # 清空结果表格
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        self.status_label.config(text="结果已清空")
    
    def start_detection(self):
        if self.is_detecting:
            messagebox.showinfo("提示", "检测正在进行中，请等待完成")
            return
        
        # 获取URL列表
        urls = self.url_input.get("1.0", tk.END).strip().split("\n")
        urls = [url.strip() for url in urls if url.strip()]
        
        if not urls:
            messagebox.showinfo("提示", "请输入至少一个URL")
            return
        
        # 清空之前的结果
        self.clear_results()
        
        # 设置状态
        self.is_detecting = True
        self.detect_btn.config(state=tk.DISABLED)
        total_urls = len(urls)
        self.status_label.config(text=f"正在检测 0/{total_urls}")
        self.progress_var.set(0)
        
        # 清空队列
        while not result_queue.empty():
            result_queue.get()
        
        # 创建并启动检测线程
        max_threads = min(int(self.thread_var.get()), 50)  # 限制最大线程数为50
        self.detection_threads = []
        
        # 创建结果更新定时器
        self.processed_count = 0
        self.update_timer = self.root.after(100, self.update_results)
        
        # 使用线程池管理线程
        self.thread_pool = []
        self.urls_to_process = urls.copy()
        self.total_urls = len(urls)
        
        # 启动初始线程
        for i in range(min(max_threads, len(urls))):
            if self.urls_to_process:
                url = self.urls_to_process.pop(0)
                t = threading.Thread(target=check_url, args=(url, i+1))
                t.daemon = True
                self.thread_pool.append(t)
                self.detection_threads.append(t)
                t.start()
        
        # 创建线程管理器
        self.thread_manager = threading.Thread(target=self.manage_threads, args=(max_threads,))
        self.thread_manager.daemon = True
        self.thread_manager.start()
    
    def manage_threads(self, max_threads):
        """管理线程池，确保同时运行的线程数不超过最大值"""
        try:
            while self.urls_to_process and self.is_detecting:
                # 检查当前活动线程数
                active_threads = [t for t in self.thread_pool if t.is_alive()]
                self.thread_pool = active_threads
                
                # 如果活动线程数小于最大线程数，启动新线程
                while len(self.thread_pool) < max_threads and self.urls_to_process:
                    url = self.urls_to_process.pop(0)
                    index = self.total_urls - len(self.urls_to_process)
                    t = threading.Thread(target=check_url, args=(url, index))
                    t.daemon = True
                    self.thread_pool.append(t)
                    self.detection_threads.append(t)
                    t.start()
                
                # 短暂休眠，避免CPU占用过高
                time.sleep(0.1)
        except Exception as e:
            print(f"线程管理器异常: {str(e)}")
    
    def update_results(self):
        try:
            # 从队列获取结果并更新UI
            total_urls = len(self.detection_threads)
            if total_urls == 0:  # 防止除零错误
                return
            
            # 处理队列中的所有结果，但限制每次处理的数量，避免UI阻塞
            results_to_display = []
            max_results_per_update = 10  # 每次更新最多处理10个结果
            count = 0
            
            while not result_queue.empty() and count < max_results_per_update:
                result = result_queue.get()
                results_to_display.append(result)
                self.processed_count += 1
                count += 1
            
            # 按照原始序号排序结果
            results_to_display.sort(key=lambda x: x['index'])
            
            # 将排序后的结果添加到表格
            for result in results_to_display:
                self.result_tree.insert("", tk.END, values=(
                    result['index'],
                    result['url'],
                    result['status'],
                    result['title'],
                    result['has_captcha'],
                    result['time']
                ))
                
                # 更新UI，确保响应性
                self.root.update_idletasks()
            
            # 更新进度
            progress = (self.processed_count / total_urls) * 100
            self.progress_var.set(progress)
            self.status_label.config(text=f"正在检测 {self.processed_count}/{total_urls}")
            
            # 检查是否所有线程都已完成
            if self.processed_count >= total_urls:
                self.is_detecting = False
                self.detect_btn.config(state=tk.NORMAL)
                self.status_label.config(text=f"检测完成，共 {total_urls} 个URL")
                return  # 停止定时器
            
            # 继续定时更新
            self.update_timer = self.root.after(100, self.update_results)
        except Exception as e:
            # 发生异常时，恢复UI状态并显示错误
            self.is_detecting = False
            self.detect_btn.config(state=tk.NORMAL)
            self.status_label.config(text=f"发生错误: {str(e)}")
            messagebox.showerror("错误", f"更新结果时发生错误: {str(e)}")

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 主程序入口
if __name__ == "__main__":
    root = tk.Tk()
    app = URLDetectorApp(root)
    root.mainloop()