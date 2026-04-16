import cv2
# 将原生的 requests 替换为 curl_cffi 提供的浏览器模拟 requests
from curl_cffi import requests
from pyzbar.pyzbar import decode
import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab, ImageTk
import keyboard
import numpy as np
import time
import threading
import ctypes
import platform

# ========== 解决 Windows 下缩放导致截图放大的问题 ==========
if platform.system() == "Windows":
    try:
        # 适用于 Windows 8.1 及以上
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            # 适用于 Windows 7 及以下
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

# ========== 配置区域 ==========
TOKEN = ""  # 你的 Authorization
API_URL = "https://bff.gds.org.cn/gds/searching-api/ProductService/ProductListByGTIN"


# ========== 核心应用类 ==========
class BarcodeScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("全局条码扫描助手")
        self.root.geometry("350x150")
        self.root.attributes("-topmost", True)  # 保持置顶

        # 界面提示信息
        tk.Label(root, text="🚀 扫描助手已在后台运行", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(root, text="按 【Ctrl + Alt + A】 框选屏幕条形码\n按 【ESC】 退出截图", font=("Arial", 10)).pack(pady=10)

        # 标记是否正在截屏，防止快捷键重复触发
        self.is_snipping = False

        # 注册全局快捷键 (后台监听)
        keyboard.add_hotkey('ctrl+alt+a', self.trigger_snip)

        # 启动定时器：用于在主线程中安全地拉起截图窗口
        # (避免跨线程直接操作 tkinter 导致的崩溃)
        self.check_trigger()

    def trigger_snip(self):
        """快捷键触发回调，修改状态位"""
        if not self.is_snipping:
            self.is_snipping = True

    def check_trigger(self):
        """轮询检查是否需要启动截图"""
        if self.is_snipping:
            self.start_snip()
            self.is_snipping = False
        # 每100毫秒检查一次
        self.root.after(100, self.check_trigger)

    # ========== 截图核心逻辑 ==========
    def start_snip(self):
        """开始全屏截图并进入裁剪模式"""
        # 截取当前全屏幕（现在不会被系统错误放大了）
        self.full_screen = ImageGrab.grab()

        # 创建全屏无边框的顶层窗口
        self.snip_win = tk.Toplevel(self.root)
        self.snip_win.attributes('-fullscreen', True)
        self.snip_win.attributes('-topmost', True)
        self.snip_win.config(cursor="cross")  # 鼠标变成十字星

        # 将截图放置在画布上
        self.tk_img = ImageTk.PhotoImage(self.full_screen)
        self.canvas = tk.Canvas(self.snip_win, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        # 截图区域坐标初始化
        self.rect = None
        self.start_x = None
        self.start_y = None

        # 绑定鼠标事件
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        # 绑定ESC键退出截图
        self.snip_win.bind("<Escape>", lambda e: self.snip_win.destroy())

    def on_press(self, event):
        """鼠标按下，记录起始点"""
        self.start_x = event.x
        self.start_y = event.y
        # 绘制红框
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2
        )

    def on_drag(self, event):
        """鼠标拖动，更新红框大小"""
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        """鼠标松开，完成截图并开始识别"""
        end_x, end_y = event.x, event.y
        self.snip_win.destroy()  # 关闭截图窗口

        # 确保坐标是从左上到右下
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        # 忽略过小的误触点击
        if x2 - x1 > 10 and y2 - y1 > 10:
            # 裁剪选中的区域
            cropped_img = self.full_screen.crop((x1, y1, x2, y2))
            self.process_image(cropped_img)

    # ========== 条码识别逻辑 ==========
    def process_image(self, pil_image):
        """处理裁剪后的图像进行条码识别"""
        print("\n[📷] 正在识别截图...")

        # 将 PIL Image 转换为 OpenCV 格式 (NumPy 数组)
        open_cv_image = np.array(pil_image)
        # 转换 RGB 为 BGR (OpenCV 默认格式)
        open_cv_image = open_cv_image[:, :, ::-1].copy()

        # 开始识别
        barcodes = decode(open_cv_image)

        if not barcodes:
            messagebox.showwarning("识别失败", "未在截图区域内发现条形码，请重新框选！")
            return

        for barcode in barcodes:
            code = barcode.data.decode("utf-8")

            # 标准 EAN-13 + 69码
            if code.startswith("69") and len(code) == 13:
                print(f"[✓] 识别到69码: {code}")
                # 补0变成14位查询码
                search_code = "0" + code
                # 开启新线程请求网络，避免阻塞UI主线程
                threading.Thread(target=self.query_product, args=(search_code,), daemon=True).start()
                return  # 找到一个有效的就跳出循环

        messagebox.showwarning("识别失败", "截图中未发现有效的69码！")

    # ========== 接口请求与解析 ==========
    def query_product(self, barcode):
        """发起网络请求查询商品"""
        print(f"[→] 正在请求接口: {barcode}")
        params = {
            "PageSize": 30,
            "PageIndex": 1,
            "SearchItem": barcode
        }

        headers = {
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Connection": "keep-alive",
            "Cookie": "pingtai5090=37132023"
        }

        try:
            # 💡 核心改动：使用 impersonate 参数完美模拟 Chrome 110 的真实 TLS 指纹
            response = requests.get(
                API_URL,
                headers=headers,
                params=params,
                timeout=10,
                impersonate="chrome110"  # 绕过服务器 TLS 指纹拦截的神器
            )
            data = response.json()
            # 解析并弹窗
            self.parse_and_show(data, barcode)

        except Exception as e:
            # 提取出纯文本错误信息，避开 lambda 的闭包陷阱
            error_msg = str(e)
            print(f"❌ 请求失败: {error_msg}")
            # 利用默认参数的方式，把 error_msg 的值安全地传递进 lambda 中
            self.root.after(0, lambda msg=error_msg: messagebox.showerror("网络错误", f"请求接口失败: {msg}"))

    def parse_and_show(self, data, barcode):
        """解析 JSON 数据并显示弹窗"""
        if data.get("Code") == 1 and data.get("Data") and data["Data"].get("Items"):
            item = data["Data"]["Items"][0]

            # 提取关键信息，如果没有对应字段则显示"未知"
            keyword = item.get("keyword", "未知")
            brand = item.get("brandcn", "未知")
            firm = item.get("firm_name", "未知")
            spec = item.get("specification", "未知")
            gpc = item.get("gpcname", "未知")

            # 组装展示文本
            info_text = f"📦 识别条码：{barcode}\n\n"
            info_text += f"🔖 商品名称：{keyword}\n"
            info_text += f"🏭 生产企业：{firm}\n"
            info_text += f"🏷️ 品牌信息：{brand}\n"
            info_text += f"📏 包装规格：{spec}\n"
            info_text += f"📁 商品分类：{gpc}\n"

            # 在主线程中调用 tkinter 弹窗
            self.root.after(0, lambda: messagebox.showinfo("🎉 查询成功", info_text))
        else:
            self.root.after(0, lambda: messagebox.showwarning("查无结果", f"条码 [{barcode}] 未查询到相关商品信息。"))


if __name__ == "__main__":
    # 创建 Tkinter 主窗口
    root = tk.Tk()

    # 实例化应用
    app = BarcodeScannerApp(root)

    # 进入消息循环
    root.mainloop()