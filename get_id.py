from DrissionPage import Chromium, ChromiumOptions
from loguru import logger
import redis
import json
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.headers.update({'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'})
retry = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retry))


def get_oid(bvid):
    try:
        resp = session.get(f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}', timeout=10).json()
        if resp['code'] == 0:
            data = resp['data']
            oid = str(data['aid'])
            title = data.get('title', '')
            reply_count = data.get('stat', {}).get('reply', 0)
            return oid, title, reply_count
    except Exception as e:
        logger.warning(f'获取oid失败 {bvid}: {e}')
    return None, None, 0


def get_video_ids(keyword='罗翔说刑法合集', pages=3):
    co = ChromiumOptions()
    co.headless()
    co.no_imgs(True)
    co.set_argument('--disable-gpu')
    try:
        browser = Chromium(co)
    except Exception as e:
        logger.error(f'无头浏览器启动失败: {e}')
        raise
    all_videos = []
    seen = set()

    try:
        tab = browser.latest_tab
        for page in range(1, pages + 1):
            search_url = f'https://search.bilibili.com/video?keyword={keyword}&page={page}'
            logger.info(f'正在采集第{page}页: {search_url}')
            tab.get(search_url)

            # 等待搜索结果出现，最长 10s
            try:
                tab.wait.ele_displayed('css:a[href*="/video/BV"]', timeout=10)
            except Exception:
                logger.warning(f'第{page}页超时未加载出视频链接')
                break

            # 滚动触发懒加载
            for _ in range(3):
                tab.scroll.down(400)
                time.sleep(0.3)

            time.sleep(0.5)

            js_code = '''
            var links = document.querySelectorAll('a[href*="/video/BV"]');
            var result = [];
            var seen = new Set();
            links.forEach(function(a) {
                var match = a.href.match(/\\/video\\/(BV[a-zA-Z0-9]+)/);
                if (match && !seen.has(match[1])) {
                    seen.add(match[1]);
                    result.push(match[1]);
                }
            });
            return JSON.stringify(result);
            '''
            bvids = json.loads(tab.run_js(js_code))
            logger.info(f'第{page}页提取到 {len(bvids)} 个bvid')

            if not bvids:
                logger.warning(f'第{page}页无数据，停止')
                break

            for bvid in bvids:
                if bvid in seen:
                    continue
                seen.add(bvid)
                oid, title, reply_count = get_oid(bvid)
                if oid:
                    all_videos.append({'bvid': bvid, 'oid': oid, 'title': title, 'reply_count': reply_count})
                    logger.info(f'第{page}页 | bvid:{bvid} | oid:{oid} | 标题:{title}')
                time.sleep(0.3)
    finally:
        browser.quit()

    logger.success(f'共提取 {len(all_videos)} 条视频ID')
    return all_videos


def save_to_redis(video_list):
    redis_pwd = os.environ.get('REDIS_PASSWORD', '123456')
    r = redis.Redis(host='localhost', port=6379, db=0, password=redis_pwd, decode_responses=True)
    r.delete('bilibili_id')
    for video in video_list:
        r.hset('bilibili_id', video['bvid'], video['oid'])
    logger.success(f'共存入 {len(video_list)} 条数据到 Redis key=bilibili_id')


if __name__ == '__main__':
    video_list = get_video_ids(keyword='罗翔说刑法合集', pages=3)
    save_to_redis(video_list)

