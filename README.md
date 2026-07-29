# B站评论采集系统

> 极验三代点选验证码协议还原 | YOLO + Siamese 双模型识别 | WBI 签名 | 大规模评论采集

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![ONNX Runtime](https://img.shields.io/badge/ONNX-Runtime-orange.svg)](https://onnxruntime.ai/)
[![DrissionPage](https://img.shields.io/badge/DrissionPage-Chromium-green.svg)](https://drissionpage.cn/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 项目概述

一套完整的 B站评论大规模采集系统。核心挑战在于**极验三代（GeeTest v3）点选验证码的协议层还原**——不依赖第三方打码平台、不调用外部 API，纯 Python 实现「客户端指纹模拟 → 加密参数构造 → 验证码图像识别 → 轨迹行为模拟 → 登录鉴权」全链路自动化。

## 核心技术架构

```
┌──────────────────────────────────────────────────────────────┐
│                        Tkinter 桌面应用                        │
│            搜索 │ 导入 │ 登录 │ 采集 │ 停止                    │
└───────────────┬──────────────────────────────────────────────┘
                │
    ┌───────────┼───────────┬───────────────┐
    ▼           ▼           ▼               ▼
┌───────┐  ┌───────┐  ┌──────────┐  ┌──────────┐
│ 搜索   │  │ 登录   │  │ 验证码    │  │ 采集     │
│ 模块   │  │ 模块   │  │ 识别模块  │  │ 模块     │
└───┬───┘  └───┬───┘  └────┬─────┘  └────┬─────┘
    │          │            │              │
    ▼          ▼            ▼              ▼
 Drission  GeeTest v3    YOLOv8s       WBI 签名
 Page      协议还原      + Siamese     + 翻页游标
 无头浏览   全参数分析    双模型         + MySQL
```

## 逆向深度

### 极验三代验证码 — 全参数协议还原

不从浏览器 JS 环境偷 cookie，而是**完全在 Python 层还原加密流程**：

```
┌─────────────────────────────────────────────────────┐
│  w1 参数: 配置加密 + RSA 公钥加密                    │
│  ├─ AES-128-CBC (自定义 IV)                         │
│  ├─ 自定义 Base64 变体 ($_HCB / $_HEJ)              │
│  │  字符集: A-Za-z0-9()  (非标准 Base64)            │
│  └─ RSA-1024 PKCS1_v1_5 加密 AES 密钥               │
├─────────────────────────────────────────────────────┤
│  w2 参数: 轨迹编码 + 设备指纹 + MD5                  │
│  ├─ $_BHIh 轨迹压缩: RLE + 类型编码 + 有符号整数编码 │
│  │  数百个鼠标事件 → 几十字符                        │
│  ├─ ep/tm 设备指纹                                   │
│  └─ MD5 整体校验                                     │
├─────────────────────────────────────────────────────┤
│  w3 参数: 点击坐标 + 时间戳 + W2 校验 + RSA 签名     │
│  ├─ ca 坐标数组                                      │
│  ├─ W2 二次校验                                      │
│  └─ RSA 签名                                         │
└─────────────────────────────────────────────────────┘
```

**参考文件**: `bilibili_login.py`（800+ 行）

### 验证码图像识别 — YOLO + Siamese 双模型

```
验证码图片下载
  │
  ▼
YOLOv8s 全图检测 (ONNX)
  ├─ 检测所有文字/图标候选框
  └─ 按框大小分区 NMS → 题目区 / 选项区
  │
  ▼
Siamese 孪生网络 (ONNX)
  ├─ 题目图 × 选项图 → 相似度矩阵
  ├─ 贪心匹配: 每题匹配最相似选项
  └─ 输出点击坐标列表 [(x1,y1), (x2,y2), ...]
```

**性能**: CPU 推理 < 1s，无需 GPU

### B站 WBI 签名还原

```python
# mixin_key 派生
img_key + sub_key → mixin_key (64选32位)

# 参数签名
sorted(params) + mixin_key → MD5 → w_rid
# 时间戳签名
ts + hexSign (HMAC-SHA256) → bili_ticket
```

### 翻页游标修复

通过 Reqable HAR 抓包对比浏览器 vs 脚本请求，发现 B站评论接口 `pagination_reply` 返回的字段名为 `next_offset`，但翻页请求参数名必须为 `offset`。字段名不匹配导致第 2 页起全部返回缓存数据（20 条重复、`code=0`，无任何报错）——**典型的服务端静默反爬**。

## 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 验证码还原 | AES-CBC + RSA-1024 + MD5 | w1/w2/w3 全参数构造 |
| 编码还原 | 自定义 Base64 变体 | `$_HCB` 字符集 `A-Za-z0-9()` |
| 轨迹模拟 | RLE + 类型编码 | `$_BHIh` 轨迹压缩算法 |
| 图像识别 | YOLOv8s + Siamese (ONNX) | CPU 推理，无需 GPU |
| 浏览器自动化 | DrissionPage (Chromium) | 无头搜索 + 设备指纹提取 |
| WBI 签名 | HMAC-SHA256 + MD5 | B站新版接口签名 |
| 数据存储 | MySQL + Redis | 评论持久化 + 视频 ID 队列 |
| GUI | Tkinter + 多线程 | 蓝白风格桌面应用 |

## 登录流程

```
用户输入账号密码
  │
  ▼
获取极验挑战参数 (gt/challenge)
  │
  ▼
下载验证码图片
  │
  ▼
YOLO + Siamese 识别 → 点击坐标
  │
  ▼
构造 w1/w2/w3 加密参数
  │
  ▼
POST 极验验证接口
  │
  ├─ 成功 → B站登录 (RSA密码加密)
  │         └─ 成功 → 提取 SESSDATA / bili_jct
  │
  ├─ 二次风控 → 短信验证
  │              └─ DrissionPage 打开浏览器 → 用户手动验证
  │
  └─ 失败 → 刷新验证码重试 (最多3次)
```

## 项目结构

```
bilibili-comment-collector/
├── main.py              # Tkinter 桌面入口 (871行)
├── bilibili_login.py    # 极验三代全参数还原 + 登录流程 (800+行)
├── click_identify.py    # YOLO + Siamese 验证码识别 (141行)
├── comment.py           # 评论采集: WBI签名 + 分页 + MySQL
├── get_id.py            # 无头浏览器搜索视频 ID
├── model/
│   ├── yolov8s.onnx     # YOLOv8s 目标检测模型
│   └── siamese.onnx     # Siamese 孪生网络相似度模型
├── requirements.txt     # Python 依赖
└── README.md
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 确保 Redis 和 MySQL 已启动

# 启动应用
python main.py
```

**操作流程**: 搜索关键词 → 导入视频 → 输入账号密码 → 登录（自动过极验） → 采集评论

## 项目亮点

- **极验三代 w1/w2/w3 协议还原**: 分析 `click.3.1.2.js` + `fullpage.9.2.0.js`（经 Babel AST 反混淆），纯 Python 还原 AES-CBC + 自定义 Base64 `$_HCB` + RSA-1024 + MD5 全链路，零第三方打码依赖
- **YOLO + Siamese 端到端点选识别**: 全图检测 → 分区 NMS → 孪生网络贪心匹配，CPU 推理 < 1s
- **轨迹压缩算法还原**: 逆向 `$_BHIh` RLE + 类型编码 + 有符号整数压缩，数百鼠标事件压缩为几十字符
- **B站新版 WBI 签名 + 翻页游标修复**: 完整还原签名机制，抓包对比修复静默反爬
- **工程化交付**: Tkinter 多线程桌面应用，支持批量采集、进度追踪、异常重试

## License

MIT

## 免责声明

**本项目仅用于技术研究与学习，严禁用于任何商业用途或非法爬取行为。使用者须自行承担一切法律责任，开发者概不负责。**
