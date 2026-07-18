# https://passport.bilibili.com/login?gourl=https%3A%2F%2Faccount.bilibili.com%2Faccount%2Fhome

from Crypto.Cipher import PKCS1_v1_5, AES as CryptoAES
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad
from PIL import Image
from loguru import logger
import numpy as np
import requests
import cv2
import time
import random
import json
import math
import base64
import hashlib
import uuid
import os
from pathlib import Path
from click_identify import predict

BASE = Path(__file__).parent

# ── 常量 ────────────────────────────────────────────────

ALPHABET_64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789()"

TRACE_ALPHABET = "()*,-./0123456789:?@ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz~"

EVENT_TYPES = {"move": 0, "down": 1, "up": 2, "scroll": 3, "focus": 4, "blur": 5, "unload": 6, "unknown": 7}

RSA_N = "00C1E3934D1614465B33053E7F48EE4EC87B14B95EF88947713D25EECBFF7E74C7977D02DC1D9451F79DD5D1C10C29ACB6A9B4D6FB7D0A0279B6719E1772565F09AF627715919221AEF91899CAE08C0D686D748B20A3603BE2318CA6BC2B59706592A9219D0BF05C9F65023A21D2330807252AE0066D59CEEFA5F2748EA80BAB81"
RSA_E = "10001"

CONFIG_DATA = {
    "gt": "6216680937717fdab947ed9e71a3aaa1",
    "challenge": "b5529e5888ef926cbfd80ea88b6b83cd",
    "offline": False,
    "new_captcha": True,
    "product": "float",
    "width": "300px",
    "https": True,
    "api_server": "apiv6.geetest.com",
    "protocol": "https://",
    "type": "fullpage",
    "static_servers": ["static.geetest.com/", "static.geevisit.com/"],
    "beeline": "/static/js/beeline.1.0.1.js",
    "voice": "/static/js/voice.1.2.6.js",
    "click": "/static/js/click.3.1.2.js",
    "fullpage": "/static/js/fullpage.9.2.0-guwyxh.js",
    "slide": "/static/js/slide.7.9.3.js",
    "geetest": "/static/js/geetest.6.0.9.js",
    "aspect_radio": {"slide": 103, "click": 128, "voice": 128, "beeline": 50},
    "cc": 20,
    "ww": True,
    "i": "-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1"
}

W2_C = [12, 58, 98, 36, 43, 95, 62, 15, 12]
W2_T = "M(*((1((M(("
W2_N = "-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1magic data-1"
W2_CCFV = "-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1!!-1"

cookies = {}


def _generate_device_cookies(session):
    """从 DrissionPage 连接的 Chrome 中提取真实设备指纹"""
    try:
        from DrissionPage import Chromium, ChromiumOptions
        co = ChromiumOptions()
        co.headless()
        co.no_imgs(True)
        co.set_argument('--disable-gpu')
        browser = Chromium(co)
        tab = browser.latest_tab
        tab.get('https://www.bilibili.com/')
        tab.wait(3)
        browser_cookies = {}
        for c in tab.cookies():
            name = c.get('name') if isinstance(c, dict) else getattr(c, 'name', '')
            value = c.get('value') if isinstance(c, dict) else getattr(c, 'value', '')
            if name:
                browser_cookies[name] = value
        browser.quit()

        for key in ('buvid3', 'buvid4', 'b_nut', 'buvid_fp', '_uuid', 'b_lsid',
                     'rpdid', 'sid', 'bili_ticket', 'CURRENT_FNVAL', 'CURRENT_QUALITY'):
            if key in browser_cookies:
                cookies[key] = browser_cookies[key]

        cookies['bsource'] = 'search_baidu'
        if 'CURRENT_FNVAL' not in cookies:
            cookies['CURRENT_FNVAL'] = '2000'
        if 'CURRENT_QUALITY' not in cookies:
            cookies['CURRENT_QUALITY'] = '0'
        logger.info(f'已从浏览器提取设备指纹: buvid3={cookies.get("buvid3","?")[:20]}...')
    except Exception as e:
        logger.error(f'提取浏览器指纹失败: {e}，使用降级方案')
        ts = int(time.time())
        cookies['b_nut'] = str(ts)
        cookies['bsource'] = 'search_google'
        cookies['CURRENT_FNVAL'] = '4048'
        cookies['CURRENT_QUALITY'] = '0'
        try:
            resp = session.get('https://api.bilibili.com/x/frontend/finger/spi',
                               headers=headers, verify=False, timeout=10).json()
            data = resp.get('data', {})
            cookies['buvid3'] = data.get('b_3', '')
            cookies['buvid4'] = data.get('b_4', '')
            cookies['buvid_fp'] = hashlib.md5(
                f'{uuid.uuid4()}{int(time.time()*1000)}'.encode()
            ).hexdigest()
        except Exception:
            pass


headers = {
    'accept': '*/*',
    'accept-language': 'zh-CN,zh;q=0.9',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://passport.bilibili.com/login?gourl=https%3A%2F%2Faccount.bilibili.com%2Faccount%2Fhome',
    'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
}


# ── 辅助函数 ─────────────────────────────────────────────

def _h(n, length):
    s = bin(n)[2:]
    return '0' * (length - len(s)) + s


def _clamp_round(v):
    if not isinstance(v, (int, float)):
        return v
    if v > 32767:
        v = 32767
    elif v < -32767:
        v = -32767
    return round(v)


# ── 1. 自定义 Base64 编码 ($_HCB / $_HEJ) ───────────────

def _HBZ(e, t):
    return (e >> t) & 1


def _HCB(e):
    GCC = 7274496
    GDn = 9483264
    GE_ = 19220
    GFq = 235
    GGH = 24

    def _t(e_val, t_val):
        n = 0
        for r in range(GGH - 1, -1, -1):
            if _HBZ(t_val, r) == 1:
                n = (n << 1) + _HBZ(e_val, r)
        return n

    n = ""
    r = ""
    s = len(e)
    a = 0
    while a < s:
        if a + 2 < s:
            val = (e[a] << 16) + (e[a + 1] << 8) + e[a + 2]
            n += ALPHABET_64[_t(val, GCC)] + ALPHABET_64[_t(val, GDn)] + ALPHABET_64[_t(val, GE_)] + ALPHABET_64[
                _t(val, GFq)]
        else:
            c = s % 3
            if c == 2:
                val = (e[a] << 16) + (e[a + 1] << 8)
                n += ALPHABET_64[_t(val, GCC)] + ALPHABET_64[_t(val, GDn)] + ALPHABET_64[_t(val, GE_)]
                r = "."
            elif c == 1:
                val = e[a] << 16
                n += ALPHABET_64[_t(val, GCC)] + ALPHABET_64[_t(val, GDn)]
                r = ".."
        a += 3
    return {"res": n, "end": r}


def _HEJ(e):
    t = _HCB(e)
    return t["res"] + t["end"]


# ── 2. AES-CBC 加密 ─────────────────────────────────────

def aes_encrypt(data_str, key_str):
    key = key_str.encode('utf-8')
    iv = b'0000000000000000'
    cipher = CryptoAES.new(key, CryptoAES.MODE_CBC, iv)
    padded = pad(data_str.encode('utf-8'), CryptoAES.block_size)
    encrypted = cipher.encrypt(padded)
    return list(encrypted)


# ── 3. 极验 RSA 加密 (硬编码公钥) ────────────────────────

def rsa_encrypt_geetest(data_str):
    n_int = int(RSA_N, 16)
    e_int = int(RSA_E, 16)
    key = RSA.construct((n_int, e_int))
    cipher = PKCS1_v1_5.new(key)
    encrypted = cipher.encrypt(data_str.encode('utf-8'))
    return encrypted.hex()


# ── 4. MD5 ──────────────────────────────────────────────

def md5(s):
    return hashlib.md5(s.encode('utf-8')).hexdigest()


# ── 5. 轨迹处理与编码 ($_BHJq / $_BHIh / $_HDl) ─────────

def _filter_track(e):
    t = ""
    n = 0
    while not t and n < len(e):
        t = e[n][4] if len(e[n]) > 4 and e[n][4] else ""
        n += 1
    if not t:
        return e

    r = ""
    for prefix in ["mouse", "touch", "pointer", "MSPointer"]:
        if t.startswith(prefix):
            r = prefix
            break

    a = e[:]
    for i in range(len(a) - 1, -1, -1):
        c = a[i]
        l = c[0]
        if l in ["move", "down", "up"]:
            if not (c[4] or "").startswith(r):
                a.pop(i)
    return a


def _process_track(e):
    BHA = 300
    t = 0
    n = 0
    r = []
    lastTime = 0

    if len(e) <= 0:
        return []

    filtered = _filter_track(e)
    start_idx = max(0, len(filtered) - BHA)

    for l in range(start_idx, len(filtered)):
        u = filtered[l]
        p = u[0]

        if p in ["down", "move", "up", "scroll"]:
            r.append([p, [u[1] - t, u[2] - n], _clamp_round(lastTime and u[3] - lastTime or lastTime)])
            t = u[1]
            n = u[2]
            lastTime = u[3]
        elif p in ["blur", "focus", "unload"]:
            r.append([p, _clamp_round(lastTime and u[1] - lastTime or lastTime)])
            lastTime = u[1]

    return r


def _encode_types(types):
    result = []
    n = len(types)
    r = 0
    while r < n:
        o = types[r]
        i = 0
        while True:
            if i >= 16:
                break
            s = r + i + 1
            if n <= s:
                break
            if types[s] != o:
                break
            i += 1
        r = r + 1 + i
        a = EVENT_TYPES[o]
        if i != 0:
            result.append(8 | a)
            result.append(i - 1)
        else:
            result.append(a)
    header = _h(32768 | n, 16)
    body = ''.join(_h(v, 4) for v in result)
    return header + body


def _encode_values(e, signed):
    e = [max(-32767, min(32767, v)) for v in e]

    n = len(e)
    r = 0
    encoded = []
    while r < n:
        i = 1
        s = e[r]
        a = abs(s)
        while True:
            if n <= r + i:
                break
            if e[r + i] != s:
                break
            if a >= 127 or i >= 127:
                break
            i += 1
        if i > 1:
            flag = 49152 if s < 0 else 32768
            encoded.append(flag | (i << 7) | a)
        else:
            encoded.append(s)
        r += i

    r_bits = []
    o_bits = []
    for v in encoded:
        abs_v = abs(v)
        t_val = math.ceil(math.log(abs_v + 1, 16)) if abs_v + 1 > 1 else 1
        if t_val == 0:
            t_val = 1
        r_bits.append(_h(t_val - 1, 2))
        o_bits.append(_h(abs_v, 4 * t_val))

    i_bits = ''.join(r_bits)
    s_bits = ''.join(o_bits)

    n_bits = ""
    if signed:
        signs = []
        for v in encoded:
            if v != 0 and (v >> 15) != 1:
                signs.append('1' if v < 0 else '0')
        n_bits = ''.join(signs)

    header = _h(32768 | len(e), 16)
    return header + i_bits + s_bits + n_bits


def _trace_encode(events):
    types = []
    values = []
    x_coords = []
    y_coords = []

    for ev in events:
        types.append(ev[0])
        if len(ev) == 2:
            values.append(ev[1])
        elif len(ev) == 3:
            values.append(ev[2])
            x_coords.append(ev[1][0])
            y_coords.append(ev[1][1])

    c = _encode_types(types) + _encode_values(values, False) + _encode_values(x_coords, True) + _encode_values(y_coords,
                                                                                                               True)

    l = len(c)
    if l % 6 != 0:
        c += _h(0, 6 - l % 6)

    result = ""
    for i in range(len(c) // 6):
        chunk = c[6 * i:6 * (i + 1)]
        result += TRACE_ALPHABET[int(chunk, 2)]
    return result


def track_to_encoded(track):
    processed = _process_track(track)
    return _trace_encode(processed)


# ── 6. 指纹轨迹生成 & tmObject ──────────────────────────

def generate_fingerprint_track():
    startX = 480
    startY = 290
    targetX = 356
    track = []
    currentTime = int(time.time() * 1000)
    totalPoints = random.randint(70, 100)
    moveSteps = totalPoints - 2
    midY = 211
    endY = 317
    for i in range(moveSteps):
        progress = i / (moveSteps - 1)
        easeRatio = -(math.cos(math.pi * progress) - 1) / 2
        currX = startX + (targetX * easeRatio)
        if progress < 0.5:
            subProgress = progress / 0.5
            currY = startY + (midY - startY) * subProgress
        else:
            subProgress = (progress - 0.5) / 0.5
            currY = midY + (endY - midY) * subProgress
        currY += (random.random() - 0.5) * 2
        currentTime += random.randint(5, 15)
        track.append(["move", round(currX), round(currY), currentTime, "pointermove"])
    currentTime += random.randint(10, 20)
    track.append(["focus", currentTime])
    finalX = round(startX + targetX)
    finalY = endY
    currentTime += random.randint(20, 70)
    track.append(["up", finalX, finalY, currentTime, "pointerup"])
    return track


def get_tmObject(track):
    now = track[0][3] - 520
    return {
        "a": now, "b": now + 47, "c": now + 47, "d": 0, "e": 0,
        "f": now + 1, "g": now + 1, "h": now + 1, "i": now + 1, "j": now + 1,
        "k": 0, "l": now + 4, "m": now + 35, "n": now + 36,
        "o": now + 50, "p": now + 114, "q": now + 114,
        "r": now + 116, "s": now + 445, "t": now + 445, "u": now + 445
    }


# ── 7. tt / strict_calculate_tt ─────────────────────────

def strict_calculate_tt(e, o_c, o_s):
    if not o_c or not o_s:
        return e
    i = e
    s = o_c[0]
    a = o_c[2]
    _ = o_c[4]
    fixed_length = len(e)
    o = 0
    while o < len(o_s):
        r = o_s[o:o + 2]
        o += 2
        if not r:
            break
        c = int(r, 16)
        l = chr(c)
        u = (s * c * c + a * c + _) % fixed_length
        i = i[:u] + l + i[u:]
    return i


# ── 8. get_w1 ───────────────────────────────────────────

def get_w1(common_key):
    r_ = rsa_encrypt_geetest(common_key)
    o_ = aes_encrypt(json.dumps(CONFIG_DATA, separators=(',', ':')), common_key)
    i_ = _HEJ(o_)
    w1 = i_ + r_
    return w1


# ── 9. get_w2 ───────────────────────────────────────────

def get_w2(s, pass_time, gt, challenge, common_key, fingerprint_track, tmObject):
    targetStr = track_to_encoded(fingerprint_track)
    lightValue = "DIV_0"

    ep = {
        "v": "9.2.0-guwyxh",
        "te": False,
        "$_BBn": True,
        "ven": "Google Inc. (Intel)",
        "ren": "ANGLE (Intel, Intel(R) UHD Graphics (0x00004626) Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "fp": fingerprint_track[0],
        "lp": fingerprint_track[-1],
        "em": {"ph": 0, "cp": 0, "ek": "11", "wd": 1, "nt": 0, "si": 0, "sc": 0},
        "tm": tmObject,
        "dnf": "dnf",
        "by": 0
    }

    paramList = [
        ["lang", "zh-cn"],
        ["type", "fullpage"],
        ["tt", strict_calculate_tt(targetStr, W2_C, s)],
        ["light", lightValue],
        ["s", md5(_HEJ([ord(c) for c in W2_T]))],
        ["h", md5(_HEJ([ord(c) for c in W2_N]))],
        ["hh", md5(W2_N)],
        ["hi", md5(W2_CCFV)],
        ["vip_order", -1],
        ["ct", -1],
        ["ep", ep],
        ["passtime", pass_time],
        ["rp", md5(gt + challenge + str(pass_time))]
    ]

    _CECm = ""
    for key, value in paramList:
        _CECm += '"{}":{},'.format(key, json.dumps(value, separators=(',', ':')))

    captchaToken = 1784315673
    finalR = "{" + _CECm + '"captcha_token":"' + str(captchaToken) + '","tsfq":"xovrayel"}'

    w2 = _HEJ(aes_encrypt(finalR, common_key))
    return w2


# ── 10. get_w3 ──────────────────────────────────────────

def get_w3(arr, a_val, pic, trace_data, gt, challenge, ss, commit_x, commit_y, common_key, c=None, tmObject=None):
    pass_time = 3000 + random.randint(0, 3000)
    cc = c if c else [12, 58, 98, 36, 43, 95, 62, 15, 12]

    n = len(arr)
    ca = []
    for i in range(n - 1):
        ca.append({
            "x": arr[i][0],
            "y": arr[i][1],
            "t": 1,
            "dt": random.randint(600, 1800)
        })
    ca.append({
        "x": arr[n - 1][0],
        "y": arr[n - 1][1],
        "t": 3,
        "dt": random.randint(600, 1200)
    })

    o = {
        "lang": "zh-cn",
        "passtime": pass_time,
        "a": a_val,
        "pic": pic,
        "tt": strict_calculate_tt(track_to_encoded(trace_data), cc, ss),
        "ep": {
            "ca": ca,
            "v": "3.1.2",
            "$_FG": False,
            "me": True,
            "tm": tmObject if tmObject else {}
        },
        "h9s9": "1816378497",
        "rp": md5(gt + challenge + str(pass_time))
    }

    h = aes_encrypt(json.dumps(o, separators=(',', ':')), common_key)
    p = _FEu = _HEJ(h)
    u = rsa_encrypt_geetest(common_key)
    w3 = p + u
    return w3


# ── 11. B站登录流程 ─────────────────────────────────────

def register_click(session):
    url = 'https://passport.bilibili.com/x/passport-login/captcha'
    params = {
        'source': 'main-fe',
        'web_location': '333.1228',
        'x-bili-locale-json': '{"c_locale":{"language":"zh","region":"CN"},"always_translate":true}',
    }
    res = session.get(url, headers=headers, cookies=cookies, params=params, verify=False, timeout=15).json()
    geetest = res['data'].get('geetest')
    gt = geetest['gt']
    challenge = geetest['challenge']
    token = res['data'].get('token')
    return gt, challenge, token


def gettype(session, gt):
    url = "https://api.geetest.com/gettype.php"
    params = {
        "gt": gt,
        "callback": "geetest_" + str(int(time.time() * 1000))
    }
    response = session.get(url, headers=headers, params=params, verify=False, timeout=15)
    if "success" in response.text:
        # logger.info("指定获取验证码类型成功(点选)")
        pass


def init(session, gt, challenge, common_key):
    url = 'https://api.geetest.com/get.php'
    w1 = get_w1(common_key)
    params = {
        "gt": gt,
        "challenge": challenge,
        "lang": "zh-cn",
        "pt": "0",
        "client_type": "web",
        "w": w1,
        "callback": "geetest_" + str(int(time.time() * 1000))
    }
    response = session.get(url, headers=headers, cookies=cookies, params=params, verify=False, timeout=15)
    s0 = json.loads(response.text[22:-1])['data']['s']
    # logger.info(f"初始化提取s值 -> {s0}")
    return s0


def first_ajax(session, gt, challenge, s0, pass_time, common_key, fingerprint_track, tmObject):
    url = 'https://api.geetest.com/ajax.php'
    w2 = get_w2(s0, pass_time, gt, challenge, common_key, fingerprint_track, tmObject)
    params = {
        "gt": gt,
        "challenge": challenge,
        "lang": "zh-cn",
        "pt": "0",
        "client_type": "web",
        "w": w2,
        "callback": "geetest_" + str(int(time.time() * 1000))
    }
    response = session.get(url, headers=headers, params=params, verify=False, timeout=15)
    if "click" in response.text:
        # logger.info("第一次ajax请求成功")
        pass


def get_captcha(session, gt, challenge):
    url = 'https://api.geetest.com/get.php'
    params = {
        "is_next": "true",
        "type": "click",
        "gt": gt,
        "challenge": challenge,
        "lang": "zh-cn",
        "https": "true",
        "protocol": "https://",
        "offline": "false",
        "product": "float",
        "api_server": "api.geevisit.com",
        "isPC": "true",
        "autoReset": "true",
        "width": "100%",
        "callback": "geetest_" + str(int(time.time() * 1000))
    }
    response = session.get(url, headers=headers, params=params, verify=False, timeout=15)
    return json.loads(response.text[22:-1])['data']


def download_captcha(session, img_url, challenge):
    url = "https://static.geetest.com" + img_url
    # logger.info(f"图片地址 -> {url}")
    params = {"challenge": challenge}
    res = session.get(url, headers=headers, params=params, verify=False, timeout=15)
    save_path = str(BASE / "dx_img.png")
    with open(save_path, 'wb') as f:
        f.write(res.content)
    # logger.info("验证码图片已保存")


def parse_coordinates():
    img_path = str(BASE / "dx_img.png")
    pts = predict(img_path)
    coordinates = '|'.join(','.join(map(str, item)) for item in pts)
    return coordinates


def crop_img():
    input_path = str(BASE / "dx_img.png")
    output_path = str(BASE / "dx_img_304.png")
    img = Image.open(input_path)
    width, height = img.size
    crop_bottom = 40
    cropped = img.crop((0, 0, width, height - crop_bottom))
    final_img = cropped.resize((304, 304), Image.LANCZOS)
    final_img.save(output_path, quality=95)
    # logger.info(f"图片调整后已保存为: {output_path}")


# ── 12. 点击轨迹生成 (main.py 原有) ─────────────────────

def _generate_segment(sx, sy, ex, ey, total_n):
    dx = ex - sx
    dy = ey - sy
    dist = math.hypot(dx, dy)
    if dist < 0.5 or total_n < 2:
        return [[ex, ey]] * max(total_n, 1)
    n = total_n

    lead_x = abs(dx) > abs(dy)
    if random.random() < 0.30:
        lead_x = not lead_x

    b1 = random.uniform(0.08, 0.16)
    b2 = random.uniform(0.32, 0.50)

    progress_curve = []
    total_area = 0.0
    for i in range(n + 1):
        frac = i / n
        if frac < b1:
            vel = 0.2 + 1.3 * (frac / b1)
        elif frac < b2:
            rf = (frac - b1) / (b2 - b1)
            vel = 1.5 + 5.0 * rf
        elif frac < 0.88:
            rf = (frac - b2) / (0.88 - b2)
            vel = 6.5 - 3.0 * rf
        else:
            rf = (frac - 0.88) / 0.12
            vel = 3.5 - 3.0 * rf + 0.3
        vel = max(vel, 0.1)
        total_area += vel
        progress_curve.append(vel)

    acc = 0.0
    for i in range(n + 1):
        acc += progress_curve[i] / total_area
        progress_curve[i] = acc

    pts = []
    cur_x, cur_y = float(sx), float(sy)

    for i in range(n):
        frac = i / max(n - 1, 1)
        progress = progress_curve[i]

        ideal_x = sx + dx * progress
        ideal_y = sy + dy * progress

        if i == n - 1:
            cur_x, cur_y = float(ex), float(ey)
        else:
            if frac < b1 and lead_x:
                target_x = ideal_x
                target_y = sy + dy * progress * 0.15
            elif frac < b1:
                target_x = sx + dx * progress * 0.15
                target_y = ideal_y
            elif frac < b2 and lead_x:
                rf = (frac - b1) / (b2 - b1)
                catchup = 0.2 + 0.8 * rf
                target_x = ideal_x
                target_y = sy + dy * progress * catchup
            elif frac < b2:
                rf = (frac - b1) / (b2 - b1)
                catchup = 0.2 + 0.8 * rf
                target_x = sx + dx * progress * catchup
                target_y = ideal_y
            else:
                target_x = ideal_x
                target_y = ideal_y

            step_x = target_x - cur_x
            step_y = target_y - cur_y

            max_step = dist / n * 3.0
            if abs(step_x) > max_step:
                step_x = max_step if step_x > 0 else -max_step
            if abs(step_y) > max_step:
                step_y = max_step if step_y > 0 else -max_step

            step_x += random.uniform(-0.5, 0.5)
            step_y += random.uniform(-0.5, 0.5)

            cur_x += step_x
            cur_y += step_y

            if (dx > 0 and cur_x > ex) or (dx < 0 and cur_x < ex):
                cur_x = ex
            if (dy > 0 and cur_y > ey) or (dy < 0 and cur_y < ey):
                cur_y = ey

        pts.append([cur_x, cur_y])

    return [[round(p[0]), round(p[1])] for p in pts]


def generate_trace(points):
    if len(points) < 2:
        raise ValueError("points requires at least 2 (x, y) tuples")

    start_x = random.randint(855, 876)
    start_y = random.randint(320, 340)

    total = random.randint(350, 400)
    fixed = 9
    move_needed = total - fixed

    n_segs = len(points)
    segs = [(start_x, start_y, points[0][0], points[0][1])]
    for i in range(n_segs - 1):
        segs.append((points[i][0], points[i][1], points[i + 1][0], points[i + 1][1]))

    dists = [max(math.hypot(ex - sx, ey - sy), 1.0) for sx, sy, ex, ey in segs]
    total_dist = sum(dists)
    seg_n = [max(8, int(move_needed * d / total_dist)) for d in dists]

    diff = move_needed - sum(seg_n)
    order = list(range(n_segs))
    random.shuffle(order)
    while diff != 0:
        for i in order:
            if diff == 0:
                break
            if diff > 0:
                seg_n[i] += 1
                diff -= 1
            else:
                if seg_n[i] > 12:
                    seg_n[i] -= 1
                    diff += 1

    base_ts = int(time.time() * 1000) - random.randint(2000, 5000)
    ts = base_ts
    trace = []

    for seg_i in range(n_segs):
        sx, sy, ex, ey = segs[seg_i]
        n = seg_n[seg_i]
        seg_pts = _generate_segment(sx, sy, ex, ey, n)

        for px, py in seg_pts:
            ts += random.randint(6, 15)
            trace.append(["move", px, py, ts, "pointermove"])

        tx = seg_pts[-1][0]
        ty = seg_pts[-1][1]

        ts += random.randint(10, 20)
        trace.append(["down", tx, ty, ts, "pointerdown"])

        if seg_i == n_segs - 1:
            ts += random.randint(1, 5)
            trace.append(["focus", ts])
            ts += random.randint(80, 140)
        else:
            ts += random.randint(80, 140)

        trace.append(["up", tx, ty, ts, "pointerup"])
        ts += random.randint(30, 70)

    return trace


def verify_captcha(session, arr, a_val, pic, trace_data, gt, challenge, ss, c_val, commit_x, commit_y, key, tmObject):
    url = "https://api.geetest.com/ajax.php"
    w3 = get_w3(arr, a_val, pic, trace_data, gt, challenge, ss, commit_x, commit_y, key, c_val, tmObject)
    params = {
        "gt": gt,
        "challenge": challenge,
        "lang": "zh-cn",
        "pt": "0",
        "client_type": "web",
        "w": w3,
        "callback": "geetest_" + str(int(time.time() * 1000))
    }
    response = session.get(url, headers=headers, params=params, verify=False, timeout=15)
    res = json.loads(response.text[22:-1])
    if res.get('data') and res['data'].get('validate'):
        validate = res['data']['validate']
        logger.info(f'validate -> {validate}')
        return validate
    logger.error(f'验证码校验失败: {res}')
    return None


def get_pem_key(session):
    params = {
        '_': str(int(time.time() * 1000)),
        'web_location': '333.1228',
        'x-bili-locale-json': '{"c_locale":{"language":"zh","region":"CN"},"always_translate":true}',
    }
    res = session.get(
        'https://passport.bilibili.com/x/passport-login/web/key',
        params=params,
        cookies=cookies,
        headers=headers,
        verify=False,
        timeout=15,
    ).json()['data']
    hash_val = res.get('hash')
    pem_key = res.get('key')
    return hash_val, pem_key


def encrypt_password(public_key_pem, hash_val, password):
    public_key = RSA.import_key(public_key_pem)
    cipher = PKCS1_v1_5.new(public_key)
    plaintext = (hash_val + password).encode("utf-8")
    encrypted = cipher.encrypt(plaintext)
    return base64.b64encode(encrypted).decode("utf-8")


def login(session, token, validate, challenge, key, hash_val, username, pwd):
    params = {
        'x-bili-locale-json': '{"c_locale":{"language":"zh","region":"CN"},"always_translate":true}',
        'b_ret': 'BEYAAAAASUVORK5CYII=D//3AojzIAAAAGSURBVAMAhF3/8J6k+I8AAAAASUVORK5CYII=',
    }
    data = {
        'source': 'main_web',
        'username': username,
        'password': encrypt_password(key, hash_val, pwd),
        'go_url': 'https://account.bilibili.com/account/home',
        'token': token,
        'validate': validate,
        'seccode': str(validate) + '|jordan',
        'challenge': challenge,
    }
    response = session.post(
        'https://passport.bilibili.com/x/passport-login/web/login',
        params=params,
        cookies=cookies,
        headers=headers,
        data=data,
        verify=False,
        timeout=15,
    )
    resp_json = response.json()
    logger.info(f'登录结果:{resp_json}')
    if resp_json.get('code') != 0:
        logger.error(f'登录失败: code={resp_json.get("code")} message={resp_json.get("message")}')
        return {'status': 'fail', 'message': resp_json.get('message', '')}
    data = resp_json.get('data', {})
    if data.get('status') == 2:
        url = data.get('url', '')
        logger.info(f'触发短信验证, url={url}')
        return {'status': 'sms', 'url': url, 'message': data.get('message', '')}
    # logger.success('登录成功')
    return {'status': 'ok'}


def get_login_cookie(username='', password=''):
    if not username:
        username = os.environ.get('BILIBILI_USERNAME', '')
    if not password:
        password = os.environ.get('BILIBILI_PASSWORD', '')
    if not username or not password:
        logger.error('请设置环境变量 BILIBILI_USERNAME 和 BILIBILI_PASSWORD')
        return {}

    session = requests.Session()
    session.proxies = {"http": None, "https": None}
    session.trust_env = False
    _generate_device_cookies(session)

    for attempt in range(1, 4):
        logger.info(f'=== 登录尝试 {attempt}/3 ===')
        common_key = ''.join(random.choice('0123456789abcdefg') for _ in range(16))
        gt, challenge, token = register_click(session)
        gettype(session, gt)
        s0 = init(session, gt, challenge, common_key)
        pass_time = random.randint(1800, 2400)

        fingerprint_track = generate_fingerprint_track()
        tmObject = get_tmObject(fingerprint_track)

        first_ajax(session, gt, challenge, s0, pass_time, common_key, fingerprint_track, tmObject)
        msg = get_captcha(session, gt, challenge)
        c = msg['c']
        s = msg['s']
        pic = msg['pic']
        download_captcha(session, pic, challenge)
        coordinates = parse_coordinates()

        if not coordinates:
            logger.warning(f'验证码识别失败，重试...')
            continue

        logger.info(f"识别坐标 -> {coordinates}")
        pairs = [p.split(',') for p in coordinates.split('|')]
        target_pairs = pairs[:4]
        true_coordinates = '|'.join(f"{int(x) * 304 // 344},{int(y) * 304 // 344}" for x, y in target_pairs)
        arr = list(map(int, true_coordinates.replace('|', ',').split(',')))
        arr = [val + (798 if i % 2 == 0 else 319) for i, val in enumerate(arr)]
        arr = list(zip(arr[::2], arr[1::2]))
        commit_x = random.randint(1045, 1050)
        commit_y = random.randint(655, 660)
        arr.append((commit_x, commit_y))
        trace_data = generate_trace(arr)
        IMG_LEFT, IMG_TOP, IMG_SIZE = 798, 319, 304
        n_text = len(arr) - 1
        a_parts = []
        for i in range(n_text):
            ax = round((arr[i][0] - IMG_LEFT) / IMG_SIZE * 10000)
            ay = round((arr[i][1] - IMG_TOP) / IMG_SIZE * 10000)
            a_parts.append(f"{ax}_{ay}")
        a_val = ",".join(a_parts)
        sleep_ms = random.randint(3000, 5500) / 1000
        # logger.info(f"等待 {sleep_ms:.1f}s ...")
        time.sleep(sleep_ms)
        validate = verify_captcha(session, arr, a_val, pic, trace_data, gt, challenge, s, c, commit_x, commit_y, common_key,
                                  tmObject)
        hash_val, pem_key = get_pem_key(session)
        result = login(session, token, validate, challenge, pem_key, hash_val, username, password)
        if result['status'] == 'ok':
            all_cookies = dict(cookies)  # 先复制设备指纹
            all_cookies.update(session.cookies.get_dict())  # 再合并登录会话
            return all_cookies
        elif result['status'] == 'sms':
            return {'need_sms': True, 'url': result['url'], 'message': result.get('message', '')}
        logger.warning(f'登录失败: {result.get("message", "未知")}，重试...')

    logger.error('登录重试3次均失败')
    return {}


# ── 主流程 ──────────────────────────────────────────────

if __name__ == '__main__':
    update_cookie = get_login_cookie()
    logger.info(f'cookies -> {update_cookie}')

