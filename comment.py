import requests
import datetime
import time
import json
import random
import os
import hmac
import hashlib
import uuid
import pymysql
import bilibili_login
from urllib.parse import quote
from loguru import logger
import redis

BASE = __import__('pathlib').Path(__file__).parent
_pool = {}


class BiliAuth:
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'

    MIXIN_KEY_ENC_TAB = []

    @staticmethod
    def get_buvid():
        resp = requests.get(
            'https://api.bilibili.com/x/frontend/finger/spi',
            headers={'user-agent': BiliAuth.UA},
            timeout=10,
        ).json()
        return resp['data']['b_3'], resp['data']['b_4'], str(int(time.time()))

    @staticmethod
    def get_buvid_fp():
        fp_data = f'{uuid.uuid4()}{int(time.time() * 1000)}'
        return hashlib.md5(fp_data.encode()).hexdigest()

    @staticmethod
    def get_bili_ticket(bili_jct=''):
        ts = int(time.time())
        hex_sign = hmac.new(b'XgwSnGZ1p', f'ts{ts}'.encode(), hashlib.sha256).hexdigest()
        params = {
            'key_id': 'ec02',
            'hexsign': hex_sign,
            'context[ts]': str(ts),
            'csrf': bili_jct,
        }
        resp = requests.post(
            'https://api.bilibili.com/bapis/bilibili.api.ticket.v1.Ticket/GenWebTicket',
            params=params,
            headers={'user-agent': BiliAuth.UA},
            timeout=10,
        ).json()
        data = resp['data']
        img_key = data['nav']['img'].rsplit('/', 1)[1].split('.')[0]
        sub_key = data['nav']['sub'].rsplit('/', 1)[1].split('.')[0]
        return data['ticket'], img_key, sub_key

    @staticmethod
    def get_wbi_sign(params, img_key, sub_key):
        raw = img_key + sub_key
        mixin_key = ''.join(raw[i] for i in BiliAuth.MIXIN_KEY_ENC_TAB if i < len(raw))[:32]
        wts = int(time.time())
        params['wts'] = wts
        filtered = {}
        for k, v in params.items():
            v = str(v)
            v = ''.join(c for c in v if c not in "!'()*")
            filtered[k] = v
        query = '&'.join(f'{quote(k, safe="")}={quote(v, safe="")}' for k, v in sorted(filtered.items()))
        w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()
        return w_rid, str(wts)

    @staticmethod
    def build_cookies(bili_jct=''):
        buvid3, buvid4, b_nut = BiliAuth.get_buvid()
        bili_ticket, img_key, sub_key = BiliAuth.get_bili_ticket(bili_jct)
        cookies = {
            'buvid3': buvid3,
            'buvid4': buvid4,
            'b_nut': b_nut,
            'buvid_fp': BiliAuth.get_buvid_fp(),
            'bili_ticket': bili_ticket,
        }
        return cookies, img_key, sub_key


class DatabaseManager:

    def __init__(self, host='localhost', user='root', password=None, database='bilibili'):
        if password is None:
            password = os.environ.get('MYSQL_PASSWORD', 'root')
        self.conn = pymysql.connect(host=host, user=user, password=password, charset='utf8mb4')
        self.cursor = self.conn.cursor()
        self.cursor.execute(f'CREATE DATABASE IF NOT EXISTS {database}')
        self.cursor.execute(f'USE {database}')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bilibili_comments (
                rpid BIGINT PRIMARY KEY,
                bvid VARCHAR(20),
                oid BIGINT,
                title TEXT,
                mid BIGINT,
                content TEXT,
                likes INT,
                reply_count INT,
                ctime VARCHAR(50)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        ''')
        self.conn.commit()
        self._batch = []
        self._batch_size = 20
        self._total = 0

    def save(self, data):
        self._batch.append(data)
        if len(self._batch) >= self._batch_size:
            self._flush()

    def _flush(self):
        if not self._batch:
            return
        sql = '''
            INSERT IGNORE INTO bilibili_comments
            (rpid, bvid, oid, title, mid, content, likes, reply_count, ctime)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        rows = [
            (d['rpid'], d['bvid'], d['oid'], d['title'],
             d['mid'], d['content'], d['like'], d['rcount'], d['ctime'])
            for d in self._batch
        ]
        n = self.cursor.executemany(sql, rows)
        self.conn.commit()
        self._total += n
        self._batch.clear()

    def close(self):
        self._flush()
        self.cursor.close()
        self.conn.close()
        return self._total


def get_video_info(bvid):
    resp = requests.get(
        f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}',
        headers={'user-agent': BiliAuth.UA},
        timeout=10,
    ).json()
    if resp.get('code') != 0:
        return None, None
    return str(resp['data']['aid']), resp['data'].get('title', '')


class BiliCollector:

    @staticmethod
    def timestamp_to_beijing(timestamp):
        if not timestamp:
            return None
        beijing_time = datetime.datetime.utcfromtimestamp(timestamp) + datetime.timedelta(hours=8)
        return beijing_time.strftime('%Y-%m-%d %H:%M:%S')

    @staticmethod
    def parse_data(reply, bvid='', oid='', title=''):
        return {
            'rpid': reply['rpid'],
            'bvid': bvid,
            'oid': oid,
            'title': title,
            'mid': reply['mid'],
            'content': reply['content']['message'],
            'like': reply['like'],
            'rcount': reply['rcount'],
            'ctime': BiliCollector.timestamp_to_beijing(reply['ctime']),
        }

    @staticmethod
    def collect_comments(oid, cookies, img_key, sub_key, bvid='', title='', pages=5):
        url = 'https://api.bilibili.com/x/v2/reply/wbi/main'
        headers = {
            'accept': '*/*',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cache-control': 'no-cache',
            'origin': 'https://www.bilibili.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': f'https://www.bilibili.com/video/{bvid}/' if bvid else 'https://www.bilibili.com/',
            'sec-ch-ua': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': BiliAuth.UA,
        }

        db = DatabaseManager()
        pagination_str = '{"offset":""}'
        total = 0

        try:
            for page in range(1, pages + 1):
                # 每页刷新 bili_ticket 和 wbi 密钥，保持设备指纹不变
                new_ticket, img_key, sub_key = BiliAuth.get_bili_ticket(cookies.get('bili_jct', ''))
                cookies['bili_ticket'] = new_ticket

                params = {
                    'oid': oid,
                    'type': 1,
                    'mode': 2,
                    'pagination_str': pagination_str,
                    'plat': 1,
                    'web_location': '',
                }
                w_rid, wts = BiliAuth.get_wbi_sign(params, img_key, sub_key)
                params['w_rid'] = w_rid
                params['wts'] = wts

                response = requests.get(url, params=params, headers=headers, cookies=cookies, timeout=15).json()
                if response.get('code') != 0:
                    code = response.get('code')
                    msg = response.get('message', '')
                    if code == -403:
                        logger.error(f'权限不足(-403)，Cookie可能已失效，请重新登录')
                    else:
                        logger.error(f'请求失败 code={code}: {msg}')
                    break

                logger.debug(f'cursor: {response["data"].get("cursor")}')
                replies = response['data'].get('replies')
                if not replies:
                    logger.warning(f'第{page}页无数据，停止采集')
                    break

                for reply in replies:
                    data = BiliCollector.parse_data(reply, bvid=bvid, oid=oid, title=title)
                    db.save(data)
                    total += 1
                    logger.info(
                        f'第{page}页 | 已采集{total}条 | 用户id:{data["mid"]} | 点赞数:{data["like"]} | 内容:{data["content"]}')

                next_page = response['data'].get('cursor', {}).get('pagination_reply')
                if not next_page:
                    logger.warning(f'已到最后一页')
                    break
                if isinstance(next_page, dict) and 'next_offset' in next_page:
                    pagination_str = json.dumps({"offset": next_page['next_offset']})
                else:
                    pagination_str = json.dumps(next_page) if isinstance(next_page, dict) else next_page
                time.sleep(5 + random.random() * 3)
        finally:
            written = db.close()
            logger.success(f'采集完成，实际写入MySQL {written} 条')


def login_once():
    logger.info('开始登录B站...')
    login_cookies = bilibili_login.get_login_cookie()
    if not login_cookies:
        logger.error('登录失败，无法继续采集')
        return None, None, None

    bili_jct = login_cookies.get('bili_jct', '')
    device_cookies, img_key, sub_key = BiliAuth.build_cookies(bili_jct)
    all_cookies = {**device_cookies, **login_cookies}
    logger.success('登录成功，Cookie已生成')
    return all_cookies, img_key, sub_key


def run_from_redis(pages=3):
    cookies, img_key, sub_key = login_once()
    if cookies is None:
        return

    r = redis.Redis(host='localhost', port=6379, db=0, password=os.environ.get('REDIS_PASSWORD', '123456'), decode_responses=True)
    videos = r.hgetall('bilibili_id')
    if not videos:
        logger.error('Redis中bilibili_id为空，请先运行get_id.py')
        return

    logger.info(f'从Redis获取到 {len(videos)} 个视频')
    for bvid, oid in videos.items():
        logger.info(f'开始采集: bvid={bvid} oid={oid}')
        actual_oid, title = get_video_info(bvid)
        if actual_oid is None:
            logger.warning(f'获取视频信息失败 bvid={bvid}，使用Redis中的oid')
            actual_oid = oid
            title = ''
        BiliCollector.collect_comments(
            oid=actual_oid, cookies=cookies, img_key=img_key, sub_key=sub_key,
            bvid=bvid, title=title, pages=pages,
        )
        time.sleep(2)


if __name__ == '__main__':
    run_from_redis(pages=3)

